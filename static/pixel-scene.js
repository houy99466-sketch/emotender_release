(function () {
  "use strict";

  const MAX_VISIBLE_PER_ROLE = 3;
  const TAIL_EXTENSION = 20;
  const STACK_GAP = 8;
  const SCENE_SAFE_TOP = 8;
  const DEFAULT_ANCHORS = Object.freeze({
    user: Object.freeze({ x: 29.36, y: 44.55 }),
    robot: Object.freeze({ x: 72.93, y: 37.97 })
  });
  const ANCHOR_STORAGE_KEY = "emotend-pixel-scene-anchors-v1";

  let messages = [];
  let scene = null;
  let conversationWindow = null;
  let historyList = null;
  let recommendationEntry = null;
  let positionModeButton = null;
  let positionReadout = null;
  let anchors = readAnchors();
  let layoutFrame = 0;
  let dragState = null;

  // ===== Scene State Machine =====
  const SCENE_STATES = {
    EMPTY: "empty",
    ENTERING: "entering",
    CHATTING: "chatting",
    SERVING: "serving",
    RECOMMENDATION_READY: "recommendation_ready"
  };

  const SCENE_IMAGES = {
    empty: "/static/pixel-scene/scene-empty.png",
    chatting: "/static/pixel-scene/scene-chat.png",
    recommendation_ready: "/static/pixel-scene/scene-recommendation.png"
  };

  const SCENE_VIDEOS = {
    entering: "/static/pixel-scene/customer-enter.mp4",
    serving: "/static/pixel-scene/mingming-serve.mp4"
  };

  let currentSceneState = SCENE_STATES.EMPTY;
  let sceneBgImage = null;
  let sceneVideo = null;
  let recommendationAlreadyServed = false;

  function ensureSceneElements() {
    if (!sceneBgImage || !sceneBgImage.isConnected) {
      sceneBgImage = document.getElementById("scene-bg");
    }
    if (!sceneVideo || !sceneVideo.isConnected) {
      sceneVideo = document.getElementById("scene-action-video");
    }
    return Boolean(sceneBgImage && sceneVideo);
  }

  function setSceneBackground(state) {
    if (!ensureSceneElements()) return;
    const url = SCENE_IMAGES[state];
    if (!url) return;
    // Track if this is the first load attempt to prevent infinite fallback loop
    var alreadyTried = (sceneBgImage.dataset.fallbackTried === 'true');
    sceneBgImage.dataset.state = state;
    sceneBgImage.dataset.fallbackTried = 'false';
    sceneBgImage.src = url;
    sceneBgImage.onerror = function () {
      if (sceneBgImage.dataset.fallbackTried === 'true') return;
      sceneBgImage.dataset.fallbackTried = 'true';
      sceneBgImage.src = "/static/pixel-scene/scene.png";
    };
  }

  function switchSceneState(newState) {
    if (!ensureSceneElements()) return;
    currentSceneState = newState;
    if (newState === SCENE_STATES.RECOMMENDATION_READY) {
      recommendationAlreadyServed = true;
    }
    if (newState === SCENE_STATES.CHATTING) {
      recommendationAlreadyServed = false;
    }
    setSceneBackground(newState);
  }

  function isVideoAvailable(url) {
    // Assume video is available; onerror handler will catch failures
    return true;
  }

  function playSceneVideo(videoKey, onComplete) {
    if (!ensureSceneElements()) {
      if (onComplete) onComplete();
      return;
    }
    const url = SCENE_VIDEOS[videoKey];
    if (!url) {
      if (onComplete) onComplete();
      return;
    }

    // Set up video
    sceneVideo.src = url;
    sceneVideo.currentTime = 0;
    sceneVideo.classList.add("playing");

    var handled = false;
    function finish() {
      if (handled) return;
      handled = true;
      sceneVideo.classList.remove("playing");
      sceneVideo.pause();
      sceneVideo.removeEventListener("ended", finish);
      sceneVideo.removeEventListener("error", finish);
      if (onComplete) onComplete();
    }

    sceneVideo.addEventListener("ended", finish);
    sceneVideo.addEventListener("error", function () {
      // Video failed to load - skip to completion
      finish();
    });

    // Play with timeout fallback
    var playPromise = sceneVideo.play();
    if (playPromise !== undefined) {
      playPromise.catch(function () {
        finish();
      });
    }

    // Safety timeout: if video hasn't ended in 8 seconds, force finish
    setTimeout(function () {
      if (!handled) finish();
    }, 15000);
  }

  function enterScene() {
    if (currentSceneState === SCENE_STATES.ENTERING) {
      // Already playing entrance animation
      return;
    }
    if (currentSceneState === SCENE_STATES.CHATTING && !recommendationAlreadyServed) {
      // Already in chatting with no pending recommendation
      return;
    }

    switchSceneState(SCENE_STATES.ENTERING);
    recommendationAlreadyServed = false;
    playSceneVideo("entering", function () {
      switchSceneState(SCENE_STATES.CHATTING);
    });
  }

  function serveRecommendation() {
    if (currentSceneState === SCENE_STATES.SERVING) return; // Already serving
    if (currentSceneState === SCENE_STATES.RECOMMENDATION_READY) {
      // Already served - just show button
      if (recommendationEntry) {
        recommendationEntry.classList.add("visible");
      }
      return;
    }
    if (recommendationAlreadyServed && currentSceneState === SCENE_STATES.CHATTING) {
      // Already served this session, skip animation
      switchSceneState(SCENE_STATES.RECOMMENDATION_READY);
      if (recommendationEntry) {
        recommendationEntry.classList.add("visible");
      }
      return;
    }

    // Hide recommendation button during animation
    if (recommendationEntry) {
      recommendationEntry.classList.remove("visible");
    }

    switchSceneState(SCENE_STATES.SERVING);
    playSceneVideo("serving", function () {
      switchSceneState(SCENE_STATES.RECOMMENDATION_READY);
      if (recommendationEntry) {
        recommendationEntry.classList.add("visible");
      }
    });
  }

  function resetScene() {
    if (!ensureSceneElements()) return;
    sceneVideo.classList.remove("playing");
    sceneVideo.pause();
    sceneVideo.removeAttribute("src");
    recommendationAlreadyServed = false;
    switchSceneState(SCENE_STATES.EMPTY);
  }

  function getSceneState() {
    return currentSceneState;
  }

  // Override setRecommendationVisible to integrate with scene state machine
  var _originalSetRecVisible = setRecommendationVisible;
  setRecommendationVisible = function (visible) {
    if (!ensureSceneElements()) return _originalSetRecVisible(visible);
    if (visible) {
      serveRecommendation();
    } else {
      if (recommendationEntry) {
        recommendationEntry.classList.remove("visible");
      }
    }
  };


  function cloneAnchors(source) {
    return {
      user: { x: source.user.x, y: source.user.y },
      robot: { x: source.robot.x, y: source.robot.y }
    };
  }

  function validAnchor(value) {
    return value && Number.isFinite(value.x) && Number.isFinite(value.y);
  }

  function readAnchors() {
    try {
      const stored = JSON.parse(localStorage.getItem(ANCHOR_STORAGE_KEY) || "null");
      if (stored && validAnchor(stored.user) && validAnchor(stored.robot)) {
        return cloneAnchors(stored);
      }
    } catch (error) {
      // Invalid local state falls back to the approved layout.
    }
    return cloneAnchors(DEFAULT_ANCHORS);
  }

  function saveAnchors() {
    localStorage.setItem(ANCHOR_STORAGE_KEY, JSON.stringify(anchors));
  }

  function ensureElements() {
    if (scene && scene.isConnected) return true;
    scene = document.getElementById("pixel-scene");
    conversationWindow = document.getElementById("scene-conversation-window");
    historyList = document.getElementById("conversation-list");
    recommendationEntry = document.getElementById("recommendation-entry");
    positionModeButton = document.getElementById("position-mode-button");
    positionReadout = document.getElementById("position-readout");
    return Boolean(scene && conversationWindow && historyList);
  }

  function normalizeMessages(items) {
    if (!Array.isArray(items)) return [];
    return items.flatMap(function (item, index) {
      if (!item || (item.role !== "user" && item.role !== "robot")) return [];
      const text = String(item.text || "").trim();
      if (!text) return [];
      const key = String(item.key || item.role + "-" + index);
      return [{ key: key, role: item.role, text: text }];
    });
  }

  function selectVisibleMessages(items) {
    const counts = { user: 0, robot: 0 };
    const selected = [];
    for (let index = items.length - 1; index >= 0; index -= 1) {
      const item = items[index];
      if (counts[item.role] >= MAX_VISIBLE_PER_ROLE) continue;
      counts[item.role] += 1;
      selected.push(item);
    }
    return selected.reverse();
  }

  function createBubble(item) {
    const bubble = document.createElement("article");
    bubble.className = "pixel-chat-bubble is-entering";
    bubble.dataset.messageKey = item.key;
    const surface = document.createElement("div");
    surface.className = "pixel-bubble-surface";
    const text = document.createElement("div");
    text.className = "pixel-bubble-text";
    const more = document.createElement("span");
    more.className = "pixel-bubble-more";
    more.setAttribute("aria-hidden", "true");
    more.textContent = "▼";
    surface.appendChild(text);
    surface.appendChild(more);
    bubble.appendChild(surface);
    requestAnimationFrame(function () {
      bubble.classList.remove("is-entering");
    });
    return bubble;
  }

  function renderBubbles() {
    if (!ensureElements()) return;
    const visible = selectVisibleMessages(messages);
    const existing = new Map(
      Array.from(conversationWindow.querySelectorAll(".pixel-chat-bubble")).map(function (bubble) {
        return [bubble.dataset.messageKey, bubble];
      })
    );
    const visibleKeys = new Set(visible.map(function (item) { return item.key; }));

    existing.forEach(function (bubble, key) {
      if (!visibleKeys.has(key)) bubble.remove();
    });

    const ageByRole = { user: 0, robot: 0 };
    const roleAges = new Map();
    for (let index = visible.length - 1; index >= 0; index -= 1) {
      roleAges.set(visible[index].key, ageByRole[visible[index].role]);
      ageByRole[visible[index].role] += 1;
    }

    visible.forEach(function (item, index) {
      let bubble = existing.get(item.key);
      if (!bubble || !bubble.isConnected) bubble = createBubble(item);
      const globalAge = visible.length - 1 - index;
      const priority = globalAge === 0
        ? "current"
        : globalAge === 1
          ? "context"
          : globalAge <= 3
            ? "recent"
            : "older";
      bubble.dataset.role = item.role;
      bubble.dataset.age = String(roleAges.get(item.key));
      bubble.dataset.priority = priority;
      bubble.hidden = false;
      bubble.dataset.baseAriaLabel = (item.role === "user" ? "顾客" : "茗茗") + "：" + item.text;
      bubble.setAttribute("aria-label", bubble.dataset.baseAriaLabel);
      bubble.querySelector(".pixel-bubble-text").textContent = item.text;
      conversationWindow.appendChild(bubble);
    });

    scheduleLayout();
  }

  function renderHistory() {
    if (!ensureElements()) return;
    historyList.replaceChildren();
    if (!messages.length) {
      const empty = document.createElement("div");
      empty.id = "conversation-empty";
      empty.textContent = "说点什么。茗茗会记住本轮对话，再决定此刻适合你的风味。";
      historyList.appendChild(empty);
      return;
    }

    messages.forEach(function (item) {
      const row = document.createElement("article");
      row.className = "pixel-history-row";
      row.dataset.role = item.role;
      row.dataset.messageKey = item.key;
      const role = document.createElement("div");
      role.className = "pixel-history-role";
      role.textContent = item.role === "user" ? "顾客" : "茗茗";
      const text = document.createElement("div");
      text.className = "pixel-history-text";
      text.textContent = item.text;
      row.appendChild(role);
      row.appendChild(text);
      historyList.appendChild(row);
    });
  }

  function horizontalLeft(role, anchorX, width) {
    if (role === "user") return anchorX - width * 0.12 - 4;
    return anchorX - width * 0.88 + 4;
  }

  function layoutRole(role, sceneWidth, sceneHeight) {
    const roleBubbles = Array.from(
      conversationWindow.querySelectorAll('.pixel-chat-bubble[data-role="' + role + '"]')
    ).filter(function (bubble) { return !bubble.hidden; });
    if (!roleBubbles.length) return;
    const anchor = anchors[role];
    const anchorX = sceneWidth * anchor.x / 100;
    const anchorY = sceneHeight * anchor.y / 100;
    let nextTop = null;

    for (let index = roleBubbles.length - 1; index >= 0; index -= 1) {
      const bubble = roleBubbles[index];
      const width = bubble.offsetWidth;
      const height = bubble.offsetHeight;
      const left = horizontalLeft(role, anchorX, width);
      const top = nextTop === null
        ? anchorY - height - TAIL_EXTENSION
        : nextTop - STACK_GAP - TAIL_EXTENSION - height;
      bubble.style.left = Math.max(0, Math.min(sceneWidth - width, left)).toFixed(2) + "px";
      bubble.style.top = top.toFixed(2) + "px";
      bubble.classList.toggle("is-anchor-bubble", index === roleBubbles.length - 1);
      nextTop = top;
    }
  }

  function oldestRemovableBubble() {
    return Array.from(conversationWindow.querySelectorAll(".pixel-chat-bubble")).find(function (bubble) {
      return !bubble.hidden
        && bubble.dataset.priority !== "current";
    }) || null;
  }

  function visibleTopIsSafe() {
    return Array.from(conversationWindow.querySelectorAll(".pixel-chat-bubble")).every(function (bubble) {
      if (bubble.hidden) return true;
      const top = parseFloat(bubble.style.top);
      return Number.isFinite(top) && top >= SCENE_SAFE_TOP;
    });
  }

  function bubblesOverlap(a, b) {
    const aLeft = parseFloat(a.style.left);
    const aTop = parseFloat(a.style.top);
    const bLeft = parseFloat(b.style.left);
    const bTop = parseFloat(b.style.top);
    return aLeft < bLeft + b.offsetWidth
      && aLeft + a.offsetWidth > bLeft
      && aTop < bTop + b.offsetHeight
      && aTop + a.offsetHeight > bTop;
  }

  function liftOlderBubblesAboveOverlaps() {
    const visible = Array.from(conversationWindow.querySelectorAll(".pixel-chat-bubble")).filter(function (bubble) {
      return !bubble.hidden;
    });
    for (let newerIndex = visible.length - 1; newerIndex > 0; newerIndex -= 1) {
      const newer = visible[newerIndex];
      for (let olderIndex = newerIndex - 1; olderIndex >= 0; olderIndex -= 1) {
        const older = visible[olderIndex];
        if (bubblesOverlap(older, newer)) {
          const newerTop = parseFloat(newer.style.top);
          older.style.top = (newerTop - STACK_GAP - TAIL_EXTENSION - older.offsetHeight).toFixed(2) + "px";
        }
      }
    }
  }

  function updateTruncationStates() {
    Array.from(conversationWindow.querySelectorAll(".pixel-chat-bubble")).forEach(function (bubble) {
      if (bubble.hidden) {
        bubble.classList.remove("is-truncated");
        bubble.removeAttribute("tabindex");
        bubble.setAttribute("aria-label", bubble.dataset.baseAriaLabel || "");
        return;
      }
      const text = bubble.querySelector(".pixel-bubble-text");
      const truncated = text.scrollHeight > text.clientHeight + 1;
      bubble.classList.toggle("is-truncated", truncated);
      if (truncated) {
        bubble.tabIndex = 0;
        bubble.setAttribute("aria-label", (bubble.dataset.baseAriaLabel || "") + "，按下可查看完整内容");
      } else {
        bubble.removeAttribute("tabindex");
        bubble.setAttribute("aria-label", bubble.dataset.baseAriaLabel || "");
      }
    });
  }

  function layoutBubbles() {
    layoutFrame = 0;
    if (!ensureElements()) return;
    const width = scene.clientWidth;
    const height = scene.clientHeight;
    if (!width || !height) return;
    Array.from(conversationWindow.querySelectorAll(".pixel-chat-bubble")).forEach(function (bubble) {
      bubble.hidden = false;
      bubble.classList.remove("is-anchor-bubble");
    });
    while (true) {
      layoutRole("user", width, height);
      layoutRole("robot", width, height);
      liftOlderBubblesAboveOverlaps();
      if (visibleTopIsSafe()) break;
      const removable = oldestRemovableBubble();
      if (!removable) break;
      removable.hidden = true;
    }
    updateTruncationStates();
  }

  function scheduleLayout() {
    if (layoutFrame) cancelAnimationFrame(layoutFrame);
    layoutFrame = requestAnimationFrame(layoutBubbles);
  }

  function setMessages(items) {
    messages = normalizeMessages(items);
    renderHistory();
    renderBubbles();
  }

  function clear() {
    setMessages([]);
    resetScene();
  }

  function setRecommendationVisible(visible) {
    if (!ensureElements() || !recommendationEntry) return;
    recommendationEntry.classList.toggle("visible", Boolean(visible));
  }

  function setHistoryOpen(open) {
    if (!ensureElements()) return;
    const historyButton = document.getElementById("history-button");
    const historyDrawer = document.getElementById("history-drawer");
    const drawerBackdrop = document.getElementById("drawer-backdrop");
    scene.classList.toggle("history-open", Boolean(open));
    if (historyButton) historyButton.setAttribute("aria-expanded", String(Boolean(open)));
    if (historyDrawer) historyDrawer.setAttribute("aria-hidden", String(!open));
    if (drawerBackdrop) drawerBackdrop.setAttribute("aria-hidden", String(!open));
  }

  function setPositionMode(enabled) {
    if (!ensureElements()) return;
    scene.dataset.positionMode = enabled ? "on" : "off";
    positionModeButton.setAttribute("aria-pressed", String(enabled));
    positionModeButton.textContent = enabled ? "完成调整" : "调整位置";
    if (positionReadout) {
      positionReadout.textContent = enabled ? "拖动顾客或茗茗最新的气泡" : "锚点位置已保存";
    }
  }

  function updateReadout(role) {
    if (!positionReadout) return;
    if (!role) {
      positionReadout.textContent = "先开始对话，再拖动最新气泡";
      return;
    }
    const label = role === "user" ? "顾客" : "茗茗";
    positionReadout.textContent = label + "尾巴锚点 · X " + anchors[role].x.toFixed(2)
      + "% · Y " + anchors[role].y.toFixed(2) + "%";
  }

  async function copyAnchors() {
    const text = JSON.stringify(anchors, null, 2);
    try {
      await navigator.clipboard.writeText(text);
    } catch (error) {
      const textarea = document.createElement("textarea");
      textarea.value = text;
      textarea.style.position = "fixed";
      textarea.style.opacity = "0";
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand("copy");
      textarea.remove();
    }
    if (positionReadout) positionReadout.textContent = "两组尾巴锚点已复制";
  }

  function resetAnchors() {
    anchors = cloneAnchors(DEFAULT_ANCHORS);
    localStorage.removeItem(ANCHOR_STORAGE_KEY);
    scheduleLayout();
    if (positionReadout) positionReadout.textContent = "已恢复确认后的默认锚点";
  }

  function getAnchors() {
    return cloneAnchors(anchors);
  }

  function openHistoryAtMessage(key) {
    if (!ensureElements()) return;
    setHistoryOpen(true);
    historyList.querySelectorAll(".pixel-history-row").forEach(function (row) {
      row.dataset.highlighted = String(row.dataset.messageKey === key);
    });
    const target = historyList.querySelector('.pixel-history-row[data-message-key="' + CSS.escape(key) + '"]');
    if (target) requestAnimationFrame(function () { target.scrollIntoView({ block: "center" }); });
  }

  function pointerDown(event) {
    if (!scene || scene.dataset.positionMode !== "on") return;
    const bubble = event.target.closest(".pixel-chat-bubble.is-anchor-bubble");
    if (!bubble || !conversationWindow.contains(bubble)) return;
    event.preventDefault();
    const role = bubble.dataset.role;
    dragState = {
      role: role,
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      anchorX: anchors[role].x,
      anchorY: anchors[role].y
    };
    bubble.setPointerCapture(event.pointerId);
    updateReadout(role);
  }

  function pointerMove(event) {
    if (!dragState || dragState.pointerId !== event.pointerId) return;
    const sceneRect = scene.getBoundingClientRect();
    const deltaX = (event.clientX - dragState.startX) / sceneRect.width * 100;
    const deltaY = (event.clientY - dragState.startY) / sceneRect.height * 100;
    anchors[dragState.role].x = Math.max(4, Math.min(96, dragState.anchorX + deltaX));
    anchors[dragState.role].y = Math.max(8, Math.min(72, dragState.anchorY + deltaY));
    scheduleLayout();
    updateReadout(dragState.role);
  }

  function pointerEnd(event) {
    if (!dragState || dragState.pointerId !== event.pointerId) return;
    saveAnchors();
    updateReadout(dragState.role);
    dragState = null;
  }

  function bindEvents() {
    if (!ensureElements()) return;
    const historyButton = document.getElementById("history-button");
    const drawerClose = document.getElementById("drawer-close");
    const drawerBackdrop = document.getElementById("drawer-backdrop");
    const copyButton = document.getElementById("position-copy-button");
    const resetButton = document.getElementById("position-reset-button");

    if (historyButton) historyButton.addEventListener("click", function () { setHistoryOpen(true); });
    if (drawerClose) drawerClose.addEventListener("click", function () { setHistoryOpen(false); });
    if (drawerBackdrop) drawerBackdrop.addEventListener("click", function () { setHistoryOpen(false); });
    if (positionModeButton) {
      positionModeButton.addEventListener("click", function () {
        setPositionMode(scene.dataset.positionMode !== "on");
      });
    }
    if (copyButton) copyButton.addEventListener("click", copyAnchors);
    if (resetButton) resetButton.addEventListener("click", resetAnchors);

    conversationWindow.addEventListener("pointerdown", pointerDown);
    conversationWindow.addEventListener("pointermove", pointerMove);
    conversationWindow.addEventListener("pointerup", pointerEnd);
    conversationWindow.addEventListener("pointercancel", pointerEnd);
    conversationWindow.addEventListener("click", function (event) {
      if (scene.dataset.positionMode === "on") return;
      const bubble = event.target.closest(".pixel-chat-bubble.is-truncated");
      if (bubble) openHistoryAtMessage(bubble.dataset.messageKey);
    });
    conversationWindow.addEventListener("keydown", function (event) {
      if (scene.dataset.positionMode === "on" || (event.key !== "Enter" && event.key !== " ")) return;
      const bubble = event.target.closest(".pixel-chat-bubble.is-truncated");
      if (!bubble) return;
      event.preventDefault();
      openHistoryAtMessage(bubble.dataset.messageKey);
    });
    window.addEventListener("resize", scheduleLayout);
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && scene.classList.contains("history-open")) setHistoryOpen(false);
    });
  }

  window.EmoTenderPixelScene = {
    setMessages: setMessages,
    clear: clear,
    setRecommendationVisible: setRecommendationVisible,
    setHistoryOpen: setHistoryOpen,
    copyAnchors: copyAnchors,
    resetAnchors: resetAnchors,
    getAnchors: getAnchors,
    scheduleLayout: scheduleLayout,
    enterScene: enterScene,
    serveRecommendation: serveRecommendation,
    resetScene: resetScene,
    getSceneState: getSceneState,
    switchSceneState: switchSceneState,
    SCENE_STATES: SCENE_STATES
  };

  document.addEventListener("DOMContentLoaded", function () {
    if (!ensureElements()) return;
    bindEvents();
    renderHistory();
    renderBubbles();
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(scheduleLayout);
  });
})();
