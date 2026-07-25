# Light Beverage UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the alcohol-oriented radar axes and dark visual theme with the approved broad-beverage flavor model and light beverage-lab interface.

**Architecture:** Keep the single-file frontend architecture and backend contract intact. Update static preview data and chart rendering in `static/index.html`, then add a final light-theme CSS layer so existing layout and behavior remain stable.

**Tech Stack:** HTML, CSS, vanilla JavaScript, Python `unittest`, Playwright visual QA.

---

### Task 1: Lock the new flavor contract

**Files:**
- Modify: `tests/test_frontend_flow.py`
- Modify: `static/index.html`

- [ ] Add assertions for the exact six-axis order and the new customization keys.
- [ ] Run `python -m unittest tests.test_frontend_flow -v` and confirm the new tests fail because the old axes remain.
- [ ] Replace all six drink preview objects, flavor defaults, and adjustment rules with the new keys.
- [ ] Run the focused frontend tests and confirm they pass.

### Task 2: Apply the light beverage-lab theme

**Files:**
- Modify: `tests/test_frontend_flow.py`
- Modify: `static/index.html`

- [ ] Add assertions for the light-theme marker and semantic color variables.
- [ ] Run the focused test and confirm it fails before the theme exists.
- [ ] Add semantic CSS variables and light styles for the page, face stage, chat, controls, recommendation, report, receipt, and modal.
- [ ] Update hardcoded SVG chart colors to the light chart palette.
- [ ] Run the focused tests and confirm they pass.

### Task 3: Verify behavior and presentation

**Files:**
- Test: `tests/test_frontend_flow.py`
- Temporary QA artifacts: `E:\codex produce\_qa_emotend_light_beverage_ui`

- [ ] Run `python -m unittest discover -s tests` and confirm all tests pass.
- [ ] Start Uvicorn from the project-local virtual environment on an unused localhost port.
- [ ] Use Playwright to exercise conversation, recommendation, customization, and report states at desktop and mobile viewports.
- [ ] Check page identity, meaningful content, console health, overflow, interaction state changes, and screenshots.
- [ ] Keep the preview server running for user review.

