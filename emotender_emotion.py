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

    active_emotions = {emotion for emotion, score in scores.items() if score > 0}
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
            "source": source_by_emotion[emotion],
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
