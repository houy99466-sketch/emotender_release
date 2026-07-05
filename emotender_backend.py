import json
import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from funasr import AutoModel
from openai import OpenAI

load_dotenv()

app = FastAPI(title="EmoTender Backend")

BASE_DIR = Path(__file__).resolve().parent
AUDIO_PATH = BASE_DIR / "recording.wav"
PROMPT_LIBRARY_PATH = BASE_DIR / "prompts" / "drink_mapping.json"
recording_process: Optional[subprocess.Popen] = None
last_result: Optional[dict] = None

ASR_MODEL = AutoModel(
    model="paraformer-zh",
    vad_model="fsmn-vad",
    punc_model="ct-punc-c",
)

client = OpenAI(
    api_key=os.environ["LLM_API_KEY"],
    base_url=os.environ["LLM_BASE_URL"],
)

MODEL = os.environ["LLM_MODEL"]

ALLOWED_ACTION_SEQUENCES = {
    "make_cold_start",
    "make_soft_comfort",
    "make_spark_restart",
    "serve_only",
    "gesture_thinking",
    "gesture_thumb_up",
    "gesture_shrug",
}

ALLOWED_FACE_STATES = {
    "idle",
    "listening",
    "thinking",
    "focused",
    "happy",
    "gentle",
    "awkward",
    "mysterious",
}

ALLOWED_RECIPE_MODULES = {
    "blue_calm",
    "clear_balance",
    "spark_restart",
    "soft_comfort",
    "bright_bubble",
    "bitter_focus",
}


def transcribe_audio(wav_path: Path) -> str:
    result = ASR_MODEL.generate(input=str(wav_path))
    text = result[0].get("text", "").strip()
    if not text:
        raise RuntimeError("ASR returned empty text")
    return text


def extract_json(content: str) -> dict:
    content = content.strip()

    if content.startswith("```json"):
        content = content.removeprefix("```json").strip()
    if content.startswith("```"):
        content = content.removeprefix("```").strip()
    if content.endswith("```"):
        content = content.removesuffix("```").strip()

    return json.loads(content)


def analyze_text(user_text: str) -> dict:
    with open(PROMPT_LIBRARY_PATH, "r", encoding="utf-8") as f:
        prompt_library = json.load(f)
    prompt = f"""
你是 EmoTender 情绪酒保的 AI 中控分析模块。

你必须只输出一个合法 JSON 对象。
不要输出 Markdown。
不要输出解释。
不要输出代码块。
不要在 JSON 前后添加任何文字。

用户原话：
{user_text}

这是 EmoTender 的 prompt 库，包含情绪维度、混合规则、隐藏饮品、配方模块、表情状态和动作序列：
{json.dumps(prompt_library, ensure_ascii=False, indent=2)}

必须输出这些字段：
schema_version, turn_type, user_text, emotion_label, emotion_blend, complex_emotion,
need_summary, drink_name, recipe_modules, flavor_profile, color_profile,
face_state, bartender_line, action_sequence, feedback_prompt。

字段类型要求：
- schema_version 必须是字符串，例如 "1.0"
- turn_type 必须是字符串，例如 "initial_order"
- user_text 必须是字符串
- emotion_label 必须是字符串
- complex_emotion 必须是字符串
- need_summary 必须是字符串
- drink_name 必须是字符串
- recipe_modules 必须是字符串数组，例如 ["blue_calm", "clear_balance"]
- flavor_profile 必须是字符串
- color_profile 必须是字符串
- face_state 必须是单个字符串，例如 "focused"，不能是数组
- bartender_line 必须是字符串
- action_sequence 必须是单个字符串，例如 "make_cold_start"，不能是数组
- feedback_prompt 必须是字符串
- emotion_blend 必须是数组，每一项包含 emotion 和 weight，例如 [{{"emotion": "难过", "weight": 0.7}}, {{"emotion": "焦虑", "weight": 0.3}}]
- emotion_blend 的 weight 总和必须接近 1.0
"""

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": "你只输出合法 JSON 对象。"},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
    )

    content = response.choices[0].message.content
    return extract_json(content)


def normalize_result(data: dict) -> dict:
    if isinstance(data.get("action_sequence"), list):
        if len(data["action_sequence"]) == 1:
            data["action_sequence"] = data["action_sequence"][0]
        else:
            raise TypeError(f"action_sequence must be a string, got list: {data['action_sequence']}")

    if isinstance(data.get("face_state"), list):
        if len(data["face_state"]) == 1:
            data["face_state"] = data["face_state"][0]
        else:
            raise TypeError(f"face_state must be a string, got list: {data['face_state']}")

    return data


def validate_result(data: dict) -> None:
    required_fields = [
        "schema_version",
        "turn_type",
        "user_text",
        "emotion_label",
        "complex_emotion",
        "need_summary",
        "drink_name",
        "recipe_modules",
        "flavor_profile",
        "color_profile",
        "face_state",
        "bartender_line",
        "action_sequence",
        "feedback_prompt",
        "emotion_blend",
    ]

    for field in required_fields:
        if field not in data:
            raise ValueError(f"Missing field: {field}")

    if not isinstance(data["emotion_blend"], list):
        raise TypeError(f"emotion_blend must be a list, got {type(data['emotion_blend']).__name__}: {data['emotion_blend']}")

    if not data["emotion_blend"]:
        raise ValueError("emotion_blend must not be empty")

    total_weight = 0.0
    for item in data["emotion_blend"]:
        if not isinstance(item, dict):
            raise TypeError(f"emotion_blend item must be an object, got {type(item).__name__}: {item}")

        if "emotion" not in item:
            raise ValueError(f"emotion_blend item missing emotion: {item}")

        if "weight" not in item:
            raise ValueError(f"emotion_blend item missing weight: {item}")

        if not isinstance(item["emotion"], str):
            raise TypeError(f"emotion_blend emotion must be a string: {item}")

        if not isinstance(item["weight"], (int, float)):
            raise TypeError(f"emotion_blend weight must be a number: {item}")

        if item["weight"] < 0 or item["weight"] > 1:
            raise ValueError(f"emotion_blend weight must be between 0 and 1: {item}")

        total_weight += item["weight"]

    if abs(total_weight - 1.0) > 0.05:
        raise ValueError(f"emotion_blend weights must sum to 1.0, got {total_weight}")

    string_fields = [
        "schema_version",
        "turn_type",
        "user_text",
        "emotion_label",
        "complex_emotion",
        "need_summary",
        "drink_name",
        "flavor_profile",
        "color_profile",
        "face_state",
        "bartender_line",
        "action_sequence",
        "feedback_prompt",
    ]

    for field in string_fields:
        if not isinstance(data[field], str):
            raise TypeError(f"{field} must be a string, got {type(data[field]).__name__}: {data[field]}")
        if not data[field].strip():
            raise ValueError(f"{field} must not be empty")

    if not isinstance(data["recipe_modules"], list):
        raise TypeError(f"recipe_modules must be a list, got {type(data['recipe_modules']).__name__}: {data['recipe_modules']}")

    if not data["recipe_modules"]:
        raise ValueError("recipe_modules must not be empty")

    for module in data["recipe_modules"]:
        if not isinstance(module, str):
            raise TypeError(f"recipe_modules item must be a string, got {type(module).__name__}: {module}")
        if module not in ALLOWED_RECIPE_MODULES:
            raise ValueError(f"Unknown recipe module: {module}")

    if data["face_state"] not in ALLOWED_FACE_STATES:
        raise ValueError(f"Unknown face_state: {data['face_state']}")

    if data["action_sequence"] not in ALLOWED_ACTION_SEQUENCES:
        raise ValueError(f"Unknown action_sequence: {data['action_sequence']}")


def fallback_result(user_text: str) -> dict:
    return {
        "schema_version": "1.0",
        "turn_type": "initial_order",
        "user_text": user_text,
        "emotion_label": "清醒",
        "emotion_blend": [
            {
                "emotion": "清醒",
                "weight": 1.0,
            }
        ],
        "complex_emotion": "无法稳定解析用户情绪时，先进入清醒、克制、低风险的默认状态。",
        "need_summary": "需要一杯低甜、清爽、稳定注意力的饮品。",
        "drink_name": "冷启动",
        "recipe_modules": [
            "clear_balance",
            "bitter_focus",
            "spark_restart",
        ],
        "flavor_profile": "清爽、微苦、低甜、带轻微气泡感",
        "color_profile": "透明偏冷调，带一点淡青色",
        "face_state": "focused",
        "bartender_line": "我先给你一杯清醒、低甜、微苦的冷启动，等你状态稳定一点再细调。",
        "action_sequence": "make_cold_start",
        "feedback_prompt": "喝完告诉我，它是刚好让你清醒，还是需要再柔和一点。",
    }


def run_pipeline() -> dict:
    user_text = transcribe_audio(AUDIO_PATH)
    used_fallback = False
    llm_error = None

    try:
        result = analyze_text(user_text)
        result = normalize_result(result)
        validate_result(result)
    except Exception as exc:
        used_fallback = True
        llm_error = str(exc)
        result = fallback_result(user_text)
        validate_result(result)

    return {
        "ok": True,
        "audio_path": str(AUDIO_PATH),
        "user_text": user_text,
        "control_json": result,
        "used_fallback": used_fallback,
        "llm_error": llm_error,
    }


@app.get("/api/status")
def status():
    return {
        "recording": recording_process is not None,
        "audio_path": str(AUDIO_PATH),
        "last_result": last_result,
    }


@app.post("/api/voice/start")
def start_recording():
    global recording_process

    if recording_process is not None:
        raise HTTPException(status_code=400, detail="Recording is already running")

    if AUDIO_PATH.exists():
        AUDIO_PATH.unlink()

    command = [
        "arecord",
        "-D",
        "default",
        "-f",
        "S16_LE",
        "-r",
        "16000",
        "-c",
        "1",
        str(AUDIO_PATH),
    ]

    recording_process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        preexec_fn=os.setsid,
    )

    time.sleep(0.2)

    if recording_process.poll() is not None:
        _, stderr = recording_process.communicate()
        recording_process = None
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start recording: {stderr.decode(errors='ignore')}",
        )

    return {
        "ok": True,
        "state": "listening",
        "message": "Recording started",
    }


@app.post("/api/voice/stop")
def stop_recording():
    global recording_process
    global last_result

    if recording_process is None:
        raise HTTPException(status_code=400, detail="Recording is not running")

    os.killpg(os.getpgid(recording_process.pid), signal.SIGINT)
    _, stderr = recording_process.communicate(timeout=5)
    recording_process = None

    if not AUDIO_PATH.exists():
        raise HTTPException(
            status_code=500,
            detail=f"Recording file was not created: {stderr.decode(errors='ignore')}",
        )

    if AUDIO_PATH.stat().st_size == 0:
        raise HTTPException(status_code=500, detail="Recording file is empty")

    try:
        last_result = run_pipeline()
        return last_result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/reset")
def reset():
    global recording_process
    global last_result

    if recording_process is not None:
        os.killpg(os.getpgid(recording_process.pid), signal.SIGINT)
        recording_process.communicate(timeout=5)
        recording_process = None

    last_result = None

    return {
        "ok": True,
        "message": "Reset complete",
    }


@app.get("/", response_class=HTMLResponse)
def index():
    return """
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>EmoTender Voice Test</title>
  <style>
    body {
      font-family: Arial, sans-serif;
      margin: 40px;
      background: #f6f7f9;
      color: #1f2933;
    }
    h1 {
      margin-bottom: 24px;
    }
    .panel {
      background: white;
      border: 1px solid #d9dee7;
      border-radius: 8px;
      padding: 24px;
      max-width: 900px;
    }
    button {
      font-size: 18px;
      padding: 12px 22px;
      margin-right: 12px;
      border: none;
      border-radius: 6px;
      cursor: pointer;
    }
    #startBtn {
      background: #2563eb;
      color: white;
    }
    #stopBtn {
      background: #dc2626;
      color: white;
    }
    #resetBtn {
      background: #4b5563;
      color: white;
    }
    .status {
      margin-top: 24px;
      padding: 16px;
      background: #eef2ff;
      border-left: 5px solid #2563eb;
      font-size: 20px;
      font-weight: bold;
    }
    pre {
      margin-top: 24px;
      padding: 16px;
      background: #111827;
      color: #d1fae5;
      border-radius: 8px;
      overflow-x: auto;
      min-height: 220px;
      white-space: pre-wrap;
    }
  </style>
</head>
<body>
  <div class="panel">
    <h1>EmoTender Voice Test</h1>

    <button id="startBtn" onclick="startRecording()">Start</button>
    <button id="stopBtn" onclick="stopRecording()">Stop</button>
    <button id="resetBtn" onclick="resetSystem()">Reset</button>

    <div class="status" id="statusBox">状态：空闲</div>

    <pre id="resultBox">结果会显示在这里。</pre>
  </div>

  <script>
    const statusBox = document.getElementById("statusBox");
    const resultBox = document.getElementById("resultBox");

    function setStatus(text) {
      statusBox.textContent = "状态：" + text;
    }

    function setResult(data) {
      resultBox.textContent = JSON.stringify(data, null, 2);
    }

    async function callApi(path) {
      const response = await fetch(path, { method: "POST" });
      const data = await response.json();

      if (!response.ok) {
        throw data;
      }

      return data;
    }

    async function startRecording() {
      try {
        setStatus("正在输入，请开始说话");
        resultBox.textContent = "录音中...";
        const data = await callApi("/api/voice/start");
        setResult(data);
        setStatus("正在输入，请说话，说完后点击 Stop");
      } catch (err) {
        setStatus("开始录音失败");
        setResult(err);
      }
    }

    async function stopRecording() {
      try {
        setStatus("正在停止录音并分析，请稍等");
        resultBox.textContent = "正在进行语音转文字和 AI 分析...";
        const data = await callApi("/api/voice/stop");
        setResult(data);
        setStatus("完成");
      } catch (err) {
        setStatus("停止或分析失败");
        setResult(err);
      }
    }

    async function resetSystem() {
      try {
        setStatus("正在重置");
        const data = await callApi("/api/reset");
        setResult(data);
        setStatus("空闲");
      } catch (err) {
        setStatus("重置失败");
        setResult(err);
      }
    }
  </script>
</body>
</html>
"""
