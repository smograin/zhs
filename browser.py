"""智慧树自动播放 - 浏览器启动与登录"""
import os, logging, time
from playwright.sync_api import sync_playwright

log = logging.getLogger("zhihuishu")


def launch_browser(pw: sync_playwright, config):
    """启动 Edge 浏览器，返回 (browser, context, page_zhihuishu, page_deepseek)"""
    browser = pw.chromium.launch(
        channel="msedge",
        headless=config.HEADLESS,
    )
    context = browser.new_context(
        viewport=config.VIEWPORT,
    )
    page_zhihuishu = context.new_page()
    page_deepseek  = context.new_page()
    return browser, context, page_zhihuishu, page_deepseek


def wait_login(page_zhihuishu, page_deepseek):
    """等待用户在终端输入 Y 确认两个网页都登录完成"""
    log.info("[登录] 请在浏览器中手动登录 智慧树 和 DeepSeek")
    log.info("[登录] 两个网页都登录成功后，在终端输入 Y 并回车继续...")
    while True:
        try:
            answer = input("").strip().upper()
        except EOFError:
            time.sleep(3)
            continue
        if answer == "Y":
            log.info("[登录] 用户确认登录成功，继续执行")
            return
        log.info("[登录] 请输入 Y 确认登录")
