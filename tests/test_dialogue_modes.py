import importlib
import json
import os
import sys
import types
import unittest
from unittest.mock import patch
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
        "emotion_blend": [{"emotion": "疲惫", "weight": 1.0, "source": "用户说今天真的挺累。"}],
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
        "recommendation_reason": "你今天真的挺累，这杯冷启动会用清爽低甜的口感陪你把节奏慢慢拉回来。",
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

    def test_emotion_blend_requires_current_session_source(self):
        data = base_result("recommendation")
        del data["emotion_blend"][0]["source"]

        with self.assertRaisesRegex(ValueError, "emotion_blend item missing source"):
            backend.validate_result(data)

    def test_recommendation_requires_personalized_reason(self):
        data = base_result("recommendation")
        data["recommendation_reason"] = ""

        with self.assertRaisesRegex(ValueError, "recommendation_reason must not be empty"):
            backend.validate_result(data)

    def test_prompt_library_does_not_duplicate_backend_drink_menu(self):
        with backend.PROMPT_LIBRARY_PATH.open("r", encoding="utf-8") as prompt_file:
            prompt_library = json.load(prompt_file)

        self.assertNotIn("hidden_drinks", prompt_library)

    def test_recommendation_rejects_drink_name_outside_backend_menu(self):
        data = base_result("recommendation")
        data["drink_name"] = "不存在的饮品"

        with self.assertRaisesRegex(ValueError, "Unknown drink_name"):
            backend.validate_result(data)

    def test_unknown_recommendation_drink_falls_back_with_receipt_metadata(self):
        llm_result = base_result("recommendation")
        llm_result["drink_name"] = "不存在的饮品"

        with patch.object(backend, "analyze_text", return_value=llm_result):
            response = backend.process_user_text("推荐一杯清爽一点的。")

        self.assertTrue(response["used_fallback"])
        self.assertIn("Unknown drink_name", response["llm_error"])
        self.assertEqual(response["control_json"]["drink_name"], "冷启动")
        self.assertEqual(response["control_json"]["drink_metadata"]["name"], "冷启动")

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

    def test_process_user_text_returns_control_json_and_updates_memory(self):
        llm_result = base_result("recommendation")
        llm_result["user_text"] = "我今天有点累，给我推荐一杯。"

        with patch.object(backend, "analyze_text", return_value=llm_result):
            response = backend.process_user_text("我今天有点累，给我推荐一杯。")

        self.assertTrue(response["ok"])
        self.assertEqual(response["user_text"], "我今天有点累，给我推荐一杯。")
        self.assertEqual(response["turn_type"], "recommendation")
        self.assertEqual(response["control_json"]["drink_name"], "冷启动")
        self.assertEqual(response["robot_reply_text"], "我先给你一杯清醒一点的。")
        self.assertEqual(len(response["conversation_state"]["history"]), 1)

    def test_affirmative_reply_after_recommendation_offer_switches_to_recommendation(self):
        chat_turn = base_result("bar_chat")
        chat_turn.update(
            {
                "user_text": "我今天有点累。",
                "drink_name": "无正式推荐",
                "recipe_modules": [],
                "flavor_profile": "无正式推荐",
                "color_profile": "无正式推荐",
                "bartender_line": "听起来你需要先缓一下。",
                "feedback_prompt": "要不要让我正式给你推荐一杯？",
            }
        )
        backend.update_conversation_state(chat_turn)

        llm_result = base_result("recommendation")
        llm_result["user_text"] = "好"

        with patch.object(backend, "analyze_text", return_value=llm_result) as mocked:
            response = backend.process_user_text("好")

        self.assertEqual(response["turn_type"], "recommendation")
        self.assertEqual(response["control_json"]["drink_name"], "冷启动")
        self.assertEqual(mocked.call_args.args[1], "recommendation")

    def test_llm_turn_type_can_override_keyword_router_hint(self):
        llm_result = base_result("recommendation")
        llm_result["user_text"] = "可以，你看着安排。"

        with patch.object(backend, "route_turn_type", return_value="bar_chat"):
            with patch.object(backend, "analyze_text", return_value=llm_result) as mocked:
                response = backend.process_user_text("可以，你看着安排。")

        self.assertEqual(mocked.call_args.args[1], "bar_chat")
        self.assertEqual(response["turn_type"], "recommendation")
        self.assertEqual(response["control_json"]["turn_type"], "recommendation")
        self.assertEqual(response["control_json"]["drink_name"], "冷启动")


if __name__ == "__main__":
    unittest.main()
