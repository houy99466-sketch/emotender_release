# Prompt 库修改说明

主要修改文件：

```text
prompts/drink_mapping.json
```

可以优先修改：

1. `emotion_dimensions`：情绪维度描述，例如高兴、焦虑、疲惫、难过分别代表什么。
2. `blend_rules`：混合情绪规则，例如 70% 高兴 + 30% 焦虑时，饮品应该更提神还是更稳定。
3. `allowed_recipe_modules`：LLM 允许输出的配方模块 ID。
4. `allowed_face_states`：LLM 允许输出的表情状态 ID。
5. `allowed_action_sequences`：LLM 允许输出的动作序列 ID。
6. `description` 和 `rule` 这类情绪、规则文案。

饮品名称、适配情绪、配方模块、风味描述、颜色、小票故事和实际配方统一维护在：

```text
emotender_backend.py
```

对应常量：

```python
DRINK_MENU
```

不要在 `drink_mapping.json` 中再建立第二份饮品菜单。正式推荐的 `drink_name` 必须存在于 `DRINK_MENU`，否则后端会进入 fallback。

如果只改文案、描述、规则文字，不新增新的英文 ID，通常不需要改代码。

不要随便新增这些字段里的英文 ID：

```text
recipe_modules
face_state
action_sequence
```

如果必须新增，要同步修改 `emotender_backend.py` 里的三个白名单：

```python
ALLOWED_RECIPE_MODULES
ALLOWED_FACE_STATES
ALLOWED_ACTION_SEQUENCES
```

否则后端会认为 LLM 输出了未知动作或未知模块，然后进入 fallback。

改完 `drink_mapping.json` 后，先检查 JSON 格式：

```bash
python -m json.tool prompts/drink_mapping.json >/dev/null
```

没有报错再重启后端测试。
