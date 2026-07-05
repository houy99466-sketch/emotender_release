# 发给 VMware Ubuntu 里的 AI 的部署指令

请在 VMware Ubuntu 中部署 EmoTender Speech AI Control Backend。不要改业务逻辑，按下面步骤执行并把每一步结果告诉我。

## 目标

把共享文件夹中的发布包：

```text
emotender_release
```

部署到：

```bash
~/asr_test
```

并启动 FastAPI 后端。

## 1. 找到共享目录

优先检查：

```bash
ls /mnt/hgfs/vmwareshare/emotender_release
```

如果不存在，执行：

```bash
find /mnt /media -name emotender_release -type d 2>/dev/null
```

找到后进入该目录。下面命令里的 `/mnt/hgfs/vmwareshare/emotender_release` 如果不是实际路径，请替换成你找到的真实路径。

```bash
cd /mnt/hgfs/vmwareshare/emotender_release
```

## 2. 检查发布包文件

执行：

```bash
find . -maxdepth 3 -type f | sort
```

必须至少看到：

```text
./.env.example
./README.md
./VMWARE_AI_DEPLOY_INSTRUCTIONS.md
./emotender_backend.py
./prompts/drink_mapping.json
./requirements.txt
./scripts/deploy_to_asr_test.sh
./scripts/start_backend.sh
```

## 3. 运行部署脚本

执行：

```bash
chmod +x scripts/deploy_to_asr_test.sh scripts/start_backend.sh
./scripts/deploy_to_asr_test.sh
```

如果提示缺少 `python3-venv`，执行：

```bash
sudo apt update
sudo apt install -y python3-venv
./scripts/deploy_to_asr_test.sh
```

如果提示 `arecord` 不存在，执行：

```bash
sudo apt update
sudo apt install -y alsa-utils
```

## 4. 填写 LLM 中转站配置

打开：

```bash
gedit ~/asr_test/.env
```

填写真实值：

```env
LLM_BASE_URL=https://中转站真实地址/v1
LLM_API_KEY=中转站真实_API_Key
LLM_MODEL=中转站实际支持的模型名
```

注意：这是 Python 后端直接调用 OpenAI 兼容中转站，不是 CC switch，不要修改 Codex 配置文件。

## 5. 启动后端

执行：

```bash
cd ~/asr_test
source .venv/bin/activate
uvicorn emotender_backend:app --host 0.0.0.0 --port 8000
```

保持这个终端不要关闭。

## 6. 打开页面测试

在 VMware Ubuntu 浏览器打开：

```text
http://127.0.0.1:8000/
```

点击：

1. Start
2. 对麦克风说：我有点难过，但是也有点焦虑，我想稳定下来。
3. Stop

页面应返回 JSON，其中应包含：

```json
"control_json"
```

以及：

```json
"emotion_blend"
```

如果看到：

```json
"used_fallback": true
```

请把同一个 JSON 里的：

```json
"llm_error"
```

完整发给我。

## 7. 后续修改 prompt 库

如果要改情绪到酒的映射，改：

```bash
gedit ~/asr_test/prompts/drink_mapping.json
```

改完后检查 JSON：

```bash
cd ~/asr_test
python -m json.tool prompts/drink_mapping.json >/dev/null
```

然后重启后端。

如果新增了新的 `recipe_modules`、`face_state` 或 `action_sequence` 名字，也要同步修改：

```bash
gedit ~/asr_test/emotender_backend.py
```

里面的：

```python
ALLOWED_RECIPE_MODULES
ALLOWED_FACE_STATES
ALLOWED_ACTION_SEQUENCES
```

否则后端会拒绝不在白名单里的 LLM 输出。
