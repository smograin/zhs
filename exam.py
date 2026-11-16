"""智慧树自动播放 - 章节测试处理

智慧树测试页面 DOM 结构（从实际 HTML 提取）:
- .examPaper_subject  每道题容器（一次只显示一道，其余 display:none）
- .subject_stem       题干区
- .subject_num        题号 (1, 2, ...)
- .subject_type > span 题型 (【判断题】【单选题】【多选题】)
- .subject_describe   题目文本（closed Shadow DOM，需 JS 提取）
- .subject_node       选项容器
- .nodeLab            单个选项（可点击）
- .label              选项内可点击区域
- span.mr10           选项字母 (A. B. ...)
- span.mr10.ABCase    选项字母（单选/多选题使用此样式）
- .node_detail.examquestions-answer  选项文本
- input[type=radio]   单选/判断题
- input[type=checkbox] 多选题
- .switch-btn-box     上一题/下一题导航
- button 提交作业 / 暂存作业
- .answerCard         答题卡侧栏

重要：点击测试入口后，智慧树会在**新标签页**打开测试页面，
所以 enter_test() 必须捕获新 page，后续所有操作在新 page 上执行。
"""
import logging, time, re

log = logging.getLogger("zhihuishu")


# ═══════════════ 测试入口检测 ═══════════════

def find_test_entry(page):
    """在侧边栏找到可点击的章节测试入口（.test-box），返回 locator 或 None"""
    try:
        test_boxes = page.locator(".test-box")
        for i in range(test_boxes.count()):
            box = test_boxes.nth(i)
            try:
                if box.is_visible():
                    return box
            except Exception:
                continue
    except Exception:
        pass
    return None


def find_mastery_exam_entry(page):
    """找到"去答题"按钮（mastery-btn-free-exam），返回 locator 或 None"""
    try:
        btn = page.locator(".mastery-btn-free-exam")
        for i in range(btn.count()):
            el = btn.nth(i)
            try:
                if el.is_visible():
                    return el
            except Exception:
                continue
    except Exception:
        pass
    return None


def detect_chapter_test(page) -> bool:
    """检测当前页面是否有可进入的章节测试"""
    entry = find_test_entry(page) or find_mastery_exam_entry(page)
    return entry is not None


def enter_test(page, context) -> "Page | None":
    """点击章节测试入口，等待新标签页打开，返回新 page 对象。

    智慧树点击测试入口后会新开标签页打开测试页面，
    所以需要用 context.expect_event('page') 捕获新 page。

    返回新标签页的 Page 对象，失败返回 None。
    """
    # 先找到入口
    entry = find_test_entry(page) or find_mastery_exam_entry(page)
    if not entry:
        log.warning("[测试] 未找到测试入口")
        return None

    # 点击入口，同时监听新标签页打开
    try:
        with context.expect_event('page') as new_page_info:
            entry.click()
        new_page = new_page_info.value
        log.info("[测试] 已点击测试入口，新标签页已打开: %s", new_page.url)
        # 等待新页面加载
        new_page.wait_for_load_state("domcontentloaded", timeout=15000)
        new_page.wait_for_timeout(2000)
        return new_page
    except Exception as e:
        log.warning("[测试] 点击测试入口后未捕获到新标签页: %s", e)

    # 兜底：检查 context 中是否多出了新 page
    try:
        all_pages = context.pages
        for p in all_pages:
            if p != page and is_exam_page(p):
                log.info("[测试] 在 context 中找到测试页面: %s", p.url)
                p.wait_for_load_state("domcontentloaded", timeout=10000)
                return p
    except Exception as e:
        log.debug("[测试] 兜底查找新 page 失败: %s", e)

    return None


# ═══════════════ 测试页面检测 ═══════════════

def is_exam_page(page) -> bool:
    """判断当前是否已进入测试/考试页面"""
    try:
        # 检查测试页面特征选择器
        exam_selectors = [
            ".examPaper_subject",
            ".examPaper_box",
            ".subject_type",
            ".subject_node",
        ]
        for sel in exam_selectors:
            if page.locator(sel).count() > 0:
                return True

        # URL 特征
        url = page.url
        if any(kw in url for kw in ("exam", "test", "ExamDo", "examDo", "doExam", "stuExamWeb")):
            return True
    except Exception:
        pass
    return False


# ═══════════════ 题目文本提取（Shadow DOM）═════════════════

def _extract_question_text(subject_el) -> str:
    """从 .examPaper_subject 元素中提取题目文本。

    题目文本在 .subject_describe 内，使用 closed Shadow DOM:
    <template shadowrootmode="closed"><span>题目文本</span></template>

    策略：
    1. 先尝试 inner_text()（Playwright 可能已支持 Shadow DOM 穿透）
    2. 若为空，用 JS 从 shadowRoot 提取
    3. 兜底：从父容器文本中减去选项文本
    """
    # 方式1: 直接 inner_text
    try:
        desc = subject_el.locator(".subject_describe")
        if desc.count() > 0:
            text = desc.first.inner_text().strip()
            if text and len(text) > 1:
                return text
    except Exception:
        pass

    # 方式2: JS 提取 Shadow DOM 内容
    try:
        text = subject_el.evaluate("""el => {
            const desc = el.querySelector('.subject_describe');
            if (!desc) return '';
            // 尝试穿透 closed shadow DOM
            const templates = desc.querySelectorAll('template');
            for (const tpl of templates) {
                // closed shadow root 可能挂载在父元素上
                const parent = tpl.parentElement;
                if (parent && parent.shadowRoot) {
                    return parent.shadowRoot.textContent.trim();
                }
            }
            // 遍历 desc 下所有带 shadowRoot 的元素
            const allEls = desc.querySelectorAll('*');
            for (const e of allEls) {
                if (e.shadowRoot) {
                    const t = e.shadowRoot.textContent.trim();
                    if (t) return t;
                }
            }
            // 兜底：取 desc 的 textContent（可能包含 Shadow DOM 内容）
            const fullText = desc.textContent.trim();
            return fullText;
        }""")
        if text and len(text) > 1:
            return text
    except Exception as e:
        log.debug("[测试] JS 提取 Shadow DOM 失败: %s", e)

    # 方式3: 从整个题干区文本中减去题型和题号
    try:
        stem = subject_el.locator(".subject_stem")
        if stem.count() > 0:
            full_text = stem.first.inner_text().strip()
            # 移除题型标记和题号
            cleaned = re.sub(r'【[^】]+】', '', full_text)
            cleaned = re.sub(r'^\d+\.?\s*', '', cleaned)
            cleaned = re.sub(r'\(\d+分\)', '', cleaned)
            cleaned = cleaned.strip()
            if cleaned and len(cleaned) > 1:
                return cleaned
    except Exception:
        pass

    return ""


# ═══════════════ 单题解析 ═══════════════

def _parse_one_question(subject_el) -> dict | None:
    """解析单个 .examPaper_subject 元素，返回题目字典。

    返回:
    {
        "type": "判断题" | "单选题" | "多选题",
        "question": "题目文本",
        "options": [{"letter": "A", "text": "选项文本"}, ...],
    }
    """
    try:
        # ── 提取题型 ──
        type_el = subject_el.locator(".subject_type")
        type_text = type_el.first.inner_text().strip() if type_el.count() > 0 else ""
        quiz_type = "单选题"
        if "判断题" in type_text:
            quiz_type = "判断题"
        elif "多选题" in type_text:
            quiz_type = "多选题"
        elif "单选题" in type_text:
            quiz_type = "单选题"

        # ── 提取题目文本 ──
        question_text = _extract_question_text(subject_el)

        # ── 提取选项 ──
        options = []
        node_container = subject_el.locator(".subject_node")
        if node_container.count() > 0:
            node_els = node_container.first.locator(".nodeLab")
            for i in range(node_els.count()):
                node = node_els.nth(i)
                try:
                    # 提取字母: span.mr10 或 span.mr10.ABCase
                    letter_el = node.locator("span.mr10")
                    letter = ""
                    if letter_el.count() > 0:
                        letter_text = letter_el.first.inner_text().strip()
                        # 提取单个字母 (A., B., ...) -> A, B
                        m = re.match(r'([A-Za-z])\.?', letter_text)
                        if m:
                            letter = m.group(1).upper()

                    # 提取选项文本
                    detail_el = node.locator(".node_detail")
                    opt_text = ""
                    if detail_el.count() > 0:
                        opt_text = detail_el.first.inner_text().strip()

                    if letter:
                        options.append({"letter": letter, "text": opt_text})
                except Exception as e:
                    log.debug("[测试] 解析选项 %d 异常: %s", i, e)
                    continue

        if not question_text and not options:
            return None

        return {
            "type": quiz_type,
            "question": question_text,
            "options": options,
        }

    except Exception as e:
        log.warning("[测试] 解析题目异常: %s", e)
        return None


# ═══════════════ 全部题目解析 ═══════════════

def parse_exam_questions(page) -> list[dict]:
    """解析测试页面所有题目（包括隐藏的），返回题目列表。

    智慧树测试页面一次只显示一道题，其余 display:none，
    但 DOM 中所有题目都存在，可直接遍历 .examPaper_subject。
    """
    questions = []
    try:
        subjects = page.locator(".examPaper_subject")
        count = subjects.count()
        log.info("[测试] 找到 %d 个题目容器 (.examPaper_subject)", count)

        for i in range(count):
            subject = subjects.nth(i)
            q = _parse_one_question(subject)
            if q:
                q["index"] = i  # 记录在 DOM 中的位置
                questions.append(q)
                log.info(
                    "[测试] 题目 %d: [%s] %s (选项: %s)",
                    i + 1, q["type"], q["question"][:40],
                    ", ".join(f"{o['letter']}. {o['text'][:15]}" for o in q["options"]),
                )
            else:
                log.warning("[测试] 题目 %d 解析失败", i + 1)

    except Exception as e:
        log.error("[测试] 解析题目异常: %s", e)

    return questions


# ═══════════════ 可见题目定位 ═══════════════

def _get_visible_subject(page):
    """获取当前可见的题目容器（非 display:none 的 .examPaper_subject）。"""
    try:
        # 用 JS 找到可见的题目容器索引
        idx = page.evaluate("""() => {
            const subjects = document.querySelectorAll('.examPaper_subject');
            for (let i = 0; i < subjects.length; i++) {
                const el = subjects[i];
                // 检查元素及所有祖先都不是 display:none
                let node = el;
                let visible = true;
                while (node) {
                    const style = window.getComputedStyle(node);
                    if (style.display === 'none') { visible = false; break; }
                    node = node.parentElement;
                }
                if (visible) return i;
            }
            return 0;
        }""")
        return page.locator(".examPaper_subject").nth(idx)
    except Exception:
        return page.locator(".examPaper_subject").first


# ═══════════════ 答案选择 ═══════════════

def _select_answer(page, subject_el, answer_letters: list[str], quiz_type: str) -> bool:
    """在指定题目容器中选择答案选项。

    answer_letters: 答案字母列表，如 ["A"] 或 ["A", "C", "D"]
    """
    try:
        node_container = subject_el.locator(".subject_node")
        if node_container.count() == 0:
            log.warning("[测试] 未找到选项容器 .subject_node")
            return False

        node_els = node_container.first.locator(".nodeLab")
        selected = []

        for i in range(node_els.count()):
            node = node_els.nth(i)
            try:
                # 获取选项字母
                letter_el = node.locator("span.mr10")
                if letter_el.count() == 0:
                    continue
                letter_text = letter_el.first.inner_text().strip()
                m = re.match(r'([A-Za-z])\.?', letter_text)
                if not m:
                    continue
                letter = m.group(1).upper()

                if letter in answer_letters:
                    # 点击 .label（选项的可点击区域）
                    label = node.locator(".label")
                    if label.count() > 0:
                        label.first.click()
                    else:
                        node.click()
                    selected.append(letter)
                    log.info("[测试] 已选择选项 %s", letter)
                    page.wait_for_timeout(300)

            except Exception as e:
                log.debug("[测试] 点击选项 %d 异常: %s", i, e)

        if selected:
            log.info("[测试] 已选择: %s", "/".join(selected))
            return True
        else:
            log.warning("[测试] 未成功选择任何选项")
            return False

    except Exception as e:
        log.error("[测试] 选择答案异常: %s", e)
        return False


# ═══════════════ DeepSeek 答题 ═══════════════

def _get_answer_from_deepseek(page_ds, quiz: dict, available_letters: list, default: str = "A") -> list[str]:
    """通过 DeepSeek 网页获取答案，失败则返回默认答案列表。"""
    try:
        from deepseek import build_prompt, send_to_deepseek, extract_answer_letters

        prompt = build_prompt(quiz)
        log.info("[测试] 发送题目给 DeepSeek...")
        reply = send_to_deepseek(page_ds, prompt)

        if reply:
            letters = extract_answer_letters(reply, available_letters)
            if letters:
                log.info("[测试] DeepSeek 返回答案: %s", "/".join(letters))
                return letters
            else:
                log.warning("[测试] 无法从 DeepSeek 回答中提取答案字母，使用默认 %s", default)
        else:
            log.warning("[测试] DeepSeek 未返回回答，使用默认答案 %s", default)
    except Exception as e:
        log.warning("[测试] DeepSeek 对接异常: %s，使用默认答案 %s", e, default)

    return [default.upper().strip()]


# ═══════════════ 答题卡导航 ═══════════════

def _click_answer_card_item(page, question_num: int) -> bool:
    """点击答题卡中的第 N 题以跳转到该题。question_num 从 1 开始。"""
    try:
        items = page.locator(".answerCard_list1 li")
        if items.count() >= question_num:
            items.nth(question_num - 1).click()
            log.info("[测试] 已点击答题卡第 %d 题", question_num)
            page.wait_for_timeout(500)
            return True
    except Exception as e:
        log.debug("[测试] 点击答题卡失败: %s", e)
    return False


def _click_next_question(page) -> bool:
    """点击"下一题"按钮"""
    try:
        btn = page.locator("button:has-text('下一题')")
        for i in range(btn.count()):
            el = btn.nth(i)
            try:
                if el.is_visible() and not el.is_disabled():
                    el.click()
                    log.info("[测试] 已点击 [下一题]")
                    page.wait_for_timeout(800)
                    return True
            except Exception:
                continue
    except Exception:
        pass
    return False


# ═══════════════ 提交 ═══════════════

def _submit_exam(page) -> bool:
    """点击提交作业按钮"""
    try:
        btn = page.locator("button:has-text('提交作业')")
        for i in range(btn.count()):
            el = btn.nth(i)
            try:
                if el.is_visible():
                    el.click()
                    log.info("[测试] 已点击 [提交作业]")
                    page.wait_for_timeout(1000)
                    _handle_confirm_dialog(page)
                    return True
            except Exception:
                continue
    except Exception:
        pass

    # 兜底选择器
    for sel in [".btnStyleXSumit", "button:has-text('提交')"]:
        try:
            btn = page.locator(sel)
            for i in range(btn.count()):
                el = btn.nth(i)
                try:
                    if el.is_visible():
                        el.click()
                        log.info("[测试] 已点击提交按钮 (selector: %s)", sel)
                        page.wait_for_timeout(1000)
                        _handle_confirm_dialog(page)
                        return True
                except Exception:
                    continue
        except Exception:
            continue

    log.warning("[测试] 未找到提交按钮")
    return False


def _handle_confirm_dialog(page):
    """处理提交后可能弹出的确认弹窗"""
    for sel in [
        "button:has-text('确定')",
        "button:has-text('确认')",
        "button:has-text('是的')",
        ".el-message-box__btns button:last-child",
        ".el-dialog__footer button:has-text('确')",
    ]:
        try:
            btn = page.locator(sel)
            if btn.count() > 0:
                for i in range(btn.count()):
                    try:
                        el = btn.nth(i)
                        if el.is_visible():
                            el.click(timeout=2000)
                            log.info("[测试] 已点击确认弹窗")
                            page.wait_for_timeout(1000)
                            return
                    except Exception:
                        continue
        except Exception:
            continue


# ═══════════════ 逐题作答 ═══════════════

def answer_exam_questions(
    page,
    questions: list[dict],
    page_ds=None,
    use_deepseek: bool = False,
    default_answer: str = "A",
) -> int:
    """
    逐题作答：使用答题卡导航到每道题，解析当前题，选择答案。

    注意：page 是**测试标签页**（新打开的），不是视频页。

    返回成功作答的题目数。
    """
    answered = 0
    total = len(questions)

    for q_idx, q in enumerate(questions):
        question_num = q_idx + 1

        log.info(
            "[测试] ── 第 %d/%d 题 [%s] ──",
            question_num, total, q["type"],
        )

        # ── 通过答题卡跳转到该题 ──
        if question_num > 1:
            _click_answer_card_item(page, question_num)
            page.wait_for_timeout(500)

        # ── 重新解析当前可见题目 ──
        try:
            visible_subject = _get_visible_subject(page)
            current_q = _parse_one_question(visible_subject)
            if current_q:
                q = current_q
                q["index"] = q_idx
        except Exception:
            pass

        # ── 获取答案 ──
        available_letters = [o["letter"] for o in q.get("options", [])]
        if not available_letters:
            log.warning("[测试] 第 %d 题无选项，跳过", question_num)
            _click_next_question(page)
            continue

        if use_deepseek and page_ds:
            answer_letters = _get_answer_from_deepseek(
                page_ds, q, available_letters, default_answer,
            )
        else:
            answer_letters = [default_answer.upper().strip()]
            log.info("[测试] 使用默认答案: %s", answer_letters[0])

        # ── 选择答案 ──
        try:
            visible_subject = _get_visible_subject(page)
            ok = _select_answer(page, visible_subject, answer_letters, q["type"])
            if ok:
                answered += 1
        except Exception as e:
            log.warning("[测试] 选择答案异常: %s", e)

        # ── 点击下一题保存 ──
        if question_num < total:
            _click_next_question(page)

    return answered


# ═══════════════ 完整测试流程 ═══════════════

def handle_chapter_test(page, context, page_ds=None, use_deepseek: bool = False, default_answer: str = "A", auto_answer: bool = True) -> bool:
    """处理章节测试的完整流程：

    1. 在视频页(page)上点击测试入口
    2. 捕获新打开的测试标签页(exam_page)
    3. 在 exam_page 上解析题目、作答、提交
    4. 关闭 exam_page，回到视频页

    参数:
        page:     视频页面（智慧树主页面）
        context:  浏览器 context（用于捕获新标签页）
        page_ds:  DeepSeek 页面
        use_deepseek: 是否使用 DeepSeek
        default_answer: 默认答案
        auto_answer: 是否自动作答

    返回 True 表示成功处理了测试。
    """
    log.info("[测试] 检测到章节测试入口...")

    exam_page = None

    # ── 1. 点击入口，捕获新标签页 ──
    exam_page = enter_test(page, context)
    if exam_page is None:
        log.warning("[测试] 无法进入测试页面（未捕获到新标签页）")
        return False

    log.info("[测试] 已在新标签页打开测试: %s", exam_page.url)

    # 等待测试页面加载
    for _ in range(5):
        if is_exam_page(exam_page):
            break
        exam_page.wait_for_timeout(2000)
    else:
        log.info("[测试] 未检测到标准测试页面标记，尝试直接解析题目...")

    # ── 2. 在测试页面上解析所有题目 ──
    questions = parse_exam_questions(exam_page)
    if not questions:
        log.warning("[测试] 未找到任何题目，关闭测试标签页")
        try:
            exam_page.close()
        except Exception:
            pass
        return False

    log.info("[测试] 共 %d 道题，开始作答...", len(questions))

    # ── 3. 作答 ──
    if not auto_answer:
        log.info("[测试] 自动答题已关闭，等待手动完成...")
        input("[测试] 完成后按回车继续...")
        try:
            exam_page.close()
        except Exception:
            pass
        return True

    answered = answer_exam_questions(
        exam_page, questions,
        page_ds=page_ds,
        use_deepseek=use_deepseek,
        default_answer=default_answer,
    )
    log.info("[测试] 已作答 %d/%d 题", answered, len(questions))

    # ── 4. 提交 ──
    exam_page.wait_for_timeout(1000)
    if _submit_exam(exam_page):
        log.info("[测试] 测试已提交")
    else:
        log.warning("[测试] 提交失败，可能需要手动提交")

    # ── 5. 等待结果页面，关闭测试标签页 ──
    exam_page.wait_for_timeout(3000)

    try:
        exam_page.close()
        log.info("[测试] 已关闭测试标签页，回到视频页面")
    except Exception as e:
        log.warning("[测试] 关闭测试标签页失败: %s", e)

    return True
