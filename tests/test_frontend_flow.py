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

    def test_recommendation_waits_in_chat_before_opening_preview(self):
        emotion_change = re.search(
            r"function onEmotionChange\(.*?\n}", self.html, re.DOTALL
        )
        self.assertIsNotNone(emotion_change)
        self.assertNotIn("confirmFlavor();", emotion_change.group(0))
        self.assertNotIn("enterRecommendationPreview(controlJson)", emotion_change.group(0))
        self.assertIn("prepareRecommendationPreview(controlJson)", emotion_change.group(0))

    def test_chat_and_report_have_explicit_back_navigation(self):
        self.assertIn('id="recommendation-entry"', self.html)
        self.assertIn('onclick="openRecommendationPreview()">查看推荐方案', self.html)
        self.assertIn('onclick="returnToConversation()">返回聊天', self.html)
        self.assertIn('onclick="returnToRecommendationPreview()">返回确认', self.html)

    def test_flavor_confirmation_button_belongs_to_preview_not_report_chart(self):
        preview_start = self.html.find('<section id="recommendation-preview"')
        report_start = self.html.find('<section id="final-report"')
        preview_markup = self.html[preview_start:report_start]
        self.assertIn('id="btnConfirm"', preview_markup)
        flavor = re.search(
            r'<div id="flavor-section">.*?</div>\s*</div>',
            preview_markup,
            re.DOTALL,
        )
        self.assertIsNotNone(flavor)
        self.assertNotIn('id="btnConfirm"', flavor.group(0))

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
            "04 / SPACE SETTING",
            "05 / YOUR RECEIPT",
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
        self.assertIn("#interaction-dock.report-mode { display:none; }", self.html)
        self.assertIn(
            "dock.classList.toggle('report-mode', mode === 'report')", self.html
        )

    def test_flavor_chart_uses_light_grid_and_bloom_visual(self):
        chart = re.search(
            r"function renderFlavorChart\(animate\).*?\n}", self.html, re.DOTALL
        )
        self.assertIsNotNone(chart)
        body = chart.group(0)
        self.assertIn("flavor-bloom", body)
        self.assertIn("轻量刻度环", body)
        self.assertNotIn("外圈齿轮环", body)
        self.assertNotIn("flavor-dot", body)
        preview = re.search(
            r"function enterRecommendationPreview\(.*?\n}", self.html, re.DOTALL
        )
        self.assertIsNotNone(preview)
        self.assertIn("renderFlavorChart(true)", preview.group(0))

    def test_composition_visual_replaces_random_reference_photo(self):
        self.assertIn('id="drink-composition"', self.html)
        self.assertIn('id="composition-caption">饮品构成示意', self.html)
        self.assertNotIn('id="flavor-photo"', self.html)
        self.assertNotIn("Math.floor(Math.random() * 6) + 1", self.html)
        self.assertNotIn("'/static/photo/' + randIdx + '.png'", self.html)

    def test_flavor_chart_is_read_only(self):
        self.assertNotIn("onDotMouseDown", self.html)
        self.assertNotIn("onDotTouchStart", self.html)
        self.assertNotIn("onSvgClick", self.html)
        self.assertNotIn("updateFlavorFromMouse", self.html)

    def test_flavor_chart_uses_broad_beverage_axes(self):
        self.assertIn(
            'const FLAVOR_KEYS = ["甜度","茶感","奶香","果香","清爽度","口感层次"]',
            self.html,
        )
        self.assertIn("next.甜度", self.html)
        self.assertIn("next.清爽度", self.html)
        self.assertIn("next.奶香", self.html)
        self.assertIn("next.口感层次", self.html)
        self.assertNotIn('const FLAVOR_KEYS = ["甜","鲜","酸","咸","涩","苦"]', self.html)

    def test_interface_uses_light_beverage_theme(self):
        self.assertIn('<body data-theme="light-beverage">', self.html)
        self.assertIn("--canvas: #f4f7f6", self.html)
        self.assertIn("--surface: #ffffff", self.html)
        self.assertIn("--accent: #e96f51", self.html)

    def test_animated_face_uses_light_stage_in_live_and_report_views(self):
        self.assertIn(
            '<rect x="0" y="0" width="400" height="400" fill="#f9fbfa"/>',
            self.html,
        )
        self.assertNotIn(
            '<rect x="0" y="0" width="400" height="400" fill="#000000"/>',
            self.html,
        )
        self.assertIn("ctx.fillStyle='#f9fbfa'", self.html)

    def test_preview_opens_grouped_specification_editor(self):
        self.assertIn('id="btnCustomize"', self.html)
        self.assertIn('onclick="openCustomization()">调整规格', self.html)
        self.assertIn('id="customization-modal"', self.html)
        self.assertIn('id="customization-summary"', self.html)
        self.assertIn('data-spec-group="口感"', self.html)
        self.assertIn('data-spec-group="温度"', self.html)
        self.assertIn('data-spec-group="甜度"', self.html)
        self.assertIn('onclick="closeCustomization()">取消', self.html)
        self.assertIn('onclick="confirmCustomization()">确认调整', self.html)

    def test_ambient_opt_in_sits_before_confirmation(self):
        preview = self.html[
            self.html.find('<section id="recommendation-preview"'):
            self.html.find('<div id="customization-modal"')
        ]
        self.assertIn('id="ambient-plan-toggle"', preview)
        self.assertLess(
            preview.find('id="ambient-plan-toggle"'),
            preview.find('id="btnConfirm"'),
        )
        self.assertIn("仅生成建议，不会实际控制设备", preview)

    def test_final_report_has_optional_ambient_section(self):
        self.assertIn('id="ambient-plan-section"', self.html)
        self.assertIn('id="ambient-air-conditioner"', self.html)
        self.assertIn('id="ambient-light"', self.html)
        self.assertIn('id="ambient-air-purifier"', self.html)
        self.assertIn("C('/api/ambient/plan'", self.html)

    def test_emotion_pie_supports_nrc_labels(self):
        for label in (
            "愤怒",
            "期待",
            "厌恶",
            "恐惧",
            "喜悦",
            "悲伤",
            "惊讶",
            "信任",
        ):
            self.assertIn(f'"{label}"', self.html)


if __name__ == "__main__":
    unittest.main()
