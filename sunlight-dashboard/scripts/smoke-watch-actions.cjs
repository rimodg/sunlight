// Read-only browser journeys against an isolated ledger populated by smoke-review-queue.
const { chromium } = require(
  process.env.SUNLIGHT_PLAYWRIGHT_MODULE || "playwright",
);
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const base = process.env.SUNLIGHT_SMOKE_URL || "http://127.0.0.1:8047";
if (!["127.0.0.1", "localhost", "[::1]"].includes(new URL(base).hostname))
  throw new Error("Use an isolated local ledger.");
const artifacts =
  process.env.SUNLIGHT_SMOKE_ARTIFACT_DIR || "/tmp/sunlight-watch-actions";
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
    });
    const errors = [];
    p.on("pageerror", (e) => errors.push(e.message));
    const r = await p.request.get(base + "/workbench/review-queue?limit=1");
    assert(r.ok());
    const real = await r.json();
    assert(
      real.items.length,
      "Populate an isolated ledger with smoke-review-queue first.",
    );
    await p.goto(base + "/watch/");
    const actions = p.getByRole("region", {
      name: "Watch actions",
      exact: true,
    });
    await actions
      .getByRole("heading", { name: "What needs attention" })
      .waitFor();
    await actions.getByText(real.items[0].title, { exact: true }).waitFor();
    const box = await actions.boundingBox();
    assert(
      box.y + box.height < 420,
      "Action surface must be visible above the globe without scrolling.",
    );
    await p.locator(".ev-world-canvas").waitFor({ state: "visible" });
    await p.evaluate(
      () =>
        (window.__actionsGlobe = document.querySelector(".ev-world-canvas")),
    );
    await p.screenshot({ path: path.join(artifacts, "Watch-Actions.png") });
    await actions.getByRole("button", { name: /need assignment/ }).click();
    const queue = p.getByRole("region", {
      name: "Review queue tools",
      exact: true,
    });
    await queue.locator(".rq-items article").first().waitFor();
    assert(
      await queue.getByLabel("Needs assignment", { exact: true }).isChecked(),
    );
    assert(
      await p.evaluate(
        () =>
          window.__actionsGlobe === document.querySelector(".ev-world-canvas"),
      ),
    );
    await p.getByRole("button", { name: "Global watch", exact: true }).click();
    await actions
      .getByRole("button", {
        name: "Open evidence & next steps →",
        exact: true,
      })
      .click();
    await p.waitForURL(
      (url) =>
        url.searchParams.get(
          real.items[0].kind === "delivery" ? "obligation" : "case",
        ) === real.items[0].id,
    );
    await p.getByRole("button", { name: "Global watch", exact: true }).click();
    await actions.getByRole("button", { name: /Explore money flows/ }).click();
    await p
      .getByRole("region", { name: "Monetary atlas tools", exact: true })
      .waitFor({ state: "visible" });
    await p.getByRole("button", { name: "Global watch", exact: true }).click();
    await actions
      .getByRole("button", { name: /Verify funds & delivery/ })
      .click();
    await p
      .getByRole("heading", { name: "Delivery assurance", exact: true })
      .waitFor();
    await p.getByRole("button", { name: "Global watch", exact: true }).click();
    await p.setViewportSize({ width: 390, height: 844 });
    const globe = await p.locator(".ev-world-canvas").boundingBox();
    assert(
      globe.height > 180,
      "The globe must retain working space on mobile.",
    );
    assert(
      await p.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    );
    await p.screenshot({
      path: path.join(artifacts, "Watch-Actions-Mobile.png"),
    });
    // Explicitly exercise unavailable status; a failed fetch must never become a zero.
    await p.route("**/workbench/review-queue?*", (route) =>
      route.fulfill({ status: 503, json: { detail: "Validation outage" } }),
    );
    await p.reload();
    await actions.getByRole("alert").waitFor();
    assert.match(await actions.innerText(), /No current review counts/);
    assert(!/0 review records/.test(await actions.innerText()));
    await p.unroute("**/workbench/review-queue?*");
    await actions.getByRole("button", { name: "Retry review status" }).click();
    await actions.getByText(real.items[0].title, { exact: true }).waitFor();
    // Empty coverage and finished reviews require different, truthful first-use actions.
    await p.route("**/workbench/review-queue?*", (route) =>
      route.fulfill({
        json: {
          ...real,
          items: [],
          total: 0,
          unassigned: 0,
          registered: { delivery: 0, operations: 0 },
        },
      }),
    );
    await p.reload();
    await actions
      .getByText("Arrival and delivery checks start with evidence", {
        exact: true,
      })
      .waitFor();
    await actions
      .getByRole("button", { name: "Open source intake →" })
      .click();
    await p
      .getByRole("region", { name: "Records tools", exact: true })
      .waitFor({ state: "visible" });
    assert.deepEqual(errors, []);
    console.log(
      JSON.stringify({
        visiblePriorities: true,
        assignmentFilter: true,
        exactRecord: true,
        moneyAndDeliveryActions: true,
        sameGlobe: true,
        mobile: true,
        failureAndRetry: true,
        honestEmptyState: true,
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
