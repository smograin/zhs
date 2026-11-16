"""智慧树自动播放 - 主入口"""
import sys, logging
from playwright.sync_api import sync_playwright

import config
from browser import launch_browser, wait_login
from player  import enter_course, set_speed, click_play
from quiz    import handle_all_popups
from monitor import monitor_and_advance

LEVEL_EMOJI = {
    "DEBUG":    "\U0001F50D",  # 🔍
    "INFO":     "\U0001F7E2",  # 🟢
    "WARNING":  "\U0001F7E1",  # 🟡
    "ERROR":    "\U0001F534",  # 🔴
    "CRITICAL": "\U0001F4A5",  # 💥
}


class EmojiFormatter(logging.Formatter):
    """把日志级别 [INFO] 等替换成对应的 emoji，输出更好看"""

    def format(self, record):
        record.level_emoji = LEVEL_EMOJI.get(record.levelname, "\U0001F539")  # 默认 🔹
        return super().format(record)


class ErrorHandler(logging.Handler):
    """🔴 红色日志（ERROR / CRITICAL）→ 终止程序"""

    def emit(self, record):
        if record.levelno >= logging.ERROR:
            # 确保消息已经格式化并刷到终端
            logging.shutdown()
            sys.exit(1)


_handler = logging.StreamHandler()
_handler.setFormatter(EmojiFormatter(
    fmt="%(asctime)s %(level_emoji)s %(message)s",
    datefmt="%H:%M:%S",
))

# 🔴 红色日志终止 handler
_error_handler = ErrorHandler()

logging.basicConfig(
    level=logging.INFO,
    handlers=[_handler, _error_handler],
)
log = logging.getLogger("zhihuishu")


def main():
    pw = sync_playwright().start()
    browser, context, page, page_deepseek = launch_browser(pw, config)

    try:
        # 1. 打开登录页
        log.info("▶️ 打开智慧树登录页...")
        page.goto(config.LOGIN_URL, wait_until="domcontentloaded", timeout=30000)

        # 2. Open DeepSeek and require the user to log in to both pages.
        page_deepseek.goto(config.DEEPSEEK_URL, wait_until="domcontentloaded", timeout=30000)
        wait_login(page, page_deepseek)

        # 3. 进入课程
        if not enter_course(page, config.COURSE_NAME):
            log.error("❌ 无法进入课程，请检查课程名称是否正确")
            return

        # 4. 等待视频加载
        log.info("▶️ 等待视频加载...")
        page.wait_for_selector("video", timeout=30000)
        page.wait_for_timeout(2000)

        # 5. 关闭进入课程后的初始弹窗（课程提示、课程提醒公众号绑定等）
        #    课程提醒弹窗通过点击 X 关闭按钮关闭
        log.info("▶️ 检查并关闭初始弹窗...")
        popup_found = False
        for round_i in range(5):
            if not handle_all_popups(
                page,
                config.QUIZ_DEFAULT_ANSWER,
                config.QUIZ_AUTO_ANSWER,
                page_ds=page_deepseek,
                use_deepseek=config.USE_DEEPSEEK,
            ):
                break
            log.info("🚀 第 %d 轮弹窗已处理", round_i + 1)
            popup_found = True
            page.wait_for_timeout(800)
        if popup_found:
            log.info("▶️ 初始弹窗已全部关闭，恢复视频播放...")
            page.wait_for_timeout(1000)
            click_play(page)
        log.info("▶️ 初始弹窗处理完毕")

        # 6. 设置倍速 & 播放
        set_speed(page, config.SPEED)
        click_play(page)

        # 7. 循环监控（视频进度 + 倍速保持 + 弹窗作答 + 自动切集）
        monitor_and_advance(
            page, context,
            speed=config.SPEED,
            poll_interval=config.POLL_INTERVAL,
            auto_answer=config.QUIZ_AUTO_ANSWER,
            default_answer=config.QUIZ_DEFAULT_ANSWER,
            page_ds=page_deepseek,
            use_deepseek=config.USE_DEEPSEEK,
        )

    except KeyboardInterrupt:
        log.info("▶️ 用户中断脚本")
    except SystemExit:
        raise  # 让 ErrorHandler 的 sys.exit(1) 正常生效
    finally:
        try:
            browser.close()
            pw.stop()
        except Exception:
            pass


if __name__ == "__main__":
    main()
