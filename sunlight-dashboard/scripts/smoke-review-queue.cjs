/* Exercises real APIs and UI against an isolated local ledger only. */
const { chromium } = require(
  process.env.SUNLIGHT_PLAYWRIGHT_MODULE || "playwright",
);
const assert = require("node:assert/strict"),
  fs = require("node:fs"),
  path = require("node:path");
const base = process.env.SUNLIGHT_SMOKE_URL || "http://127.0.0.1:8047";
if (!["127.0.0.1", "localhost", "[::1]"].includes(new URL(base).hostname))
  throw new Error("Use an isolated local ledger.");
const artifacts =
  process.env.SUNLIGHT_SMOKE_ARTIFACT_DIR || "/tmp/sunlight-review-queue";
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
  async function post(url, data) {
    const r = await p.request.post(base + url, { data });
    assert(r.ok(), await r.text());
    return r.json();
  }
  const stamp = Date.now(),
    prefix = "Queue validation " + stamp;
  async function obligation(suffix) {
    return post("/assurance/obligations", {
      reference: "queue-" + stamp + "-" + suffix,
      title: prefix + " " + suffix,
      sector: "Health",
      country: "GH",
      origin_country: "NL",
      community: "Fictional validation site",
      promise: "Accept 100 usable kits.",
      owner: "Programme owner",
      recipient: "Receiving authority",
      baseline_url: "https://example.org/validation/contract",
      due_at: "2025-10-01T00:00:00Z",
      delivery_target: { value: "100", unit: "kit" },
      budget: "1000",
      currency: "USD",
    });
  }
  let first = await obligation("residual"),
    second = await obligation("arrival");
  async function evidence(record, kind, value) {
    const financial = kind.startsWith("funds_");
    return post("/assurance/obligations/" + record.id + "/evidence", {
      expected_version: record.version,
      kind,
      value,
      unit: financial ? "currency" : "kit",
      currency: financial ? "USD" : null,
      issuer_id:
        kind === "funds_sent"
          ? "treasury"
          : kind === "funds_received"
            ? "receiving-bank"
            : "inspector",
      issuer_name: "Validation issuer",
      ledger_reference: stamp + "-" + kind,
      document_url: "https://example.org/validation/" + kind,
      observed_at: "2025-10-02T00:00:00Z",
      note: "Isolated browser validation.",
      ...(financial
        ? {
            transfer_id: "queue-transfer-" + stamp,
            sender_id: "treasury",
            recipient_id: "recipient",
            settlement_due_at:
              kind === "funds_sent" ? "2025-10-03T00:00:00Z" : null,
          }
        : { covers_through: "2025-10-02T00:00:00Z" }),
    });
  }
  first = await evidence(first, "funds_sent", "1000");
  first = await evidence(first, "funds_received", "960");
  const sourceId = "queue-" + stamp;
  await post("/operations/sources", {
    source_id: sourceId,
    name: "Validation publisher",
    publisher_url: "https://example.org",
    profile: "us_federal",
  });
  const now = new Date().toISOString(),
    before = new Date(Date.now() - 60000).toISOString(),
    end = new Date(Date.now() - 864000000).toISOString().slice(0, 10),
    start = new Date(Date.now() - 2592000000).toISOString().slice(0, 10);
  async function operational(suffix) {
    const measure = {
      value: "100",
      metric: "delivery",
      unit: "kit",
      currency: null,
      period_start: start,
      period_end: end,
      document_url: "https://example.org/validation/measure",
    };
    const events = [
      {
        event_id: suffix,
        contract_id: "queue-" + stamp + "-" + suffix,
        item_id: "kits",
        revision: 1,
        title: prefix + " " + suffix,
        category: "validation",
        origin_country: "NL",
        destination_country: "GH",
        published_at: now,
        expected: { ...measure, due_at: "2025-10-01T00:00:00Z" },
        observed: { ...measure, value: "73", observed_at: before },
      },
    ];
    if (suffix === "case-a")
      events[0].procurement_record = {
        ocid: events[0].contract_id,
        buyer: { name: "Validation authority" },
        tender: {
          procurementMethod: "direct",
          value: { amount: 1000000, currency: "USD" },
        },
      };
    events[0].expected.due_at = new Date(
      Date.now() - 7 * 86400000,
    ).toISOString();
    return (await post("/operations/ingest", { source_id: sourceId, events }))
      .results[0].case_id;
  }
  const caseA = await operational("case-a"),
    caseB = await operational("case-b");
  await p.goto(base + "/watch/#queue");
  const queue = p.getByRole("region", {
    name: "Review queue tools",
    exact: true,
  });
  await queue
    .getByRole("heading", { name: "Review queue", exact: true })
    .waitFor();
  await p.evaluate(
    () => (window.__reviewGlobe = document.querySelector(".ev-world-canvas")),
  );
  async function globe() {
    assert(await p.locator(".ev-world-canvas").isVisible());
    assert(
      await p.evaluate(
        () =>
          window.__reviewGlobe === document.querySelector(".ev-world-canvas"),
      ),
    );
  }
  await queue
    .getByLabel("Find record, owner or evidence issue", { exact: true })
    .fill(prefix);
  await queue
    .locator(".rq-items article")
    .filter({ hasText: prefix + " residual" })
    .waitFor();
  const residual = queue
    .locator(".rq-items article")
    .filter({ hasText: prefix + " residual" });
  assert.match(await residual.innerText(), /40 USD/);
  await residual
    .getByRole("button", { name: "Assign evidence follow-up", exact: true })
    .click();
  const form = queue.getByRole("form", { name: "Assign evidence follow-up" });
  await form
    .getByLabel("Responsible owner", { exact: true })
    .fill("Finance controller");
  await form
    .getByLabel("Follow-up deadline", { exact: true })
    .fill("2026-10-21T12:00");
  // A concurrent evidence revision must not silently overwrite or resubmit a draft.
  first = await evidence(first, "accepted", "73");
  await form
    .getByRole("button", { name: "Record follow-up", exact: true })
    .click();
  await form.getByRole("alert").waitFor();
  assert.equal(
    await form.getByLabel("Responsible owner", { exact: true }).inputValue(),
    "Finance controller",
  );
  await form
    .getByRole("button", {
      name: "Refresh record version; retain draft",
      exact: true,
    })
    .click();
  await form
    .getByRole("alert")
    .filter({ hasText: "Current record version loaded" })
    .waitFor();
  await form
    .getByRole("button", { name: "Record follow-up", exact: true })
    .click();
  await queue
    .getByRole("status")
    .filter({ hasText: "Follow-up recorded" })
    .waitFor();
  await residual
    .locator("dd")
    .filter({ hasText: "Finance controller" })
    .waitFor();
  assert.match(await residual.innerText(), /Finance controller/);
  await globe();
  const [brief] = await Promise.all([
    p.waitForEvent("popup"),
    queue.getByRole("link", { name: /Review meeting brief/ }).click(),
  ]);
  await brief.waitForLoadState();
  assert.match(await brief.innerText("body"), /Next evidence:/);
  await brief.close();
  await residual
    .getByRole("button", {
      name: "Open record & engine findings",
      exact: false,
    })
    .click();
  const delivery = p.getByRole("region", {
    name: "Delivery tools",
    exact: true,
  });
  await delivery
    .getByRole("heading", { name: prefix + " residual", exact: true })
    .waitFor();
  assert.match(p.url(), new RegExp("obligation=" + first.id));
  await globe();
  await p.getByRole("button", { name: "Review queue", exact: true }).click();
  await queue
    .locator(".rq-items article")
    .filter({ hasText: prefix + " arrival" })
    .getByRole("button", {
      name: "Open record & engine findings",
      exact: false,
    })
    .click();
  await delivery
    .getByRole("heading", { name: prefix + " arrival", exact: true })
    .waitFor();
  assert.match(p.url(), new RegExp("obligation=" + second.id));
  await p.getByRole("button", { name: "Review queue", exact: true }).click();
  await queue
    .locator(".rq-items article")
    .filter({ hasText: prefix + " case-a" })
    .getByRole("button", {
      name: "Open record & engine findings",
      exact: false,
    })
    .click();
  const ops = p.getByRole("region", { name: "Records tools", exact: true }),
    dossier = ops.getByRole("complementary", { name: "Case investigation" });
  await dossier
    .getByRole("heading", { name: prefix + " case-a", exact: true })
    .waitFor();
  await dossier
    .getByRole("region", { name: "Procurement decision basis" })
    .waitFor();
  await dossier
    .getByLabel("Owner / analyst label", { exact: true })
    .fill("Draft owner");
  await dossier
    .getByLabel("Review note (required)", { exact: true })
    .fill("Retain this draft while another record is requested.");
  await p.getByRole("button", { name: "Review queue", exact: true }).click();
  await queue
    .locator(".rq-items article")
    .filter({ hasText: prefix + " case-b" })
    .getByRole("button", {
      name: "Open record & engine findings",
      exact: false,
    })
    .click();
  await ops
    .getByRole("alert")
    .filter({ hasText: "A different case was requested" })
    .waitFor();
  assert.equal(
    await dossier
      .getByLabel("Owner / analyst label", { exact: true })
      .inputValue(),
    "Draft owner",
  );
  assert.match(p.url(), new RegExp("case=" + caseA));
  await ops
    .getByRole("button", {
      name: "Discard draft and open requested case",
      exact: true,
    })
    .click();
  await dossier
    .getByRole("heading", { name: prefix + " case-b", exact: true })
    .waitFor();
  assert.match(p.url(), new RegExp("case=" + caseB));
  await globe();
  await p.reload();
  await p
    .getByRole("complementary", { name: "Case investigation" })
    .getByRole("heading", { name: prefix + " case-b", exact: true })
    .waitFor();
  await p.getByRole("button", { name: "Review queue", exact: true }).click();
  await queue
    .getByLabel("Find record, owner or evidence issue", { exact: true })
    .fill(prefix);
  await queue.getByLabel("Work focus", { exact: true }).selectOption("finance");
  await queue
    .locator(".rq-items article")
    .filter({ hasText: prefix + " residual" })
    .waitFor();
  await queue
    .locator(".rq-items article")
    .filter({ hasText: prefix + " residual" })
    .getByRole("button", { name: "Locate country on watch", exact: true })
    .click();
  await p
    .locator(".ev-camera-scope")
    .filter({ hasText: "Country research: Ghana" })
    .waitFor();
  await queue.evaluate((el) => el.scrollTo({ top: 0 }));
  await p.waitForTimeout(700);
  await p.screenshot({
    path: path.join(artifacts, "Institutional-Review-Queue.png"),
  });
  await p.setViewportSize({ width: 390, height: 844 });
  await p.waitForTimeout(300);
  assert(
    await p.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth + 1,
    ),
  );
  await p.screenshot({
    path: path.join(artifacts, "Institutional-Review-Mobile.png"),
  });
  assert.deepEqual(errors, []);
  console.log(
    JSON.stringify({
      queue: true,
      exactResidual: true,
      assignment: true,
      concurrentDraft: true,
      scopedBrief: true,
      exactObligationHandoff: true,
      exactCaseHandoff: true,
      unsavedReviewPreserved: true,
      caseReload: true,
      countryFocus: true,
      mobile: true,
      errors,
    }),
  );
  await browser.close();
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
