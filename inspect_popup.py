"""一次性脚本：提取智慧树当前弹窗问题的 DOM 结构"""
import json
from playwright.sync_api import sync_playwright

pw = sync_playwright().start()
browser = pw.chromium.launch(channel="msedge", headless=False)
context = browser.new_context(viewport={"width": 1280, "height": 800})
page = context.new_page()
page.goto("https://onlineweb.zhihuishu.com/onlinestuh5", wait_until="domcontentloaded", timeout=30000)

# 让用户手动导航到有弹窗的页面
input("按回车继续（确保页面有弹窗问题出现）…")

# 提取弹窗区域 HTML
html = page.evaluate("""() => {
    // 常见弹窗选择器
    const candidates = [
        document.querySelector('[class*="pop"], [class*="modal"], [class*="dialog"], [class*="quiz"], [class*="exam"], [class*="test"], [class*="question"]'),
        document.querySelector('.el-dialog, .ant-modal, .vjs-modal'),
    ].filter(Boolean);

    if (candidates.length > 0) {
        return { type: 'found', html: candidates[0].outerHTML.slice(0, 5000) };
    }

    // 兜底：取整个页面中包含"题目"或"选项"文字的元素
    const all = document.querySelectorAll('div, section');
    for (const el of all) {
        const text = el.innerText || '';
        if ((text.includes('题目') || text.includes('选项') || text.includes('A.') || text.includes('单选')) && text.length < 2000) {
            return { type: 'guessed', html: el.outerHTML.slice(0, 5000), text: text.slice(0, 1000) };
        }
    }
    return { type: 'not_found' };
}""")

print(json.dumps(html, ensure_ascii=False, indent=2))

# 也截一张图
page.screenshot(path="question_popup.png")
print("截图已保存: question_popup.png")

input("按回车退出…")
browser.close()
pw.stop()
