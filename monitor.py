"""智慧树自动播放 - 监控循环（视频进度 + 弹窗处理）"""
import time, logging
from quiz import handle_all_popups
from exam import handle_chapter_test, detect_chapter_test, is_exam_page
from player import click_play, get_video_info, set_speed, switch_next_chapter, wait_video_ready

log = logging.getLogger("zhihuishu")


def resume_playback(page, max_wait: float = 5.0) -> bool:
    """尽快恢复播放：立即点击播放，之后每 300ms 确认一次，未恢复则重试"""
    click_play(page)
    deadline = time.time() + max_wait
    while time.time() < deadline:
        page.wait_for_timeout(300)
        try:
            if not page.evaluate("document.querySelector('video')?.paused ?? true"):
                return True
        except Exception:
            pass
        click_play(page)
    log.warning("[视频] 视频仍未恢复播放")
    return False


def monitor_and_advance(
    page,
    context,
    speed: float,
    poll_interval: float = 1.0,
    auto_answer: bool = True,
    default_answer: str = "A",
    page_ds=None,
    use_deepseek: bool = False,
):
    """
    主监控循环:
    - 每 poll_interval 秒检测视频播放进度
    - 检测弹窗题目并自动作答
    - 播放完毕自动切换下一集

    参数:
        page:     智慧树视频页面
        context:  浏览器 context（用于捕获测试新标签页）
    """

    episode = 1
    last_log_second = -1

    while True:
        time.sleep(poll_interval)

        # ── 弹窗检测（最高优先级，视频暂停等弹窗关闭）──
        popup_handled = handle_all_popups(
            page,
            default_answer,
            auto_answer,
            page_ds=page_ds,
            use_deepseek=use_deepseek,
        )
        if popup_handled:
            log.info("[监控] 弹窗已处理，等待页面稳定后恢复播放...")
            page.wait_for_timeout(1500)
            resume_playback(page)

        # ── 获取视频信息 ──
        info = get_video_info(page)
        if info is None:
            # 没有视频 → 可能已进入测试页面
            if is_exam_page(page):
                log.info("[监控] 检测到测试页面，开始处理...")
                handle_chapter_test(
                    page, context,
                    page_ds=page_ds,
                    use_deepseek=use_deepseek,
                    default_answer=default_answer,
                    auto_answer=auto_answer,
                )
                # 测试完成后恢复视频
                page.wait_for_timeout(2000)
                for retry in range(3):
                    if switch_next_chapter(page):
                        episode += 1
                        try:
                            page.wait_for_selector("video", timeout=10000)
                        except Exception:
                            pass
                        wait_video_ready(page, timeout=8.0)
                        set_speed(page, speed)
                        resume_playback(page, max_wait=1.5)
                        last_log_second = -1
                        break
                    page.wait_for_timeout(2000)
                continue
            log.debug("未检测到 video 元素")
            continue

        cur = info["currentTime"]
        dur = info["duration"]
        ended = info["ended"]
        paused = info["paused"]
        sec = int(cur)

        # ── 进度日志（每 15 秒）──
        if sec % 15 == 0 and sec != last_log_second and dur > 0:
            pct = cur / dur * 100
            status = "暂停" if paused else "播放中"
            log.info(
                "[视频] 第%d集  %d/%ds (%.1f%%) %s",
                episode,
                sec,
                int(dur),
                pct,
                status,
            )
            last_log_second = sec

        # ── 暂停恢复（非弹窗导致的暂停）──
        near_end = dur > 0 and cur >= dur - 0.5
        if paused and not ended and not near_end and cur > 0:
            # 先再检查一次弹窗
            if handle_all_popups(
                page,
                default_answer,
                auto_answer,
                page_ds=page_ds,
                use_deepseek=use_deepseek,
            ):
                log.info("[监控] 暂停时检测到弹窗，已处理，恢复播放...")
                page.wait_for_timeout(1000)
                resume_playback(page)
            else:
                click_play(page)

        # ── 播放完毕 ──
        if ended or (dur > 0 and cur >= dur - 0.5):
            log.info("[视频] 第 %d 集播放完毕！", episode)
            ok = False
            for attempt in range(3):
                if switch_next_chapter(page):
                    ok = True
                    break
                log.info("[监控] 第 %d 次切换失败，先处理弹窗再重试...", attempt + 1)
                handle_all_popups(
                    page,
                    default_answer,
                    auto_answer,
                    page_ds=page_ds,
                    use_deepseek=use_deepseek,
                )
                page.wait_for_timeout(2000)

            if ok:
                episode += 1
                try:
                    page.wait_for_selector("video", timeout=10000)
                except Exception:
                    pass
                wait_video_ready(page, timeout=8.0)

                for _ in range(5):
                    if not handle_all_popups(
                        page,
                        default_answer,
                        auto_answer,
                        page_ds=page_ds,
                        use_deepseek=use_deepseek,
                    ):
                        break
                    page.wait_for_timeout(300)

                set_speed(page, speed)
                resume_playback(page, max_wait=1.5)
                last_log_second = -1
            else:
                # 切换下一节失败，可能是章末测试，尝试处理
                log.info("[监控] 无法切换下一节，检查是否有章节测试...")
                if detect_chapter_test(page):
                    test_ok = handle_chapter_test(
                        page, context,
                        page_ds=page_ds,
                        use_deepseek=use_deepseek,
                        default_answer=default_answer,
                        auto_answer=auto_answer,
                    )
                    if test_ok:
                        log.info("[监控] 章节测试已完成，继续切换下一章...")
                        page.wait_for_timeout(2000)
                        for retry in range(3):
                            if switch_next_chapter(page):
                                episode += 1
                                try:
                                    page.wait_for_selector("video", timeout=10000)
                                except Exception:
                                    pass
                                wait_video_ready(page, timeout=8.0)
                                set_speed(page, speed)
                                resume_playback(page, max_wait=1.5)
                                last_log_second = -1
                                break
                            page.wait_for_timeout(2000)
                        else:
                            log.warning("[视频] 测试后仍无法切换下一章，脚本退出")
                            return
                    else:
                        log.warning("[视频] 章节测试处理失败，脚本退出")
                        return
                else:
                    log.warning("[视频] 多次尝试后仍无法切换下一节且无测试，脚本退出")
                    return
