// Run against an isolated local API database; this script creates synthetic test records.
// Optional browser verification; Playwright is supplied by the execution environment.
const { chromium } = require(
  process.env.SUNLIGHT_PLAYWRIGHT_MODULE || "playwright",
);
const fs = require("node:fs");
const path = require("node:path");
const base = process.env.SUNLIGHT_SMOKE_URL || "http://127.0.0.1:8043";
if (!["127.0.0.1", "localhost", "[::1]"].includes(new URL(base).hostname))
  throw new Error(
    "Use an isolated local API, not a hosted institutional deployment.",
  );
const artifacts =
  process.env.SUNLIGHT_SMOKE_ARTIFACT_DIR ||
  "/tmp/sunlight-delivery-assurance-smoke";
fs.mkdirSync(artifacts, { recursive: true });
const assert = require("node:assert/strict");
(async () => {
  const browser = await chromium.launch({
    executablePath: process.env.SUNLIGHT_CHROMIUM_PATH || undefined,
    headless: true,
    args: ["--no-sandbox"],
  });
  const p = await browser.newPage({ viewport: { width: 1680, height: 1080 } });
  const errors = [];
  p.on("pageerror", (e) => errors.push(e.message));
  p.on("console", (m) => {
    if (
      m.type() === "error" &&
      /Pattern attribute|Invalid regular/.test(m.text())
    )
      errors.push(m.text());
  });
  await p.goto(base + "/watch/");
  await p
    .getByRole("heading", { name: "Global economic watch", exact: true })
    .waitFor();
  await p
    .getByRole("button", { name: "Open delivery assurance →", exact: true })
    .click();
  await p
    .getByRole("heading", { name: "Delivery assurance", exact: true })
    .waitFor();
  await p
    .getByRole("button", { name: "Open worked example ↗", exact: true })
    .click();
  await p
    .locator(".da-mission h2")
    .filter({ hasText: "clinic supply programme" })
    .waitFor();
  assert.match(await p.locator(".da-finance").innerText(), /30000/);
  assert.match(
    await p.locator(".da-chain").innerText(),
    /270 medical kit shortfall/,
  );
  await p
    .getByLabel("Delivery calibration profile", { exact: true })
    .selectOption("us_federal");
  await p
    .getByRole("button", {
      name: "Run calibrated delivery checks",
      exact: true,
    })
    .click();
  await p
    .getByRole("status")
    .filter({
      hasText: "Calibrated delivery analysis retained with its evidence basis.",
    })
    .waitFor();
  await p
    .locator(".da-engine article")
    .filter({ hasText: "DEL-OUT-001" })
    .last()
    .waitFor();
  await p.screenshot({
    path: path.join(artifacts, "Delivery-Assurance-Desktop.png"),
    fullPage: true,
  });
  const [report] = await Promise.all([
    p.waitForEvent("popup"),
    p.getByRole("link", { name: "Readable brief / PDF", exact: false }).click(),
  ]);
  await report.waitForLoadState();
  assert.match(await report.innerText("body"), /30000/);
  assert.match(await report.innerText("body"), /DEL-OUT-001/);
  await report.pdf({
    path: path.join(artifacts, "Delivery-Assurance-Example.pdf"),
    format: "A4",
    printBackground: true,
  });
  await report.close();
  await p
    .getByRole("button", { name: "Investigate this obligation →", exact: true })
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
  assert.match(await p.locator("#research-result").innerText(), /30000/);
  assert.match(
    await p.locator("#research-result").innerText(),
    /SYNTHETIC EXAMPLE/,
  );
  await p
    .getByRole("button", { name: "Delivery assurance", exact: true })
    .click();
  await p
    .getByRole("button", { name: "Register an obligation +", exact: true })
    .click();
  let d = p.getByRole("dialog");
  await d.waitFor();
  const token = Date.now();
  const fields = {
    "Obligation reference": "browser-water-" + token,
    "Programme / contract title": "Browser water delivery " + token,
    "Intended communities / facilities": "Five fictional communities",
    "Responsible programme owner": "Programme team",
    "Receiving organization": "Receiving authority",
    "What should people receive, and what counts as accepted delivery?":
      "Deliver and accept one hundred usable water kits for five communities.",
    "Baseline / contract document URL": "https://example.org/contract",
    "Delivery & service deadline": "2025-10-01T00:00",
    "Delivery target quantity": "100",
    "Delivery unit": "kit",
    "Service outcome target (optional)": "5",
    "Service outcome unit": "community",
    "Budget context (optional)": "1000",
    "Budget currency (ISO code)": "USD",
  };
  for (const [key, value] of Object.entries(fields))
    await d.getByLabel(key, { exact: true }).fill(value);
  await d
    .getByLabel("Receiving country / territory", { exact: true })
    .selectOption("GH");
  await d
    .getByRole("button", { name: "Register obligation", exact: true })
    .click();
  await d.waitFor({ state: "hidden" });
  await p
    .locator(".da-mission h2")
    .filter({ hasText: "Browser water delivery" })
    .waitFor();
  async function record(kind, data) {
    await p
      .getByRole("button", { name: "Record evidence +", exact: true })
      .click();
    const dialog = p.getByRole("dialog");
    await dialog
      .getByLabel("Evidence stage", { exact: true })
      .selectOption(kind);
    for (const [key, value] of Object.entries(data))
      await dialog.getByLabel(key, { exact: true }).fill(value);
    await dialog
      .getByRole("button", { name: "Retain evidence & reconcile", exact: true })
      .click();
    await dialog.waitFor({ state: "hidden" });
  }
  const financial = {
    "Ledger entry amount": "1000",
    "Currency (ISO code)": "USD",
    "Shared transfer reference": "tx-browser-" + token,
    "Sender party ID": "treasury-browser-" + token,
    "Recipient party ID": "authority-browser-" + token,
    "Declared issuer party ID": "treasury-browser-" + token,
    "Declared issuer name": "Example treasury",
    "Unique issuer entry / snapshot reference": "debit-browser-" + token,
    "Observation / value time": "2025-10-02T00:00",
    "Supporting document URL": "https://example.org/debit",
    "Evidence basis, scope and limitations":
      "Executed sender debit supplied for a synthetic browser check.",
    "Settlement deadline": "2025-10-03T00:00",
  };
  await record("funds_sent", financial);
  assert.match(
    await p.locator(".da-finance").innerText(),
    /Arrival evidence missing/,
  );
  assert.match(await p.locator(".da-finance").innerText(), /Not calculable/);
  const credit = {
    ...financial,
    "Ledger entry amount": "960",
    "Declared issuer party ID": "bank-browser-" + token,
    "Declared issuer name": "Example receiving bank",
    "Unique issuer entry / snapshot reference": "credit-browser-" + token,
    "Observation / value time": "2025-10-04T00:00",
    "Supporting document URL": "https://example.org/credit",
  };
  delete credit["Settlement deadline"];
  await record("funds_received", credit);
  assert.match(await p.locator(".da-finance").innerText(), /40/);
  const acceptance = {
    "Cumulative quantity": "73",
    "Snapshot unit": "kit",
    "Cumulative coverage through": "2025-10-04T00:00",
    "Declared issuer party ID": "inspector-browser-" + token,
    "Declared issuer name": "Example receiving inspector",
    "Unique issuer entry / snapshot reference": "accept-browser-" + token,
    "Observation / value time": "2025-10-04T00:00",
    "Supporting document URL": "https://example.org/acceptance",
    "Evidence basis, scope and limitations":
      "Cumulative acceptance record for this obligation.",
  };
  await record("accepted", acceptance);
  assert.match(await p.locator(".da-chain").innerText(), /27 kit shortfall/);
  const issue = p
    .locator(".da-signals article")
    .filter({ hasText: "Accepted: shortfall" });
  await issue.getByRole("button", { name: "Assign follow-up →" }).click();
  d = p.getByRole("dialog");
  await d
    .getByLabel("Response deadline", { exact: true })
    .fill("2099-01-01T00:00");
  await d
    .getByRole("button", { name: "Assign follow-up", exact: true })
    .click();
  await d.waitFor({ state: "hidden" });
  await p
    .getByRole("button", { name: "Update follow-up", exact: true })
    .click();
  d = p.getByRole("dialog");
  await d
    .getByLabel("Follow-up status", { exact: true })
    .selectOption("completed");
  await d
    .getByLabel("Completion evidence (required)", { exact: true })
    .selectOption({
      label:
        "Accepted delivery · Example receiving inspector · accept-browser-" +
        token,
    });
  await d
    .getByLabel("Progress / result and its evidence basis", { exact: true })
    .fill(
      "Inspection completed and its supporting evidence retained. Delivery discrepancy remains open.",
    );
  await d.getByRole("button", { name: "Save progress", exact: true }).click();
  await d.waitFor({ state: "hidden" });
  assert.match(await p.locator(".da-chain").innerText(), /27 kit shortfall/);
  await p
    .getByRole("button", { name: "Source register (3)", exact: true })
    .click();
  const acceptanceCard = p
    .locator(".da-evidence>article")
    .filter({ hasText: "Accepted delivery" });
  await acceptanceCard
    .getByRole("button", { name: "Record correction", exact: true })
    .click();
  d = p.getByRole("dialog");
  await d.getByLabel("Cumulative quantity", { exact: true }).fill("100");
  await d
    .getByLabel("Evidence basis, scope and limitations", { exact: true })
    .fill(
      "Corrected acceptance: the subsequent inspection confirms one hundred kits.",
    );
  // Another reviewer changes history while this correction remains a draft.
  const oid = new URL(p.url()).searchParams.get("obligation");
  const snapshot = await (
    await p.request.get(base + "/assurance/obligations/" + oid)
  ).json();
  const concurrent = await p.request.post(
    base + "/assurance/obligations/" + oid + "/actions",
    {
      data: {
        expected_version: snapshot.version,
        title: "Concurrent evidence review",
        kind: "evidence_request",
        owner: "Second example reviewer",
        due_at: "2099-01-01T00:00:00Z",
        note: "Obtain corroboration while the first reviewer edits a correction.",
      },
    },
  );
  assert.equal(concurrent.status(), 200);
  await d
    .getByRole("button", { name: "Retain evidence & reconcile", exact: true })
    .click();
  const rebase = d.getByRole("button", {
    name: "Use latest version and retain draft",
    exact: true,
  });
  await rebase.waitFor();
  assert.equal(
    await d.getByLabel("Cumulative quantity", { exact: true }).inputValue(),
    "100",
  );
  await rebase.click();
  await d
    .getByRole("button", { name: "Retain evidence & reconcile", exact: true })
    .click();
  await d.waitFor({ state: "hidden" });
  await p
    .getByRole("button", { name: "Evidence & breaks", exact: true })
    .click();
  assert.match(
    await p.locator(".da-signals").innerText(),
    /Review completed follow-up evidence/,
  );
  await p.reload();
  await p
    .locator(".da-mission h2")
    .filter({ hasText: "Browser water delivery" })
    .waitFor();
  assert.match(await p.locator(".da-finance").innerText(), /40/);
  await p.setViewportSize({ width: 390, height: 844 });
  assert(
    await p.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
    "mobile overflow",
  );
  await p.screenshot({
    path: path.join(artifacts, "Delivery-Assurance-Mobile.png"),
    fullPage: true,
  });
  await p
    .getByRole("button", { name: "Locate on watch ↗", exact: true })
    .click();
  await p
    .getByRole("status")
    .filter({ hasText: "Country research: Ghana" })
    .waitFor();
  assert(await p.locator(".ev-world-canvas").isVisible());
  assert(await p.locator(".da-mission h2").isVisible());
  await p.getByRole("button", { name: "Close tools ×", exact: true }).click();
  await p
    .getByRole("button", { name: "Delivery assurance", exact: true })
    .click();
  await p
    .locator(".da-mission h2")
    .filter({ hasText: "Browser water delivery" })
    .waitFor();
  assert(
    await p.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
  );
  assert.deepEqual(errors, []);
  await browser.close();
  console.log(
    "PASS: watch to assurance, isolated worked chain, calibrated engine, readable PDF, exact obligation inquiry, guided registration, sender/credit reconciliation, acceptance shortfall, evidence-backed follow-up, retained corrections, reload, country watch handoff, desktop/mobile without browser errors.",
  );
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
