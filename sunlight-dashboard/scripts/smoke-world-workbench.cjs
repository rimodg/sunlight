// Browser regression against an isolated local API; never run against institutional records.
const { chromium } = require(
  process.env.SUNLIGHT_PLAYWRIGHT_MODULE || "playwright",
);
const assert = require("node:assert/strict");
const fs = require("node:fs"),
  path = require("node:path");
const base = process.env.SUNLIGHT_SMOKE_URL || "http://127.0.0.1:8044";
if (!["127.0.0.1", "localhost", "[::1]"].includes(new URL(base).hostname))
  throw new Error("Use an isolated local API.");
const artifacts =
  process.env.SUNLIGHT_SMOKE_ARTIFACT_DIR || "/tmp/sunlight-world-workbench";
fs.mkdirSync(artifacts, { recursive: true });
(async () => {
  const browser = await chromium.launch({
    executablePath: process.env.SUNLIGHT_CHROMIUM_PATH || undefined,
    headless: true,
    args: ["--no-sandbox"],
  });
  const p = await browser.newPage({ viewport: { width: 1680, height: 1050 } }),
    errors = [];
  p.on("pageerror", (e) => errors.push(e.message));
  await p.goto(base + "/watch/");
  await p
    .getByRole("heading", { name: "Global economic watch", exact: true })
    .waitFor();
  await p.evaluate(
    () => (window.__sunlightGlobe = document.querySelector(".ev-world-canvas")),
  );
  async function worldRemains() {
    assert(await p.locator(".ev-world-canvas").isVisible());
    assert(
      await p.evaluate(
        () =>
          window.__sunlightGlobe === document.querySelector(".ev-world-canvas"),
      ),
    );
    assert.equal(await p.locator(".ev-world-canvas").count(), 1);
  }
  await p.getByRole("button", { name: "Flow tracking", exact: true }).click();
  const desk = p.getByRole("region", {
    name: "Flow tracking tools",
    exact: true,
  });
  await desk
    .getByLabel("Connection layer", { exact: true })
    .selectOption("material");
  const card = desk.locator(".ev-connection-cards article").first();
  await card.waitFor();
  const endpoints = await card.locator("h2").innerText();
  await card
    .getByRole("button", { name: "Trace on globe ↗", exact: true })
    .click();
  const inspector = desk.getByRole("complementary", {
    name: "Selected connection",
  });
  await inspector.waitFor();
  assert.equal(await inspector.locator("h2").innerText(), endpoints);
  await worldRemains();
  await p.waitForTimeout(650);
  await p.screenshot({ path: path.join(artifacts, "World-Flow-Tracking.png") });
  // Selected evidence remains attached while research opens; the world never remounts.
  const [brief] = await Promise.all([
    p.waitForEvent("popup"),
    inspector
      .getByRole("button", {
        name: "Open connection brief / save PDF",
        exact: false,
      })
      .click(),
  ]);
  await brief.waitForLoadState();
  assert.match(await brief.innerText("body"), /Exact bilateral dollars/);
  await brief.close();
  await inspector
    .getByRole("button", { name: "Investigate this connection", exact: false })
    .click();
  await p
    .getByRole("heading", { name: "Research desk", exact: true })
    .waitFor();
  await worldRemains();
  assert.match(
    await p.getByLabel("What do you want to investigate?").inputValue(),
    /Material exports/,
  );
  await p
    .getByRole("button", { name: "Investigate & save", exact: true })
    .click();
  await p
    .getByRole("status")
    .filter({ hasText: "Investigation saved with its evidence snapshot." })
    .waitFor();
  assert.match(await p.locator("#research-result").innerText(), /2023 — 2023/);
  await worldRemains();
  await p
    .getByRole("button", { name: "Delivery assurance", exact: true })
    .click();
  await p
    .getByRole("heading", { name: "Delivery assurance", exact: true })
    .waitFor();
  await worldRemains();
  await p
    .getByRole("button", { name: "Open worked example ↗", exact: true })
    .click();
  await p
    .locator(".da-mission h2")
    .filter({ hasText: "clinic supply programme" })
    .waitFor();
  await worldRemains();
  await p.screenshot({ path: path.join(artifacts, "World-Delivery-Dock.png") });
  await p
    .getByRole("button", { name: "Records & review", exact: true })
    .click();
  await p
    .getByRole("heading", { name: "Records & review", exact: true })
    .waitFor();
  await worldRemains();
  await p.getByRole("button", { name: "Close tools ×", exact: true }).click();
  await p.getByRole("button", { name: "Clear trace ×", exact: true }).click();
  await p.getByLabel("Visible flow layer", { exact: true }).selectOption("");
  await p.waitForTimeout(650);
  await worldRemains();
  const timing = await p.evaluate(
    () =>
      new Promise((resolve) => {
        const times = [];
        let previous = null,
          mutations = 0;
        const start = performance.now();
        const observer = new MutationObserver(
          (events) => (mutations += events.length),
        );
        observer.observe(document.querySelector(".ev-globe"), {
          subtree: true,
          attributes: true,
          childList: true,
        });
        function tick(now) {
          if (previous !== null) times.push(now - previous);
          previous = now;
          if (now - start < 3000) requestAnimationFrame(tick);
          else {
            observer.disconnect();
            times.sort((a, b) => a - b);
            resolve({
              frames: times.length,
              fps: 1000 / (times.reduce((a, b) => a + b, 0) / times.length),
              p95_ms: times[Math.floor(times.length * 0.95)],
              svg_mutations: mutations,
            });
          }
        }
        requestAnimationFrame(tick);
      }),
  );
  assert.equal(
    timing.svg_mutations,
    0,
    "automatic rotation must not rebuild SVG geometry or update React DOM",
  );
  await p.screenshot({ path: path.join(artifacts, "World-Global-Watch.png") });
  await p.getByLabel("Research a country or territory").fill("Ghana");
  await p.locator(".ev-country-search form").getByRole("button").click();
  await p
    .getByRole("status")
    .filter({ hasText: "Country research: Ghana" })
    .waitFor();
  await worldRemains();
  await p.getByRole("button", { name: "Global view", exact: true }).click();
  await p.setViewportSize({ width: 390, height: 844 });
  await p.getByRole("button", { name: "Flow tracking", exact: true }).click();
  await p
    .getByRole("heading", { name: "Flow tracking", exact: true })
    .waitFor();
  await worldRemains();
  const globe = await p.locator(".ev-world-canvas").boundingBox(),
    dock = await desk.boundingBox();
  assert(globe.height > 150 && globe.y + globe.height <= dock.y + 1);
  assert(
    await p.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
  );
  await p.screenshot({
    path: path.join(artifacts, "World-Mobile-Workbench.png"),
  });
  const reduced = await browser.newPage({
    viewport: { width: 1280, height: 900 },
    reducedMotion: "reduce",
  });
  reduced.on("pageerror", (e) => errors.push(e.message));
  await reduced.goto(base + "/watch/");
  await reduced
    .getByRole("heading", { name: "Global economic watch", exact: true })
    .waitFor();
  await reduced.waitForTimeout(1000);
  const pixels = () =>
    reduced.evaluate(() => {
      const c = document.querySelector(".ev-world-canvas"),
        v = c.getContext("2d").getImageData(0, 0, c.width, c.height).data;
      let hash = 0;
      for (let i = 0; i < v.length; i += 113) hash = (hash * 31 + v[i]) | 0;
      return hash;
    });
  const before = await pixels();
  await reduced.waitForTimeout(250);
  assert.equal(await pixels(), before, "reduced motion keeps the scene steady");
  await reduced.close();
  assert.deepEqual(errors, []);
  await browser.close();
  console.log(
    "PASS: persistent world across tracking, research, delivery and records; source trace and brief; saved scoped inquiry; country search; mobile split view; reduced motion; zero SVG rebuilds during rotation. Local timing:",
    JSON.stringify(timing),
  );
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
