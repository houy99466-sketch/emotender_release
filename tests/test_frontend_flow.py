import re
import unittest
from pathlib import Path


INDEX = Path(__file__).resolve().parents[1] / "static" / "index.html"


class FrontendFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = INDEX.read_text(encoding="utf-8")

    def test_conversation_view_keeps_animated_face_and_history(self):
        conversation = re.search(
            r'<main id="conversation-view".*?</main>', self.html, re.DOTALL
        )
        self.assertIsNotNone(conversation)
        markup = conversation.group(0)
        self.assertIn('id="crt-screen"', markup)
        self.assertIn('id="conversation-list"', markup)

    def test_recommendation_does_not_print_receipt_automatically(self):
        emotion_change = re.search(
            r"function onEmotionChange\(.*?\n}", self.html, re.DOTALL
        )
        self.assertIsNotNone(emotion_change)
        self.assertNotIn("confirmFlavor();", emotion_change.group(0))
        self.assertIn("enterRecommendationPreview(controlJson)", emotion_change.group(0))

    def test_final_report_contains_confirmed_face_and_required_sections(self):
        start = self.html.find('<section id="final-report"')
        end = self.html.find('<div id="reply-area"', start)
        self.assertGreaterEqual(start, 0)
        self.assertGreater(end, start)
        markup = self.html[start:end]
        self.assertIn('id="report-face-image"', markup)
        for label in (
            "01 / EMOTION MIX",
            "02 / WHY THIS POUR",
            "03 / FLAVOR PROFILE",
            "04 / YOUR RECEIPT",
        ):
            self.assertIn(label, markup)

    def test_confirmation_captures_face_before_showing_report(self):
        confirmation = re.search(
            r"async function confirmFlavor\(\).*?\n}", self.html, re.DOTALL
        )
        self.assertIsNotNone(confirmation)
        body = confirmation.group(0)
        self.assertIn("createFaceSnapshotDataUrl()", body)
        self.assertIn("enterFinalReport", body)

    def test_final_report_hides_preview_confirmation_and_bottom_dock(self):
        self.assertIn("#final-report #btnConfirm { display:none; }", self.html)
        self.assertIn("#interaction-dock.report-mode { display:none; }", self.html)
        self.assertIn(
            "dock.classList.toggle('report-mode', mode === 'report')", self.html
        )


if __name__ == "__main__":
    unittest.main()
