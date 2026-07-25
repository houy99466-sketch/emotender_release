# NRC Emotion and Ambient Plan Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace free-form six-label emotion inference with NRC eight-category structured scoring, then add an optional deterministic air-conditioner, light, and air-purifier plan to the recommendation flow.

**Architecture:** Add a focused `emotender_emotion.py` domain module that owns exact NRC identifiers, validation, compatibility conversion, target flavor calculation, and ambient presets. `emotender_backend.py` remains responsible for LLM orchestration and HTTP endpoints; `static/index.html` remains responsible for the toggle, report rendering, and image export.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, OpenAI-compatible chat completions, unittest, HTML/CSS/vanilla JavaScript.

---

## File Structure

- Create `emotender_emotion.py`: NRC constants, validation, legacy conversion, flavor matrix, ambient preset generation.
- Create `tests/test_nrc_emotion.py`: deterministic unit tests for NRC validation, conversion, flavor vectors, and ambient bounds.
- Modify `emotender_backend.py`: Prompt schema, fallback data, response validation, disabled ambient default, and `/api/ambient/plan`.
- Modify `tests/test_dialogue_modes.py`: add NRC assessment fixtures and backend integration assertions.
- Modify `static/index.html`: NRC pie colors, ambient opt-in control, report section, API call, reset behavior, and responsive styles.
- Modify `tests/test_frontend_flow.py`: verify opt-in placement, report rendering, API request, and export inclusion.
- Modify `README.md` and `CHANGELOG.md`: document the new response field, endpoint, limitations, and test commands.

### Task 1: Add the NRC Domain Module

**Files:**
- Create: `emotender_emotion.py`
- Create: `tests/test_nrc_emotion.py`

- [ ] **Step 1: Write failing validation and mapping tests**

Create `tests/test_nrc_emotion.py` with tests that import these exact functions:

```python
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
        "evidence": [{
            "quote": "明天就要答辩了，我脑子停不下来",
            "emotions": ["fear", "anticipation"],
            "interpretation": "用户担心即将发生的答辩",
        }],
        "clarification_needed": False,
    }


class NrcEmotionTests(unittest.TestCase):
    def test_valid_assessment_passes(self):
        validate_emotion_assessment(
            fear_assessment(),
            ["明天就要答辩了，我脑子停不下来"],
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
        self.assertIn(plan["air_purifier"]["mode"], {"auto", "silent", "boost"})


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the new tests and verify the module is missing**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_nrc_emotion -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'emotender_emotion'`.

- [ ] **Step 3: Implement exact NRC identifiers and deterministic mappings**

Create `emotender_emotion.py` with:

```python
from __future__ import annotations

from copy import deepcopy

NRC_EMOTIONS = (
    "anger", "anticipation", "disgust", "fear",
    "joy", "sadness", "surprise", "trust",
)

NRC_DISPLAY_NAMES = {
    "anger": "愤怒", "anticipation": "期待", "disgust": "厌恶", "fear": "恐惧",
    "joy": "喜悦", "sadness": "悲伤", "surprise": "惊讶", "trust": "信任",
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
    "anger":       (20, 70, 20, 30, 80, 65),
    "anticipation":(45, 55, 20, 65, 75, 75),
    "disgust":     (15, 65, 10, 35, 90, 55),
    "fear":        (55, 35, 65, 30, 45, 55),
    "joy":         (65, 30, 35, 80, 75, 70),
    "sadness":     (70, 25, 80, 30, 35, 65),
    "surprise":    (50, 35, 20, 85, 80, 80),
    "trust":       (55, 45, 70, 35, 45, 75),
}

AMBIENT_PRESETS = {
    "anger":       (23, 45, 3500, "auto", "降低环境刺激并保持空气流动"),
    "anticipation":(24, 70, 4500, "auto", "保持明亮且有行动感的空间"),
    "disgust":     (22, 75, 5000, "boost", "增强清洁与通透的空间感受"),
    "fear":        (25, 40, 3000, "silent", "提供低刺激且安静的空间氛围"),
    "joy":         (24, 80, 4200, "auto", "保留明亮轻快的空间状态"),
    "sadness":     (25, 45, 3000, "silent", "提供柔和安静的陪伴氛围"),
    "surprise":    (23, 85, 5000, "auto", "强化清晰明快的空间感受"),
    "trust":       (25, 55, 3200, "silent", "维持稳定柔和的空间氛围"),
}


def _ensure_number(value, field):
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
        if not isinstance(item.get("interpretation"), str) or not item["interpretation"].strip():
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
    blend = [{
        "emotion": NRC_DISPLAY_NAMES[emotion],
        "weight": round(score / total, 4),
        "source": source_by_emotion.get(emotion, assessment["evidence"][0]["quote"]),
    } for emotion, score in top]
    blend[-1]["weight"] = round(1.0 - sum(item["weight"] for item in blend[:-1]), 4)
    return {"emotion_label": emotion_label, "face_state": face_state, "emotion_blend": blend}


def build_target_flavor_vector(scores: dict) -> dict:
    return {
        key: round(sum(scores[emotion] * FLAVOR_MATRIX[emotion][index] for emotion in NRC_EMOTIONS))
        for index, key in enumerate(FLAVOR_KEYS)
    }


def build_ambient_plan(assessment: dict) -> dict:
    ranked = sorted(assessment["scores"].items(), key=lambda item: item[1], reverse=True)
    primary, primary_score = ranked[0]
    secondary, secondary_score = ranked[1]
    primary_values = AMBIENT_PRESETS[primary]
    secondary_values = AMBIENT_PRESETS[secondary]
    ratio = min(secondary_score / max(primary_score + secondary_score, 0.0001), 0.35)
    temperature = round(primary_values[0] * (1 - ratio) + secondary_values[0] * ratio)
    brightness = round(primary_values[1] * (1 - ratio) + secondary_values[1] * ratio)
    color_temperature = round(primary_values[2] * (1 - ratio) + secondary_values[2] * ratio)
    return {
        "enabled": True,
        "disclaimer": "方案预览，不会实际控制设备",
        "air_conditioner": {
            "temperature_c": min(28, max(16, temperature)),
            "reason": primary_values[4],
        },
        "light": {
            "brightness_percent": min(100, max(20, brightness)),
            "color_temperature_k": min(6500, max(2700, color_temperature)),
            "reason": primary_values[4],
        },
        "air_purifier": {"mode": primary_values[3], "reason": primary_values[4]},
    }
```

- [ ] **Step 4: Run the unit tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_nrc_emotion -v
```

Expected: 7 tests PASS.

- [ ] **Step 5: Commit the domain module**

```powershell
git add emotender_emotion.py tests/test_nrc_emotion.py
git commit -m "feat: add deterministic NRC emotion engine"
```

### Task 2: Integrate NRC Output Into the LLM Pipeline

**Files:**
- Modify: `emotender_backend.py:20-25,617-749,752-930,943-988`
- Modify: `tests/test_dialogue_modes.py`

- [ ] **Step 1: Extend the existing backend fixture and add failing integration tests**

Add an `emotion_assessment_for(text, primary="sadness")` fixture that returns all eight keys, uses `text` as its evidence quote, and assigns the highest score to `primary`. Make `base_result()` call it with its own `user_text`. Add this helper for existing tests that replace the user text:

```python
def set_result_user_text(data, text, primary="sadness"):
    data["user_text"] = text
    data["emotion_assessment"] = emotion_assessment_for(text, primary)
    return data
```

Update every test that passes a patched LLM result into `process_user_text()` to call `set_result_user_text()` with the exact input passed to `process_user_text()`. This keeps the evidence check meaningful instead of weakening it for tests. Add tests asserting:

```python
def test_validation_requires_nrc_assessment(self):
    data = base_result("recommendation")
    del data["emotion_assessment"]
    with self.assertRaisesRegex(ValueError, "Missing field: emotion_assessment"):
        backend.validate_result(data)

def test_process_user_text_derives_legacy_fields_from_nrc(self):
    data = base_result("recommendation")
    set_result_user_text(data, "明天就要答辩了，我脑子停不下来，推荐一杯。", "fear")
    data["emotion_label"] = "错误旧标签"
    data["face_state"] = "happy"
    with patch.object(backend, "analyze_text", return_value=data):
        response = backend.process_user_text("明天就要答辩了，我脑子停不下来，推荐一杯。")
    control = response["control_json"]
    self.assertEqual(control["emotion_label"], "焦虑")
    self.assertEqual(control["face_state"], "focused")
    self.assertIn("target_flavor_vector", control)
```

- [ ] **Step 2: Run the two tests and verify they fail**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_dialogue_modes.DialogueModeTests.test_validation_requires_nrc_assessment tests.test_dialogue_modes.DialogueModeTests.test_process_user_text_derives_legacy_fields_from_nrc -v
```

Expected: FAIL because `emotion_assessment` is not required and legacy fields are not derived.

- [ ] **Step 3: Import the NRC engine and extend the Prompt schema**

In `emotender_backend.py`, import:

```python
from emotender_emotion import (
    NRC_EMOTIONS,
    build_target_flavor_vector,
    derive_legacy_fields,
    validate_emotion_assessment,
)
```

Add `emotion_assessment` to the required Prompt fields and include the exact fixed keys from `NRC_EMOTIONS`. State that the LLM must extract current-session quotes first, then score all eight keys; scores sum to 1.0; profile emotion history is forbidden; negation and transitions must be respected.

- [ ] **Step 4: Normalize and validate NRC data before legacy fields**

Add:

```python
def current_emotion_evidence_texts(user_text: str) -> list[str]:
    return [
        user_text,
        *(str(item.get("user_text", "")) for item in get_recent_history()),
    ]


def apply_emotion_compatibility(data: dict) -> dict:
    legacy = derive_legacy_fields(data["emotion_assessment"])
    data.update(legacy)
    data["target_flavor_vector"] = build_target_flavor_vector(
        data["emotion_assessment"]["scores"]
    )
    return data
```

In `process_user_text()`, after `normalize_result()` and before `validate_result()`:

```python
validate_emotion_assessment(
    result["emotion_assessment"],
    current_emotion_evidence_texts(user_text),
)
result = apply_emotion_compatibility(result)
```

Add `emotion_assessment` to `validate_result.required_fields`. Store it in current session history, but do not add it to stable profile fields.

- [ ] **Step 5: Add NRC data to both fallback branches**

Use a helper returning a complete neutral `trust` assessment whose evidence quote is the current `user_text`. Run it through `apply_emotion_compatibility()` so fallback and LLM paths have the same shape.

- [ ] **Step 6: Run dialogue tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_dialogue_modes -v
```

Expected: all dialogue tests PASS.

- [ ] **Step 7: Commit backend NRC integration**

```powershell
git add emotender_backend.py tests/test_dialogue_modes.py
git commit -m "feat: enforce NRC emotion output in backend"
```

### Task 3: Add the Ambient Plan API

**Files:**
- Modify: `emotender_backend.py:37-48,1089-1097`
- Modify: `tests/test_nrc_emotion.py`

- [ ] **Step 1: Write failing API-function tests**

Add tests that call `backend.ambient_plan_api()` with `AmbientPlanRequest` and assert the three exact device keys, `enabled=True`, and `16 <= temperature_c <= 28`. Add a malformed score-key test expecting HTTP 400.

- [ ] **Step 2: Run the ambient API tests and verify failure**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_nrc_emotion -v
```

Expected: FAIL because `AmbientPlanRequest` and `ambient_plan_api` do not exist.

- [ ] **Step 3: Implement the request model and endpoint**

Add:

```python
class AmbientPlanRequest(BaseModel):
    emotion_assessment: dict


@app.post("/api/ambient/plan")
def ambient_plan_api(payload: AmbientPlanRequest):
    try:
        validate_emotion_assessment(
            payload.emotion_assessment,
            [item["quote"] for item in payload.emotion_assessment.get("evidence", [])],
        )
        return {
            "ok": True,
            "ambient_plan": build_ambient_plan(payload.emotion_assessment),
        }
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
```

Import `build_ambient_plan`. Add `"ambient_plan": {"enabled": False}` to normalized recommendation results so the frontend has an explicit off state before opt-in.

- [ ] **Step 4: Run NRC and dialogue tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_nrc_emotion tests.test_dialogue_modes -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit the endpoint**

```powershell
git add emotender_backend.py tests/test_nrc_emotion.py
git commit -m "feat: expose optional ambient plan endpoint"
```

### Task 4: Add the Opt-In UI and Final Report Section

**Files:**
- Modify: `static/index.html:943-978,1040-1075,1135-1150,1400-1595,1693-1770`
- Modify: `tests/test_frontend_flow.py`

- [ ] **Step 1: Add failing frontend structure tests**

Add assertions for these exact identifiers and behaviors:

```python
def test_ambient_opt_in_sits_before_confirmation(self):
    preview = self.html[
        self.html.find('<section id="recommendation-preview"'):
        self.html.find('<div id="customization-modal"')
    ]
    self.assertIn('id="ambient-plan-toggle"', preview)
    self.assertLess(preview.find('id="ambient-plan-toggle"'), preview.find('id="btnConfirm"'))
    self.assertIn("仅生成建议，不会实际控制设备", preview)

def test_final_report_has_optional_ambient_section(self):
    self.assertIn('id="ambient-plan-section"', self.html)
    self.assertIn('id="ambient-air-conditioner"', self.html)
    self.assertIn('id="ambient-light"', self.html)
    self.assertIn('id="ambient-air-purifier"', self.html)
    self.assertIn('C("/api/ambient/plan"', self.html)

def test_emotion_pie_supports_nrc_labels(self):
    for label in ("愤怒", "期待", "厌恶", "恐惧", "喜悦", "悲伤", "惊讶", "信任"):
        self.assertIn(f'"{label}"', self.html)
```

- [ ] **Step 2: Run frontend tests and verify failure**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_frontend_flow -v
```

Expected: the three new tests FAIL because the controls and NRC colors are absent.

- [ ] **Step 3: Add the recommendation opt-in control**

Insert below `#drink-composition` and above `.view-actions`:

```html
<label id="ambient-plan-option">
  <span>
    <strong>同步生成空间氛围方案</strong>
    <small>仅生成建议，不会实际控制设备</small>
  </span>
  <input id="ambient-plan-toggle" type="checkbox" aria-label="同步生成空间氛围方案">
</label>
```

Style it as one unframed settings row with a native checkbox-style switch, matching the current light theme and using no nested card.

- [ ] **Step 4: Add the final report section**

Insert between flavor profile and receipt:

```html
<div class="report-block" id="ambient-plan-section" hidden>
  <div class="report-section-label">04 / SPACE SETTING</div>
  <div class="ambient-device-grid">
    <section id="ambient-air-conditioner"></section>
    <section id="ambient-light"></section>
    <section id="ambient-air-purifier"></section>
  </div>
  <div id="ambient-plan-disclaimer"></div>
</div>
```

Change the receipt label to `05 / YOUR RECEIPT`.

- [ ] **Step 5: Request and render the plan during confirmation**

Add:

```javascript
async function resolveAmbientPlan() {
  const toggle = document.getElementById('ambient-plan-toggle');
  if (!toggle || !toggle.checked || !currentControlJson?.emotion_assessment) {
    return {enabled:false};
  }
  const response = await C('/api/ambient/plan', {
    emotion_assessment: currentControlJson.emotion_assessment
  });
  return response.ambient_plan;
}

function renderAmbientPlan(plan) {
  const section = document.getElementById('ambient-plan-section');
  const enabled = !!(plan && plan.enabled);
  section.hidden = !enabled;
  if (!enabled) return;
  document.getElementById('ambient-air-conditioner').textContent =
    `空调 ${plan.air_conditioner.temperature_c}°C`;
  document.getElementById('ambient-light').textContent =
    `灯光 ${plan.light.brightness_percent}% · ${plan.light.color_temperature_k}K`;
  const modeNames = {auto:'自动', silent:'静音', boost:'增强'};
  document.getElementById('ambient-air-purifier').textContent =
    `空气净化器 ${modeNames[plan.air_purifier.mode]}`;
  document.getElementById('ambient-plan-disclaimer').textContent = plan.disclaimer;
}
```

At the start of existing `async function confirmFlavor()`, call `resolveAmbientPlan()`. On success assign `currentControlJson.ambient_plan`, render it, and continue. On failure use `{enabled:false}`, show a non-blocking reply-area message, and still enter the report.

- [ ] **Step 6: Add NRC pie colors and reset behavior**

Add these exact colors for the eight Chinese NRC labels to the existing emotion color map:

```javascript
const NRC_EMOTION_COLORS = {
  "愤怒":"#d65a4a",
  "期待":"#d69b3c",
  "厌恶":"#6f8f5f",
  "恐惧":"#7766a8",
  "喜悦":"#e6b84f",
  "悲伤":"#5f88b5",
  "惊讶":"#df7f53",
  "信任":"#4f9b88"
};
```

Merge this map into the color lookup used by `renderEmotionPie()`. In `resetFlavorPanels()` uncheck `#ambient-plan-toggle`, hide `#ambient-plan-section`, and clear its three device elements. Because the report export captures `#final-report`, a visible ambient section is automatically included in the saved long image.

- [ ] **Step 7: Run frontend tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_frontend_flow -v
```

Expected: all frontend tests PASS.

- [ ] **Step 8: Commit the UI**

```powershell
git add static/index.html tests/test_frontend_flow.py
git commit -m "feat: add ambient plan opt-in and report"
```

### Task 5: Run Full Verification and Update Documentation

**Files:**
- Modify: `README.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Run the complete automated suite**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Expected: every test PASS with no errors or failures.

- [ ] **Step 2: Start the Windows backend for manual browser verification**

Run:

```powershell
.\.venv\Scripts\python.exe -m uvicorn emotender_backend:app --host 127.0.0.1 --port 8011
```

Verify at `http://127.0.0.1:8011/` using text input:

1. A chat turn returns NRC assessment but does not show recommendation panels.
2. A formal recommendation shows the NRC emotion pie and six-dimensional flavor chart.
3. With the ambient toggle off, the report omits the space section.
4. With the ambient toggle on, the report shows air conditioner, light, and air purifier values.
5. The air-conditioner value is within `16–28°C`.
6. Saving the report includes the visible space section.

- [ ] **Step 3: Verify desktop and mobile layout**

Use Playwright at `1440 × 1000` and `390 × 844`. Confirm no overlap, horizontal overflow, clipped labels, or nested cards in the recommendation and final report views.

- [ ] **Step 4: Document exact behavior**

In `README.md`, add:

- NRC eight-category output and the meaning of `scores`.
- `emotion_assessment` response schema.
- `POST /api/ambient/plan` request and response examples.
- Statement that the ambient plan does not control real devices.
- Air-conditioner `16–28°C`, light `20–100%` and `2700–6500K`, purifier `auto|silent|boost` limits.

In `CHANGELOG.md`, add one entry summarizing NRC standardization, backward-compatible emotion fields, target flavor mapping, and optional ambient report.

- [ ] **Step 5: Commit documentation and verification changes**

```powershell
git add README.md CHANGELOG.md
git commit -m "docs: describe NRC and ambient recommendation flow"
```

- [ ] **Step 6: Verify final repository state**

Run:

```powershell
git status --short --branch
git log -6 --oneline --decorate
```

Expected: clean `feature/windows-ui-preview` worktree with the NRC and ambient feature commits at HEAD.
