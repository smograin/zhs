"""智慧树自动播放 - 弹窗题目检测与作答"""
import logging

log = logging.getLogger("zhihuishu")


# ═══════════════ 弹窗检测 ═══════════════

QUIZ_SELECTORS = (
    ".ai-class-exercise-dialog",
    ".ai-class-exercise",
    ".ai-exercise-dialog",
)

# Element Plus 弹窗由外层 .el-overlay 控制可见性（display:none / display:flex），
# 内层 .el-dialog 始终 display:flex，所以必须选外层 overlay 来判断。
NOTICE_OVERLAY_SELECTOR = ".el-overlay:has(.ai-notice-dialog)"
REMINDER_OVERLAY_SELECTOR = ".el-overlay.ss2077-custom-modal"


def _visible_items(page, selector):
    """返回 selector 匹配且真正可见的元素列表。"""
    locator = page.locator(selector)
    items = []
    for i in range(locator.count()):
        item = locator.nth(i)
        try:
            if item.is_visible():
                items.append(item)
        except Exception:
            continue
    return items


def _looks_like_quiz(item) -> bool:
    """通过弹窗文本确认这是随堂练习，避免把同名容器误判为弹窗。"""
    try:
        text = item.inner_text()
    except Exception:
        return False
    return "AI随堂练习" in text and any(t in text for t in ("判断题", "单选题", "多选题"))


def _find_quiz(page):
    """找到当前可见的 AI 随堂练习弹窗；只检查 DOM 存在会把隐藏弹窗误判为可见。"""
    for selector in QUIZ_SELECTORS:
        for item in _visible_items(page, selector):
            if _looks_like_quiz(item):
                return item

    # 旧类名失效时，用无障碍 role 和弹窗文本兜底。
    for item in _visible_items(page, '[role="dialog"], .el-dialog'):
        if _looks_like_quiz(item):
            return item
    return None


def _find_notifications(page):
    """找到可见的通知/提醒弹窗，并排除随堂练习弹窗。

    关键：选外层 .el-overlay 而不是内层 .el-dialog，
    因为 Element Plus 通过 overlay 的 display 控制显隐，
    内层 dialog 即使在 overlay 隐藏时也自带 display:flex，
    导致 Playwright is_visible() 可能误判。
    """
    notices = _visible_items(page, NOTICE_OVERLAY_SELECTOR)
    reminders = []
    for overlay in _visible_items(page, REMINDER_OVERLAY_SELECTOR):
        try:
            text = overlay.inner_text()
        except Exception:
            continue
        if "AI随堂练习" not in text:
            reminders.append(overlay)
    return notices, reminders


def detect_quiz(page) -> bool:
    """检测是否存在当前可见的 AI 随堂练习弹窗。"""
    try:
        if _find_quiz(page) is not None:
            log.info("[弹窗] 检测到 AI随堂练习 弹窗")
            return True
        return False
    except Exception as e:
        log.debug("[弹窗] 检测随堂练习异常: %s", e)
        return False


def detect_notification(page) -> bool:
    """检测是否存在当前可见的课程提醒 / 视频提示弹窗。"""
    try:
        notices, reminders = _find_notifications(page)
        total = len(notices) + len(reminders)
        if total > 0:
            parts = []
            if reminders:
                parts.append(f"课程提醒x{len(reminders)}")
            if notices:
                parts.append(f"视频提示x{len(notices)}")
            log.info("[弹窗] 检测到通知弹窗: %s", ", ".join(parts))
            return True
        return False
    except Exception as e:
        log.debug("[弹窗] 检测通知弹窗异常: %s", e)
        return False


# ═══════════════ 弹窗解析 ═══════════════

def parse_quiz(page) -> dict | None:
    """
    解析随堂练习弹窗内容，返回:
    {
        "type": "判断题" | "单选题" | "多选题",
        "question": "题目文本",
        "options": [{"letter": "A", "text": "对"}, {"letter": "B", "text": "错"}],
    }
    """
    try:
        d = _find_quiz(page)
        if d is None:
            return None

        # ── 提取题型 ──
        type_el = d.locator(".type")
        type_text = type_el.first.inner_text().strip() if type_el.count() > 0 else ""
        quiz_type = "单选题"
        if "判断题" in type_text:
            quiz_type = "判断题"
        elif "单选题" in type_text:
            quiz_type = "单选题"
        elif "多选题" in type_text:
            quiz_type = "多选题"

        # ── 提取题目文本 ──
        question_text = ""
        question_el = d.locator(".question-info")
        if question_el.count() > 0:
            question_text = question_el.first.inner_text().strip()

        # ── 提取选项 ──
        options = []
        option_els = d.locator(".option")
        for i in range(option_els.count()):
            opt = option_els.nth(i)
            letter = opt.locator(".class-question-select").inner_text().strip()
            text = opt.locator(".answer").inner_text().strip()
            options.append({"letter": letter, "text": text})

        result = {
            "type": quiz_type,
            "question": question_text,
            "options": options,
        }
        log.info("[弹窗] 解析题目: [%s] %s", quiz_type, question_text[:60])
        for opt in options:
            log.info("[弹窗]   选项 %s: %s", opt["letter"], opt["text"])
        return result

    except Exception as e:
        log.warning("[弹窗] 解析题目失败: %s", e)
        return None


# ═══════════════ 弹窗作答 ═══════════════

def answer_quiz(page, answer: str = "A", page_ds=None, use_deepseek: bool = False) -> bool:
    """
    作答随堂练习:
    1. 解析弹窗获取题目和选项
    2. 如启用 DeepSeek：发送题目给 DeepSeek，获取答案字母
    3. 点击指定答案对应的 .class-question-select
    4. 点击"提交作答"
    5. 点击弹窗右上角 .header-icon (X) 关闭弹窗
    """
    d = _find_quiz(page)
    if d is None:
        log.warning("[弹窗] 未检测到题目弹窗，无法作答")
        return False

    quiz = parse_quiz(page)
    if quiz is None:
        return False

    options = quiz["options"]
    if not options:
        log.warning("[弹窗] 未提取到选项")
        return False

    available_letters = [o["letter"] for o in options]

    # ── 确定答案（支持多选） ──
    target_letters = [answer.upper().strip()]

    if use_deepseek and page_ds is not None:
        # 使用 DeepSeek 网页作答，返回字母列表
        target_letters = _get_answer_from_deepseek(page_ds, quiz, available_letters, default=answer)
    else:
        log.info("[弹窗] 使用默认答案: %s", "/".join(target_letters))

    # 验证答案在选项中，过滤掉不在选项中的
    target_letters = [l for l in target_letters if l in available_letters]
    if not target_letters:
        log.warning("[弹窗] 答案均不在选项中，默认选 %s", available_letters[0])
        target_letters = [available_letters[0]]

    log.info("[弹窗] 最终选择答案: %s", "/".join(target_letters))

    # ── 点击选项（逐个点击，支持多选） ──
    clicked = []
    try:
        option_els = d.locator(".option")
        for i in range(option_els.count()):
            opt = option_els.nth(i)
            letter = opt.locator(".class-question-select").inner_text().strip()
            if letter in target_letters:
                opt.locator(".class-question-select").click()
                clicked.append(letter)
                log.info("[弹窗] 已点击选项 %s", letter)
                page.wait_for_timeout(200)  # 多选时每个选项间隔一下
        # 检查是否所有目标选项都已点击
        missed = [l for l in target_letters if l not in clicked]
        if missed:
            log.warning("[弹窗] 未能点击的选项: %s", "/".join(missed))
    except Exception as e:
        log.warning("[弹窗] 点击选项失败: %s", e)
        return False

    # ── 验证选项已选中 ──
    page.wait_for_timeout(300)
    try:
        for letter in target_letters:
            is_selected = page.evaluate("""(letter) => {
                const dialog = document.querySelector('.ai-class-exercise-dialog');
                if (!dialog) return false;
                const opts = dialog.querySelectorAll('.option');
                for (const opt of opts) {
                    const sel = opt.querySelector('.class-question-select');
                    if (sel && sel.innerText.trim() === letter) {
                        return sel.classList.contains('isSelect');
                    }
                }
                return false;
            }""", letter)
            if is_selected:
                log.info("[弹窗] 选项 %s 已选中", letter)
            else:
                log.warning("[弹窗] 选项 %s 可能未选中", letter)
    except Exception:
        pass

    # ── 点击"提交作答" ──
    page.wait_for_timeout(300)
    try:
        submit_btn = d.locator(".el-dialog__footer button")
        if submit_btn.count() > 0:
            submit_btn.first.click()
            log.info("[弹窗] 已点击 [提交作答]")
            for _ in range(10):
                page.wait_for_timeout(200)
                if page.locator(".ai-class-exercise-dialog").count() == 0:
                    break
        else:
            log.warning("[弹窗] 未找到提交按钮")
            return False
    except Exception as e:
        log.warning("[弹窗] 提交作答失败: %s", e)
        return False

    # ── 等待答题结果动画完成 ──
    page.wait_for_timeout(2000)

    # ── 点击弹窗右上角关闭按钮 (.header-icon = X) ──
    page.wait_for_timeout(500)
    try:
        close_icon = page.locator(".ai-class-exercise-dialog .header-icon")
        if close_icon.count() > 0:
            close_icon.first.click()
            log.info("[弹窗] 已点击关闭按钮 [X]，弹窗已关闭")
            page.wait_for_timeout(300)
        else:
            log.debug("[弹窗] 未找到 .header-icon 关闭按钮，弹窗可能已自动关闭")
    except Exception as e:
        log.debug("[弹窗] 点击关闭按钮失败: %s", e)

    return True


def _get_answer_from_deepseek(page_ds, quiz: dict, available_letters: list, default: str = "A") -> list[str]:
    """通过 DeepSeek 网页获取答案，失败则返回默认答案列表。
    多选题返回多个字母，单选/判断题返回单个字母的列表。
    """
    try:
        from deepseek import build_prompt, send_to_deepseek, extract_answer_letters

        prompt = build_prompt(quiz)
        log.info("[弹窗] 发送题目给 DeepSeek...")
        reply = send_to_deepseek(page_ds, prompt)

        if reply:
            letters = extract_answer_letters(reply, available_letters)
            if letters:
                log.info("[弹窗] DeepSeek 返回答案: %s", "/".join(letters))
                return letters
            else:
                log.warning("[弹窗] 无法从 DeepSeek 回答中提取答案字母，使用默认 %s", default)
        else:
            log.warning("[弹窗] DeepSeek 未返回回答，使用默认答案 %s", default)
    except Exception as e:
        log.warning("[弹窗] DeepSeek 对接异常: %s，使用默认答案 %s", e, default)

    return [default.upper().strip()]


def dismiss_notification(page) -> bool:
    """关闭所有当前可见的非题目弹窗（视频提示 + 课程提醒）。

    _find_notifications() 返回的是外层 .el-overlay 定位器，
    操作按钮时需要从 overlay 内部查找。
    """
    handled = False
    notices, reminders = _find_notifications(page)

    # ── 关闭视频提示弹窗 ──
    for overlay in notices:
        try:
            log.info("[弹窗] 检测到视频提示弹窗 (.ai-notice-dialog)")
            btn = overlay.locator(".btn, button:has-text(\"好的\"), button:has-text(\"确定\")")
            if btn.count() > 0:
                btn.first.click()
                log.info("[弹窗] 已关闭视频提示弹窗 -> 点击确认按钮")
                page.wait_for_timeout(300)
                handled = True
            else:
                log.warning("[弹窗] 视频提示弹窗未找到确认按钮")
        except Exception as e:
            log.debug("[弹窗] 关闭视频提示失败: %s", e)

    # ── 关闭课程提醒弹窗 ──
    for overlay in reminders:
        try:
            log.info("[弹窗] 检测到课程提醒弹窗")
            closed = False
            for sel in (
                "header .icon",
                ".ss2077-custom-title .icon",
                ".el-dialog__headerbtn",
                "[aria-label=\"Close\"]",
                ".icon",
            ):
                try:
                    close_btn = overlay.locator(sel)
                    if close_btn.count() > 0:
                        close_btn.first.click()
                        log.info("[弹窗] 已关闭课程提醒弹窗 -> 点击关闭按钮")
                        page.wait_for_timeout(300)
                        handled = True
                        closed = True
                        break
                except Exception:
                    continue

            if not closed:
                try:
                    btn = overlay.get_by_text("下次再说", exact=True)
                    if btn.count() > 0:
                        btn.first.click()
                        log.info("[弹窗] 已关闭课程提醒弹窗 -> 点击 [下次再说]（兜底）")
                        page.wait_for_timeout(300)
                        handled = True
                        closed = True
                except Exception:
                    pass
            if not closed:
                log.warning("[弹窗] 课程提醒弹窗未找到关闭方式")
        except Exception as e:
            log.debug("[弹窗] 关闭课程提醒失败: %s", e)

    return handled


def handle_all_popups(page, default_answer: str = "A", auto_answer: bool = True,
                      page_ds=None, use_deepseek: bool = False) -> bool:
    """
    统一处理所有弹窗（通知 + 随堂练习）
    返回 True 表示处理了弹窗
    """
    handled = False

    # 先识别随堂练习，避免把包含题目内容的自定义 modal 误判为通知。
    if detect_quiz(page):
        if auto_answer:
            log.info("[弹窗] 自动作答随堂练习")
            if answer_quiz(page, default_answer, page_ds=page_ds, use_deepseek=use_deepseek):
                handled = True
        else:
            log.info("[弹窗] 检测到随堂练习，暂停等待手动作答")
            handled = True

    # 再关闭普通通知弹窗
    if detect_notification(page):
        if dismiss_notification(page):
            handled = True

    if handled:
        log.info("[弹窗] 弹窗处理完成")
    return handled
