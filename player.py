"""智慧树自动播放 - 视频播放控制"""
import time, logging

log = logging.getLogger("zhihuishu")


def enter_course(page, name: str):
    """在共享课下点击目标课程进入学习"""
    current_url = page.url
    if "study" in current_url and "recruitAndCourseId" in current_url:
        log.info("[课程] 已在课程页面内，跳过选课步骤")
        return True

    # ── 等待首页加载 ──
    log.info("[课程] 等待首页加载...")
    page.wait_for_timeout(3000)

    # ── 第一步：点击「共享课」标签（确保共享课列表可见）──
    log.info("[课程] 切换到「共享课」标签...")
    shared_tab_selectors = [
        "li.blackFont:has-text('共享课')",
        "li:has-text('共享课')",
        "text=共享课",
        "span:has-text('共享课')",
        "div:has-text('共享课')",
    ]
    clicked_tab = False
    for sel in shared_tab_selectors:
        try:
            tab = page.locator(sel)
            if tab.count() > 0:
                tab.first.click()
                log.info("[课程] 已点击「共享课」标签 (selector: %s)", sel)
                clicked_tab = True
                page.wait_for_timeout(1500)
                break
        except Exception:
            continue
    if not clicked_tab:
        log.warning("[课程] 未找到「共享课」标签，尝试直接查找课程")

    # ── 第二步：在共享课列表中点击目标课程 ──
    log.info("[课程] 查找课程「%s」...", name)

    # 方式1：通过 .courseName 匹配（首页共享课卡片内的课程名）
    try:
        course_name_els = page.locator(".courseName")
        count = course_name_els.count()
        log.info("[课程] .courseName 元素数量: %d", count)
        if count > 0:
            for i in range(count):
                try:
                    txt = course_name_els.nth(i).inner_text()
                    if name in txt:
                        log.info("[课程] 找到课程卡片: %s", txt.strip())
                        # 点击 .item-left-course（课程卡片左侧可点击区域）进入课程
                        card = course_name_els.nth(i).locator("..")
                        card.click()
                        log.info("[课程] 已点击课程卡片，等待页面跳转...")
                        page.wait_for_load_state("networkidle", timeout=15000)
                        page.wait_for_timeout(2000)
                        return True
                except Exception as e:
                    log.debug("[课程] 点击课程卡片异常: %s", e)
                    continue
    except Exception as e:
        log.debug("[课程] .courseName 查找异常: %s", e)

    # 方式2：通过 dt 内文本匹配
    try:
        dt_els = page.locator("dt")
        dt_count = dt_els.count()
        log.info("[课程] dt 元素数量: %d", dt_count)
        if dt_count > 0:
            for i in range(dt_count):
                try:
                    txt = dt_els.nth(i).inner_text()
                    if name in txt:
                        log.info("[课程] 找到课程 (dt): %s", txt.strip()[:50])
                        dt_els.nth(i).click()
                        page.wait_for_load_state("networkidle", timeout=15000)
                        page.wait_for_timeout(2000)
                        return True
                except Exception:
                    continue
    except Exception:
        pass

    # 方式3：兜底文本匹配
    try:
        text_match = page.locator(f"text={name}")
        if text_match.count() > 0:
            log.info("[课程] 通过文本匹配点击课程")
            text_match.first.click()
            page.wait_for_load_state("networkidle", timeout=15000)
            page.wait_for_timeout(2000)
            return True
    except Exception:
        pass

    log.error("[课程] 未找到课程「%s」", name)
    return False


def set_speed(page, speed: float):
    """设置视频播放倍速"""
    log.info("[倍速] 设置倍速 x%.1f", speed)

    # ── 直接设置 playbackRate ──
    try:
        result = page.evaluate(f"""() => {{
            const v = document.querySelector('video');
            if (!v) return {{ ok: false, reason: 'no video element' }};
            v.playbackRate = {speed};
            return {{ ok: true, rate: v.playbackRate }};
        }}""")
        if result.get("ok"):
            actual = result["rate"]
            if abs(actual - speed) < 0.01:
                log.info("[倍速] 已设置为 x%.1f", actual)
            else:
                log.warning("[倍速] 期望 x%.1f, 实际 x%.1f", speed, actual)
        else:
            log.warning("[倍速] 设置失败: %s", result.get("reason"))
    except Exception as e:
        log.warning("[倍速] 设置异常: %s", e)

    # ── UI 同步 ──
    try:
        for sel in [".vjs-playback-rate", "button:has-text('倍速')", "span:has-text('倍速')", "div:has-text('倍速')"]:
            btn = page.locator(sel)
            if btn.count() > 0:
                btn.first.click()
                page.wait_for_timeout(300)
                speed_str = f"{speed:g}"
                for msel in [f"li:has-text('{speed_str}')", f"div:has-text('{speed_str}')", f"span:has-text('{speed_str}')"]:
                    target = page.locator(msel)
                    if target.count() > 0:
                        target.first.click()
                        break
                else:
                    try: btn.first.click()
                    except: pass
                break
    except: pass

    # ── 验证 ──
    page.wait_for_timeout(300)
    try:
        actual = page.evaluate("document.querySelector('video')?.playbackRate || 0")
        if abs(actual - speed) < 0.01:
            log.info("[倍速] 验证通过: x%.1f", actual)
        else:
            log.error("[倍速] 验证失败: 期望 x%.1f, 实际 x%.1f", speed, actual)
    except: pass


def click_play(page):
    """点击播放按钮恢复播放（兼容 video.js 播放器）"""
    # video.js 和智慧树自定义播放器的播放按钮选择器（按优先级排列）
    play_selectors = [
        # video.js 控制栏播放按钮
        ".vjs-play-control",
        "button.vjs-play",
        # video.js 大播放按钮（视频中央）
        ".vjs-big-play-button",
        # 智慧树自定义
        "button[class*='play']",
        "div[class*='play'][class*='btn']",
        "[class*='playBtn']",
        "[class*='video-play']",
        # 兜底：含 播放 文字的按钮
        "button:has-text('播放')",
    ]
    try:
        for sel in play_selectors:
            btn = page.locator(sel)
            for j in range(btn.count()):
                try:
                    el = btn.nth(j)
                    if el.is_visible():
                        el.click(timeout=3000)
                        log.info("[视频] 已点击播放按钮 (selector: %s)", sel)
                        return
                except Exception:
                    continue
        # 所有按钮都未命中 → JS 直调 video.play()
        video = page.locator("video")
        if video.count() > 0:
            page.evaluate("document.querySelector('video')?.play()")
            log.info("[视频] 通过 JS 播放视频")
    except Exception as e:
        log.debug("点击播放失败: %s", e)

def get_video_info(page) -> dict:
    """获取视频播放信息"""
    return page.evaluate("""() => {
        const v = document.querySelector('video');
        if (!v) return null;
        return {
            currentTime: v.currentTime || 0,
            duration:    v.duration   || 0,
            ended:       v.ended,
            paused:      v.paused,
        };
    }""")


def _video_signature(page) -> dict | None:
    """获取用于对比的视频签名（进度/时长/源地址）"""
    try:
        return page.evaluate("""() => {
            const v = document.querySelector('video');
            if (!v) return null;
            return {
                time: v.currentTime || 0,
                dur:  v.duration   || 0,
                ended: v.ended,
                src:  v.currentSrc || v.src || '',
            };
        }""")
    except Exception:
        return None


def _video_changed(before: dict | None, after: dict | None) -> bool:
    """判断切换下一节后视频是否真的变化了"""
    if after is None:
        return False
    if before is None:
        return True
    if before.get("src") and after.get("src") and before["src"] != after["src"]:
        return True
    if before.get("dur") and after.get("dur") and abs(before["dur"] - after["dur"]) > 1:
        return True
    if after["time"] < before["time"] - 10:
        return True
    return False


def _wait_video_change(page, before, timeout: float = 3.0) -> bool:
    """轮询等待视频签名变化"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        page.wait_for_timeout(300)
        if _video_changed(before, _video_signature(page)):
            return True
    return False


def _click_first_visible(page, selector: str, timeout_ms: int = 3000) -> bool:
    """点击第一个可见的匹配元素"""
    try:
        loc = page.locator(selector)
        for i in range(loc.count()):
            el = loc.nth(i)
            try:
                if not el.is_visible():
                    continue
                el.click(timeout=timeout_ms)
                return True
            except Exception:
                continue
    except Exception as e:
        log.debug("[视频] 选择器 %s 查找异常: %s", selector, e)
    return False


def wait_video_ready(page, timeout: float = 8.0) -> bool:
    """轮询等待视频可播放"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            st = page.evaluate("""() => {
                const v = document.querySelector('video');
                if (!v) return null;
                return { rs: v.readyState, dur: v.duration || 0 };
            }""")
            if st and st.get("dur") and st.get("rs", 0) >= 3:
                return True
        except Exception:
            pass
        page.wait_for_timeout(250)
    return False


def switch_next_chapter(page) -> bool:
    """切换到下一小节"""
    log.info("[视频] 尝试切换下一小节...")
    before = _video_signature(page)

    candidates = [
        "button:has-text('下一节')",
        "span:has-text('下一节')",
        "div:has-text('下一节')",
        "[class*='nextBtn']",
        "[class*='btn-next']",
        ".vjs-next-btn",
        "[class*='next']:not([class*='prev'])",
    ]
    for sel in candidates:
        if _click_first_visible(page, sel):
            if _wait_video_change(page, before, timeout=3.0):
                log.info("[视频] 已切换下一节 (selector: %s)", sel)
                return True
            log.debug("[视频] 点击 %s 后视频未变化，尝试下一个入口", sel)

    # ── 兜底：侧栏章节列表 ──
    sidebar_sels = [
        "[class*='section'][class*='active'] + [class*='section']",
        "[class*='current'] + *",
        ".active + li",
        "[class*='active'] + li",
    ]
    for sel in sidebar_sels:
        if _click_first_visible(page, sel, timeout_ms=2000):
            if _wait_video_change(page, before, timeout=3.0):
                log.info("[视频] 已点击下一小节（侧栏, selector: %s）", sel)
                return True

    log.warning("[视频] 所有下一节入口均尝试失败")
    return False