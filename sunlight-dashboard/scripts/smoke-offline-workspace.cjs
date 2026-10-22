// Cold browser session: only loopback requests are allowed. Uses a local API
// started with SUNLIGHT_OFFLINE=1; creates fictional validation records only.
const { chromium } = require(
  process.env.SUNLIGHT_PLAYWRIGHT_MODULE || "playwright",
);
const assert = require("node:assert/strict"),
  fs = require("node:fs"),
  path = require("node:path"),
  { spawnSync } = require("node:child_process");
const base = process.env.SUNLIGHT_SMOKE_URL || "http://127.0.0.1:8055";
if (!["127.0.0.1", "localhost", "[::1]"].includes(new URL(base).hostname))
  throw new Error("Use an isolated local instance.");
const artifacts =
  process.env.SUNLIGHT_SMOKE_ARTIFACT_DIR || "/tmp/sunlight-offline-browser";
fs.mkdirSync(artifacts, { recursive: true });
(async () => {
  const browser = await chromium.launch({
    executablePath: process.env.SUNLIGHT_CHROMIUM_PATH,
    headless: true,
    args: ["--no-sandbox"],
  });
  try {
    const context = await browser.newContext({
        viewport: { width: 1680, height: 1050 },
      }),
      blocked = [],
      errors = [];
    await context.route("**/*", (route) => {
      const u = new URL(route.request().url());
      if (["127.0.0.1", "localhost", "[::1]"].includes(u.hostname))
        return route.continue();
      blocked.push(u.origin);
      return route.abort("internetdisconnected");
    });
    const p = await context.newPage();
    p.on("pageerror", (e) => errors.push(e.message));
    const mode = await p.request.get(base + "/offline/status");
    assert(
      (await mode.json()).offline_policy,
      "Start the local API with offline policy enabled.",
    );
    await p.goto(base + "/watch/");
    await p
      .getByRole("button", { name: "Offline workspace", exact: true })
      .click();
    const panel = p.getByRole("region", { name: "Offline tools", exact: true });
    await panel
      .locator(".of-mode")
      .filter({ hasText: "Offline policy active" })
      .waitFor();
    await p.evaluate(
      () =>
        (window.__offlineGlobe = document.querySelector(".ev-world-canvas")),
    );
    assert.match(
      await panel.innerText(),
      /Remote refreshes|External refreshes/,
    );
    const [guide] = await Promise.all([
      p.waitForEvent("popup"),
      panel
        .getByRole("link", {
          name: "Local installation guide / PDF ↗",
          exact: true,
        })
        .click(),
    ]);
    await guide.waitForLoadState();
    assert.match(await guide.innerText("body"), /start.sh/);
    await guide.close();
    const stamp = Date.now(),
      source = "offline-browser-" + stamp,
      title = "Fictional offline browser medical kits " + stamp;
    async function post(url, data) {
      const r = await p.request.post(base + url, { data });
      assert(r.ok(), await r.text());
      return r.json();
    }
    await post("/operations/sources", {
      source_id: source,
      name: "Isolated offline browser validation",
      publisher_url: "https://example.org",
      profile: "us_federal",
    });
    const measure = {
      metric: "delivery",
      unit: "kit",
      value: "100",
      period_start: "2025-01-01",
      period_end: "2025-02-01",
      document_url: "https://example.org/validation",
    };
    await post("/operations/ingest", {
      source_id: source,
      events: [
        {
          event_id: "event",
          contract_id: source,
          item_id: "kits",
          category: "medical",
          revision: 1,
          title,
          origin_country: "NL",
          destination_country: "GH",
          published_at: "2025-03-03T00:00:00Z",
          expected: { ...measure, due_at: "2025-03-01T00:00:00Z" },
          observed: {
            ...measure,
            value: "73",
            observed_at: "2025-03-02T00:00:00Z",
          },
        },
      ],
    });
    await panel
      .getByRole("button", { name: /Source and transaction references/ })
      .click();
    await p
      .getByRole("heading", { name: "Records & review", exact: true })
      .waitFor();
    await p.getByText(title, { exact: true }).waitFor();
    assert(
      await p.evaluate(
        () =>
          window.__offlineGlobe === document.querySelector(".ev-world-canvas"),
      ),
    );
    await p
      .getByRole("button", { name: "Offline workspace", exact: true })
      .click();
    await panel
      .getByRole("button", { name: /Documents, calculations and inquiry/ })
      .click();
    await p
      .getByRole("heading", { name: "Research desk", exact: true })
      .waitFor();
    await p
      .locator("#research-question")
      .fill(
        "Investigate Ghana medical kit delivery in the offline browser source records",
      );
    await p
      .getByRole("button", { name: "Investigate & save", exact: true })
      .click();
    await p
      .getByRole("status")
      .filter({ hasText: "Investigation saved with its evidence snapshot." })
      .waitFor();
    assert.match(
      await p.locator("#research-result").innerText(),
      /Ghana|medical|kit/i,
    );
    await p
      .getByRole("button", { name: "Offline workspace", exact: true })
      .click();
    await panel
      .getByRole("button", { name: "Refresh local status", exact: true })
      .click();
    await panel
      .locator(".of-counts")
      .filter({ hasText: "Saved investigations" })
      .waitFor();
    const [download] = await Promise.all([
      p.waitForEvent("download"),
      panel
        .getByRole("link", {
          name: "Download full evidence checkpoint ↓",
          exact: true,
        })
        .click(),
    ]);
    const file = await download.path();
    assert(fs.statSync(file).size > 1000);
    const python =
      process.env.SUNLIGHT_PYTHON || "/workspace/.venvs/sunlight/bin/python";
    const checked = spawnSync(
      python,
      ["-m", "portable_checkpoint", "verify", file],
      {
        env: { ...process.env, PYTHONPATH: path.resolve("code") },
        encoding: "utf8",
      },
    );
    assert.equal(checked.status, 0, checked.stdout + checked.stderr);
    await p.screenshot({ path: path.join(artifacts, "Offline-Workspace.png") });
    await p.setViewportSize({ width: 390, height: 844 });
    assert(await p.locator(".ev-world-canvas").isVisible());
    assert(
      await p.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth + 1,
      ),
    );
    await p.screenshot({
      path: path.join(artifacts, "Offline-Workspace-Mobile.png"),
    });
    await p.waitForURL((u) => u.hash === "#offline");
    for (let i = 0; i < 2; i++) {
      await p.reload();
      await panel
        .locator(".of-mode")
        .filter({ hasText: "Offline policy active" })
        .waitFor();
    }
    assert.deepEqual(
      blocked,
      [],
      "The cold local workspace must not depend on external browser assets or data.",
    );
    assert.deepEqual(errors, []);
    console.log(
      JSON.stringify({
        coldLocalLoad: true,
        externalBrowserRequests: blocked.length,
        offlineStatus: true,
        localRecordIntake: true,
        localSavedResearch: true,
        checkpointDownloadAndVerification: true,
        retainedGlobe: true,
        mobile: true,
        reload: true,
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
