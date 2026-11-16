# README.md
@'
# 智慧树自动播放脚本

自动打开 Edge 浏览器 → 同时打开智慧树和 DeepSeek → 手动登录两个网站 → 进入课程 → 设置倍速 → 自动播放 → 弹窗自动作答 → 章节测试自动作答 → 播完自动切集。

## 项目结构

```text
├── auto_play.py     # 主入口（启动两个网页并串联完整流程）
├── config.py        # 配置（课程名、倍速、DeepSeek 开关等）
├── browser.py       # 浏览器启动与双站点登录等待
├── player.py        # 视频控制（进入课程、倍速设置、播放/暂停、切集）
├── quiz.py          # 弹窗处理（随堂练习解析、DeepSeek 请求、选项点击、提交作答）
├── exam.py          # 章节测试处理（进入测试、解析题目、DeepSeek 作答、提交、返回视频）
├── deepseek.py      # DeepSeek 网页对话（构造提示词、发送问题、提取答案）
├── monitor.py       # 监控循环（进度 + 弹窗 + 章节测试 + 自动切集）
├── inspect_popup.py # 一次性 DOM 检查工具
└── requirements.txt # 依赖
```

## 使用方法

### 1. 安装依赖

```bash
pip install -r requirements.txt
python -m playwright install msedge
```

### 2. 运行脚本

```bash
python auto_play.py
```

脚本会同时打开两个页面：

1. 智慧树学习页；
2. DeepSeek 网页版。

### 3. 手动登录

分别完成智慧树和 DeepSeek 登录。两个页面都登录成功后，回到终端输入：

```text
Y
```

这是唯一确认，脚本随即继续执行。

### 4. 自动运行

脚本随后自动完成：

- 进入 `config.COURSE_NAME` 指定的课程；
- 设置 `config.SPEED` 指定的倍速；
- 播放视频；
- 每 `config.POLL_INTERVAL` 秒检查一次状态；
- 检测到随堂练习时解析题目和选项；
- 将题目和选项发送给 DeepSeek；
- 要求 DeepSeek 只返回答案字母；
- 点击返回的答案并提交（单选/多选/判断均支持）；
- 每章视频播完后检测章节测试入口；
- 自动进入测试页面，逐题 DeepSeek 作答并提交；
- 播完自动切换下一集。

DeepSeek 失败时会使用 `QUIZ_DEFAULT_ANSWER` 作为兜底答案。

## 章节测试流程

当一章最后一节视频播完后：

1. 脚本检测侧边栏 `.test-box`（测试）或 `.mastery-btn-free-exam`（去答题）入口
2. 点击进入测试页面
3. 解析所有题目（题型/题目/选项）
4. 逐题发送给 DeepSeek 获取答案
5. 点击选项（多选题支持多个答案如 A/C/D）
6. 点击提交并处理确认弹窗
7. 返回视频页面，继续下一章

## 配置说明

编辑 `config.py` 可修改：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `COURSE_NAME` | `"运动安全与健康"` | 课程名称（模糊匹配） |
| `SPEED` | `1.5` | 播放倍速 |
| `POLL_INTERVAL` | `1` | 检测间隔（秒） |
| `DEEPSEEK_URL` | `https://chat.deepseek.com` | DeepSeek 网页地址 |
| `USE_DEEPSEEK` | `True` | 是否将题目发给 DeepSeek |
| `QUIZ_AUTO_ANSWER` | `True` | 是否自动提交题目 |
| `QUIZ_DEFAULT_ANSWER` | `"A"` | DeepSeek 失败时的兜底选项 |

## DeepSeek 提示词

随堂练习或章节测试触发后，脚本会构造如下提示词：

```text
请回答以下{题型}，只返回答案字母（如A/B/C/D），不要返回任何其他内容。

题目：{题目}

选项：
A. {选项A}
B. {选项B}

答案：
```

- 单选题返回单个字母如 `A`
- 多选题返回多个字母如 `A/C/D`
- 判断题返回 `A`（对）或 `B`（错）

脚本会从 DeepSeek 的回复中提取答案字母，并点击对应的选项。
