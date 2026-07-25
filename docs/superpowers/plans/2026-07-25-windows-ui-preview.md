# EmoTend Windows UI Preview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a Windows-browser recommendation preview with a read-only flavor chart, deterministic drink composition illustration, and ordering-style specification editor while preserving all current models, menu data, and backend behavior.

**Architecture:** Keep the existing single-file frontend and add isolated markup, CSS, and local JavaScript state inside `static/index.html`. Extend the existing source-level frontend regression tests to lock the new interaction contract without adding backend dependencies.

**Tech Stack:** Static HTML/CSS/JavaScript, Python `unittest`, FastAPI, Playwright for rendered QA.

---

### Task 1: Lock the new preview contract

**Files:**
- Modify: `tests/test_frontend_flow.py`

- [ ] Add failing tests that require `调整规格`, the specification modal, composition illustration, and read-only chart.
- [ ] Add failing tests that reject random photo selection and draggable flavor handlers.
- [ ] Run `E:\vmwareshare\emotender_release\.venv\Scripts\python.exe -m unittest tests.test_frontend_flow -v` and verify the new tests fail for missing behavior.

### Task 2: Implement the Windows preview

**Files:**
- Modify: `static/index.html`

- [ ] Remove the random image block and random `/static/photo/` selection.
- [ ] Remove flavor-chart pointer and touch editing.
- [ ] Add the deterministic composition illustration and its update function.
- [ ] Add `调整规格`, grouped option controls, selected states, summary, cancel, and confirm behavior.
- [ ] Keep option changes local and label them as interface preview data.
- [ ] Run `E:\vmwareshare\emotender_release\.venv\Scripts\python.exe -m unittest tests.test_frontend_flow -v` and verify the frontend tests pass.

### Task 3: Regression and rendered QA

**Files:**
- Modify only if QA identifies a defect: `static/index.html`

- [ ] Run the full unit-test suite and verify all tests pass.
- [ ] Start FastAPI on an available local port.
- [ ] Use Playwright because the Browser plugin is not available in this session.
- [ ] Verify desktop and mobile viewports, modal open/close, option selection, confirmation, no horizontal overflow, and no console errors.
- [ ] Save QA screenshots outside the repository under `E:\codex produce\_qa_emotend_windows_ui_preview`.

