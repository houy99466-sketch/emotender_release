import json
import logging
import os
import hashlib
import signal
import subprocess
import time
from datetime import datetime
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
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from openai import OpenAI
from pydantic import BaseModel

from drink_matcher import (
    match_drinks,
    build_llm_drink_prompt,
    weighted_emotion_flavor,
    FLAVOR_DIMS,
    DRINK_DB,
)

from emotender_emotion import (
    NRC_EMOTIONS,
    build_uev,
    build_ambient_plan,
    build_fallback_emotion_assessment,
    build_target_flavor_vector,
    derive_legacy_fields,
    validate_emotion_assessment,
    build_vad_vector,
    compute_emotion_trend,
    TREND_DISPLAY,
)

import httpx
import base64

load_dotenv()

app = FastAPI(title="EmoTender · 此刻一杯 Backend")


class TextAnalyzeRequest(BaseModel):
    user_text: str
    username: Optional[str] = None


class UserLoginRequest(BaseModel):
    username: str


class UserLogoutRequest(BaseModel):
    username: Optional[str] = None


class AmbientPlanRequest(BaseModel):
    emotion_assessment: dict

BASE_DIR = Path(__file__).resolve().parent
AUDIO_PATH = BASE_DIR / "recording.wav"
PROMPT_LIBRARY_PATH = BASE_DIR / "prompts" / "drink_mapping.json"
PROFILE_SUMMARY_PROMPT_PATH = BASE_DIR / "prompts" / "profile_summary_prompt.md"
PROFILE_DIR = BASE_DIR / "data" / "profiles"
STATIC_DIR = BASE_DIR / "static"
recording_process: Optional[subprocess.Popen] = None
last_result: Optional[dict] = None
conversation_history: list[dict] = []
conversation_summary = ""
emotion_history: list[dict] = []  # Track VAD trend across turns
current_username: Optional[str] = None
MAX_EMOTION_HISTORY = 5

MAX_HISTORY_ITEMS = 8
MAX_SUMMARY_CHARS = 1200
NO_FORMAL_DRINK_NAME = "无正式推荐"
PROFILE_LIST_KEYS = (
    "taste_preferences",
    "emotion_patterns",
    "drink_history",
    "conversation_style",
    "avoidances",
    "mood_regulation_style",
)

# ==================== Drink Menu (from teammate frontend/backend update) ====================
# Old DRINK_MENU removed - now using drink_matcher.DRINK_DB

DRINK_METADATA_FIELDS = (
    "name",
    "name_en",
    "recipe_modules",
    "flavor_profile",
    "color_profile",
    "face_state",
    "action_sequence",
    "kernel",
    "emotional_value",
    "serve_line",
    "flavor",
    "backstory",
    "recipe",
    "color",
    "emotions",
)


def _build_single_menu_lines() -> list[str]:
    """从 drink_matcher.DRINK_DB 构建完整菜单行"""
    lines = []
    for drink in DRINK_DB:
        flavor_str = ", ".join(f"{k}:{v}" for k, v in zip(
            ("甜度", "茶感", "奶香", "果香", "清爽度", "口感层次"), drink["flavor"]))
        lines.append(
            f"  「{drink['name']}」({drink['category']}): "
            f"{drink['desc']} | 风味[{flavor_str}]"
        )
    return lines

def _build_blend_menu_lines() -> list[str]:
    """兼容旧接口，返回空列表（新品单已整合到 single_menu）"""
    return []

MENU_LINES_SINGLE = _build_single_menu_lines()
MENU_LINES_BLEND = _build_blend_menu_lines()


def get_drink_info(drink_name: str) -> Optional[dict]:
    """从 DRINK_DB 查找饮品"""
    for drink in DRINK_DB:
        if drink["name"] == drink_name:
            return drink
    return None

def build_drink_metadata(drink_name: str) -> Optional[dict]:
    drink = get_drink_info(drink_name)
    if drink is None:
        return None
    return {field: drink[field] for field in DRINK_METADATA_FIELDS if field in drink}


def enrich_result_with_drink_metadata(data: dict) -> dict:
    if data["turn_type"] in CHAT_ONLY_TURN_TYPES or data["drink_name"] == NO_FORMAL_DRINK_NAME:
        data["drink_metadata"] = None
        return data

    data["drink_metadata"] = build_drink_metadata(data["drink_name"])
    return data


# MiMo ASR 云端配置
ASR_API_KEY = os.environ.get("ASR_API_KEY", "")
ASR_BASE_URL = os.environ.get("ASR_BASE_URL", "https://api.xiaomimimo.com/v1")
ASR_MODEL_NAME = os.environ.get("ASR_MODEL", "mimo-v2.5-asr")
ASR_ENABLED = bool(ASR_API_KEY and not ASR_API_KEY.startswith("在这里"))

# MiMo TTS 云端配置
TTS_API_KEY = os.environ.get("TTS_API_KEY", os.environ.get("ASR_API_KEY", ""))
TTS_BASE_URL = os.environ.get("TTS_BASE_URL", os.environ.get("ASR_BASE_URL", "https://api.xiaomimimo.com/v1"))
TTS_MODEL = os.environ.get("TTS_MODEL", "mimo-v2.5-tts")
TTS_VOICE = os.environ.get("TTS_VOICE", "冰糖")
TTS_ENABLED = bool(TTS_API_KEY and not TTS_API_KEY.startswith("在这里"))

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

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

RECOMMENDATION_CONFIRMATIONS = (
    "好",
    "好的",
    "可以",
    "行",
    "来吧",
    "嗯",
    "嗯嗯",
    "要",
    "需要",
    "开始吧",
    "按你说的",
    "你做主",
)

RECOMMENDATION_OFFER_MARKERS = (
    "正式推荐",
    "推荐一杯",
    "给你推荐",
    "为你推荐",
    "要不要",
    "需不需要",
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

ALLOWED_TURN_TYPES = {
    "bar_chat",
    "recommendation",
    "safety",
}


def previous_turn_offered_recommendation() -> bool:
    if not conversation_history:
        return False

    previous = conversation_history[-1]
    prompt_text = " ".join(
        str(previous.get(key, ""))
        for key in ("bartender_line", "feedback_prompt")
    )
    return any(marker in prompt_text for marker in RECOMMENDATION_OFFER_MARKERS)


def is_recommendation_confirmation(user_text: str) -> bool:
    text = user_text.strip()
    return any(trigger in text for trigger in RECOMMENDATION_CONFIRMATIONS)


def route_turn_type(user_text: str) -> str:
    text = user_text.strip()

    if any(trigger in text for trigger in SAFETY_TRIGGERS):
        return "safety"

    if any(trigger in text for trigger in RECOMMENDATION_TRIGGERS):
        return "recommendation"

    if previous_turn_offered_recommendation() and is_recommendation_confirmation(text):
        return "recommendation"

    return "bar_chat"


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def normalize_username(username: Optional[str]) -> Optional[str]:
    if username is None:
        return None
    cleaned = username.strip()
    return cleaned or None


def require_username(username: Optional[str]) -> str:
    cleaned = normalize_username(username)
    if cleaned is None:
        raise ValueError("username must not be empty")
    return cleaned


def profile_path_for_username(username: str) -> Path:
    digest = hashlib.sha256(username.encode("utf-8")).hexdigest()
    return PROFILE_DIR / f"{digest}.json"


def default_user_profile(username: str) -> dict:
    timestamp = now_iso()
    return {
        "username": username,
        "created_at": timestamp,
        "updated_at": timestamp,
        "stable_profile": {
            "taste_preferences": [],
            "emotion_patterns": [],
            "drink_history": [],
            "conversation_style": [],
            "avoidances": [],
            "mood_regulation_style": [],
        },
        "session_summaries": [],
    }


def load_user_profile(username: str) -> dict:
    username = require_username(username)
    path = profile_path_for_username(username)
    if not path.exists():
        return default_user_profile(username)
    with open(path, "r", encoding="utf-8") as f:
        profile = json.load(f)
    profile.setdefault("username", username)
    profile.setdefault("created_at", now_iso())
    profile.setdefault("updated_at", now_iso())
    profile.setdefault("stable_profile", {})
    profile.setdefault("session_summaries", [])
    for key in PROFILE_LIST_KEYS:
        profile["stable_profile"].setdefault(key, [])
    return profile


def save_user_profile(username: str, profile: dict) -> dict:
    username = require_username(username)
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    profile["username"] = username
    profile["updated_at"] = now_iso()
    profile.setdefault("created_at", profile["updated_at"])
    path = profile_path_for_username(username)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)
    return profile


def append_unique(target: list, values) -> None:
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list):
        return
    for value in values:
        if not isinstance(value, str):
            continue
        cleaned = value.strip()
        if cleaned and cleaned not in target:
            target.append(cleaned)


def compact_profile_context(username: Optional[str]) -> dict:
    username = normalize_username(username)
    if username is None:
        return {
            "mode": "anonymous",
            "message": "用户未登录，不使用长期 profile。",
        }
    profile = load_user_profile(username)
    return {
        "mode": "logged_in",
        "username": username,
        "stable_profile": profile["stable_profile"],
        "recent_session_summaries": profile["session_summaries"][-5:],
    }


def build_prompt_profile_context(profile_context: dict) -> dict:
    """Expose only stable recommendation preferences, never historical emotion evidence."""
    if profile_context.get("mode") != "logged_in":
        return {
            "mode": "anonymous",
            "message": "用户未登录，不使用长期 profile。",
        }

    stable = profile_context.get("stable_profile", {})
    return {
        "mode": "logged_in",
        "username": profile_context.get("username"),
        "taste_preferences": list(stable.get("taste_preferences", [])),
        "drink_history": list(stable.get("drink_history", [])),
        "conversation_style": list(stable.get("conversation_style", [])),
        "avoidances": list(stable.get("avoidances", [])),
        "mood_regulation_style": list(stable.get("mood_regulation_style", [])),
    }


def merge_session_summary_into_profile(profile: dict, summary: dict) -> dict:
    stable = profile.setdefault("stable_profile", {})
    for key in PROFILE_LIST_KEYS:
        stable.setdefault(key, [])

    append_unique(stable["taste_preferences"], summary.get("taste_preferences", []))
    append_unique(stable["emotion_patterns"], summary.get("emotional_pattern", ""))
    append_unique(stable["drink_history"], summary.get("drink_name", ""))
    append_unique(stable["conversation_style"], summary.get("conversation_style", []))
    append_unique(stable["avoidances"], summary.get("avoidances", []))
    append_unique(stable["mood_regulation_style"], summary.get("mood_regulation_style", []))

    profile.setdefault("session_summaries", []).append(summary)
    profile["session_summaries"] = profile["session_summaries"][-20:]
    return profile


def get_recent_history() -> list[dict]:
    return conversation_history[-MAX_HISTORY_ITEMS:]


def get_conversation_state() -> dict:
    return {
        "summary": conversation_summary,
        "history": list(conversation_history),
        "username": current_username,
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
        "feedback_prompt": data["feedback_prompt"],
        "emotion_assessment": data["emotion_assessment"],
    }

    if data["turn_type"] == "recommendation":
        item["drink_name"] = data["drink_name"]
        item["recipe_modules"] = data["recipe_modules"]
        item["recommendation_reason"] = data["recommendation_reason"]

    conversation_history.append(item)
    vad = data["emotion_assessment"].get("vad")
    if vad:
        emotion_history.append({"valence": vad["valence"], "arousal": vad["arousal"], "label": data.get("emotion_label", "?")})
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
    if not ASR_ENABLED:
        raise RuntimeError("asr_unavailable")

    logger.info(f"开始 MiMo ASR 语音识别: {wav_path}")
    url = f"{ASR_BASE_URL.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {ASR_API_KEY}",
        "Content-Type": "application/json",
    }

    # 读取音频文件并 base64 编码
    with open(wav_path, "rb") as f:
        audio_bytes = f.read()
    audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")

    payload = {
        "model": ASR_MODEL_NAME,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_audio",
                        "input_audio": {
                            "data": audio_b64,
                            "format": "wav",
                        },
                    }
                ],
            }
        ],
        "asr_options": {"language": "zh"},
        "stream": False,
    }

    last_error = None
    for attempt in range(3):
        try:
            resp = httpx.post(url, headers=headers, json=payload, timeout=30)
            if resp.status_code != 200:
                raise RuntimeError(f"asr_error_{resp.status_code}")
            result = resp.json()
            text = ""
            choices = result.get("choices", [])
            if choices:
                msg = choices[0].get("message", {})
                text = msg.get("content", "").strip()
            if not text or len(text) < 2:
                logger.warning(f"静默或过短语音: '{text}'")
                raise RuntimeError("silence_detected")
            logger.info(f"MiMo ASR 识别结果: {text}")
            return text
        except Exception as e:
            last_error = e
            if attempt < 2:
                logger.warning(f"ASR 尝试 {attempt+1} 失败, 重试: {e}")
                time.sleep(1)
    raise last_error


def extract_json(content: str) -> dict:
    content = content.strip()

    if content.startswith("```json"):
        content = content.removeprefix("```json").strip()
    if content.startswith("```"):
        content = content.removeprefix("```").strip()
    if content.endswith("```"):
        content = content.removesuffix("```").strip()

    return json.loads(content)


def analyze_text(user_text: str, turn_type: str, profile_context: Optional[dict] = None) -> dict:
    with open(PROMPT_LIBRARY_PATH, "r", encoding="utf-8") as f:
        prompt_library = json.load(f)
    recent_history = get_recent_history()
    profile_context = profile_context or compact_profile_context(None)
    prompt_profile_context = build_prompt_profile_context(profile_context)
    single_menu = "\n".join(MENU_LINES_SINGLE)
    blend_menu = "\n".join(MENU_LINES_BLEND)

    # Build emotion trend
    emotion_trend = ""
    if len(emotion_history) >= 2:
        trend_labels = [h["label"] if isinstance(h, dict) else str(h) for h in (emotion_history[-3:] if len(emotion_history) >= 3 else emotion_history)]
        emotion_trend = f"\n用户情绪变化趋势（最近{len(trend_labels)}轮）：{' → '.join(trend_labels)}。该趋势只能用于调整回应语气，不能作为本轮 NRC 评分证据。"


    # === 智能饮品匹配 ===
    default_scores = {"trust": 0.5, "anticipation": 0.3, "joy": 0.2}
    matched_candidates = match_drinks(default_scores, "犹豫", top_n=5)
    candidate_lines = "\n".join(
        f"  - {c['name']}（{c['category']}）：{c['desc']}"
        for c in matched_candidates
    )

    prompt = f"""
你是「此刻一杯」情绪茶饮的 AI 中控分析模块。
你的角色是茗茗，28岁，开了6年茶饮店。
你的信念是：茶是情绪的容器，不是答案。
你的表达必须低沉、松弛、直球、不说废话。

你必须只输出一个合法 JSON 对象。内部推理尽量简洁，不要展开分析。
不要输出 Markdown。
不要输出解释。
不要输出代码块。
不要在 JSON 前后添加任何文字。

规则路由给出的初步模式建议：
{turn_type}

你必须根据用户原话、最近对话历史和用户长期 profile 自行决定最终 turn_type。
规则路由只是提示，不是最终答案。

用户原话：
{user_text}

会话摘要：
{conversation_summary or "暂无"}
{emotion_trend}

最近对话历史：
{json.dumps(recent_history, ensure_ascii=False, indent=2)}

用户长期 profile 中可用于推荐的稳定偏好：
{json.dumps(prompt_profile_context, ensure_ascii=False, indent=2)}

本轮情绪隔离规则：
- emotion_assessment、emotion_label、emotion_blend、emotion_blend.source 和 complex_emotion 只能依据用户本轮原话与当前会话历史判断。
- 不得根据用户长期 profile、历史会话摘要、上次使用时的情绪或过去发生的事件判断本轮情绪。
- 长期 profile 只能用于口味偏好、避忌、交流风格和历史饮品参考。

NRC 八类情绪评估规则：
- 唯一允许的情绪键为：{json.dumps(NRC_EMOTIONS, ensure_ascii=False)}。
- emotion_assessment.taxonomy 必须是 "nrc_emolex_8"。
- emotion_assessment.scores 必须包含全部八个键，每项范围 0.0 到 1.0，总和必须接近 1.0。
- 必须先从当前会话提取原话证据，再为八类情绪评分。
- primary_emotion 必须对应最高分。
- evidence 每项必须包含 quote、emotions 和 interpretation；quote 必须逐字来自本轮原话或当前会话历史。
- 每个分数大于零的情绪都必须至少出现在一项 evidence.emotions 中。
- 用户明确自述优先；必须正确处理“不是”“没有”“并不”等否定表达，以及“但是”“不过”“同时”等转折或混合表达。
- confidence 范围为 0.0 到 1.0；证据不足时降低 confidence，并将 clarification_needed 设为 true。
- NRC 分数是情绪构成分数，不是医学诊断或心理学概率。

这是 EmoTender 的 prompt 库，包含情绪维度、混合规则、配方模块、表情状态和动作序列：
{json.dumps(prompt_library, ensure_ascii=False, indent=2)}

系统根据情绪风味向量匹配的候选饮品（按相似度排序）：
{candidate_lines}

你可以从以上候选中选择，也可以根据用户具体情绪从完整菜单中选择更合适的：
单品：
{single_menu}

混合情绪特调：
{blend_menu}

选择饮品时的规则：
- 优先从候选饮品中选择
- 如果候选不合适，可以从完整菜单中选择
- 必须选择真实存在的饮品名

必须输出这些字段：
schema_version, turn_type, user_text, emotion_assessment, emotion_label, emotion_blend, complex_emotion,
need_summary, drink_name, recipe_modules, flavor_profile, color_profile,
face_state, bartender_line, action_sequence, feedback_prompt, recommendation_reason。

字段类型要求：
- schema_version 必须是字符串，例如 "1.0"
- turn_type 必须是字符串，例如 "initial_order"
- user_text 必须是字符串
- emotion_assessment 必须是对象，包含 taxonomy、scores、primary_emotion、confidence、evidence、clarification_needed
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
- recommendation_reason 必须是字符串
- emotion_blend 必须是数组，每一项包含 emotion、weight 和 source，例如 [{{"emotion": "难过", "weight": 0.7, "source": "用户说今天考试没有考好"}}, {{"emotion": "焦虑", "weight": 0.3, "source": "用户担心明天仍然没有状态"}}]
- emotion_blend 的 weight 总和必须接近 1.0
- emotion_blend.source 必须简短说明该情绪在当前会话中的来源，不能引用长期 profile 或过去会话。

模式规则：
- turn_type 只能是 "bar_chat"、"recommendation" 或 "safety"。
- 如果 turn_type 是 "bar_chat"，这一轮是闲聊。你仍然必须输出完整 JSON，用于驱动机器人表情、动作和台词，但不要正式推荐饮品。
- 如果 turn_type 是 "bar_chat"，drink_name 使用 "无正式推荐"，recipe_modules 使用 []，flavor_profile 使用 "无正式推荐"，color_profile 使用 "无正式推荐"。
- 如果 turn_type 是 "bar_chat"，recommendation_reason 使用 "无正式推荐"。
- 如果 turn_type 是 "bar_chat"，face_state 必须体现用户情绪，action_sequence 优先使用 "gesture_thinking"、"gesture_shrug"、"serve_only"。
- 如果 turn_type 是 "recommendation"，必须正式推荐当前后端饮品菜单中的饮品，drink_name 必须精确使用菜单里的中文饮品名，recipe_modules 不能为空。
- 如果 turn_type 是 "recommendation"，recommendation_reason 使用 2 到 4 句话：先准确接住用户在当前会话中提到的具体经历，再说明这款饮品为什么适合此刻；不能引用历史 profile 中的事件或情绪，不能承诺饮品能够解决现实问题。
- 如果推荐时判断为单一情绪，优先使用菜单“单品”；如果判断为两种或三种主要情绪，可以使用菜单“混合情绪特调”。
- 推荐饮品时，bartender_line 优先使用或贴近菜单中对应饮品的 serve_line。
- 如果用户明确要求推荐、来一杯、让你做主，turn_type 必须是 "recommendation"。
- 如果最近一轮你询问是否正式推荐饮品，而用户本轮表达同意、接受、让你安排，turn_type 必须是 "recommendation"。
- 如果用户只是继续倾诉、闲聊、打招呼，且没有表达要饮品推荐，turn_type 使用 "bar_chat"。
- 如果 turn_type 是 "safety"，只推荐无咖啡因温和饮品，drink_name 使用 "无正式推荐"，recipe_modules 使用 []，action_sequence 优先使用 "serve_only"。
- 如果 turn_type 是 "safety"，recommendation_reason 使用 "无正式推荐"。
- 如果用户长期 profile 中有口味偏好、历史饮品或情绪模式，请把它作为个性化依据，但不要在台词里暴露“我保存了你的资料”这类后台措辞。
- 每轮最多问一个问题。
- 不要使用这些词：亲、哦、呢、呀、哈、啦、咱、呗。
- 不要做医学诊断、法律建议、股票建议。

正向情绪放大规则：
- 当 joy 为 primary_emotion 且权重超过 0.5 时，feedback_prompt 应主动引导用户放大此刻的好心情。
- 可以建议：趁状态好试试从没试过的新搭配；把这杯分享给身边的人；记住这个味道，下次不开心时能想起来今天。
- 不要只说"开心就好"，要有具体的、可执行的小建议。

情绪调节建议规则：
- 当用户本轮情绪明显负面（sadness、fear、anger 中任一权重超过 0.4）时，feedback_prompt 末尾可以轻度附带一个情绪调节建议。
- 建议必须温和、具体、不说教。例如："喝完这杯，出去走走"、"今天早点休息"、"给一个信任的人打个电话"、"深呼吸三次"。
- 每轮最多一个调节建议，放在 feedback_prompt 最后，用句号或逗号与前文连接。
- 不要每次都给，根据对话上下文自然决定是否需要。如果用户已经在做调节行为（比如已经在散步），就不再建议。
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
                max_completion_tokens=8192,
                timeout=90,
            )
            llm_content = response.choices[0].message.content
            raw_reasoning = getattr(response.choices[0].message, 'reasoning_content', None)
            logger.info(f"LLM raw content (first 300): {repr(llm_content[:300] if llm_content else None)}")
            logger.info(f"LLM raw reasoning (first 200): {repr(raw_reasoning[:200] if raw_reasoning else None)}")
            logger.info(f"LLM finish_reason: {response.choices[0].finish_reason}")
            parsed = extract_json(llm_content)
            validate_emotion_assessment(
                parsed["emotion_assessment"],
                [
                    user_text,
                    *(str(item.get("user_text", "")) for item in recent_history),
                ],
            )
            return parsed
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


def current_emotion_evidence_texts(user_text: str) -> list[str]:
    return [
        user_text,
        *(str(item.get("user_text", "")) for item in get_recent_history()),
    ]


# 中文情绪名 -> NRC 英文键映射
_CN_TO_NRC = {
    "愤怒": "anger", "期待": "anticipation", "厌恶": "disgust", "恐惧": "fear",
    "喜悦": "joy", "悲伤": "sadness", "惊讶": "surprise", "信任": "trust",
    "生气": "anger", "焦虑": "anger", "紧张": "fear", "害怕": "fear",
    "开心": "joy", "高兴": "joy", "快乐": "joy", "难过": "sadness",
    "伤心": "sadness", "吃惊": "surprise", "意外": "surprise",
}

def _normalize_emotion_blend(blend: list) -> list:
    """将 emotion_blend 中的中文情绪名映射回英文 NRC 键"""
    for item in blend:
        emo = item.get("emotion", "")
        if emo in _CN_TO_NRC:
            item["emotion"] = _CN_TO_NRC[emo]
    return blend

def apply_emotion_compatibility(data: dict) -> dict:
    if "emotion_blend" in data:
        _normalize_emotion_blend(data["emotion_blend"])
    data.update(derive_legacy_fields(data["emotion_assessment"]))
    data["target_flavor_vector"] = build_target_flavor_vector(
        data["emotion_assessment"]["scores"]
    )
    # 生成标准化 UEV
    data["uev"] = build_uev(data["emotion_assessment"], emotion_history)
    return data


def validate_result(data: dict) -> None:
    required_fields = [
        "schema_version",
        "turn_type",
        "user_text",
        "emotion_assessment",
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
        "recommendation_reason",
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

        if "source" not in item:
            raise ValueError(f"emotion_blend item missing source: {item}")

        if not isinstance(item["emotion"], str):
            raise TypeError(f"emotion_blend emotion must be a string: {item}")

        if not isinstance(item["weight"], (int, float)):
            raise TypeError(f"emotion_blend weight must be a number: {item}")

        if not isinstance(item["source"], str):
            raise TypeError(f"emotion_blend source must be a string: {item}")

        if not item["source"].strip():
            raise ValueError(f"emotion_blend source must not be empty: {item}")

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
        "recommendation_reason",
    ]

    for field in string_fields:
        if not isinstance(data[field], str):
            raise TypeError(f"{field} must be a string, got {type(data[field]).__name__}: {data[field]}")
        if not data[field].strip():
            raise ValueError(f"{field} must not be empty")

    if data["turn_type"] not in ALLOWED_TURN_TYPES:
        raise ValueError(f"Unknown turn_type: {data['turn_type']}")

    if data["turn_type"] == "recommendation" and get_drink_info(data["drink_name"]) is None:
        raise ValueError(f"Unknown drink_name: {data['drink_name']}")

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
    emotion_assessment = build_fallback_emotion_assessment(user_text)
    if turn_type in CHAT_ONLY_TURN_TYPES:
        result = {
            "schema_version": "1.0",
            "turn_type": turn_type,
            "user_text": user_text,
            "emotion_assessment": {**emotion_assessment, "vad": build_vad_vector(emotion_assessment["scores"]), "trend": "steady", "trend_display": TREND_DISPLAY["steady"]},
            "emotion_label": "疲惫",
            "emotion_blend": [
                {"emotion": "疲惫", "weight": 1.0, "source": "系统无法完成本轮情绪分析。"}
            ],
            "complex_emotion": "大模型链路超载，触发酒馆全息自检保护协议。",
            "need_summary": "系统自检中，需要被接住而不是立刻推荐饮品。",
            "drink_name": NO_FORMAL_DRINK_NAME,
            "recipe_modules": [],
            "flavor_profile": NO_FORMAL_DRINK_NAME,
            "color_profile": NO_FORMAL_DRINK_NAME,
            "face_state": "gentle",
            "bartender_line": "（安全协议启动）我的核心大脑似乎开了一会儿小差，不过别担心，你先缓一缓，我马上回来。先喝口茶暖暖。",
            "action_sequence": "gesture_thinking" if turn_type == "bar_chat" else "serve_only",
            "feedback_prompt": "你愿意的话，可以再说一点。",
            "recommendation_reason": NO_FORMAL_DRINK_NAME,
        }
        return apply_emotion_compatibility(result)

    result = {
        "schema_version": "1.0",
        "turn_type": "recommendation",
        "user_text": user_text,
        "emotion_assessment": {**emotion_assessment, "vad": build_vad_vector(emotion_assessment["scores"]), "trend": "steady", "trend_display": TREND_DISPLAY["steady"]},
        "emotion_label": "清醒",
        "emotion_blend": [
            {"emotion": "清醒", "weight": 1.0, "source": "系统进入推荐 fallback。"}
        ],
        "complex_emotion": "大模型链路超载，触发酒馆全息自检保护协议。",
        "need_summary": "系统自检，需要一杯清爽低甜的特调冷启动。",
        "drink_name": "晨露茉莉",
        "recipe_modules": [
            "clear_balance",
            "bitter_focus",
        ],
        "flavor_profile": "清爽、微苦、低甜、带轻微气泡感",
        "color_profile": "透明偏冷调，带一点淡青色",
        "face_state": "focused",
        "bartender_line": "（安全协议启动）我的核心大脑似乎开了一会儿小差，不过别担心，我先为你推荐一杯标志性的'晨露茉莉'，让我们重新连接。",
        "action_sequence": "make_cold_start",
        "feedback_prompt": "喝完感觉清醒一点了吗？",
        "recommendation_reason": "这次分析没有完整返回，我先用一杯清爽低甜的冷启动接住这一轮。它不能替你解决正在面对的事情，但能让推荐流程保持完整。",
    }
    return apply_emotion_compatibility(result)


def build_robot_reply_text(control_json: dict) -> str:
    bartender_line = control_json["bartender_line"].strip()
    feedback_prompt = control_json["feedback_prompt"].strip()

    if control_json["turn_type"] == "bar_chat" and feedback_prompt:
        return f"{bartender_line}\n{feedback_prompt}"

    return bartender_line


def process_user_text(user_text: str, username: Optional[str] = None) -> dict:
    global current_username

    user_text = user_text.strip()
    if not user_text:
        raise ValueError("user_text must not be empty")

    username = normalize_username(username) or current_username
    current_username = username
    profile_context = compact_profile_context(username)
    turn_type_hint = route_turn_type(user_text)
    used_fallback = False
    llm_error = None

    try:
        result = analyze_text(user_text, turn_type_hint, profile_context)
        result = normalize_result(result)
        validate_emotion_assessment(
            result["emotion_assessment"],
            current_emotion_evidence_texts(user_text),
        )
        # VAD 三维向量（后处理推导，不依赖 LLM）
        vad = build_vad_vector(result["emotion_assessment"]["scores"])
        result["emotion_assessment"]["vad"] = vad
        # 情绪趋势
        trend = compute_emotion_trend(emotion_history)
        result["emotion_assessment"]["trend"] = trend
        result["emotion_assessment"]["trend_display"] = TREND_DISPLAY.get(trend, trend)
        result = apply_emotion_compatibility(result)
        if turn_type_hint == "safety":
            result["turn_type"] = "safety"
        elif result.get("turn_type") not in ALLOWED_TURN_TYPES:
            result["turn_type"] = turn_type_hint
        result["user_text"] = user_text
        validate_result(result)
        result = enrich_result_with_drink_metadata(result)
        if result["turn_type"] == "recommendation":
            result["ambient_plan"] = {"enabled": False}
    except Exception as exc:
        used_fallback = True
        llm_error = str(exc)
        logger.warning(f"LLM/NLP 链路异常，使用熔断兜底: {exc}", exc_info=True)
        result = fallback_result(user_text, turn_type_hint)
        validate_result(result)
        result = enrich_result_with_drink_metadata(result)
        if result["turn_type"] == "recommendation":
            result["ambient_plan"] = {"enabled": False}

    update_conversation_state(result)

    return {
        "ok": True,
        "username": username,
        "user_text": user_text,
        "turn_type": result["turn_type"],
        "control_json": result,
        "robot_reply_text": build_robot_reply_text(result),
        "profile_context": profile_context,
        "conversation_state": get_conversation_state(),
        "used_fallback": used_fallback,
        "llm_error": llm_error,
    }


def load_profile_summary_prompt() -> str:
    if PROFILE_SUMMARY_PROMPT_PATH.exists():
        return PROFILE_SUMMARY_PROMPT_PATH.read_text(encoding="utf-8")
    return (
        "你是 EmoTender 的用户记忆整理模块。根据本次对话输出合法 JSON，"
        "字段包含 date, username, session_emotion, drink_name, drink_result, "
        "event_summary, taste_preferences, emotional_pattern, future_hint。"
    )


def summarize_session_for_profile(username: str, profile: dict, state: dict) -> dict:
    prompt = f"""
{load_profile_summary_prompt()}

用户名：
{username}

已有 profile：
{json.dumps(profile, ensure_ascii=False, indent=2)}

本次会话：
{json.dumps(state, ensure_ascii=False, indent=2)}
"""
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": "你只输出合法 JSON 对象。"},
            {"role": "user", "content": prompt},
        ],
        temperature=0.1,
        max_completion_tokens=8192,
        timeout=90,
    )
    summary = extract_json(response.choices[0].message.content)
    summary["username"] = username
    summary.setdefault("date", datetime.now().date().isoformat())
    summary.setdefault("drink_name", NO_FORMAL_DRINK_NAME)
    summary.setdefault("drink_result", "未记录")
    summary.setdefault("event_summary", "本次会话没有形成明确事件摘要。")
    summary.setdefault("taste_preferences", [])
    summary.setdefault("emotional_pattern", "")
    summary.setdefault("future_hint", "")
    return summary


def run_pipeline() -> dict:
    try:
        user_text = transcribe_audio(AUDIO_PATH)
    except RuntimeError as exc:
        if "silence_detected" in str(exc):
            logger.info("检测到静默录音，返回提示")
            silence_assessment = {
                "taxonomy": "nrc_emolex_8",
                "scores": {
                    "anger": 0.0,
                    "anticipation": 0.0,
                    "disgust": 0.0,
                    "fear": 0.0,
                    "joy": 0.0,
                    "sadness": 0.0,
                    "surprise": 0.0,
                    "trust": 1.0,
                },
                "primary_emotion": "trust",
                "confidence": 0.0,
                "evidence": [
                    {
                        "quote": "本轮没有检测到有效语音。",
                        "emotions": ["trust"],
                        "interpretation": "没有足够的用户输入用于情绪判断",
                    }
                ],
                "clarification_needed": True,
            }
            silence_result = {
                "schema_version": "1.0",
                "turn_type": "bar_chat",
                "user_text": "",
                "emotion_assessment": silence_assessment,
                "emotion_label": "清醒",
                "emotion_blend": [{"emotion": "清醒", "weight": 1.0, "source": "本轮没有检测到有效语音。"}],
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
                "recommendation_reason": NO_FORMAL_DRINK_NAME,
                "target_flavor_vector": build_target_flavor_vector(
                    silence_assessment["scores"]
                ),
                "drink_metadata": None,
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

    result = process_user_text(user_text)
    result["audio_path"] = str(AUDIO_PATH)
    return result


@app.get("/api/status")
def status():
    return {
        "recording": recording_process is not None,
        "audio_path": str(AUDIO_PATH),
        "last_result": last_result,
        "conversation_state": get_conversation_state(),
    }


@app.post("/api/text/analyze")
def analyze_text_api(payload: TextAnalyzeRequest):
    try:
        return process_user_text(payload.user_text, payload.username)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/ambient/plan")
def ambient_plan_api(payload: AmbientPlanRequest):
    try:
        evidence = payload.emotion_assessment.get("evidence", [])
        validate_emotion_assessment(
            payload.emotion_assessment,
            [
                item.get("quote", "")
                for item in evidence
                if isinstance(item, dict)
            ],
        )
        return {
            "ok": True,
            "ambient_plan": build_ambient_plan(payload.emotion_assessment),
        }
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/user/login")
def login_user_api(payload: UserLoginRequest):
    global current_username
    try:
        username = require_username(payload.username)
        profile = load_user_profile(username)
        save_user_profile(username, profile)
        current_username = username
        reset_conversation_state()
        return {
            "ok": True,
            "username": username,
            "profile": profile,
            "message": "Login complete",
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/user/logout")
def logout_user_api(payload: UserLogoutRequest):
    global current_username
    try:
        username = normalize_username(payload.username) or current_username
        username = require_username(username)
        profile = load_user_profile(username)
        state = get_conversation_state()
        saved_summary = None
        if state["history"]:
            saved_summary = summarize_session_for_profile(username, profile, state)
            profile = merge_session_summary_into_profile(profile, saved_summary)
            save_user_profile(username, profile)
        reset_conversation_state()
        current_username = None
        return {
            "ok": True,
            "username": username,
            "saved_summary": saved_summary,
            "profile": profile,
            "message": "Logout complete",
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/user/profile")
def get_user_profile_api(username: str):
    try:
        username = require_username(username)
        return {
            "ok": True,
            "username": username,
            "profile": load_user_profile(username),
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


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


@app.post("/api/tts")
def tts_endpoint(req: dict):
    """TTS 语音合成端点 — 将文本转为 base64 音频"""
    text = (req.get("text") or "").strip()
    voice = req.get("voice") or TTS_VOICE
    if not text:
        return {"ok": False, "error": "empty text"}
    if not TTS_ENABLED:
        return {"ok": False, "error": "TTS not configured"}

    for attempt in range(3):
        try:
            resp = httpx.post(
                f"{TTS_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {TTS_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": TTS_MODEL,
                    "messages": [{"role": "assistant", "content": text}],
                    "modalities": ["text", "audio"],
                    "audio": {"voice": voice, "format": "mp3"},
                },
                timeout=20,
            )
            data = resp.json()
            choices = data.get("choices", [])
            if not choices:
                if attempt < 2:
                    time.sleep(1)
                    continue
                return {"ok": False, "error": "no choices", "detail": data}
            audio = choices[0].get("message", {}).get("audio", {})
            audio_b64 = audio.get("data", "")
            if not audio_b64:
                if attempt < 2:
                    time.sleep(1)
                    continue
                return {"ok": False, "error": "no audio data"}
            return {"ok": True, "audio": audio_b64, "format": "mp3"}
        except Exception as e:
            if attempt < 2:
                logger.warning(f"TTS 尝试 {attempt+1} 失败, 重试: {e}")
                time.sleep(1)
            else:
                return {"ok": False, "error": str(e)}


@app.get("/api/text/stream")
async def text_stream(username: str = "", user_text: str = ""):
    """SSE streaming endpoint for text analysis"""
    import asyncio, json as _json

    def _sse(event_type, data):
        return f"event: {event_type}\ndata: {_json.dumps(data, ensure_ascii=False)}\n\n"

    async def event_generator():
        if not user_text.strip():
            yield _sse("error", {"error": "empty text"})
            return

        yield _sse("status", {"message": "正在分析情绪..."})

        # Run analysis in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(
                None, process_user_text, user_text.strip(), username or None
            )
        except Exception as exc:
            yield _sse("error", {"error": str(exc)})
            return

        # Send emotion data first
        ea = result.get("control_json", {}).get("emotion_assessment", {})
        yield _sse("emotion", {"emotion_assessment": ea})

        # Stream bartender line character by character
        bartender = result.get("control_json", {}).get("bartender_line", "")
        for ch in bartender:
            yield _sse("token", {"token": ch})
            await asyncio.sleep(0.03)

        # Send final complete result
        yield _sse("done", result)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/", response_class=HTMLResponse)
def index():
    index_path = BASE_DIR / "static" / "index.html"
    if not index_path.exists():
        return HTMLResponse(
            content="<h1>Error: static/index.html not found</h1>",
            status_code=500,
        )
    return HTMLResponse(content=index_path.read_text(encoding="utf-8"))
