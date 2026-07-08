import importlib
import os
import sys
import types
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("LLM_API_KEY", "test-key")
os.environ.setdefault("LLM_BASE_URL", "https://example.test/v1")
os.environ.setdefault("LLM_MODEL", "test-model")


class FakeAutoModel:
    def __init__(self, *args, **kwargs):
        pass

    def generate(self, *args, **kwargs):
        return [{"text": "测试文本"}]


fake_funasr = types.ModuleType("funasr")
fake_funasr.AutoModel = FakeAutoModel
sys.modules.setdefault("funasr", fake_funasr)


backend = importlib.import_module("emotender_backend")


def base_result(turn_type="recommendation"):
    return {
        "schema_version": "1.0",
        "turn_type": turn_type,
        "user_text": "今天真的挺累的。",
        "emotion_label": "疲惫",
        "emotion_blend": [{"emotion": "疲惫", "weight": 1.0}],
        "complex_emotion": "用户处在低能量状态。",
        "need_summary": "需要被接住。",
        "drink_name": "冷启动",
        "recipe_modules": ["clear_balance", "bitter_focus"],
        "flavor_profile": "清爽、微苦、低甜",
        "color_profile": "透明偏冷调",
        "face_state": "focused",
        "bartender_line": "我先给你一杯清醒一点的。",
        "action_sequence": "make_cold_start",
        "feedback_prompt": "喝完告诉我感受。",
    }


class DialogueModeTests(unittest.TestCase):
    def setUp(self):
        backend.reset_conversation_state()

    def test_bar_chat_allows_no_drink_plan_but_requires_robot_control(self):
        data = base_result("bar_chat")
        data.update(
            {
                "drink_name": "无正式推荐",
                "recipe_modules": [],
                "flavor_profile": "无正式推荐",
                "color_profile": "无正式推荐",
                "face_state": "gentle",
                "action_sequence": "gesture_thinking",
            }
        )

        backend.validate_result(data)

    def test_recommendation_still_requires_recipe_modules(self):
        data = base_result("recommendation")
        data["recipe_modules"] = []

        with self.assertRaisesRegex(ValueError, "recipe_modules must not be empty"):
            backend.validate_result(data)

    def test_memory_writer_records_chat_turn_without_drink_plan(self):
        data = base_result("bar_chat")
        data.update(
            {
                "drink_name": "无正式推荐",
                "recipe_modules": [],
                "face_state": "listening",
                "action_sequence": "gesture_thinking",
            }
        )

        backend.update_conversation_state(data)
        state = backend.get_conversation_state()

        self.assertEqual(len(state["history"]), 1)
        self.assertEqual(state["history"][0]["turn_type"], "bar_chat")
        self.assertEqual(state["history"][0]["emotion_label"], "疲惫")
        self.assertNotIn("drink_name", state["history"][0])
        self.assertIn("疲惫", state["summary"])

    def test_robot_reply_text_appends_feedback_prompt_for_bar_chat(self):
        data = base_result("bar_chat")
        data["bartender_line"] = "挺好。好心情不用急着花掉。"
        data["feedback_prompt"] = "这份好心情，是因为什么来的？"

        reply = backend.build_robot_reply_text(data)

        self.assertEqual(reply, "挺好。好心情不用急着花掉。\n这份好心情，是因为什么来的？")

    def test_robot_reply_text_uses_only_bartender_line_for_recommendation(self):
        data = base_result("recommendation")
        data["bartender_line"] = "那我做主，给你一杯冷启动。"
        data["feedback_prompt"] = "喝完告诉我感受。"

        reply = backend.build_robot_reply_text(data)

        self.assertEqual(reply, "那我做主，给你一杯冷启动。")


if __name__ == "__main__":
    unittest.main()
