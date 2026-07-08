# Changelog

后续每次改动都请在这里记录，方便队友同步。

## 2026-07-08

- 新增 `bar_chat`、`recommendation`、`safety` 三类对话模式路由。
- 新增内存会话上下文：`conversation_history` 和 `conversation_summary`。
- LLM 每轮都会输出 `control_json`，用于驱动表情、动作和台词。
- `bar_chat` 和 `safety` 下允许不正式推荐饮品，`recipe_modules` 可以为空。
- `recommendation` 下仍要求 `recipe_modules` 非空，继续触发正式饮品推荐。
- `POST /api/reset` 现在会同步清空会话上下文。

## 2026-07-05

- 初始发布 EmoTender Speech AI Control Backend。
- 包含浏览器 Start/Stop 录音入口、本地 FunASR 识别、LLM 中转站调用、结构化 JSON 校验和 fallback 控制结果。
- 包含 prompt 库 `prompts/drink_mapping.json` 和 VMware Ubuntu 部署脚本。
