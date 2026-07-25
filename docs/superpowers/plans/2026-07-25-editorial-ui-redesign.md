# EmoTend Editorial UI Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不改变任何现有功能的前提下，将 EmoTend 前端升级为已确认的编辑感饮品杂志风格。

**Architecture:** 继续使用单文件 `static/index.html`，保留现有 HTML 功能节点和全部 JavaScript。通过新增静态品牌页眉和覆盖式 CSS 完成视觉重构，以独立备份作为功能基线进行逐字验证。

**Tech Stack:** HTML5、CSS3、原生 JavaScript、内嵌 SVG、FastAPI 静态页面、Playwright/Edge 截图验证、Python unittest。

---

### Task 1: Lock The Functional Baseline

**Files:**
- Reference: `E:/codex produce/EmoTend-xiaomi-ui-preview-backups/2026-07-25-before-editorial-ui/static/index.html`
- Modify: `static/index.html`

- [ ] **Step 1:** 记录备份与工作文件的 SHA256，确认修改前完全一致。
- [ ] **Step 2:** 从备份中提取全部 `<script>`、功能 ID 和事件属性，作为修改后对照基线。

### Task 2: Apply Editorial Visual System

**Files:**
- Modify: `static/index.html`

- [ ] **Step 1:** 增加不参与业务逻辑的品牌页眉静态节点。
- [ ] **Step 2:** 在现有样式表末尾增加编辑主题 token 和覆盖样式。
- [ ] **Step 3:** 统一会话、推荐、报告、弹窗、图表、小票和底部操作区的视觉语言。
- [ ] **Step 4:** 增加 375px、768px、1024px 响应式规则和 `prefers-reduced-motion` 规则。

### Task 3: Prove Functional Preservation

**Files:**
- Test: `tests/test_frontend_flow.py`
- Verify: `static/index.html`

- [ ] **Step 1:** 比较备份和新版全部 `<script>` 内容，预期完全相同。
- [ ] **Step 2:** 比较备份和新版原有功能 ID 与事件属性，预期无删除和无修改。
- [ ] **Step 3:** 运行 `./.venv/Scripts/python.exe -m unittest discover -s tests -v`，预期全部通过。
- [ ] **Step 4:** 在 375x812、768x1024、1440x1000 视口检查布局、溢出和固定底栏。
- [ ] **Step 5:** 截取会话页视觉结果并确认原有表情仍然显示和动画。
