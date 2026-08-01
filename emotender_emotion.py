from __future__ import annotations

NRC_EMOTIONS = (
    "anger",
    "anticipation",
    "disgust",
    "fear",
    "joy",
    "sadness",
    "surprise",
    "trust",
)

NRC_DISPLAY_NAMES = {
    "anger": "愤怒",
    "anticipation": "期待",
    "disgust": "厌恶",
    "fear": "恐惧",
    "joy": "喜悦",
    "sadness": "悲伤",
    "surprise": "惊讶",
    "trust": "信任",
}

LEGACY_EMOTION_MAP = {
    "anger": ("焦虑", "focused"),
    "anticipation": ("犹豫", "thinking"),
    "disgust": ("清醒", "focused"),
    "fear": ("焦虑", "focused"),
    "joy": ("兴奋", "happy"),
    "sadness": ("难过", "gentle"),
    "surprise": ("兴奋", "happy"),
    "trust": ("清醒", "focused"),
}

FLAVOR_KEYS = ("甜度", "茶感", "奶香", "果香", "清爽度", "口感层次")

FLAVOR_MATRIX = {
    "anger": (20, 70, 20, 30, 80, 65),
    "anticipation": (45, 55, 20, 65, 75, 75),
    "disgust": (15, 65, 10, 35, 90, 55),
    "fear": (55, 35, 65, 30, 45, 55),
    "joy": (65, 30, 35, 80, 75, 70),
    "sadness": (70, 25, 80, 30, 35, 65),
    "surprise": (50, 35, 20, 85, 80, 80),
    "trust": (55, 45, 70, 35, 45, 75),
}

AMBIENT_PRESETS = {
    "anger": {
        "temperature_c": 23,
        "brightness_percent": 45,
        "color_temperature_k": 3500,
        "purifier_mode": "auto",
        "air_conditioner_reason": "保持偏凉但不过度刺激的体感",
        "light_reason": "降低亮度并使用柔和中性光",
        "air_purifier_reason": "自动维持空气流动",
    },
    "anticipation": {
        "temperature_c": 24,
        "brightness_percent": 70,
        "color_temperature_k": 4500,
        "purifier_mode": "auto",
        "air_conditioner_reason": "保持适合持续活动的稳定体感",
        "light_reason": "使用明亮中性光维持行动感",
        "air_purifier_reason": "自动维持空气状态",
    },
    "disgust": {
        "temperature_c": 22,
        "brightness_percent": 75,
        "color_temperature_k": 5000,
        "purifier_mode": "boost",
        "air_conditioner_reason": "提供偏凉且清爽的体感",
        "light_reason": "使用清晰明亮的冷白光",
        "air_purifier_reason": "增强模式突出洁净感",
    },
    "fear": {
        "temperature_c": 25,
        "brightness_percent": 40,
        "color_temperature_k": 3000,
        "purifier_mode": "silent",
        "air_conditioner_reason": "保持温和稳定的体感",
        "light_reason": "使用低亮度暖光减少视觉刺激",
        "air_purifier_reason": "静音运行减少额外噪声",
    },
    "joy": {
        "temperature_c": 24,
        "brightness_percent": 80,
        "color_temperature_k": 4200,
        "purifier_mode": "auto",
        "air_conditioner_reason": "保持轻快舒适的体感",
        "light_reason": "使用明亮自然光延续轻快氛围",
        "air_purifier_reason": "自动维持空气状态",
    },
    "sadness": {
        "temperature_c": 25,
        "brightness_percent": 45,
        "color_temperature_k": 3000,
        "purifier_mode": "silent",
        "air_conditioner_reason": "保持温和不过冷的体感",
        "light_reason": "使用柔和暖光降低空间压迫感",
        "air_purifier_reason": "静音运行保持安静",
    },
    "surprise": {
        "temperature_c": 23,
        "brightness_percent": 85,
        "color_temperature_k": 5000,
        "purifier_mode": "auto",
        "air_conditioner_reason": "保持清爽醒目的体感",
        "light_reason": "使用高亮度中性偏冷光",
        "air_purifier_reason": "自动维持空气状态",
    },
    "trust": {
        "temperature_c": 25,
        "brightness_percent": 55,
        "color_temperature_k": 3200,
        "purifier_mode": "silent",
        "air_conditioner_reason": "保持稳定温和的体感",
        "light_reason": "使用柔和暖光维持安心氛围",
        "air_purifier_reason": "静音运行保持空间稳定",
    },
}


def _ensure_number(value, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field} must be a number")


def validate_emotion_assessment(assessment: dict, current_texts: list[str]) -> None:
    if not isinstance(assessment, dict):
        raise TypeError("emotion_assessment must be an object")
    if assessment.get("taxonomy") != "nrc_emolex_8":
        raise ValueError("taxonomy must be nrc_emolex_8")

    scores = assessment.get("scores")
    if not isinstance(scores, dict) or set(scores) != set(NRC_EMOTIONS):
        raise ValueError("scores keys must match NRC_EMOTIONS")
    for key, value in scores.items():
        _ensure_number(value, f"scores.{key}")
        if not 0 <= value <= 1:
            raise ValueError(f"scores.{key} must be between 0 and 1")
    if abs(sum(scores.values()) - 1.0) > 0.05:
        raise ValueError("scores must sum to 1.0")

    primary = assessment.get("primary_emotion")
    if primary not in NRC_EMOTIONS or scores[primary] != max(scores.values()):
        raise ValueError("primary_emotion must match the highest score")

    confidence = assessment.get("confidence")
    _ensure_number(confidence, "confidence")
    if not 0 <= confidence <= 1:
        raise ValueError("confidence must be between 0 and 1")
    if not isinstance(assessment.get("clarification_needed"), bool):
        raise TypeError("clarification_needed must be a boolean")

    evidence = assessment.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        raise ValueError("evidence must not be empty")
    session_text = "\n".join(current_texts)
    linked_emotions = set()
    for item in evidence:
        quote = item.get("quote") if isinstance(item, dict) else None
        emotions = item.get("emotions") if isinstance(item, dict) else None
        if not isinstance(quote, str) or not quote.strip() or quote not in session_text:
            raise ValueError("evidence quote must exist in current session")
        if not isinstance(emotions, list) or not emotions or any(
            emotion not in NRC_EMOTIONS for emotion in emotions
        ):
            raise ValueError("evidence emotions must use NRC_EMOTIONS")
        linked_emotions.update(emotions)
        interpretation = item.get("interpretation")
        if not isinstance(interpretation, str) or not interpretation.strip():
            raise ValueError("evidence interpretation must not be empty")

    active_emotions = {emotion for emotion, score in scores.items() if score > 0.1}
    if not active_emotions.issubset(linked_emotions):
        raise ValueError("every non-zero emotion must have current-session evidence")


def derive_legacy_fields(assessment: dict) -> dict:
    primary = assessment["primary_emotion"]
    emotion_label, face_state = LEGACY_EMOTION_MAP[primary]
    source_by_emotion = {}
    for item in assessment["evidence"]:
        for emotion in item["emotions"]:
            source_by_emotion.setdefault(emotion, item["quote"])

    top = sorted(assessment["scores"].items(), key=lambda item: item[1], reverse=True)[:3]
    top = [(emotion, score) for emotion, score in top if score > 0]
    total = sum(score for _, score in top)
    blend = [
        {
            "emotion": NRC_DISPLAY_NAMES[emotion],
            "weight": round(score / total, 4),
            "source": source_by_emotion.get(emotion, assessment["evidence"][0]["quote"] if assessment.get("evidence") else ""),
        }
        for emotion, score in top
    ]
    blend[-1]["weight"] = round(
        1.0 - sum(item["weight"] for item in blend[:-1]), 4
    )
    return {
        "emotion_label": emotion_label,
        "face_state": face_state,
        "emotion_blend": blend,
    }


def build_target_flavor_vector(scores: dict) -> dict:
    return {
        key: round(
            sum(
                scores[emotion] * FLAVOR_MATRIX[emotion][index]
                for emotion in NRC_EMOTIONS
            )
        )
        for index, key in enumerate(FLAVOR_KEYS)
    }


def build_ambient_plan(assessment: dict) -> dict:
    ranked = sorted(
        assessment["scores"].items(), key=lambda item: item[1], reverse=True
    )
    primary, primary_score = ranked[0]
    secondary, secondary_score = ranked[1]
    primary_values = AMBIENT_PRESETS[primary]
    secondary_values = AMBIENT_PRESETS[secondary]
    ratio = min(
        secondary_score / max(primary_score + secondary_score, 0.0001), 0.35
    )

    def blend_value(key: str) -> int:
        return round(
            primary_values[key] * (1 - ratio) + secondary_values[key] * ratio
        )

    return {
        "enabled": True,
        "disclaimer": "方案预览，不会实际控制设备",
        "air_conditioner": {
            "temperature_c": min(28, max(16, blend_value("temperature_c"))),
            "reason": primary_values["air_conditioner_reason"],
        },
        "light": {
            "brightness_percent": min(
                100, max(20, blend_value("brightness_percent"))
            ),
            "color_temperature_k": min(
                6500, max(2700, blend_value("color_temperature_k"))
            ),
            "reason": primary_values["light_reason"],
        },
        "air_purifier": {
            "mode": primary_values["purifier_mode"],
            "reason": primary_values["air_purifier_reason"],
        },
    }


def build_fallback_emotion_assessment(user_text: str) -> dict:
    return {
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
                "quote": user_text,
                "emotions": ["trust"],
                "interpretation": "分析链路异常，使用中性兼容状态",
            }
        ],
        "clarification_needed": True,
    }


# ==================== VAD 三维连续向量 ====================
# 基于 Russell (1980) 环形模型 + Mehrabian & Russell (1974) PAD 模型
# 各 NRC 情绪对应的 VAD 代表性值（-1.0 ~ 1.0）

VAD_WEIGHTS: dict[str, tuple[float, float, float]] = {
    "anger":        (-0.60,  0.70,  0.40),
    "anticipation": ( 0.30,  0.50,  0.30),
    "disgust":      (-0.70,  0.30,  0.50),
    "fear":         (-0.70,  0.80, -0.60),
    "joy":          ( 0.80,  0.60,  0.50),
    "sadness":      (-0.70, -0.30, -0.50),
    "surprise":     ( 0.20,  0.90,  0.10),
    "trust":        ( 0.50,  0.20,  0.60),
}


def build_vad_vector(scores: dict[str, float]) -> dict:
    """从 NRC 八类分数加权推导 VAD 三维连续向量。不依赖 LLM 输出，纯后处理。"""
    valence = sum(scores[e] * VAD_WEIGHTS[e][0] for e in NRC_EMOTIONS)
    arousal = sum(scores[e] * VAD_WEIGHTS[e][1] for e in NRC_EMOTIONS)
    dominance = sum(scores[e] * VAD_WEIGHTS[e][2] for e in NRC_EMOTIONS)
    intensity = max(scores.values())
    return {
        "valence": round(valence, 4),
        "arousal": round(arousal, 4),
        "dominance": round(dominance, 4),
        "intensity": round(intensity, 4),
    }


def compute_emotion_trend(history: list[dict]) -> str:
    """根据最近 N 轮 VAD 历史判断情绪趋势。

    history: list of {"valence": float, "arousal": float}
    返回: "escalating" / "steady" / "easing"
    """
    if len(history) < 2:
        return "steady"

    recent = history[-3:] if len(history) >= 3 else history

    v_deltas = [recent[i]["valence"] - recent[i - 1]["valence"] for i in range(1, len(recent))]
    a_deltas = [recent[i]["arousal"] - recent[i - 1]["arousal"] for i in range(1, len(recent))]

    avg_v_delta = sum(v_deltas) / len(v_deltas)
    avg_a_delta = sum(a_deltas) / len(a_deltas)

    # 效价下降 或 唤醒度上升 → 情绪升级
    if avg_v_delta < -0.08 or avg_a_delta > 0.08:
        return "escalating"
    # 效价上升 或 唤醒度下降 → 情绪缓解
    if avg_v_delta > 0.08 or avg_a_delta < -0.08:
        return "easing"

    return "steady"


TREND_DISPLAY = {
    "escalating": "↑ 上升",
    "steady": "→ 稳定",
    "easing": "↓ 缓解",
}

def build_uev(assessment: dict, emotion_history: list | None = None) -> dict:
    """从 emotion_assessment 构建标准化 Universal Emotion Vector"""
    from datetime import datetime, timezone, timedelta

    scores = assessment.get("scores", {})
    vad = assessment.get("vad", {})
    evidence = assessment.get("evidence", [])

    # 构建 trend_history
    trend_history = []
    if emotion_history:
        trend_history = [h["label"] if isinstance(h, dict) else str(h) for h in emotion_history[-5:]]

    return {
        "valence": round(vad.get("valence", 0.0), 4),
        "arousal": round(vad.get("arousal", 0.0), 4),
        "dominance": round(vad.get("dominance", 0.0), 4),
        "intensity": round(vad.get("intensity", 0.0), 4),
        "nrc_scores": {k: round(v, 4) for k, v in scores.items()},
        "primary_emotion": assessment.get("primary_emotion", "trust"),
        "confidence": round(assessment.get("confidence", 0.0), 4),
        "trend": assessment.get("trend", "steady"),
        "trend_display": assessment.get("trend_display", ""),
        "trend_history": trend_history,
        "evidence_count": len(evidence),
        "evidence_summary": [
            {"quote": e.get("quote", ""), "emotions": e.get("emotions", [])}
            for e in evidence
        ],
        "timestamp": datetime.now(timezone(timedelta(hours=8))).isoformat(),
    }
