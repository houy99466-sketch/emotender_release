# EmoTender

EmoTender 是一个“情绪酒保”比赛 Demo。当前版本的核心链路是：

```text
用户在平板/网页输入语音或文字
  -> 文字发送到 Windows 后端 /api/text/analyze
  -> 后端调用 LLM，输出结构化 control_json
  -> 前端显示机器人表情、酒保回复、正式推荐结果
  -> 正式推荐时显示六维风味图和牛皮纸小票
  -> 机器人侧后续按 control_json 执行动作、表情、接待或递酒流程
```

当前比赛交付重点不是让机器人独立完成完整抓取和调酒，而是稳定展示“对话接待 + 情绪理解 + 个性化饮品推荐 + 长期用户记忆 + 平板辅助机器人”的完整体验。

## 当前版本重点

- Windows 侧可直接运行后端，不再依赖 VMware 桥接网络。
- 平板 APK 使用 Android 系统语音识别，把识别出的文字发送给 Windows 后端。
- APK 启动时要求用户输入后端地址，不再默认写死 `192.168.1.100`。
- 网页和平板共用 `static/index.html`，后端返回结果后统一更新页面。
- 闲聊模式每轮都会返回 JSON，用于驱动表情、动作和回复。
- 正式推荐模式依次显示个性化推荐理由、当前情绪占比饼图、六维风味图和牛皮纸小票。
- 每个情绪占比都包含本次会话中的来源说明；历史 profile 情绪不参与本轮情绪判断。
- 正式推荐结果可以导出为从表情到牛皮纸小票的 PNG 长图。
- 后端保留关键词触发推荐，并新增“上一轮询问是否正式推荐 + 用户本轮同意”的转推荐逻辑。
- 登录用户名后会建立本地 profile，Logout 时把本次会话压缩保存到用户长期档案。

## 文件结构

```text
emotender_release/
  android/
    EmoTenderTabletApp/
      app/src/main/
      build.gradle
      settings.gradle
  .env.example
  .gitignore
  CHANGELOG.md
  README.md
  emotender_backend.py
  requirements.txt
  requirements-asr.txt
  prompts/
    drink_mapping.json
    profile_summary_prompt.md
  scripts/
    deploy_to_asr_test.sh
    start_backend.sh
  static/
    index.html
    vendor/
      html2canvas.min.js
      html2canvas.LICENSE
  tests/
    test_dialogue_modes.py
    test_optional_asr_dependency.py
    test_user_profiles.py
  docs/
    Windows平板使用指南.md
  release/
    EmoTender-latest.apk
```

不会提交的本地文件：

```text
.env
.venv/
recording.wav
data/profiles/
__pycache__/
*.log
```

`data/profiles/` 是用户长期档案目录，属于本地隐私数据，不上传 GitHub。

## 环境变量

后端从 `.env` 读取 LLM 配置：

```env
LLM_BASE_URL=https://www.cctq.ai/v1
LLM_API_KEY=你的中转站 API Key
LLM_MODEL=gpt-5.5
```

`.env` 已被 `.gitignore` 忽略，不要把真实 API Key 提交到仓库。

## Windows 后端启动

进入项目目录：

```powershell
Set-Location 'E:\vmwareshare\emotender_release'
```

首次运行时创建虚拟环境：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

如果没有 `.env`：

```powershell
Copy-Item .env.example .env
notepad .env
```

启动后端：

```powershell
.\.venv\Scripts\python.exe -m uvicorn emotender_backend:app --host 0.0.0.0 --port 8000
```

启动后不要关闭这个 PowerShell 窗口。浏览器访问：

```text
http://127.0.0.1:8000/
```

## 平板 APK 使用

APK 成品位于：

```text
release/EmoTender-latest.apk
```

APK 1.2.0 的 Android 源码位于：

```text
android/EmoTenderTabletApp
```

安装后：

1. 确保 Windows 电脑和平板在同一个 Wi-Fi 或同一个手机热点下。
2. Windows 后端按 `--host 0.0.0.0 --port 8000` 启动。
3. Windows 查询当前网络 IPv4：

```powershell
ipconfig
```

4. 在 APK 启动弹窗里输入：

```text
http://Windows的IPv4地址:8000
```

例如：

```text
http://192.168.43.252:8000
```

5. 点 `Load` 进入页面。
6. 点 `Start` 调用 Android 系统语音识别。
7. APK 会把识别出的文字传给网页的 `submitRecognizedText(text)`。
8. 网页再请求后端 `POST /api/text/analyze`。

正式推荐完成后，页面底部会显示 `保存为图片`：

- APK 1.2.0：保存到系统 `Pictures/EmoTender`。
- 普通浏览器：按浏览器下载流程保存 PNG。

如果需要重新填写后端地址，长按 APK 页面，会重新弹出后端地址输入框。

## 网页/平板 UI

顶部左侧：

- `username` 输入框
- `Login`
- `Logout`

顶部右侧：

- 圆形 `?` 说明入口

主操作区：

- `Start`：平板中调用 Android 语音识别；普通浏览器中保留原后端录音接口。
- `Send`：发送手动输入文字。
- `Reset`：清空当前内存会话。

显示规则：

- `bar_chat`：只显示表情和回复，不显示六维风味图，不显示牛皮纸小票。
- `recommendation`：显示最终回复、个性化推荐理由、情绪占比饼图、六维风味图、牛皮纸小票和保存按钮。
- `safety`：安全回应，不推荐酒精饮品。

## 后端接口

### `GET /`

返回 `static/index.html`。

### `GET /api/status`

检查后端状态。

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/status
```

### `POST /api/text/analyze`

平板、网页手动输入和文本测试的主接口。

Windows PowerShell 发送中文时建议使用 UTF-8 字节，避免中文变成问号：

```powershell
$body = @{user_text='推荐一杯清爽一点的。'; username='demo'} | ConvertTo-Json -Compress
$bytes = [System.Text.Encoding]::UTF8.GetBytes($body)
Invoke-RestMethod `
  -Uri 'http://127.0.0.1:8000/api/text/analyze' `
  -Method POST `
  -ContentType 'application/json; charset=utf-8' `
  -Body $bytes
```

正式推荐返回中应包含：

```json
{
  "turn_type": "recommendation",
  "control_json": {
    "drink_name": "...",
    "drink_metadata": {
      "name": "...",
      "backstory": "...",
      "recipe": "..."
    }
  }
}
```

### `POST /api/user/login`

登录或创建本地用户 profile。

```powershell
$body = @{username='demo'} | ConvertTo-Json -Compress
$bytes = [System.Text.Encoding]::UTF8.GetBytes($body)
Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/user/login' -Method POST -ContentType 'application/json; charset=utf-8' -Body $bytes
```

### `POST /api/user/logout`

退出并保存本次会话摘要到本地 profile。

### `GET /api/user/profile`

查看指定用户名的本地 profile。

```text
http://127.0.0.1:8000/api/user/profile?username=demo
```

### `POST /api/reset`

清空当前内存会话，不删除已经保存到 `data/profiles/` 的长期 profile。

## 对话模式

### `bar_chat`

用户只是聊天、倾诉或打招呼时使用。后端仍会输出完整 `control_json`：

- `emotion_label`
- `emotion_blend`
- `complex_emotion`
- `face_state`
- `bartender_line`
- `action_sequence`
- `feedback_prompt`
- `recommendation_reason`

`emotion_blend` 每项包含当前会话中的情绪来源：

```json
{
  "emotion": "难过",
  "weight": 0.7,
  "source": "用户说今天考试没有考好"
}
```

此模式下：

```json
{
  "drink_name": "无正式推荐",
  "recipe_modules": [],
  "recommendation_reason": "无正式推荐",
  "drink_metadata": null
}
```

### `recommendation`

用户明确要求推荐、调酒、来一杯，或上一轮机器人询问是否正式推荐后用户表示同意时使用。

此模式下后端会：

- 要求 LLM 推荐后端菜单中的饮品。
- 校验 `recipe_modules` 非空。
- 根据 `drink_name` 自动补充 `drink_metadata`。
- 输出与当前会话具体经历相关的 `recommendation_reason`。
- 前端显示情绪饼图、六维图和牛皮纸小票，并允许保存完整长图。

长期 profile 只允许影响口味偏好、避忌、交流风格和历史饮品参考。`emotion_patterns` 和历史会话摘要不会送入本轮情绪判断 Prompt。

### `safety`

涉及未成年饮酒、酒驾、吃药后饮酒、自伤、医学诊断等内容时使用。此模式不推荐酒精饮品。

## 机器人侧对接

机器人侧主要消费后端返回的：

```json
{
  "turn_type": "recommendation",
  "robot_reply_text": "...",
  "control_json": {
    "emotion_label": "...",
    "emotion_blend": [
      {"emotion": "难过", "weight": 0.7, "source": "来自本轮对话的具体原因"}
    ],
    "recommendation_reason": "...",
    "face_state": "happy",
    "action_sequence": "serve_only",
    "drink_name": "...",
    "recipe_modules": [],
    "drink_metadata": {}
  }
}
```

建议机器人侧先对接：

- `face_state`：表情/OLED/屏幕动画。
- `action_sequence`：接待、思考、递酒等动作序列。
- `robot_reply_text`：需要播报时使用。
- `drink_name`：后台人工调酒或递酒流程使用。
- `turn_type`：判断是否已经进入正式推荐。

## 测试

运行单元测试：

```powershell
python -m unittest discover -s tests
```

编译检查：

```powershell
python -m py_compile emotender_backend.py
```

Prompt JSON 检查：

```powershell
python -m json.tool prompts\drink_mapping.json > $null
```

## 常见问题

### PowerShell 返回中文变成问号

不要直接把中文 JSON 字符串作为 `-Body` 字面量传入。使用 README 中的 UTF-8 字节写法。

### 平板连不上 Windows 后端

检查：

- 平板和 Windows 是否在同一个网络。
- 后端是否用 `--host 0.0.0.0` 启动。
- APK 中填写的是 Windows 当前网络的 IPv4，不是 VMware 的 VMnet IP。
- Windows 防火墙是否拦截 8000 端口。

### 不显示六维图和牛皮纸小票

只有后端返回：

```json
"turn_type": "recommendation"
```

并且有正式 `drink_metadata` 时才显示。闲聊模式不会显示。

### 闲聊后一直不进入推荐

可用以下话术测试：

```text
我今天有点累。
```

等机器人问是否需要正式推荐后，再说：

```text
可以，你看着安排。
```

预期返回 `turn_type = recommendation`。

## 协作规范

每次修改后建议同步更新：

- `CHANGELOG.md`
- `README.md` 中对应使用说明
- 必要的测试文件

不要提交：

- `.env`
- `.venv/`
- `data/profiles/`
- 真实 API Key
- 真实用户 profile
