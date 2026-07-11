# Changelog

每次修改代码、prompt、前端、APK 或使用方式后，请在这里记录，方便队友同步。

## 2026-07-11

### 个性化推荐结果与长图导出

- 新增 `recommendation_reason`，正式推荐时结合当前会话中的具体经历说明为什么推荐这款酒。
- `emotion_blend` 每项新增 `source`，用于说明该情绪在本次会话中的来源。
- 本轮情绪判断 Prompt 不再注入历史 `emotion_patterns` 和历史会话摘要；长期 profile 只提供口味、避忌、交流风格和历史饮品参考。
- 正式推荐页面新增带来源引线的情绪占比饼图，排列在六维风味图上方。
- 新增 PNG 长图导出，内容覆盖表情、最终回复、推荐理由、情绪饼图、六维图和牛皮纸小票。
- 本地引入 `html2canvas 1.4.1`，现场不依赖 CDN。
- APK 升级为 `1.2.0`（`versionCode 103`），新增保存图片到 `Pictures/EmoTender` 的 Android bridge。
- 新增后端回归测试，覆盖情绪来源、推荐理由和历史情绪隔离。

### 菜单单一来源

- 删除 `prompts/drink_mapping.json` 中重复的 `hidden_drinks`，饮品菜单统一以 `emotender_backend.py` 的 `DRINK_MENU` 为唯一来源。
- 更新 LLM Prompt 描述，不再把 Prompt 库描述为包含隐藏饮品。
- 正式推荐时校验 `drink_name` 必须存在于 `DRINK_MENU`；菜单外名称会进入现有 fallback，并返回“冷启动”的完整小票元数据。
- 新增回归测试，覆盖菜单外饮品拒绝、fallback 元数据以及 Prompt 库不重复保存饮品菜单。

## 2026-07-10

### 本次提交

- 修复闲聊转正式推荐的后端路由逻辑。
  - `route_turn_type()` 现在只提供初步模式提示。
  - LLM 输出的 `turn_type` 会被保留，不再被关键词路由强行覆盖。
  - 如果上一轮机器人问过是否正式推荐，用户本轮说“好 / 可以 / 你看着安排”等确认语，会进入 `recommendation`。
  - 安全场景仍会强制保持 `safety`。

- 更新 LLM prompt 约束。
  - 明确 `turn_type` 只能是 `bar_chat`、`recommendation`、`safety`。
  - 明确用户要求推荐、调酒、来一杯、让机器人做主时必须进入正式推荐。
  - 明确继续倾诉或闲聊时保持 `bar_chat`。

- 更新前端 `static/index.html`。
  - 左上角放用户名、`Login`、`Logout`。
  - 右上角放圆形 `?` 说明入口。
  - 主操作区保留 `Start`、`Send`、`Reset`。
  - 支持 Android WebView 桥接：`EmoTenderAndroid.startSpeech()` 和 `submitRecognizedText(text)`。
  - 闲聊模式只显示表情和回复。
  - 正式推荐后才显示六维风味图和牛皮纸小票。

- 新增和更新测试。
  - 覆盖“上一轮问是否正式推荐，下一轮用户确认后切到 recommendation”。
  - 覆盖“LLM 可以把关键词路由的初步提示改成最终 recommendation”。

- 上传平板 APK 成品。
  - 文件位置：`release/EmoTender-latest.apk`
  - APK 使用 Android 系统语音识别。
  - APK 启动时要求填写 Windows 后端地址，不再默认使用固定 IP。
  - 长按页面可重新配置后端地址。

- 重写项目说明。
  - `README.md` 改为当前 Windows 后端 + 平板 APK 链路。
  - 新增 `docs/Windows平板使用指南.md`，方便现场测试复用。
  - 说明 PowerShell 中文请求需要使用 UTF-8 字节写法，避免中文变成问号。

### 之前同日改动

- 新增用户 profile 体系：`/api/user/login`、`/api/user/logout`、`/api/user/profile`。
- `/api/text/analyze` 支持可选 `username`。
- 新增 `prompts/profile_summary_prompt.md`，Logout 时把本次会话压缩写入长期 profile。
- 后端加入 `DRINK_MENU`，正式推荐时自动输出 `drink_metadata`，用于牛皮纸小票展示英文名、故事、配方和颜色。
- 前端合并六维风味图、牛皮纸小票、CRT 表情动画和登录/退出 UI。
- `scripts/deploy_to_asr_test.sh` 同步复制 `prompts/profile_summary_prompt.md`。
- 新增 `tests/test_user_profiles.py`，覆盖登录、profile 注入、Logout 保存 summary、推荐模式小票元数据和闲聊模式无饮品元数据。

## 2026-07-08

- 新增 `bar_chat`、`recommendation`、`safety` 三类对话模式。
- 新增内存会话上下文：`conversation_history` 和 `conversation_summary`。
- LLM 每轮都输出 `control_json`，用于驱动表情、动作和台词。
- `bar_chat` 和 `safety` 允许不正式推荐饮品。
- `recommendation` 要求 `recipe_modules` 非空。
- `POST /api/reset` 会同步清空当前内存会话。
- 新增外层返回字段 `robot_reply_text`：
  - 闲聊模式拼接 `bartender_line` 和 `feedback_prompt`。
  - 推荐模式只播 `bartender_line`。
- 新增 CRT 像素风表情系统前端页面 `static/index.html`。
- 后端 `/` 路由改为读取 `static/index.html`。

## 2026-07-05

- 初始发布 EmoTender Speech AI Control Backend。
- 包含浏览器 Start/Stop 录音入口、本地 FunASR 识别、LLM 中转站调用、结构化 JSON 校验和 fallback 控制结果。
- 包含 prompt 库 `prompts/drink_mapping.json` 和 VMware Ubuntu 部署脚本。
