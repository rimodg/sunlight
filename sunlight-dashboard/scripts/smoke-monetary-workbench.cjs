// Local-only: published data exploration and one saved comparison inquiry.
const { chromium } = require(
  process.env.SUNLIGHT_PLAYWRIGHT_MODULE || "playwright",
);
const assert = require("node:assert/strict"),
  fs = require("node:fs"),
  path = require("node:path");
const base = process.env.SUNLIGHT_SMOKE_URL || "http://127.0.0.1:8051";
if (!["127.0.0.1", "localhost", "[::1]"].includes(new URL(base).hostname))
  throw new Error("Use an isolated local ledger.");
const artifacts =
  process.env.SUNLIGHT_SMOKE_ARTIFACT_DIR || "/tmp/sunlight-monetary-workbench";
fs.mkdirSync(artifacts, { recursive: true });
(async () => {
  const browser = await chromium.launch({
    executablePath: process.env.SUNLIGHT_CHROMIUM_PATH,
    headless: true,
    args: ["--no-sandbox"],
  });
  try {
    const p = await browser.newPage({
        viewport: { width: 1680, height: 1050 },
      }),
      errors = [];
    p.on("pageerror", (e) => errors.push(e.message));
    await p.goto(
      base +
        "/watch/?country=GH&money_measure=remittances_received&money_year=2023#money",
    );
    const dock = p.getByRole("region", {
      name: "Monetary atlas tools",
      exact: true,
    });
    await dock
      .locator(".mw-country-value")
      .filter({ hasText: "Ghana" })
      .waitFor();
    assert.equal(
      await dock
        .getByLabel("Monetary map measure", { exact: true })
        .inputValue(),
      "remittances_received",
    );
    assert.equal(
      await dock
        .getByLabel("Monetary source period", { exact: true })
        .inputValue(),
      "2023",
    );
    assert.match(await p.locator(".ev-money-map-key").innerText(), /Ghana/);
    await p.evaluate(
      () =>
        (window.__workbenchGlobe = document.querySelector(".ev-world-canvas")),
    );
    await dock
      .getByRole("button", { name: "Compare & history", exact: true })
      .click();
    await dock
      .getByLabel("Comparison country", { exact: true })
      .selectOption("NG");
    await dock
      .getByRole("button", { name: "Add country", exact: true })
      .click();
    await dock
      .getByLabel("Comparison baseline year", { exact: true })
      .selectOption("2022");
    await dock
      .locator(".mw-comparisons article")
      .filter({ hasText: "Nigeria" })
      .waitFor();
    const response = await p.request.get(
      base +
        "/watch-data/money/analysis?measure=remittances_received&countries=GH,NG&baseline=2022&year=2023",
    );
    const expected = await response.json();
    assert(response.ok());
    assert.equal(await dock.locator(".mw-comparisons article").count(), 3);
    assert(
      await p.evaluate(
        () =>
          window.__workbenchGlobe ===
          document.querySelector(".ev-world-canvas"),
      ),
    );
    await dock.locator(".mw-analysis-headline").scrollIntoViewIfNeeded();
    await p.screenshot({
      path: path.join(artifacts, "Monetary-Workbench-Comparison.png"),
    });
    const [report] = await Promise.all([
      p.waitForEvent("popup"),
      dock
        .getByRole("link", { name: "Readable analysis / PDF ↗", exact: true })
        .click(),
    ]);
    await report.waitForLoadState();
    assert.match(await report.innerText("body"), /Ghana|Nigeria/);
    assert(
      (await report.innerText("body")).includes(
        expected.series[1].current.value,
      ),
    );
    assert.match(await report.innerText("body"), /2022 \/ 2023/);
    await report.close();
    const [download] = await Promise.all([
      p.waitForEvent("download"),
      dock
        .getByRole("link", {
          name: "Download exact observations CSV ↓",
          exact: true,
        })
        .click(),
    ]);
    assert(
      fs
        .readFileSync(await download.path(), "utf8")
        .includes(expected.series[1].current.value),
    );
    await dock
      .getByRole("button", { name: "Copy workspace link", exact: true })
      .click();
    const shared = await dock
      .getByLabel("Shareable monetary workspace link", { exact: true })
      .inputValue();
    const url = new URL(shared);
    assert.equal(url.searchParams.get("country"), "GH");
    assert.equal(url.searchParams.get("money_view"), "history");
    assert.equal(url.searchParams.get("compare"), "GH,NG");
    assert.equal(url.searchParams.get("compare_from"), "2022");
    assert(!url.searchParams.has("case"));
    assert.equal(
      url.searchParams.get("money_revision"),
      expected.source_revision,
    );
    await p.goto(shared);
    await dock
      .locator(".mw-comparisons article")
      .filter({ hasText: "Nigeria" })
      .waitFor();
    assert.equal(
      await dock
        .getByLabel("Comparison baseline year", { exact: true })
        .inputValue(),
      "2022",
    );
    await dock
      .getByRole("button", { name: /Ghana, 2019, .*Inspect observation/ })
      .click();
    await dock
      .getByRole("button", { name: "Show 2019 on map →", exact: true })
      .click();
    await dock.locator(".mw-focus-meta").filter({ hasText: "2019" }).waitFor();
    assert.equal(
      await dock
        .getByLabel("Monetary source period", { exact: true })
        .inputValue(),
      "2019",
    );
    const oldRevision = new URL(shared);
    oldRevision.searchParams.set(
      "money_revision",
      "superseded-validation-revision",
    );
    await p.goto(oldRevision.href);
    await dock
      .getByRole("status")
      .filter({ hasText: "different source revision" })
      .waitFor();
    await p.goto(shared);
    await dock
      .locator(".mw-comparisons article")
      .filter({ hasText: "Nigeria" })
      .waitFor();
    const inquiryRequest = p.waitForRequest(
      (r) => r.method() === "POST" && r.url().endsWith("/research/inquiries"),
    );
    await dock
      .getByRole("button", {
        name: "Investigate this comparison →",
        exact: true,
      })
      .click();
    await p
      .getByRole("heading", { name: "Research desk", exact: true })
      .waitFor();
    await p
      .getByRole("button", { name: "Investigate & save", exact: true })
      .click();
    const payload = (await inquiryRequest).postDataJSON();
    assert.deepEqual(payload.country_codes, ["GH", "NG"]);
    assert.equal(payload.year_start, 2022);
    assert.equal(payload.year_end, 2023);
    assert(
      payload.sources.includes("monetary") &&
        payload.sources.includes("delivery_assurance"),
    );
    await p
      .getByRole("status")
      .filter({ hasText: "Investigation saved with its evidence snapshot." })
      .waitFor();
    await p
      .getByRole("button", { name: "Monetary atlas", exact: true })
      .click();
    await dock
      .getByRole("button", { name: "Focus Nigeria on globe →", exact: true })
      .click();
    await p
      .locator(".ev-camera-scope")
      .filter({ hasText: "Nigeria" })
      .waitFor();
    await dock
      .getByRole("button", { name: "Focus Ghana on globe →", exact: true })
      .click();
    await p.locator(".ev-camera-scope").filter({ hasText: "Ghana" }).waitFor();
    await dock
      .getByLabel("Comparison map year", { exact: true })
      .selectOption("2026");
    await dock
      .locator(".mw-comparisons article")
      .filter({ hasText: "Ghana" })
      .filter({ hasText: "An observation is missing" })
      .waitFor();
    assert.match(
      await p.locator(".ev-money-map-key").innerText(),
      /Unavailable/,
    );
    await dock
      .getByLabel("Comparison map year", { exact: true })
      .selectOption("2023");
    await dock
      .getByRole("button", { name: "Coverage & sources", exact: true })
      .click();
    const coverage = dock.getByRole("region", {
      name: "Monetary coverage and sources",
      exact: true,
    });
    assert.equal(await coverage.locator("tbody tr").count(), 27);
    assert.equal(
      await coverage.locator(".ev-money-missing article").count(),
      17,
    );
    await dock
      .getByLabel("Monetary map measure", { exact: true })
      .selectOption("external_debt");
    await dock
      .getByRole("button", { name: "Compare & history", exact: true })
      .click();
    await dock
      .getByText(
        "Changes describe the recorded position. They do not measure payments made during the year.",
        { exact: true },
      )
      .waitFor();
    await dock
      .getByLabel("Monetary map measure", { exact: true })
      .selectOption("aid");
    await dock
      .getByRole("button", { name: "Compare & history", exact: true })
      .click();
    await dock
      .getByLabel("Aid comparison role", { exact: true })
      .selectOption("outward");
    await dock
      .locator(".mw-comparisons article")
      .filter({ hasText: "Ghana" })
      .filter({ hasText: "Unavailable" })
      .waitFor();
    // An unavailable analysis is an explicit error with a working retry.
    await p.route("**/watch-data/money/analysis?*", (route) =>
      route.fulfill({ status: 503, json: { detail: "Validation outage" } }),
    );
    await dock
      .getByLabel("Aid comparison role", { exact: true })
      .selectOption("inward");
    await dock.getByRole("alert").waitFor();
    await p.unroute("**/watch-data/money/analysis?*");
    await dock
      .getByRole("button", { name: "Retry analysis", exact: true })
      .click();
    await dock
      .locator(".mw-comparisons article")
      .filter({ hasText: "Ghana" })
      .waitFor();
    await dock.getByRole("button", { name: "Explore", exact: true }).click();
    await dock
      .getByRole("button", { name: /Review .* evidence records/ })
      .click();
    await p
      .getByRole("region", { name: "Review queue tools", exact: true })
      .waitFor({ state: "visible" });
    assert.match(await p.locator(".rq-scope").innerText(), /Ghana/);
    await p
      .getByRole("button", { name: "Monetary atlas", exact: true })
      .click();
    await dock
      .getByLabel("Monetary map measure", { exact: true })
      .selectOption("goods_exports");
    await dock.getByLabel("Monetary country focus", { exact: true }).fill("AX");
    await dock
      .getByRole("button", { name: "Focus on globe →", exact: true })
      .click();
    await dock
      .locator(".mw-country-value")
      .filter({ hasText: "Åland Islands" })
      .filter({ hasText: "Unavailable" })
      .waitFor();
    await p
      .getByRole("button", { name: "Clear monetary map measure", exact: true })
      .click();
    await p.waitForURL(
      (url) => url.searchParams.get("money_measure") === "none",
    );
    assert.equal(
      await p.getByLabel("Visible flow layer", { exact: true }).inputValue(),
      "",
    );
    assert.equal(await p.locator(".ev-money-map-key").count(), 0);
    await dock
      .getByLabel("Monetary map measure", { exact: true })
      .selectOption("goods_exports");
    await p.setViewportSize({ width: 390, height: 844 });
    assert(await p.locator(".ev-world-canvas").isVisible());
    assert(
      await p.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth + 1,
      ),
    );
    await dock
      .getByRole("button", { name: "Compare & history", exact: true })
      .click();
    await dock.locator(".mw-analysis-headline").waitFor();
    await p.screenshot({
      path: path.join(artifacts, "Monetary-Workbench-Mobile.png"),
    });
    assert.deepEqual(errors, []);
    console.log(
      JSON.stringify({
        sharedScopeReload: true,
        revisionNotice: true,
        historyPointToMap: true,
        comparisonCountryFocus: true,
        clearMeasureRestoresFlows: true,
        comparison: true,
        exactPDFandCSV: true,
        scopedInquiry: true,
        missingYear: true,
        stockMeaning: true,
        aidDirection: true,
        coverageInventory: true,
        analysisRetry: true,
        recipientReview: true,
        missingCountry: true,
        persistentGlobe: true,
        mobile: true,
        errors,
      }),
    );
  } finally {
    await browser.close();
  }
})().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
