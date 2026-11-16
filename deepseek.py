"""智慧树自动播放 - DeepSeek 网页对接（浏览器方式）"""
import logging, re, time

log = logging.getLogger("zhihuishu")

# DeepSeek 网页关键选择器（chat.deepseek.com）
SELECTORS = {
    # 新建对话按钮
    "new_chat":     "button:has-text('新建对话'), a:has-text('新对话'), [class*='newChat'], [class*='new-chat'], button:has-text('New chat'), a:has-text('New chat')",
    # 输入框 — DeepSeek 用 textarea
    "input":        "textarea",
    # 发送按钮 — DeepSeek 实际是一个带箭头图标的按钮/div，没有文字
    "send":         (
        # 精确：输入区域内的发送/提交按钮（含图标型）
        "div[class*='chat-input'] button, "
        "div[class*='input'] button[type='submit'], "
        "button:has-text('发送'), "
        "button:has-text('Send'), "
        "button:has-text('提交'), "
        "button:has-text('Submit'), "
        # DeepSeek 特有：输入区右下角的箭头发送图标
        "[class*='send'], "
        "[class*='submit'], "
        "[data-testid='send-button'], "
        # 兜底：输入区域内最后一个 button（通常就是发送）
        "textarea ~ button, "
        "textarea ~ div button"
    ),
    # 响应内容区域（AI 回答）— 取最后一个作为最新回答
    "response":     (
        "[class*='assistant'], "
        "[class*='message-content'], "
        "[class*='bot-message'], "
        "[class*='markdown'], "
        "[class*='chat-answer'], "
        "[class*='ds-markdown'], "
        "[class*='message'] [class*='content']"
    ),
}


def build_prompt(quiz: dict) -> str:
    """
    将题目信息打包为 DeepSeek 提示词，要求只返回答案字母
    """
    q_type = quiz.get("type", "单选题")
    question = quiz.get("question", "")
    options = quiz.get("options", [])

    opt_lines = "\n".join(f"{o['letter']}. {o['text']}" for o in options)

    prompt = (
        f"请回答以下{q_type}，只返回答案字母（如A/B/C/D），不要返回任何其他内容。\n\n"
        f"题目：{question}\n\n"
        f"选项：\n{opt_lines}\n\n"
        f"答案："
    )
    return prompt


def send_to_deepseek(page_ds, prompt: str, timeout: float = 60.0) -> str | None:
    """
    在 DeepSeek 页面中：
    1. 新建对话（清空上下文）
    2. 输入提示词
    3. 点击发送（找不到按钮则按 Enter）
    4. 等待回答完成
    5. 提取回答文本

    返回 DeepSeek 的回答文本，失败返回 None
    """
    try:
        # ── 1. 新建对话 ──
        log.info("[DeepSeek] 新建对话...")
        _try_click(page_ds, "new_chat")
        page_ds.wait_for_timeout(1500)

        # ── 2. 点击输入框并输入 ──
        log.info("[DeepSeek] 输入问题...")
        input_el = _find_element(page_ds, "input")
        if input_el is None:
            log.error("[DeepSeek] 未找到输入框")
            return None

        input_el.click()
        page_ds.wait_for_timeout(300)
        input_el.fill(prompt)
        page_ds.wait_for_timeout(500)

        # ── 3. 发送：先尝试点击按钮，失败则按 Enter ──
        log.info("[DeepSeek] 发送问题...")
        sent = _try_click(page_ds, "send")
        if not sent:
            log.info("[DeepSeek] 未找到发送按钮，尝试按 Enter 键发送...")
            input_el.press("Enter")
            sent = True
        page_ds.wait_for_timeout(1000)

        if not sent:
            log.error("[DeepSeek] 发送失败：既无发送按钮，Enter 也无效")
            return None

        # ── 4. 等待回答完成（轮询直到响应区不再变化）──
        log.info("[DeepSeek] 等待回答...")
        reply = _wait_for_response(page_ds, timeout)
        if reply:
            log.info("[DeepSeek] 收到回答: %s", reply[:200])
        else:
            log.warning("[DeepSeek] 未收到回答")
        return reply

    except Exception as e:
        log.error("[DeepSeek] 对接失败: %s", e)
        return None


def extract_answer_letters(reply: str, available_letters: list[str]) -> list[str]:
    """
    从 DeepSeek 回答中提取所有答案字母（支持多选题）。
    支持格式: "A/C/D", "A,C,D", "ACD", "A、C、D", "A C D",
    以及 "答案是A/C/D", "选择A,C,D" 等。
    返回字母列表，如 ["A", "C", "D"]；单选题仍返回 ["A"]。
    """
    if not reply:
        return []

    reply = reply.strip()
    avail = set(l.upper() for l in available_letters)

    # ── 模式1: 直接从回复中提取所有可用字母 ──
    # 先尝试在"答案"关键字后的部分提取
    answer_part = reply
    for pat in [
        r"答案[是为：:\s]*(.+)",
        r"选[择：:\s]*(.+)",
        r"选择\s*(.+)",
        r"正确答案[是为：:\s]*(.+)",
        r"应该选\s*(.+)",
    ]:
        m = re.search(pat, reply)
        if m:
            answer_part = m.group(1).strip()
            break

    # 从 answer_part 中收集所有可用字母，保持出现顺序
    found = []
    for ch in answer_part:
        if ch.upper() in avail and ch.upper() not in found:
            found.append(ch.upper())

    if found:
        return found

    # ── 模式2: 兜底 — 从整个回复中提取所有可用字母 ──
    for ch in reply:
        if ch.upper() in avail and ch.upper() not in found:
            found.append(ch.upper())

    return found


# 向后兼容别名
extract_answer_letter = extract_answer_letters


def _find_element(page, key: str):
    """查找第一个可见的元素"""
    sel = SELECTORS.get(key, key)
    # 处理逗号分隔的复合选择器，逐个尝试
    parts = [s.strip() for s in sel.split(",") if s.strip()]
    for part in parts:
        try:
            loc = page.locator(part)
            for i in range(min(loc.count(), 10)):
                el = loc.nth(i)
                try:
                    if el.is_visible():
                        return el
                except Exception:
                    continue
        except Exception:
            continue
    return None


def _try_click(page, key: str) -> bool:
    """尝试点击第一个可见的匹配元素"""
    el = _find_element(page, key)
    if el:
        try:
            el.click(timeout=3000)
            return True
        except Exception as e:
            log.debug("[DeepSeek] 点击 %s 失败: %s", key, e)
    return False


def _wait_for_response(page_ds, timeout: float) -> str | None:
    """
    轮询等待 DeepSeek 回答完成
    策略：每1秒读取最后一个响应区域文本，文本不再变化即认为回答完成
    """
    deadline = time.time() + timeout
    last_text = ""
    stable_count = 0

    while time.time() < deadline:
        page_ds.wait_for_timeout(1000)

        # 收集所有响应区域的文本，取最后一个（最新回答）
        try:
            resp_sel = SELECTORS["response"]
            loc = page_ds.locator(resp_sel)
            texts = []
            for i in range(min(loc.count(), 30)):
                try:
                    el = loc.nth(i)
                    if el.is_visible():
                        texts.append(el.inner_text().strip())
                except Exception:
                    continue
            # 只取最后一个非空文本作为当前回答
            current_text = ""
            for t in reversed(texts):
                if t:
                    current_text = t
                    break
        except Exception:
            current_text = ""

        if current_text and current_text == last_text:
            stable_count += 1
            # 连续3秒文本不变且非空 → 回答完成
            if stable_count >= 3:
                return current_text
        else:
            stable_count = 0
        last_text = current_text

    # 超时，返回最后得到的文本
    return last_text if last_text else None
