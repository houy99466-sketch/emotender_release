# Pixel Conversation Scene Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the formal Web conversation view with the approved pixel milk-tea-shop scene while preserving every existing backend contract, recommendation transition, account action, customization flow, and final report.

**Architecture:** Keep `static/index.html` as the existing application shell and add a focused scene stylesheet and controller. The scene controller owns only recent-bubble rendering, history drawer rendering, anchor editing, and bubble layout; existing functions continue to own API calls and application state. The newest message uses the saved tail anchor for its role, while older visible messages are measured and positioned upward in chronological order.

**Tech Stack:** HTML, CSS, browser JavaScript, Python `unittest`, Playwright browser verification.

---

### Task 1: Preserve the current formal application

**Files:**
- Backup: `E:\codex produce\EmoTend-xiaomi-ui-preview-backups\2026-07-28-before-pixel-scene-merge`

- [ ] Copy the complete formal project before editing.
- [ ] Confirm the backup includes `static/index.html`, `.env`, tests, Android sources, and the existing virtual environment.
- [ ] Record the pre-existing dirty file with `git status --short` so it is not overwritten.

### Task 2: Add pixel scene assets and browser controller

**Files:**
- Create: `static/pixel-scene.css`
- Create: `static/pixel-scene.js`
- Create: `static/pixel-scene/scene.png`
- Create: `static/pixel-scene/fusion-pixel-zh-hans.woff2`

- [ ] Copy the approved portrait scene and bundled Simplified Chinese pixel font into the formal static directory.
- [ ] Add scene, bubble, pixel control, history drawer, input, recommendation-entry, and responsive styles.
- [ ] Define exact role anchors from the approved third customer and third Mingming bubbles.
- [ ] Implement `window.EmoTenderPixelScene` with `setMessages`, `clear`, `setRecommendationVisible`, `setHistoryOpen`, and anchor-editing behavior.
- [ ] Measure rendered bubble heights before assigning positions. Anchor the newest bubble by tail tip, then place older visible messages upward using their measured heights and a fixed visual gap.
- [ ] Keep at most three customer and three Mingming messages in the scene. Keep the complete supplied message list in the history drawer.

### Task 3: Wire the scene into the existing application shell

**Files:**
- Modify: `static/index.html`

- [ ] Load `/static/pixel-scene.css` in the document head and `/static/pixel-scene.js` before the existing application script.
- [ ] Replace only the conversation-view markup with the scene structure while retaining `crt-screen` as the emotion and final-report snapshot source.
- [ ] Move `btnStart`, `btnSend`, `status-line`, and `btnReset` into the scene control row immediately after `position-mode-button`.
- [ ] Place `manual-input` below that control row and preserve its existing ID and handlers.
- [ ] Place `recommendation-entry` over the drink position and retain `openRecommendationPreview()`.
- [ ] Add an explicit recommendation-preview back button because the conversation controls no longer live in a global fixed dock.
- [ ] Adapt `appendChatMessage`, `renderConversationHistory`, and `resetConversation` to synchronize the existing conversation state into `EmoTenderPixelScene` without changing API request or response fields.

### Task 4: Add regression coverage

**Files:**
- Modify: `tests/test_frontend_flow.py`
- Create: `tests/pixel-scene.test.cjs`

- [ ] Add static assertions for the scene asset, controller, control placement, history drawer, manual input, and recommendation button.
- [ ] Serve `static` from a local test HTTP server and open the formal page in Playwright.
- [ ] Render more than three messages per role and assert the scene shows at most three from each role while history retains all messages.
- [ ] Assert the newest tail endpoint remains within tolerance of the configured role anchor after short and long messages.
- [ ] Assert bubbles do not overlap, the page has no horizontal overflow, and the recommendation button appears only when requested.
- [ ] Run `python -m unittest tests.test_frontend_flow` and the Playwright test with the bundled `NODE_PATH`.

### Task 5: Visual verification

**Files:**
- Verify: `static/index.html`

- [ ] Capture desktop and mobile screenshots after populating three complete dialogue rounds.
- [ ] Inspect both screenshots for readable text, correct role tails, preserved characters and drink, non-overlapping controls, and a visible bottom input.
- [ ] Confirm the recommendation button appears at the drink only after formal recommendation state is enabled.
- [ ] Run the complete Python test suite and report any unrelated environment-dependent failures separately.
