import json
import logging
import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Optional

# Structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("emotender")

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
conversation_history: list[dict] = []
conversation_summary = ""
emotion_history: list[str] = []  # Track emotion trend across turns
MAX_EMOTION_HISTORY = 5

MAX_HISTORY_ITEMS = 8
MAX_SUMMARY_CHARS = 1200
NO_FORMAL_DRINK_NAME = "无正式推荐"

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

RECOMMENDATION_TRIGGERS = (
    "推荐",
    "调一杯",
    "来一杯",
    "喝什么",
    "适合喝",
    "做一杯",
    "按你说的",
    "你做主",
)

SAFETY_TRIGGERS = (
    "未成年",
    "喝醉",
    "开车",
    "酒驾",
    "吃药",
    "失眠怎么治",
    "抑郁诊断",
    "自杀",
    "伤害别人",
)

CHAT_ONLY_TURN_TYPES = {
    "bar_chat",
    "safety",
}


def route_turn_type(user_text: str) -> str:
    text = user_text.strip()

    if any(trigger in text for trigger in SAFETY_TRIGGERS):
        return "safety"

    if any(trigger in text for trigger in RECOMMENDATION_TRIGGERS):
        return "recommendation"

    return "bar_chat"


def get_recent_history() -> list[dict]:
    return conversation_history[-MAX_HISTORY_ITEMS:]


def get_conversation_state() -> dict:
    return {
        "summary": conversation_summary,
        "history": list(conversation_history),
    }


def reset_conversation_state() -> None:
    global conversation_summary, emotion_history
    conversation_history.clear()
    conversation_summary = ""
    emotion_history.clear()
    logger.info("会话状态已重置")


def update_conversation_state(data: dict) -> None:
    global conversation_summary

    item = {
        "turn_type": data["turn_type"],
        "user_text": data["user_text"],
        "emotion_label": data["emotion_label"],
        "need_summary": data["need_summary"],
        "face_state": data["face_state"],
        "action_sequence": data["action_sequence"],
        "bartender_line": data["bartender_line"],
    }

    if data["turn_type"] == "recommendation":
        item["drink_name"] = data["drink_name"]
        item["recipe_modules"] = data["recipe_modules"]

    conversation_history.append(item)
    emotion_history.append(data["emotion_label"])
    if len(emotion_history) > MAX_EMOTION_HISTORY:
        emotion_history.pop(0)

    if len(conversation_history) > MAX_HISTORY_ITEMS:
        del conversation_history[:-MAX_HISTORY_ITEMS]

    summary_piece = (
        f"第{len(conversation_history)}轮："
        f"{data['turn_type']}；"
        f"用户情绪={data['emotion_label']}；"
        f"需求={data['need_summary']}"
    )
    conversation_summary = (
        f"{conversation_summary}\n{summary_piece}".strip()
        if conversation_summary
        else summary_piece
    )

    if len(conversation_summary) > MAX_SUMMARY_CHARS:
        conversation_summary = conversation_summary[-MAX_SUMMARY_CHARS:]


def transcribe_audio(wav_path: Path) -> str:
    logger.info(f"开始语音识别: {wav_path}")
    result = ASR_MODEL.generate(input=str(wav_path))
    text = result[0].get("text", "").strip()
    if not text or len(text) < 2:
        logger.warning(f"静默或过短语音: '{text}'")
        raise RuntimeError("silence_detected")
    logger.info(f"识别结果: {text}")
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


def analyze_text(user_text: str, turn_type: str) -> dict:
    with open(PROMPT_LIBRARY_PATH, "r", encoding="utf-8") as f:
        prompt_library = json.load(f)
    recent_history = get_recent_history()

    # Build emotion trend
    emotion_trend = ""
    if len(emotion_history) >= 2:
        trend_labels = emotion_history[-3:] if len(emotion_history) >= 3 else emotion_history
        emotion_trend = f"\n用户情绪变化趋势（最近{len(trend_labels)}轮）：{' → '.join(trend_labels)}。请根据趋势判断用户情绪走向，据此调整你的回应。"

    prompt = f"""
你是 EmoTender 情绪酒保的 AI 中控分析模块。
你的角色是老柯 / Alex Cole，38岁，12年调酒师。
你的信念是：酒是情绪的缓冲剂，不是解决方案。
你的表达必须低沉、松弛、直球、不说废话。

你必须只输出一个合法 JSON 对象。
不要输出 Markdown。
不要输出解释。
不要输出代码块。
不要在 JSON 前后添加任何文字。

本轮模式：
{turn_type}

用户原话：
{user_text}

会话摘要：
{conversation_summary or "暂无"}
{emotion_trend}

最近对话历史：
{json.dumps(recent_history, ensure_ascii=False, indent=2)}

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

模式规则：
- 如果 turn_type 是 "bar_chat"，这一轮是闲聊。你仍然必须输出完整 JSON，用于驱动机器人表情、动作和台词，但不要正式推荐饮品。
- 如果 turn_type 是 "bar_chat"，drink_name 使用 "无正式推荐"，recipe_modules 使用 []，flavor_profile 使用 "无正式推荐"，color_profile 使用 "无正式推荐"。
- 如果 turn_type 是 "bar_chat"，face_state 必须体现用户情绪，action_sequence 优先使用 "gesture_thinking"、"gesture_shrug"、"serve_only"。
- 如果 turn_type 是 "recommendation"，必须正式推荐当前 prompt 库中的饮品，recipe_modules 不能为空。
- 如果 turn_type 是 "safety"，不要推荐酒精饮品，drink_name 使用 "无正式推荐"，recipe_modules 使用 []，action_sequence 优先使用 "serve_only"。
- 每轮最多问一个问题。
- 不要使用这些词：亲、哦、呢、呀、哈、啦、咱、呗。
- 不要做医学诊断、法律建议、股票建议。
"""

    # LLM 调用 + 自动重试（最多2次，指数退避）
    max_retries = 2
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            logger.info(f"LLM 调用 (尝试 {attempt+1}/{max_retries+1})")
            response = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": "你只输出合法 JSON 对象。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                timeout=30,
            )
            llm_content = response.choices[0].message.content
            return extract_json(llm_content)
        except Exception as exc:
            last_error = exc
            if attempt < max_retries:
                wait = 2 ** attempt  # 1s, 2s
                logger.warning(f"LLM 调用失败 (尝试 {attempt+1}), {wait}s 后重试: {exc}")
                time.sleep(wait)
            else:
                logger.error(f"LLM 调用全部失败: {exc}")
    raise last_error


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

    if not data["recipe_modules"] and data["turn_type"] not in CHAT_ONLY_TURN_TYPES:
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


def fallback_result(user_text: str, turn_type: str = "recommendation") -> dict:
    """内置熔断兜底：LLM 链路断开或输出非法 JSON 时，返回完整 Schema v1.0 安全字典。
    
    闲聊/安全模式 -> 点亮【疲惫】gentle 表情，不推荐饮品。
    推荐模式     -> 点亮【清醒】focused 表情，推荐标志性"冷启动"。
    """
    if turn_type in CHAT_ONLY_TURN_TYPES:
        return {
            "schema_version": "1.0",
            "turn_type": turn_type,
            "user_text": user_text,
            "emotion_label": "疲惫",
            "emotion_blend": [
                {"emotion": "疲惫", "weight": 1.0}
            ],
            "complex_emotion": "大模型链路超载，触发酒馆全息自检保护协议。",
            "need_summary": "系统自检中，需要被接住而不是立刻推荐饮品。",
            "drink_name": NO_FORMAL_DRINK_NAME,
            "recipe_modules": [],
            "flavor_profile": NO_FORMAL_DRINK_NAME,
            "color_profile": NO_FORMAL_DRINK_NAME,
            "face_state": "gentle",
            "bartender_line": "（安全协议启动）我的核心大脑似乎开了一会儿小差，不过别担心，你先缓一缓，我马上回来。",
            "action_sequence": "gesture_thinking" if turn_type == "bar_chat" else "serve_only",
            "feedback_prompt": "你愿意的话，可以再说一点。",
        }

    return {
        "schema_version": "1.0",
        "turn_type": "recommendation",
        "user_text": user_text,
        "emotion_label": "清醒",
        "emotion_blend": [
            {"emotion": "清醒", "weight": 1.0}
        ],
        "complex_emotion": "大模型链路超载，触发酒馆全息自检保护协议。",
        "need_summary": "系统自检，需要一杯清爽低甜的特调冷启动。",
        "drink_name": "冷启动",
        "recipe_modules": [
            "clear_balance",
            "bitter_focus",
        ],
        "flavor_profile": "清爽、微苦、低甜、带轻微气泡感",
        "color_profile": "透明偏冷调，带一点淡青色",
        "face_state": "focused",
        "bartender_line": "（安全协议启动）我的核心大脑似乎开了一会儿小差，不过别担心，我先为你推荐一杯标志性的'冷启动'，让我们重新连接。",
        "action_sequence": "make_cold_start",
        "feedback_prompt": "喝完感觉清醒一点了吗？",
    }


def build_robot_reply_text(control_json: dict) -> str:
    bartender_line = control_json["bartender_line"].strip()
    feedback_prompt = control_json["feedback_prompt"].strip()

    if control_json["turn_type"] == "bar_chat" and feedback_prompt:
        return f"{bartender_line}\n{feedback_prompt}"

    return bartender_line


def run_pipeline() -> dict:
    try:
        user_text = transcribe_audio(AUDIO_PATH)
    except RuntimeError as exc:
        if "silence_detected" in str(exc):
            logger.info("检测到静默录音，返回提示")
            silence_result = {
                "schema_version": "1.0",
                "turn_type": "bar_chat",
                "user_text": "",
                "emotion_label": "清醒",
                "emotion_blend": [{"emotion": "清醒", "weight": 1.0}],
                "complex_emotion": "未检测到有效语音。",
                "need_summary": "等待用户说话。",
                "drink_name": "无正式推荐",
                "recipe_modules": [],
                "flavor_profile": "无正式推荐",
                "color_profile": "无正式推荐",
                "face_state": "thinking",
                "bartender_line": "嗯？我没太听清，能再说一遍吗？",
                "action_sequence": "gesture_thinking",
                "feedback_prompt": "",
            }
            update_conversation_state(silence_result)
            return {
                "ok": True,
                "audio_path": str(AUDIO_PATH),
                "user_text": "",
                "turn_type": "bar_chat",
                "control_json": silence_result,
                "robot_reply_text": silence_result["bartender_line"],
                "conversation_state": get_conversation_state(),
                "used_fallback": False,
                "llm_error": None,
            }
        raise

    turn_type = route_turn_type(user_text)
    used_fallback = False
    llm_error = None

    try:
        result = analyze_text(user_text, turn_type)
        result = normalize_result(result)
        result["turn_type"] = turn_type
        validate_result(result)
    except Exception as exc:
        used_fallback = True
        llm_error = str(exc)
        logger.warning(f"LLM/NLP 链路异常，使用熔断兜底: {exc}")
        result = fallback_result(user_text, turn_type)
        validate_result(result)

    update_conversation_state(result)

    return {
        "ok": True,
        "audio_path": str(AUDIO_PATH),
        "user_text": user_text,
        "turn_type": turn_type,
        "control_json": result,
        "robot_reply_text": build_robot_reply_text(result),
        "conversation_state": get_conversation_state(),
        "used_fallback": used_fallback,
        "llm_error": llm_error,
    }


@app.get("/api/status")
def status():
    return {
        "recording": recording_process is not None,
        "audio_path": str(AUDIO_PATH),
        "last_result": last_result,
        "conversation_state": get_conversation_state(),
    }


@app.post("/api/voice/start")
def start_recording():
    global recording_process

    if recording_process is not None:
        # Auto-stop existing recording before starting a new one
        try:
            os.killpg(os.getpgid(recording_process.pid), signal.SIGINT)
            recording_process.communicate(timeout=2)
        except Exception:
            pass
        finally:
            recording_process = None

    if AUDIO_PATH.exists():
        AUDIO_PATH.unlink()

    import platform
    if platform.system() == "Darwin":
        command = [
            "ffmpeg",
            "-f", "avfoundation",
            "-i", ":0",
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            "-t", "30",
            "-y",
            str(AUDIO_PATH),
        ]
    else:
        command = [
            "arecord",
            "-D", "default",
            "-f", "S16_LE",
            "-r", "16000",
            "-d", "30",
            "-c", "1",
            str(AUDIO_PATH),
        ]

    recording_process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        preexec_fn=os.setsid,
    )

    time.sleep(0.5)

    if recording_process.poll() is not None:
        _, stderr = recording_process.communicate()
        recording_process = None
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start recording: {stderr.decode(errors='ignore')}",
        )

    logger.info("录音已启动 (30s 超时)")
    return {
        "ok": True,
        "state": "listening",
        "max_duration": 30,
        "message": "Recording started (30s max)",
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
        logger.info("录音已停止，开始分析管线")
        last_result = run_pipeline()
        logger.info(f"分析完成: emotion={last_result.get('control_json',{}).get('emotion_label','?')}")
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
    reset_conversation_state()

    return {
        "ok": True,
        "message": "Reset complete",
    }


@app.get("/", response_class=HTMLResponse)
def index():
    index_path = BASE_DIR / "static" / "index.html"
    if not index_path.exists():
        return HTMLResponse(
            content="<h1>Error: static/index.html not found</h1>",
            status_code=500,
        )
    return HTMLResponse(content=index_path.read_text(encoding="utf-8"))
