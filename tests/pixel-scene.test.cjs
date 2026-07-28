const assert = require("node:assert/strict");
const fs = require("node:fs");
const http = require("node:http");
const path = require("node:path");
const { chromium } = require("playwright");

const ROOT = path.resolve(__dirname, "..");
const STATIC_ROOT = path.join(ROOT, "static");
const EDGE_PATH = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";

function contentType(filePath) {
  const extension = path.extname(filePath).toLowerCase();
  return {
    ".css": "text/css; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".png": "image/png",
    ".woff2": "font/woff2"
  }[extension] || "application/octet-stream";
}

function startServer() {
  const server = http.createServer((request, response) => {
    const pathname = new URL(request.url, "http://127.0.0.1").pathname;
    const relative = pathname === "/" ? "index.html" : pathname.replace(/^\/static\//, "");
    const filePath = path.resolve(STATIC_ROOT, relative);
    if (!filePath.startsWith(STATIC_ROOT) || !fs.existsSync(filePath) || !fs.statSync(filePath).isFile()) {
      response.writeHead(404);
      response.end("not found");
      return;
    }
    response.writeHead(200, { "Content-Type": contentType(filePath) });
    fs.createReadStream(filePath).pipe(response);
  });
  return new Promise((resolve) => {
    server.listen(0, "127.0.0.1", () => resolve(server));
  });
}

function message(key, role, text) {
  return { key, role, text };
}

(async () => {
  const server = await startServer();
  const address = server.address();
  const browser = await chromium.launch({ headless: true, executablePath: EDGE_PATH });
  const page = await browser.newPage({ viewport: { width: 1280, height: 1000 } });
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));

  try {
    const screenshotDirectory = process.env.PIXEL_SCENE_SCREENSHOT_DIR;
    if (screenshotDirectory) fs.mkdirSync(screenshotDirectory, { recursive: true });
    await page.goto(`http://127.0.0.1:${address.port}/`, { waitUntil: "load" });
    await page.evaluate(() => localStorage.clear());
    await page.reload({ waitUntil: "load" });

    const messages = [
      message("u1", "user", "第一条顾客消息"),
      message("r1", "robot", "第一条茗茗回复"),
      message("u2", "user", "第二条顾客消息，长度稍微多一点。"),
      message("r2", "robot", "第二条茗茗回复。"),
      message("u3", "user", "第三条顾客消息。"),
      message("r3", "robot", "第三条茗茗回复，继续把当前情绪接住。"),
      message("u4", "user", "第四条顾客消息，场景里不再显示第一条顾客消息。"),
      message("r4", "robot", "第四条茗茗回复，场景里不再显示第一条茗茗回复。")
    ];
    await page.evaluate((items) => window.EmoTenderPixelScene.setMessages(items), messages);
    await page.waitForTimeout(320);

    assert.equal(await page.locator('.pixel-chat-bubble[data-role="user"]').count(), 3);
    assert.equal(await page.locator('.pixel-chat-bubble[data-role="robot"]').count(), 3);
    assert.equal(await page.locator(".pixel-history-row").count(), messages.length);
    assert.equal(await page.locator('.pixel-chat-bubble[data-message-key="u1"]').count(), 0);
    assert.equal(await page.locator('.pixel-chat-bubble[data-message-key="r1"]').count(), 0);

    const geometry = await page.locator(".pixel-chat-bubble").evaluateAll((elements) =>
      elements.map((element) => {
        const rect = element.getBoundingClientRect();
        return {
          key: element.dataset.messageKey,
          left: rect.left,
          right: rect.right,
          top: rect.top,
          bottom: rect.bottom,
          styleLeft: element.style.left,
          styleTop: element.style.top
        };
      })
    );
    for (let first = 0; first < geometry.length; first += 1) {
      for (let second = first + 1; second < geometry.length; second += 1) {
        const a = geometry[first];
        const b = geometry[second];
        const overlaps = a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;
        assert.equal(overlaps, false, `${a.key} must not overlap ${b.key}`);
      }
    }

    const anchorDelta = await page.locator('.pixel-chat-bubble[data-message-key="r4"]').evaluate((element) => {
      const scene = document.getElementById("pixel-scene");
      const sceneRect = scene.getBoundingClientRect();
      const rect = element.getBoundingClientRect();
      const anchor = window.EmoTenderPixelScene.getAnchors().robot;
      const tailX = rect.right - rect.width * 0.12 - 4;
      const tailY = rect.bottom + 20;
      const expectedX = sceneRect.left + sceneRect.width * anchor.x / 100;
      const expectedY = sceneRect.top + sceneRect.height * anchor.y / 100;
      return { x: Math.abs(tailX - expectedX), y: Math.abs(tailY - expectedY) };
    });
    assert.ok(anchorDelta.x < 2, `robot tail x delta was ${anchorDelta.x}`);
    assert.ok(anchorDelta.y < 2, `robot tail y delta was ${anchorDelta.y}`);

    const longMessages = [
      message("lu1", "user", "前一天发生了很多事情，我想把整个过程慢慢说清楚，也不希望最重要的部分在场景里被直接省略。"),
      message("lr1", "robot", "我会先听你说完，再从你真正介意的部分继续聊，不急着马上给出结论或者推荐。"),
      message("lu2", "user", "后来我发现自己难受的不只是结果，而是已经认真准备了很久，却还是觉得没有达到原本期待的状态。"),
      message("lr2", "robot", "这种落差会让之前付出的努力像突然失去重量，但那些准备并没有因为一次结果就被全部抹掉。"),
      message("lu3", "user", "我还担心明天继续面对同样的事情时，自己会因为今天的经历变得没有信心，所以现在脑子里一直停不下来。"),
      message("lr3", "robot", "先不用逼自己立刻恢复信心，我们可以把今天和明天分开，让现在这一刻只负责慢慢安静下来。"),
      message("lu4", "user", "我今天考试没有考好，准备了很长时间还是没有得到想要的结果，现在既失落又疲惫，也不知道明天应该怎么重新开始。"),
      message("lr4", "robot", "我知道你今天考试没有考好，也听见了那种努力很久却没有得到预期结果的失落。现在不用急着证明自己已经恢复，我们先把今天放下来，再给明天留一点重新开始的力气。")
    ];
    await page.evaluate((items) => window.EmoTenderPixelScene.setMessages(items), longMessages.slice(0, 7));
    await page.waitForTimeout(320);

    const latestUser = page.locator('.pixel-chat-bubble[data-message-key="lu4"]');
    assert.equal(await latestUser.isVisible(), true, "the latest user message must remain visible");
    const latestUserClipping = await latestUser.locator(".pixel-bubble-text").evaluate((element) => ({
      clientHeight: element.clientHeight,
      scrollHeight: element.scrollHeight
    }));
    assert.ok(
      latestUserClipping.scrollHeight <= latestUserClipping.clientHeight + 1,
      `latest user message must be complete: ${JSON.stringify(latestUserClipping)}`
    );
    assert.ok(
      await page.locator(".pixel-chat-bubble:visible").count() > 1,
      "older bubbles should remain while the latest user message still fits"
    );
    if (screenshotDirectory) {
      await page.screenshot({ path: path.join(screenshotDirectory, "latest-user-long.png"), fullPage: true });
    }

    await page.evaluate((items) => window.EmoTenderPixelScene.setMessages(items), longMessages);
    await page.waitForTimeout(320);

    const visibleBubbleCount = await page.locator(".pixel-chat-bubble:visible").count();
    assert.ok(visibleBubbleCount < 6, `long dialogue should reduce visible bubbles, got ${visibleBubbleCount}`);
    const latestRobot = page.locator('.pixel-chat-bubble[data-message-key="lr4"]');
    assert.equal(await latestRobot.isVisible(), true, "the latest Mingming reply must remain visible");
    const latestRobotClipping = await latestRobot.locator(".pixel-bubble-text").evaluate((element) => ({
      clientHeight: element.clientHeight,
      scrollHeight: element.scrollHeight
    }));
    assert.ok(
      latestRobotClipping.scrollHeight <= latestRobotClipping.clientHeight + 1,
      `latest Mingming reply must be complete: ${JSON.stringify(latestRobotClipping)}`
    );
    assert.ok(
      visibleBubbleCount > 1,
      "older bubbles should remain while the latest Mingming reply still fits"
    );
    const previousUser = page.locator('.pixel-chat-bubble[data-message-key="lu4"]');
    if (await previousUser.isVisible()) {
      const previousUserClipping = await previousUser.locator(".pixel-bubble-text").evaluate((element) => ({
        clientHeight: element.clientHeight,
        scrollHeight: element.scrollHeight
      }));
      assert.ok(
        previousUserClipping.scrollHeight > previousUserClipping.clientHeight + 1,
        "the previous user message must be compressed after Mingming replies"
      );
    }
    if (screenshotDirectory) {
      await page.screenshot({ path: path.join(screenshotDirectory, "latest-mingming-long.png"), fullPage: true });
    }
    assert.equal(await page.locator(".pixel-history-row").count(), longMessages.length);

    const compressedMessages = [
      message("cu1", "user", "我想补充一些之前发生的事情，这一段旧消息需要在场景里压缩，但历史中仍然必须保留完整原文。"),
      message("cr1", "robot", "这条较早的回复也可以压缩显示，只要用户仍然能够通过气泡入口查看完整内容。"),
      message("cu2", "user", "后来我又想了一会儿。"),
      message("cr2", "robot", "嗯，我还在听。"),
      message("cu3", "user", "现在好多了。"),
      message("cr3", "robot", "那就慢一点。")
    ];
    await page.evaluate((items) => window.EmoTenderPixelScene.setMessages(items), compressedMessages);
    await page.waitForTimeout(320);

    const truncatedBubble = page.locator(".pixel-chat-bubble.is-truncated:visible").first();
    assert.ok(await truncatedBubble.count(), "an older compressed bubble must expose a history action");
    const truncatedKey = await truncatedBubble.getAttribute("data-message-key");
    await truncatedBubble.click();
    assert.equal(await page.locator("#history-drawer").getAttribute("aria-hidden"), "false");
    assert.equal(
      await page.locator(`.pixel-history-row[data-message-key="${truncatedKey}"]`).getAttribute("data-highlighted"),
      "true"
    );
    await page.evaluate(() => window.EmoTenderPixelScene.setHistoryOpen(false));
    assert.equal(await page.locator("#pixel-scene").evaluate((element) => element.classList.contains("history-open")), false);

    await page.evaluate(() => window.EmoTenderPixelScene.setRecommendationVisible(false));
    assert.equal(await page.locator("#recommendation-entry").isVisible(), false);
    await page.evaluate(() => window.EmoTenderPixelScene.setRecommendationVisible(true));
    assert.equal(await page.locator("#recommendation-entry").isVisible(), true);

    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    assert.ok(overflow <= 1, `horizontal overflow was ${overflow}px`);

    await page.evaluate(() => renderConversationHistory({
      history: [{
        user_text: "今天考试没有考好。",
        bartender_line: "我听见了，先不用急着把失落赶走。",
        feedback_prompt: "你愿意说说最难受的是哪一部分吗？",
        turn_type: "bar_chat"
      }]
    }, "", ""));
    await page.waitForTimeout(320);
    assert.equal(await page.locator(".pixel-chat-bubble").count(), 2);
    assert.equal(await page.locator(".pixel-history-row").count(), 2);

    if (screenshotDirectory) {
      await page.screenshot({ path: path.join(screenshotDirectory, "desktop.png"), fullPage: true });
    }

    await page.setViewportSize({ width: 390, height: 844 });
    await page.evaluate(() => window.EmoTenderPixelScene.scheduleLayout());
    await page.waitForTimeout(320);
    const mobileOverflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    assert.ok(mobileOverflow <= 1, `mobile horizontal overflow was ${mobileOverflow}px`);
    assert.equal(await page.locator("#manual-input").isVisible(), true);
    assert.equal(await page.locator("#scene-controls").isVisible(), true);
    const controlStyles = await page.locator("#scene-controls .pixel-control").evaluateAll((elements) =>
      elements.map((element) => {
        const style = getComputedStyle(element);
        return {
          background: style.backgroundColor,
          border: style.borderTopColor,
          color: style.color
        };
      })
    );
    controlStyles.slice(1).forEach((style) => assert.deepEqual(style, controlStyles[0]));
    if (screenshotDirectory) {
      await page.screenshot({ path: path.join(screenshotDirectory, "mobile.png"), fullPage: true });
    }

    await page.evaluate((items) => window.EmoTenderPixelScene.setMessages(items), longMessages);
    await page.waitForTimeout(320);
    assert.equal(await page.locator("#pixel-scene").evaluate((element) => element.classList.contains("history-open")), false);
    assert.equal(await page.locator("#history-drawer").getAttribute("aria-hidden"), "true");
    const closedDrawerGeometry = await page.locator("#history-drawer").evaluate((element) => {
      const sceneRect = document.getElementById("pixel-scene").getBoundingClientRect();
      const sceneStyle = getComputedStyle(document.getElementById("pixel-scene"));
      const drawerRect = element.getBoundingClientRect();
      const style = getComputedStyle(element);
      return {
        position: style.position,
        display: style.display,
        width: style.width,
        left: style.left,
        right: style.right,
        offsetLeft: element.offsetLeft,
        offsetWidth: element.offsetWidth,
        drawerLeft: drawerRect.left,
        drawerRight: drawerRect.right,
        sceneLeft: sceneRect.left,
        sceneRight: sceneRect.right,
        sceneContentRight: sceneRect.right - parseFloat(sceneStyle.borderRightWidth),
        animations: element.getAnimations().map((animation) => ({
          playState: animation.playState,
          currentTime: animation.currentTime,
          effectEnd: animation.effect && animation.effect.getComputedTiming().endTime
        }))
      };
    });
    assert.ok(
      closedDrawerGeometry.drawerLeft >= closedDrawerGeometry.sceneContentRight - 1,
      `closed drawer must be outside the scene: ${JSON.stringify(closedDrawerGeometry)}`
    );
    const mobileLatest = page.locator('.pixel-chat-bubble[data-message-key="lr4"]');
    const mobileLatestGeometry = await mobileLatest.evaluate((element) => {
      const text = element.querySelector(".pixel-bubble-text");
      const bubbleRect = element.getBoundingClientRect();
      const sceneRect = document.getElementById("pixel-scene").getBoundingClientRect();
      return {
        clientHeight: text.clientHeight,
        scrollHeight: text.scrollHeight,
        topInset: bubbleRect.top - sceneRect.top
      };
    });
    assert.ok(mobileLatestGeometry.scrollHeight <= mobileLatestGeometry.clientHeight + 1);
    assert.ok(mobileLatestGeometry.topInset >= 0, `mobile latest bubble top was ${mobileLatestGeometry.topInset}px`);
    if (screenshotDirectory) {
      await page.screenshot({ path: path.join(screenshotDirectory, "mobile-latest-long.png"), fullPage: true });
    }

    assert.deepEqual(pageErrors, []);
    console.log("pixel scene test passed");
  } finally {
    await browser.close();
    await new Promise((resolve) => server.close(resolve));
  }
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
