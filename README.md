# EmoTender

EmoTender 是一个情绪酒保原型系统。它把用户的语音或文字输入交给 LLM 中控分析，输出可被网页、平板端和机器人侧消费的结构化 JSON，用来驱动：

1. 情绪识别和连续闲聊。
2. 个性化饮品推荐。
3. 机器人表情状态和动作序列。
4. 老柯人格台词。
5. 牛皮纸小票故事、配方和色泽说明。
6. 登录用户的长期 profile 记忆。

当前版本的重点不是让机器人独立完成全部调酒动作，而是完成一条稳定的比赛 demo 链路：

```text
用户说话或输入文字
  -> ASR 或平板系统语音识别转文字
  -> EmoTender 后端
  -> LLM 中控输出 control_json
  -> 前端/平板展示表情、台词、风味图、小票
  -> 机器人侧按 control_json 执行接待、表情、动作或递酒流程
```

## 当前能力

### 已实现

- 浏览器页面：`static/index.html`
  - Start / Stop 录音按钮。
  - Reset 重置会话。
  - 用户名 Login / Logout。
  - 顶部 `?` 说明入口。
  - CRT 表情屏。
  - 六维风味图。
  - 牛皮纸小票。
  - 前端会优先读取后端返回的 `drink_metadata`，没有时回退到前端内置 `DRINK_DB`。

- Python FastAPI 后端：`emotender_backend.py`
  - 支持语音录制和 FunASR 转写。
  - 支持纯文字输入接口，供 APK/平板端调用。
  - 支持 `bar_chat`、`recommendation`、`safety` 三种对话模式。
  - 每轮都输出完整 `control_json`，即使是闲聊也会输出情绪、表情、动作和台词。
  - `bar_chat` 下 `robot_reply_text = bartender_line + feedback_prompt`，让闲聊更像连续对话。
  - `recommendation` 和 `safety` 下 `robot_reply_text = bartender_line`。
  - 内置 LLM 输出校验和 fallback，避免 JSON 格式错误直接打断流程。
  - 支持长期用户 profile：登录用户后，会把 profile 注入 LLM prompt；Logout 时压缩本次会话并写入本地 profile。

- 饮品和小票系统
  - 后端内置 `DRINK_MENU`，包含单品和混合情绪特调。
  - 推荐饮品时，后端会根据 `drink_name` 自动补充 `drink_metadata`。
  - `drink_metadata` 包含饮品中文名、英文名、配方模块、风味、色泽、表情、动作、上酒台词、故事、配方、颜色等。

- Prompt 库
  - 情绪、配方模块、表情状态、动作序列位于 `prompts/drink_mapping.json`。
  - 用户会话压缩 prompt 位于 `prompts/profile_summary_prompt.md`。

- 测试
  - `tests/test_dialogue_modes.py`
  - `tests/test_optional_asr_dependency.py`
  - `tests/test_user_profiles.py`

### 当前不包含

- 真实机器人抓取规划。
- 真实调酒机械控制。
- 机器人侧 ROS 节点实现。
- APK 源码和 APK 成品不在本仓库内；当前仓库只提供后端接口和网页端。

机器人侧目前应接收本后端输出的 `control_json`，再由机器人侧团队按字段对接表执行表情、动作、接待、递酒等能力。

## 推荐 Demo 架构

### 浏览器语音版

```text
浏览器网页
  -> POST /api/voice/start
  -> 后端 arecord 录音
  -> POST /api/voice/stop
  -> FunASR 转文字
  -> LLM 分析
  -> 返回 control_json
  -> 网页更新表情、台词、风味图、小票
```

### 平板版

```text
平板 App
  -> 调用 Android 系统语音识别
  -> 得到 user_text
  -> POST /api/text/analyze
  -> EmoTender 后端返回 control_json
  -> 平板展示结果
  -> 机器人侧读取或接收 control_json 后执行动作
```

平板版绕开了机器人本体 ASR 不稳定的问题。比赛现场可以把平板固定在机器人身上，让平板完成语音输入、网页/App 展示和后端请求，机器人负责接待感、移动、递酒或表情动作。

### 机器人侧对接建议

机器人侧主要消费：

```json
{
  "face_state": "happy",
  "action_sequence": "serve_only",
  "robot_reply_text": "挺好。好心情不用急着花掉，慢慢喝它一口。\n这份好心情，是因为什么来的？"
}
```

推荐模式还会消费：

```json
{
  "drink_name": "冷启动",
  "recipe_modules": ["clear_balance", "bitter_focus"],
  "flavor_profile": "清爽、微苦、低甜、带轻微气泡感",
  "color_profile": "透明偏冷调，带一点淡青色",
  "drink_metadata": {
    "name": "冷启动",
    "name_en": "Cold Start",
    "serve_line": "这杯叫《冷启动》。你看它，像不像凌晨三点的海面？我用清酒和柚子汁调出了这种苦，但苦得刚刚好。喝完它，世界安静了，你也是。",
    "backstory": "以前有个总坐角落的客人，每次来都点这杯。他说：'老柯，喝别的像在逃避，喝这杯像在跟自己谈判。'后来他走了，每年跨年还给我发消息：'今晚没你，但窗外的海还是蓝的。'",
    "recipe": "清酒45ml + 鲜榨柚子汁20ml + 青柠汁10ml + 薄荷叶3片 + 龙舌兰糖浆5ml + 苏打水补满，高球杯加冰",
    "color": "透明偏冷调，淡青色"
  }
}
```

## 文件结构

```text
emotender_release/
  .env.example
  .gitignore
  CHANGELOG.md
  PROMPT_EDITING.md
  README.md
  VMWARE_AI_DEPLOY_INSTRUCTIONS.md
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
  tests/
    test_dialogue_modes.py
    test_optional_asr_dependency.py
    test_user_profiles.py
```

运行后会产生但不会提交：

```text
.env
.venv/
recording.wav
data/profiles/
__pycache__/
*.log
```

`data/profiles/` 存放登录用户的长期 profile，属于本地隐私数据，已经加入 `.gitignore`，不要上传。

## 环境变量

后端从 `.env` 读取：

```env
LLM_BASE_URL=https://www.cctq.ai/v1
LLM_API_KEY=填写你的中转站_API_Key
LLM_MODEL=gpt-5.5
```

注意：

- `.env` 不要提交。
- 这里是 Python 后端通过 OpenAI SDK 直接调用 OpenAI 兼容中转站。
- 这不是 CC switch 配置，也不需要修改 Codex 或 Claude Code 网关。

## VMware Ubuntu 部署

目标部署目录：

```bash
~/asr_test
```

### 1. 找到共享目录

优先进入：

```bash
cd /mnt/hgfs/vmwareshare/emotender_release
```

如果路径不存在：

```bash
find /mnt /media -name emotender_release -type d 2>/dev/null
```

进入实际找到的目录。

### 2. 一键部署

```bash
chmod +x scripts/deploy_to_asr_test.sh scripts/start_backend.sh
./scripts/deploy_to_asr_test.sh
```

脚本会复制：

```text
emotender_backend.py
requirements.txt
static/index.html
prompts/drink_mapping.json
prompts/profile_summary_prompt.md
```

并创建或复用：

```text
~/asr_test/.venv
~/asr_test/.env
```

### 3. 填写 `.env`

```bash
gedit ~/asr_test/.env
```

填入真实值：

```env
LLM_BASE_URL=https://www.cctq.ai/v1
LLM_API_KEY=你的真实 key
LLM_MODEL=gpt-5.5
```

### 4. 启动后端

方式一：

```bash
cd ~/asr_test
source .venv/bin/activate
uvicorn emotender_backend:app --host 0.0.0.0 --port 8000
```

方式二：

```bash
cd /mnt/hgfs/vmwareshare/emotender_release
./scripts/start_backend.sh
```

保持启动后端的终端不要关闭。

### 5. 打开网页

在 VMware Ubuntu 浏览器打开：

```text
http://127.0.0.1:8000/
```

如果用同一 Wi-Fi 下的手机或平板访问电脑/虚拟机后端，需要使用后端所在机器的局域网 IP，例如：

```text
http://192.168.xx.xx:8000/
```

并确认防火墙、虚拟机网络模式和同网段访问没有阻断。

## Windows 本地运行

Windows 可以运行后端的 LLM 文本分析和网页静态界面，但 FunASR/arecord 语音录制链路主要面向 Ubuntu。

建议 Windows 本地只用于：

- 后端单元测试。
- `/api/text/analyze` 文本接口测试。
- README / prompt / 前端修改。

基础命令：

```powershell
cd E:\vmwareshare\emotender_release
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

创建 `.env`：

```powershell
Copy-Item .env.example .env
notepad .env
```

启动：

```powershell
uvicorn emotender_backend:app --host 0.0.0.0 --port 8000
```

访问：

```text
http://127.0.0.1:8000/
```

## 网页操作

### 语音链路

1. 打开 `http://127.0.0.1:8000/`。
2. 点击 `Start`。
3. 说话。
4. 点击 `Stop`。
5. 页面显示台词，表情屏变化。
6. 如果是推荐模式，显示六维风味图。
7. 调整六维图后点击确认，生成牛皮纸小票。

### 用户 profile

1. 右上角输入用户名。
2. 点击 `Login`。
3. 正常聊天或推荐。
4. 点击 `Logout`。
5. 后端会将本次会话压缩成 summary，写入本地：

```text
data/profiles/
```

下次同一用户名登录，后端会读取该 profile，并将压缩后的长期偏好注入 LLM prompt。

### 重置

点击 `Reset` 会清空当前内存会话：

```text
conversation_history
conversation_summary
emotion_history
```

`Reset` 不会删除已经保存到 `data/profiles/` 的长期 profile。

## API

### `GET /`

返回网页 `static/index.html`。

### `GET /api/status`

查看后端状态：

```bash
curl http://127.0.0.1:8000/api/status
```

返回字段包括：

```json
{
  "recording": false,
  "audio_path": ".../recording.wav",
  "last_result": null,
  "conversation_state": {
    "summary": "",
    "history": []
  }
}
```

### `POST /api/text/analyze`

平板/App/文字测试入口。

请求：

```bash
curl -X POST http://127.0.0.1:8000/api/text/analyze \
  -H "Content-Type: application/json" \
  -d '{"user_text":"我今天心情挺好的。","username":"alice"}'
```

`username` 可选。传入后，本轮会读取对应 profile。

### `POST /api/user/login`

登录或创建本地 profile：

```bash
curl -X POST http://127.0.0.1:8000/api/user/login \
  -H "Content-Type: application/json" \
  -d '{"username":"alice"}'
```

### `POST /api/user/logout`

退出并保存本次会话 summary：

```bash
curl -X POST http://127.0.0.1:8000/api/user/logout \
  -H "Content-Type: application/json" \
  -d '{"username":"alice"}'
```

如果本次没有会话历史，`saved_summary` 为 `null`。

### `GET /api/user/profile`

查看本地 profile：

```bash
curl "http://127.0.0.1:8000/api/user/profile?username=alice"
```

### `POST /api/voice/start`

启动录音。

```bash
curl -X POST http://127.0.0.1:8000/api/voice/start
```

后端调用：

```bash
arecord -D default -f S16_LE -r 16000 -c 1 recording.wav
```

### `POST /api/voice/stop`

停止录音并执行：

```text
recording.wav
  -> FunASR
  -> user_text
  -> LLM
  -> control_json
```

```bash
curl -X POST http://127.0.0.1:8000/api/voice/stop
```

### `POST /api/reset`

清空当前内存会话：

```bash
curl -X POST http://127.0.0.1:8000/api/reset
```

## 返回 JSON 结构

外层返回：

```json
{
  "ok": true,
  "username": "alice",
  "user_text": "我今天心情挺好的。",
  "turn_type": "bar_chat",
  "control_json": {},
  "robot_reply_text": "挺好。好心情不用急着花掉，慢慢喝它一口。\n这份好心情，是因为什么来的？",
  "profile_context": {},
  "conversation_state": {},
  "used_fallback": false,
  "llm_error": null
}
```

`control_json` 必含字段：

```json
{
  "schema_version": "1.0",
  "turn_type": "bar_chat",
  "user_text": "我今天心情挺好的。",
  "emotion_label": "兴奋",
  "emotion_blend": [
    {"emotion": "兴奋", "weight": 0.7},
    {"emotion": "清醒", "weight": 0.3}
  ],
  "complex_emotion": "状态明亮，能量稳定，带一点轻松的满足感。",
  "need_summary": "否",
  "drink_name": "无正式推荐",
  "recipe_modules": [],
  "flavor_profile": "无正式推荐",
  "color_profile": "无正式推荐",
  "face_state": "happy",
  "bartender_line": "挺好。好心情不用急着花掉，慢慢喝它一口。",
  "action_sequence": "serve_only",
  "feedback_prompt": "这份好心情，是因为什么来的？",
  "drink_metadata": null
}
```

推荐模式下 `drink_metadata` 会有内容：

```json
{
  "drink_name": "冷启动",
  "drink_metadata": {
    "name": "冷启动",
    "name_en": "Cold Start",
    "recipe_modules": ["clear_balance", "bitter_focus", "spark_restart"],
    "flavor_profile": "清爽、微苦、低甜、带轻微气泡感",
    "color_profile": "透明偏冷调，带一点淡青色",
    "face_state": "focused",
    "action_sequence": "make_cold_start",
    "kernel": "不是提神，是'在长夜里给自己点一盏孤灯'",
    "emotional_value": "独处时的清醒，比喧闹中的狂欢更体面",
    "serve_line": "这杯叫《冷启动》。你看它，像不像凌晨三点的海面？我用清酒和柚子汁调出了这种苦，但苦得刚刚好。喝完它，世界安静了，你也是。",
    "flavor": "我不加多余的甜，因为清醒本身就是一种味道。",
    "backstory": "以前有个总坐角落的客人，每次来都点这杯。",
    "recipe": "清酒45ml + 鲜榨柚子汁20ml + 青柠汁10ml + 薄荷叶3片 + 龙舌兰糖浆5ml + 苏打水补满，高球杯加冰",
    "color": "透明偏冷调，淡青色"
  }
}
```

## 对话模式

### `bar_chat`

闲聊模式。

触发方式：用户没有明确要求推荐饮品时。

特点：

- 不正式推荐酒。
- `drink_name = "无正式推荐"`。
- `recipe_modules = []`。
- 仍然输出 `emotion_label`、`face_state`、`action_sequence` 和台词。
- `robot_reply_text` 会拼接 `bartender_line` 和 `feedback_prompt`。

### `recommendation`

推荐模式。

触发方式：用户说出类似：

```text
推荐
调一杯
来一杯
喝什么
适合喝
做一杯
按你说的
你做主
```

特点：

- 必须推荐后端饮品菜单中的饮品。
- `recipe_modules` 不能为空。
- 后端会自动根据 `drink_name` 附加 `drink_metadata`。
- 前端会显示六维风味图和牛皮纸小票。

### `safety`

安全边界模式。

触发方式：用户提到未成年饮酒、酒驾、吃药后饮酒、自伤伤人、医学诊断等。

特点：

- 不推荐酒精饮品。
- 使用温和拒绝或安全回应。
- `action_sequence` 优先 `serve_only`。

## 长期 Profile

### 存储方式

用户名不会直接作为文件名。后端会对 username 做 SHA-256，保存为：

```text
data/profiles/<sha256>.json
```

profile 结构包括：

```json
{
  "username": "alice",
  "created_at": "...",
  "updated_at": "...",
  "stable_profile": {
    "taste_preferences": [],
    "emotion_patterns": [],
    "drink_history": [],
    "conversation_style": [],
    "avoidances": []
  },
  "session_summaries": []
}
```

### 什么时候写入

- Login：创建或读取 profile，并清空当前临时会话。
- 每轮分析：把 profile context 注入 LLM prompt。
- Logout：如果有会话历史，调用 `profile_summary_prompt.md` 压缩本次会话，并合并到 profile。

### profile summary 字段

`prompts/profile_summary_prompt.md` 要求输出：

```json
{
  "date": "YYYY-MM-DD",
  "username": "用户名",
  "session_emotion": "本次主要情绪",
  "drink_name": "本次推荐/饮用的酒；如果没有则写无正式推荐",
  "drink_result": "是否推荐、用户反馈如何",
  "event_summary": "本次对话中用户提到的事件概要",
  "taste_preferences": [],
  "emotional_pattern": "可复用的情绪模式",
  "future_hint": "下次可用于个性化回应的提示",
  "conversation_style": [],
  "avoidances": []
}
```

## 饮品菜单和小票

后端 `DRINK_MENU` 位于 `emotender_backend.py`。

它分为：

```text
单品
混合情绪特调
```

每个饮品可包含：

```text
name
name_en
emotions
recipe_modules
flavor_profile
color_profile
face_state
action_sequence
kernel
emotional_value
serve_line
flavor
backstory
recipe
color
```

小票显示优先级：

1. 后端 `drink_metadata.backstory`。
2. 后端 `drink_metadata.serve_line`。
3. 前端 `DRINK_DB[emotion].story`。

六维风味图目前仍使用前端 `DRINK_DB` 的数值作为初始值，用户可拖动调整。

## Prompt 修改

### 情绪和白名单

修改：

```text
prompts/drink_mapping.json
```

可调整：

```text
emotion_dimensions
blend_rules
hidden_drinks
allowed_recipe_modules
allowed_face_states
allowed_action_sequences
```

如果新增了新的 `recipe_modules`、`face_state` 或 `action_sequence` 名字，必须同步修改 `emotender_backend.py` 中的：

```python
ALLOWED_RECIPE_MODULES
ALLOWED_FACE_STATES
ALLOWED_ACTION_SEQUENCES
```

否则后端校验会拒绝 LLM 输出并进入 fallback。

### 长期记忆压缩

修改：

```text
prompts/profile_summary_prompt.md
```

该文件只负责 Logout 时的本次会话压缩，不直接决定每轮推荐结果。

## 测试

### 全量测试

```bash
python -m unittest discover -s tests
```

### 编译检查

```bash
python -m py_compile emotender_backend.py
```

### Prompt JSON 检查

```bash
python -m json.tool prompts/drink_mapping.json >/dev/null
```

### Windows PowerShell 写法

```powershell
python -m unittest discover -s tests
python -m py_compile emotender_backend.py
python -m json.tool prompts\drink_mapping.json > $null
```

## 常见问题

### 1. 网页打不开

检查后端是否启动：

```bash
curl http://127.0.0.1:8000/api/status
```

确认启动命令里用了：

```bash
--host 0.0.0.0 --port 8000
```

### 2. `arecord` 不存在

安装：

```bash
sudo apt update
sudo apt install -y alsa-utils
```

### 3. 没有录音设备

查看设备：

```bash
arecord -l
```

如果没有可用设备，建议现场使用平板语音识别链路，走 `/api/text/analyze`。

### 4. LLM 一直 fallback

返回里看：

```json
"used_fallback": true,
"llm_error": "..."
```

常见原因：

1. `.env` 的 `LLM_BASE_URL` 不对。
2. `.env` 的 `LLM_API_KEY` 不对。
3. `.env` 的 `LLM_MODEL` 不被中转站支持。
4. 中转站接口不兼容 OpenAI Chat Completions。
5. LLM 输出不是合法 JSON。
6. LLM 输出字段不在白名单中。

### 5. Login / Logout 失败

检查：

```bash
curl http://127.0.0.1:8000/api/status
```

确认后端运行正常。

再检查 `data/profiles/` 是否可写：

```bash
ls -la data
```

### 6. 手机或平板连不上电脑后端

确认：

1. 手机/平板和电脑在同一个 Wi-Fi 或热点网络。
2. 使用的是电脑在该网络下的 IPv4 地址。
3. 后端启动时使用 `--host 0.0.0.0`。
4. Windows 防火墙或虚拟机网络没有阻断 8000 端口。

## 协作规范

每次修改代码、prompt、前端或 README 后，建议同步更新：

```text
CHANGELOG.md
```

至少记录：

```text
改了什么
影响哪个模块
是否需要重启后端
是否需要同步修改白名单
是否影响机器人侧字段对接
```

不要提交：

```text
.env
.venv/
recording.wav
data/profiles/
真实 API key
真实用户 profile
```

## 当前建议分工

- 前端 UI：维护 `static/index.html`，包括表情、风味图、小票和登录说明。
- Agent / 后端：维护 `emotender_backend.py`、prompt、profile、API 输出格式。
- 机器人侧：消费 `control_json`，完成接待、表情、动作、递酒等机器人能力。
- BP / 展示：围绕“情绪酒保”“独一无二的一杯酒”“用户长期偏好数据库”“平板辅助机器人接待”组织叙事。

## 最小可用测试流程

```bash
cd /mnt/hgfs/vmwareshare/emotender_release
chmod +x scripts/deploy_to_asr_test.sh scripts/start_backend.sh
./scripts/deploy_to_asr_test.sh
gedit ~/asr_test/.env
cd ~/asr_test
source .venv/bin/activate
uvicorn emotender_backend:app --host 0.0.0.0 --port 8000
```

浏览器打开：

```text
http://127.0.0.1:8000/
```

文字接口快速验证：

```bash
curl -X POST http://127.0.0.1:8000/api/text/analyze \
  -H "Content-Type: application/json" \
  -d '{"user_text":"我今天心情挺好的。","username":"demo"}'
```

推荐模式快速验证：

```bash
curl -X POST http://127.0.0.1:8000/api/text/analyze \
  -H "Content-Type: application/json" \
  -d '{"user_text":"推荐一杯清爽一点的。","username":"demo"}'
```

推荐模式返回中应包含：

```json
"turn_type": "recommendation"
```

以及：

```json
"drink_metadata": {
  "name": "...",
  "backstory": "...",
  "recipe": "..."
}
```
