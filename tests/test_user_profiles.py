import importlib
import os
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


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
        "user_text": "今天想喝点清爽的。",
        "emotion_label": "清醒",
        "emotion_blend": [{"emotion": "清醒", "weight": 1.0, "source": "用户明确说想喝清爽一点的。"}],
        "complex_emotion": "用户表达稳定，需求明确。",
        "need_summary": "希望获得一杯清爽定制饮品。",
        "drink_name": "冷启动",
        "recipe_modules": ["clear_balance", "bitter_focus"],
        "flavor_profile": "清爽、微苦、低甜",
        "color_profile": "透明偏冷调",
        "face_state": "focused",
        "bartender_line": "我给你一杯清爽一点的。",
        "action_sequence": "make_cold_start",
        "feedback_prompt": "喝完告诉我你的感受。",
        "recommendation_reason": "你现在想把状态理清楚，这杯冷启动会用清爽低甜的味道陪你找回节奏。",
    }


class UserProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.original_profile_dir = backend.PROFILE_DIR
        backend.PROFILE_DIR = self.temp_dir / "profiles"
        backend.reset_conversation_state()
        backend.current_username = None

    def tearDown(self):
        backend.PROFILE_DIR = self.original_profile_dir
        backend.reset_conversation_state()
        backend.current_username = None
        shutil.rmtree(self.temp_dir)

    def test_login_creates_profile_and_sets_current_user(self):
        response = backend.login_user_api(backend.UserLoginRequest(username="alice"))

        self.assertTrue(response["ok"])
        self.assertEqual(response["username"], "alice")
        self.assertEqual(backend.current_username, "alice")
        profile = backend.load_user_profile("alice")
        self.assertEqual(profile["username"], "alice")
        self.assertEqual(profile["session_summaries"], [])

    def test_prompt_profile_context_excludes_historical_emotions_and_sessions(self):
        profile_context = {
            "mode": "logged_in",
            "username": "alice",
            "stable_profile": {
                "taste_preferences": ["低甜"],
                "emotion_patterns": ["上次心情很好"],
                "drink_history": ["冷启动"],
                "conversation_style": ["偏好简短交流"],
                "avoidances": ["乳制品"],
            },
            "recent_session_summaries": [
                {"session_emotion": "兴奋", "event_summary": "上次考试考得很好。"}
            ],
        }

        prompt_context = backend.build_prompt_profile_context(profile_context)

        self.assertEqual(prompt_context["taste_preferences"], ["低甜"])
        self.assertEqual(prompt_context["drink_history"], ["冷启动"])
        self.assertEqual(prompt_context["conversation_style"], ["偏好简短交流"])
        self.assertEqual(prompt_context["avoidances"], ["乳制品"])
        self.assertNotIn("emotion_patterns", prompt_context)
        self.assertNotIn("recent_session_summaries", prompt_context)

    def test_process_user_text_accepts_username_and_returns_profile_context(self):
        backend.save_user_profile(
            "alice",
            {
                "username": "alice",
                "created_at": "2026-07-10T00:00:00",
                "updated_at": "2026-07-10T00:00:00",
                "stable_profile": {
                    "taste_preferences": ["低甜", "清爽"],
                    "emotion_patterns": ["疲惫时偏好低刺激饮品"],
                    "drink_history": ["冷启动"],
                    "conversation_style": [],
                    "avoidances": [],
                },
                "session_summaries": [],
            },
        )
        llm_result = base_result("recommendation")

        with patch.object(backend, "analyze_text", return_value=llm_result) as mocked:
            response = backend.process_user_text("今天想喝点清爽的。", username="alice")

        self.assertTrue(response["ok"])
        self.assertEqual(response["username"], "alice")
        self.assertIn("低甜", response["profile_context"]["stable_profile"]["taste_preferences"])
        mocked.assert_called_once()
        self.assertEqual(mocked.call_args.args[2]["username"], "alice")

    def test_recommendation_result_includes_drink_metadata_for_receipt(self):
        llm_result = base_result("recommendation")

        with patch.object(backend, "analyze_text", return_value=llm_result):
            response = backend.process_user_text("推荐一杯清爽的。")

        metadata = response["control_json"]["drink_metadata"]
        self.assertEqual(metadata["name"], "冷启动")
        self.assertEqual(metadata["name_en"], "Cold Start")
        self.assertIn("backstory", metadata)
        self.assertIn("serve_line", metadata)
        self.assertIn("recipe", metadata)
        self.assertIn("color", metadata)

    def test_bar_chat_result_has_no_drink_metadata(self):
        llm_result = base_result("bar_chat")
        llm_result["drink_name"] = backend.NO_FORMAL_DRINK_NAME
        llm_result["recipe_modules"] = []
        llm_result["flavor_profile"] = backend.NO_FORMAL_DRINK_NAME
        llm_result["color_profile"] = backend.NO_FORMAL_DRINK_NAME

        with patch.object(backend, "analyze_text", return_value=llm_result):
            response = backend.process_user_text("我今天心情不错。")

        self.assertIsNone(response["control_json"]["drink_metadata"])

    def test_logout_summarizes_session_into_profile_and_resets_state(self):
        backend.current_username = "alice"
        backend.update_conversation_state(base_result("recommendation"))
        summary = {
            "date": "2026-07-10",
            "username": "alice",
            "session_emotion": "清醒",
            "drink_name": "冷启动",
            "drink_result": "已推荐",
            "event_summary": "用户想喝清爽低甜的饮品。",
            "taste_preferences": ["清爽", "低甜"],
            "emotional_pattern": "清醒时会明确描述口味。",
            "future_hint": "之后优先考虑清爽低甜。",
        }

        with patch.object(backend, "summarize_session_for_profile", return_value=summary):
            response = backend.logout_user_api(backend.UserLogoutRequest(username="alice"))

        self.assertTrue(response["ok"])
        self.assertEqual(response["username"], "alice")
        self.assertEqual(response["saved_summary"]["drink_name"], "冷启动")
        profile = backend.load_user_profile("alice")
        self.assertEqual(profile["session_summaries"][0]["event_summary"], "用户想喝清爽低甜的饮品。")
        self.assertIn("清爽", profile["stable_profile"]["taste_preferences"])
        self.assertEqual(backend.get_conversation_state()["history"], [])
        self.assertIsNone(backend.current_username)


if __name__ == "__main__":
    unittest.main()
