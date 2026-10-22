/* Use an isolated local API/database. This saves one test inquiry. */
const { chromium } = require(
  process.env.SUNLIGHT_PLAYWRIGHT_MODULE || "playwright",
);
const assert = require("node:assert/strict"),
  fs = require("node:fs"),
  path = require("node:path");
const base = process.env.SUNLIGHT_SMOKE_URL || "http://127.0.0.1:8045";
if (!["127.0.0.1", "localhost", "[::1]"].includes(new URL(base).hostname))
  throw new Error("Use an isolated local API.");
const artifacts =
  process.env.SUNLIGHT_SMOKE_ARTIFACT_DIR || "/tmp/sunlight-monetary-atlas";
fs.mkdirSync(artifacts, { recursive: true });
(async () => {
  const browser = await chromium.launch({
    executablePath: process.env.SUNLIGHT_CHROMIUM_PATH,
    headless: true,
    args: ["--no-sandbox"],
  });
  const p = await browser.newPage({ viewport: { width: 1680, height: 1050 } }),
    errors = [];
  p.on("pageerror", (e) => errors.push(e.message));
  await p.goto(base + "/watch/");
  await p.locator(".ev-open-money").filter({ hasText: "$26.39T" }).waitFor();
  await p.evaluate(
    () => (window.__moneyCanvas = document.querySelector(".ev-world-canvas")),
  );
  async function world() {
    assert(await p.locator(".ev-world-canvas").isVisible());
    assert(
      await p.evaluate(
        () =>
          window.__moneyCanvas === document.querySelector(".ev-world-canvas"),
      ),
    );
  }
  await p.getByRole("button", { name: "Monetary atlas", exact: true }).click();
  const dock = p.getByRole("region", {
    name: "Monetary atlas tools",
    exact: true,
  });
  assert.equal(await dock.locator(".ev-money-totals button").count(), 28);
  await world();
  await p.getByText("API connected", { exact: true }).waitFor();
  await p
    .locator(".ev-map-caption")
    .filter({ hasText: "47,942 material links" })
    .waitFor();
  await p.waitForTimeout(450);
  await p.screenshot({ path: path.join(artifacts, "Monetary-Atlas.png") });
  await dock
    .getByLabel("Monetary map measure", { exact: true })
    .selectOption("remittances_received");
  await p.waitForTimeout(400);
  assert.match(await dock.locator(".ev-money-selected").innerText(), /925.55B/);
  assert.match(
    await p.locator(".ev-money-map-key").innerText(),
    /Personal remittances received/,
  );
  await dock
    .getByLabel("Find a country or connection", { exact: true })
    .fill("Nigeria");
  await dock
    .locator(".ev-money-country-list button")
    .filter({ hasText: "Nigeria" })
    .click();
  await world();
  const profile = dock.getByRole("region", {
    name: "Country monetary profile",
    exact: true,
  });
  await dock
    .getByText("Nigeria · all monetary measures", { exact: true })
    .click();
  await profile.waitFor();
  assert.match(await profile.innerText(), /Nigeria/);
  assert.equal(await profile.locator("button").count(), 28);
  assert.match(
    await p.locator(".ev-camera-scope").innerText(),
    /Country research: Nigeria/,
  );
  await p.waitForTimeout(600);
  await p.screenshot({ path: path.join(artifacts, "Monetary-Country.png") });
  await profile
    .getByRole("button", { name: "Return to all countries", exact: false })
    .click();
  await dock
    .getByLabel("Find a country or connection", { exact: true })
    .fill("");
  await dock
    .getByLabel("Monetary source period", { exact: true })
    .selectOption("2026");
  await dock.locator(".mw-focus").filter({ hasText: "Unavailable" }).waitFor();
  assert.match(
    await dock.locator(".ev-money-selected").innerText(),
    /No observation for this year/,
  );
  assert.equal(await dock.locator(".ev-money-country-list button").count(), 0);
  assert.match(await p.locator(".ev-money-map-key").innerText(), /Unavailable/);
  await dock
    .getByLabel("Monetary source period", { exact: true })
    .selectOption("");
  await dock
    .getByLabel("Monetary map measure", { exact: true })
    .selectOption("aid");
  await dock.locator(".ev-money-pair").first().waitFor();
  await dock.locator(".ev-money-pair").first().click();
  const tracking = p.getByRole("region", {
    name: "Flow tracking tools",
    exact: true,
  });
  const inspector = tracking.getByRole("complementary", {
    name: "Selected connection",
  });
  await inspector.waitFor();
  await world();
  assert.match(await inspector.innerText(), /net aid disbursements/);
  await inspector
    .getByText("Source evidence & interpretation", { exact: true })
    .click();
  assert.match(
    await inspector.innerText(),
    /does not verify recipient credits/,
  );
  const [brief] = await Promise.all([
    p.waitForEvent("popup"),
    inspector.getByRole("button", { name: /Open connection brief/ }).click(),
  ]);
  await brief.waitForLoadState();
  assert.match(await brief.innerText("body"), /Pinned data extract/);
  await brief.close();
  await p.waitForTimeout(600);
  await p.screenshot({ path: path.join(artifacts, "Monetary-Aid-Trace.png") });
  await inspector
    .getByRole("button", { name: /Investigate this connection/ })
    .click();
  await p
    .getByRole("heading", { name: "Research desk", exact: true })
    .waitFor();
  await p
    .getByRole("button", { name: "Investigate & save", exact: true })
    .click();
  await p
    .getByRole("status")
    .filter({ hasText: "Investigation saved with its evidence snapshot." })
    .waitFor();
  assert.match(
    await p.locator("#research-result").innerText(),
    /monetary|bilateral aid|Monetary atlas/i,
  );
  await world();
  await p.setViewportSize({ width: 390, height: 844 });
  await p.getByRole("button", { name: "Monetary atlas", exact: true }).click();
  await dock
    .getByRole("heading", { name: "Monetary atlas", exact: true })
    .waitFor();
  await world();
  assert(
    await p.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth + 1,
    ),
  );
  await p.screenshot({ path: path.join(artifacts, "Monetary-Mobile.png") });
  assert.deepEqual(errors, []);
  console.log(
    JSON.stringify({
      monetaryMeasures: 27,
      aidLayer: true,
      countryProfile: true,
      unknownYear: true,
      sourceBrief: true,
      savedInquiry: true,
      persistentCanvas: true,
      mobile: true,
      pageErrors: errors,
    }),
  );
  await browser.close();
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
