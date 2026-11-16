"""智慧树自动播放 - 配置文件"""

# ═══════════════ 课程与播放 ═══════════════
COURSE_NAME   = "运动安全与健康"   # 课程名称（模糊匹配）
SPEED         = 1.5                # 播放倍速（1 / 1.25 / 1.5 / 2）
POLL_INTERVAL = 1                  # 检测播放进度间隔（秒）

# ═══════════════ 页面地址 ═══════════════
LOGIN_URL     = "https://onlineweb.zhihuishu.com/onlinestuh5"
DEEPSEEK_URL  = "https://chat.deepseek.com"

# ═══════════════ 弹窗题目 ═══════════════
QUIZ_AUTO_ANSWER    = True         # 是否自动作答（False=暂停等手动）
QUIZ_DEFAULT_ANSWER = "A"          # 默认选择答案（DeepSeek 失败时的兜底）
USE_DEEPSEEK        = True         # 是否使用 DeepSeek 网页作答

# ═══════════════ 浏览器 ═══════════════
HEADLESS = False                   # False = 可见浏览器
VIEWPORT = {"width": 1280, "height": 800}
