# Changelog

后续每次改动都请在这里记录，方便队友同步。

## 2026-07-10

- 重写 `README.md`，按当前版本补全项目定位、Demo 架构、浏览器/平板/机器人交互链路、API、profile、饮品小票、部署、测试和协作规范。
- `emotender_backend.py` 新增用户 profile 体系：`/api/user/login`、`/api/user/logout`、`/api/user/profile`，并支持 `/api/text/analyze` 传入可选 `username`。
- 新增 `prompts/profile_summary_prompt.md`，用于 Logout 时把本次会话压缩进用户长期 profile。
- 合并队友的饮品故事体系：后端加入 `DRINK_MENU`，推荐模式会自动输出 `drink_metadata`，供牛皮纸小票展示英文名、故事、配方和色泽。
- 前端 `static/index.html` 合并六维风味图、牛皮纸小票、CRT 动画和登录/退出 UI，小票优先读取后端 `drink_metadata`。
- `scripts/deploy_to_asr_test.sh` 现在会同步复制 `prompts/profile_summary_prompt.md`。
- 新增 `tests/test_user_profiles.py`，覆盖登录、profile 注入、Logout 保存 summary、推荐模式小票元数据和闲聊模式无饮品元数据。
- 需要重启后端生效；如果部署到 `~/asr_test`，请重新运行部署脚本。

## 2026-07-08 (2)

- 新增 CRT 像素风表情系统前端页面 `static/index.html`，包含 6 种 SVG 面部动画（清醒/难过/焦虑/兴奋/疲惫/犹豫）。
- 前端仪表盘支持实时显示：情绪标签、复杂情绪描述、需求洞察、饮品配方模块、风味描述、颜色描述、酒保台词（打字机效果）。
- `emotender_backend.py` 的 `/` 路由改为从 `static/index.html` 读取文件，不再内联 HTML，方便独立维护前端。
- 前端通过 `data.control_json` 直连后端 `POST /api/voice/stop` 返回结果，自动驱动面部表情和仪表盘更新。
- 影响模块：`emotender_backend.py`（`index()` 改为读文件）、新增 `static/index.html`。
- 需要重启后端生效。

## 2026-07-08

- 新增 `bar_chat`、`recommendation`、`safety` 三类对话模式路由。
- 新增内存会话上下文：`conversation_history` 和 `conversation_summary`。
- LLM 每轮都会输出 `control_json`，用于驱动表情、动作和台词。
- `bar_chat` 和 `safety` 下允许不正式推荐饮品，`recipe_modules` 可以为空。
- `recommendation` 下仍要求 `recipe_modules` 非空，继续触发正式饮品推荐。
- `POST /api/reset` 现在会同步清空会话上下文。
- 新增外层返回字段 `robot_reply_text`：闲聊模式拼接 `bartender_line` 和 `feedback_prompt`，推荐模式只播放 `bartender_line`。

## 2026-07-05

- 初始发布 EmoTender Speech AI Control Backend。
- 包含浏览器 Start/Stop 录音入口、本地 FunASR 识别、LLM 中转站调用、结构化 JSON 校验和 fallback 控制结果。
- 包含 prompt 库 `prompts/drink_mapping.json` 和 VMware Ubuntu 部署脚本。
