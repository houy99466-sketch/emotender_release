# EmoTender Windows 后端与平板 APK 使用指南

本指南用于当前比赛 Demo 的现场测试。默认项目目录是：

```powershell
E:\vmwareshare\emotender_release
```

## 1. 启动 Windows 后端

打开 PowerShell：

```powershell
Set-Location 'E:\vmwareshare\emotender_release'
```

如果是首次运行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

检查 `.env`：

```text
LLM_BASE_URL=https://www.cctq.ai/v1
LLM_API_KEY=你的中转站 API Key
LLM_MODEL=gpt-5.5
```

如果没有 `.env`：

```powershell
Copy-Item .env.example .env
notepad .env
```

启动：

```powershell
.\.venv\Scripts\python.exe -m uvicorn emotender_backend:app --host 0.0.0.0 --port 8000
```

看到类似下面内容代表后端已启动：

```text
Uvicorn running on http://0.0.0.0:8000
```

不要关闭这个 PowerShell 窗口。

## 2. 本机测试后端

另开一个 PowerShell：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/status
```

测试正式推荐接口。注意：PowerShell 发送中文时要用 UTF-8 字节，避免中文变成问号。

```powershell
$body = @{user_text='推荐一杯清爽一点的。'; username='demo'} | ConvertTo-Json -Compress
$bytes = [System.Text.Encoding]::UTF8.GetBytes($body)
Invoke-RestMethod `
  -Uri 'http://127.0.0.1:8000/api/text/analyze' `
  -Method POST `
  -ContentType 'application/json; charset=utf-8' `
  -Body $bytes
```

预期结果里能看到：

```text
turn_type: recommendation
control_json.drink_metadata
```

测试闲聊转推荐：

```powershell
$body = @{user_text='我今天有点累。'; username='demo'} | ConvertTo-Json -Compress
$bytes = [System.Text.Encoding]::UTF8.GetBytes($body)
Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/text/analyze' -Method POST -ContentType 'application/json; charset=utf-8' -Body $bytes

$body = @{user_text='可以，你看着安排。'; username='demo'} | ConvertTo-Json -Compress
$bytes = [System.Text.Encoding]::UTF8.GetBytes($body)
Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/text/analyze' -Method POST -ContentType 'application/json; charset=utf-8' -Body $bytes
```

第二轮预期进入：

```text
turn_type: recommendation
```

## 3. 查询给平板用的 Windows IP

```powershell
ipconfig
```

找到当前正在使用的网络，例如 WLAN，记录 `IPv4 地址`。

示例：

```text
IPv4 地址 . . . . . . . . . . . . : 192.168.43.252
```

那么平板 APK 里填写：

```text
http://192.168.43.252:8000
```

不要填写 VMware 的 `VMnet1` 或 `VMnet8` 地址。

## 4. 安装和使用 APK

APK 文件在仓库中：

```text
release/EmoTender-latest.apk
```

操作：

1. 安装 APK。
2. 确保平板和 Windows 电脑在同一个 Wi-Fi 或同一个手机热点下。
3. 打开 APK。
4. 启动弹窗中输入 Windows 后端地址，例如：

```text
http://192.168.43.252:8000
```

5. 点 `Load`。
6. 进入页面后点 `Start`。
7. Android 系统语音识别完成后，APK 会把文字交给网页。
8. 网页向 Windows 后端发送 `/api/text/analyze` 请求。
9. 后端返回 `control_json`，页面更新表情、回复、推荐结果。

长按 APK 页面可以重新打开后端地址配置弹窗。

## 5. 页面显示规则

闲聊模式：

- 显示表情。
- 显示机器人回复。
- 不显示六维风味图。
- 不显示牛皮纸小票。

正式推荐模式：

- 显示推荐饮品。
- 显示与当前会话具体经历相关的推荐理由。
- 显示本轮情绪占比饼图及每种情绪的来源说明。
- 显示六维风味图。
- 显示牛皮纸小票。
- 小票内容来自后端 `drink_metadata`。
- 页面底部显示 `保存为图片`。

在 APK 1.2.0 中点 `保存为图片` 后，长图会保存到：

```text
Pictures/EmoTender
```

长图内容顺序为：表情、最终回复、推荐理由、情绪占比、六维风味图、牛皮纸小票。Start、Send、Reset 和确认按钮不会出现在导出图片中。

## 6. 登录与长期 profile

左上角输入用户名后点 `Login`。

登录后：

- 每轮 `/api/text/analyze` 会带上 `username`。
- 后端会读取对应 profile，并把压缩后的长期偏好注入 prompt。
- 长期 profile 只影响口味、避忌、交流风格和历史饮品参考，不参与本轮情绪占比判断。

退出时点 `Logout`。

Logout 会把本次会话压缩保存到：

```text
data/profiles/
```

这个目录是本地隐私数据，不上传 GitHub。

## 7. 常见问题

### 平板打不开页面

按顺序检查：

1. Windows 后端 PowerShell 是否还在运行。
2. 后端启动命令是否包含 `--host 0.0.0.0`。
3. 平板和 Windows 是否在同一个网络。
4. APK 中填写的是否是当前 Windows 的 IPv4。
5. Windows 防火墙是否拦截 8000 端口。

### 正式推荐后没有六维图和小票

检查后端返回是否为：

```json
"turn_type": "recommendation"
```

并且 `control_json.drink_metadata` 不为空。

### PowerShell 中文变成问号

使用本指南中的 UTF-8 字节请求写法，不要直接把中文 JSON 字面量传给 `-Body`。

### 想重新填写后端 IP

长按 APK 页面，重新输入后端地址。
