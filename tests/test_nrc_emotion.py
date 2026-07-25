import unittest

from emotender_emotion import (
    build_ambient_plan,
    build_target_flavor_vector,
    derive_legacy_fields,
    validate_emotion_assessment,
)


def fear_assessment():
    return {
        "taxonomy": "nrc_emolex_8",
        "scores": {
            "anger": 0.0,
            "anticipation": 0.25,
            "disgust": 0.0,
            "fear": 0.75,
            "joy": 0.0,
            "sadness": 0.0,
            "surprise": 0.0,
            "trust": 0.0,
        },
        "primary_emotion": "fear",
        "confidence": 0.82,
        "evidence": [
            {
                "quote": "明天就要答辩了，我脑子停不下来",
                "emotions": ["fear", "anticipation"],
                "interpretation": "用户担心即将发生的答辩",
            }
        ],
        "clarification_needed": False,
    }


class NrcEmotionTests(unittest.TestCase):
    def test_valid_assessment_passes(self):
        validate_emotion_assessment(
            fear_assessment(), ["明天就要答辩了，我脑子停不下来"]
        )

    def test_missing_fixed_score_key_fails(self):
        data = fear_assessment()
        del data["scores"]["trust"]
        with self.assertRaisesRegex(ValueError, "scores keys"):
            validate_emotion_assessment(data, [data["evidence"][0]["quote"]])

    def test_quote_outside_current_session_fails(self):
        with self.assertRaisesRegex(ValueError, "evidence quote"):
            validate_emotion_assessment(fear_assessment(), ["今天只是普通的一天"])

    def test_primary_emotion_must_match_highest_score(self):
        data = fear_assessment()
        data["primary_emotion"] = "joy"
        with self.assertRaisesRegex(ValueError, "primary_emotion"):
            validate_emotion_assessment(data, [data["evidence"][0]["quote"]])

    def test_legacy_fields_are_deterministic(self):
        fields = derive_legacy_fields(fear_assessment())
        self.assertEqual(fields["emotion_label"], "焦虑")
        self.assertEqual(fields["face_state"], "focused")
        self.assertEqual(fields["emotion_blend"][0]["emotion"], "恐惧")
        self.assertAlmostEqual(
            sum(item["weight"] for item in fields["emotion_blend"]), 1.0
        )

    def test_flavor_vector_has_exact_six_dimensions(self):
        vector = build_target_flavor_vector(fear_assessment()["scores"])
        self.assertEqual(
            set(vector), {"甜度", "茶感", "奶香", "果香", "清爽度", "口感层次"}
        )
        self.assertTrue(all(0 <= value <= 100 for value in vector.values()))

    def test_ambient_plan_uses_product_bounds(self):
        plan = build_ambient_plan(fear_assessment())
        self.assertTrue(plan["enabled"])
        self.assertGreaterEqual(plan["air_conditioner"]["temperature_c"], 16)
        self.assertLessEqual(plan["air_conditioner"]["temperature_c"], 28)
        self.assertIn(
            plan["air_purifier"]["mode"], {"auto", "silent", "boost"}
        )


if __name__ == "__main__":
    unittest.main()
