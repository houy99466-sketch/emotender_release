# EmoTender Speech AI Control Backend

这是 EmoTender 当前阶段的正式可部署版本，用于完成：

1. 浏览器页面点击 Start 开始录音。
2. 点击 Stop 停止录音。
3. 本地 FunASR 把 `recording.wav` 转成文字。
4. 后端根据用户文本进入 `bar_chat`、`recommendation` 或 `safety`。
5. LLM 根据 prompt 库、会话上下文和当前模式输出结构化 JSON。
6. 后端校验 JSON，并返回给页面。
7. 如果 LLM 输出异常，后端返回内置 fallback 控制 JSON，保证流程不中断。

## 文件结构

```text
emotender_release/
  CHANGELOG.md
  PROMPT_EDITING.md
  emotender_backend.py
  requirements.txt
  .env.example
  README.md
  VMWARE_AI_DEPLOY_INSTRUCTIONS.md
  prompts/
    drink_mapping.json
  scripts/
    deploy_to_asr_test.sh
    start_backend.sh
```

## 协作要求

后续每次提交代码或 prompt 修改时，请同步更新：

```text
CHANGELOG.md
```

记录本次改了什么、影响哪个模块、是否需要重启后端或同步修改白名单。

如果只调整 prompt 库，请先阅读：

```text
PROMPT_EDITING.md
```

## 目标部署位置

在 VMware Ubuntu 中，把文件部署到：

```bash
~/asr_test
```

部署后应形成：

```text
~/asr_test/
  emotender_backend.py
  requirements.txt
  .env
  prompts/
    drink_mapping.json
  .venv/
```

## 环境变量

后端读取 `~/asr_test/.env` 中的这三个键：

```env
LLM_BASE_URL=https://填写你的中转站地址/v1
LLM_API_KEY=填写你的中转站_API_Key
LLM_MODEL=填写中转站实际支持的模型名
```

这不是 CC switch 的配置方式。这里是 Python 后端通过 OpenAI SDK 直接请求你的 OpenAI 兼容中转站。

## 一键部署

在 VMware Ubuntu 里进入共享目录中的发布包：

```bash
cd /mnt/hgfs/vmwareshare/emotender_release
```

如果这个路径不存在，先找发布包：

```bash
find /mnt /media -name emotender_release -type d 2>/dev/null
```

然后执行：

```bash
chmod +x scripts/deploy_to_asr_test.sh scripts/start_backend.sh
./scripts/deploy_to_asr_test.sh
```

部署脚本会：

1. 创建 `~/asr_test`。
2. 复制后端代码和 prompt 库。
3. 如果没有 `.env`，从 `.env.example` 创建。
4. 创建或复用 `.venv`。
5. 安装 torch、torchaudio 和 Python 依赖。
6. 检查 Python 语法和 prompt JSON 格式。

## 启动

确保 `.env` 已经填写真实值：

```bash
gedit ~/asr_test/.env
```

然后启动：

```bash
cd ~/asr_test
source .venv/bin/activate
uvicorn emotender_backend:app --host 0.0.0.0 --port 8000
```

也可以用脚本启动：

```bash
cd /mnt/hgfs/vmwareshare/emotender_release
./scripts/start_backend.sh
```

## 打开页面

在 VMware Ubuntu 浏览器打开：

```text
http://127.0.0.1:8000/
```

页面上只有三个主要按钮：

1. Start：开始录音。
2. Stop：停止录音并执行 ASR + LLM 分析。
3. Reset：重置当前状态。

`Reset` 会同时清空当前会话上下文。

## API

```text
GET  /api/status
POST /api/voice/start
POST /api/voice/stop
POST /api/reset
GET  /
```

`POST /api/voice/stop` 成功后返回：

```json
{
  "ok": true,
  "audio_path": "/home/sysu/asr_test/recording.wav",
  "user_text": "我有点难过，但是也有点焦虑，我想稳定下来。",
  "turn_type": "recommendation",
  "control_json": {
    "schema_version": "1.0",
    "turn_type": "recommendation",
    "user_text": "我有点难过，但是也有点焦虑，我想稳定下来。",
    "emotion_label": "难过和焦虑",
    "emotion_blend": [
      {"emotion": "难过", "weight": 0.7},
      {"emotion": "焦虑", "weight": 0.3}
    ],
    "complex_emotion": "用户同时有低落和紧张，需要稳定下来。",
    "need_summary": "需要一杯柔和、低刺激、稳定情绪的饮品。",
    "drink_name": "软着陆",
    "recipe_modules": ["soft_comfort", "blue_calm", "clear_balance"],
    "flavor_profile": "柔和、低酸、低刺激、有一点甜感",
    "color_profile": "浅蓝紫色或淡粉色",
    "face_state": "gentle",
    "bartender_line": "我先给你一杯柔和一点的，让节奏慢下来。",
    "action_sequence": "make_soft_comfort",
    "feedback_prompt": "喝完告诉我，它是让你稳定了一点，还是还需要更清爽。"
  },
  "conversation_state": {
    "summary": "第1轮：recommendation；用户情绪=难过和焦虑；需求=需要一杯柔和、低刺激、稳定情绪的饮品。",
    "history": [
      {
        "turn_type": "recommendation",
        "user_text": "我有点难过，但是也有点焦虑，我想稳定下来。",
        "emotion_label": "难过和焦虑",
        "need_summary": "需要一杯柔和、低刺激、稳定情绪的饮品。",
        "face_state": "gentle",
        "action_sequence": "make_soft_comfort",
        "bartender_line": "我先给你一杯柔和一点的，让节奏慢下来。",
        "drink_name": "软着陆",
        "recipe_modules": ["soft_comfort", "blue_calm", "clear_balance"]
      }
    ]
  },
  "used_fallback": false,
  "llm_error": null
}
```

## 对话模式和上下文

当前后端每轮都会输出 `control_json`，用于驱动机器人表情、动作和台词。

`turn_type` 有三种主要状态：

1. `bar_chat`：闲聊模式。记录顾客情绪，输出 `face_state`、`action_sequence` 和 `bartender_line`，但不正式推荐酒。
2. `recommendation`：推荐模式。输出饮品、配方模块、风味、颜色、表情、动作和台词。
3. `safety`：安全边界。不给酒精推荐，优先输出温和拒绝、无酒精处理和安全动作。

`bar_chat` 和 `safety` 下允许：

```json
"drink_name": "无正式推荐",
"recipe_modules": [],
"flavor_profile": "无正式推荐",
"color_profile": "无正式推荐"
```

`recommendation` 下 `recipe_modules` 仍然必须非空。

后端会在内存里维护当前会话：

```text
conversation_history
conversation_summary
```

LLM 每轮都会拿到会话摘要和最近几轮历史。后端重启或调用 `POST /api/reset` 后，上下文会清空。

## Prompt 库怎么改

主要修改：

```text
~/asr_test/prompts/drink_mapping.json
```

可以改这些部分：

1. `emotion_dimensions`：增加或调整情绪维度。
2. `blend_rules`：调整混合情绪规则，例如 70% 难过 + 30% 焦虑。
3. `hidden_drinks`：增加酒名、风味、颜色、配方模块、表情和动作。
4. `allowed_recipe_modules`：允许出现的配方模块名。
5. `allowed_face_states`：允许出现的表情状态。
6. `allowed_action_sequences`：允许出现的动作序列。

注意：如果在 prompt 库里新增了 `recipe_modules`、`face_state` 或 `action_sequence` 的新名字，也必须同步修改 `emotender_backend.py` 里的这三个白名单：

```python
ALLOWED_RECIPE_MODULES
ALLOWED_FACE_STATES
ALLOWED_ACTION_SEQUENCES
```

否则后端校验会拒绝 LLM 输出。

## 当前后端的容错机制

`emotender_backend.py` 中有：

```python
fallback_result(user_text: str) -> dict
```

如果 LLM 调用失败、输出不是合法 JSON、缺字段、字段类型错误、字段不在白名单里，后端会返回内置 fallback JSON：

```json
"drink_name": "冷启动"
```

同时返回：

```json
"used_fallback": true
```

以及：

```json
"llm_error": "具体错误信息"
```

ASR 失败不会走 fallback，因为没有用户文字时无法进入稳定中控逻辑。

## 常见问题

### 1. `arecord` 找不到

安装：

```bash
sudo apt update
sudo apt install -y alsa-utils
```

### 2. 录音设备不可用

查看设备：

```bash
arecord -l
```

当前后端使用：

```bash
arecord -D default -f S16_LE -r 16000 -c 1 recording.wav
```

### 3. `.env` 没填

编辑：

```bash
gedit ~/asr_test/.env
```

必须填写真实的：

```env
LLM_BASE_URL
LLM_API_KEY
LLM_MODEL
```

### 4. 网页打不开

确认后端正在运行：

```bash
curl http://127.0.0.1:8000/api/status
```

### 5. LLM 结果一直 fallback

看页面返回里的：

```json
"llm_error"
```

常见原因：

1. `.env` 中转站地址不对。
2. `LLM_MODEL` 名字不被中转站支持。
3. 中转站没有 OpenAI chat completions 兼容接口。
4. LLM 输出了不符合字段要求的 JSON。
