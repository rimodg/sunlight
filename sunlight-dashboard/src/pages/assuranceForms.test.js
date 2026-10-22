import test from "node:test";
import assert from "node:assert/strict";
import {
  evidencePayload,
  obligationPayload,
  progress,
  localInput,
} from "./assuranceForms.js";

test("financial intake preserves large exact amounts, explicit zero and transaction identity", () => {
  const form = {
    expected_version: 4,
    kind: "funds_received",
    value: "999999999999999999.123456",
    currency: "usd",
    issuer_id: " bank ",
    issuer_name: " Bank ",
    ledger_reference: "credit-1",
    document_url: "https://example.org/credit",
    observed_at: "2025-01-02T00:00:00Z",
    transfer_id: "transfer-1",
    sender_id: "sender",
    recipient_id: "recipient",
    note: "Recipient ledger entry.",
  };
  const p = evidencePayload(form);
  assert.equal(p.value, form.value);
  assert.equal(p.currency, "USD");
  assert.equal(p.issuer_id, "bank");
  assert.equal(p.covers_through, null);
  assert.equal(p.settlement_due_at, null);
  assert.equal(evidencePayload({ ...form, value: "0" }).value, "0");
  assert.throws(() => evidencePayload({ ...form, value: "" }), /nonnegative/);
  assert.throws(
    () => evidencePayload({ ...form, value: "1e10" }),
    /nonnegative/,
  );
});
test("cumulative physical evidence excludes stale financial fields and keeps UTC coverage", () => {
  const p = evidencePayload({
    expected_version: 3,
    kind: "accepted",
    value: "73",
    unit: "kit",
    currency: "USD",
    transfer_id: "ignored",
    sender_id: "ignored",
    recipient_id: "ignored",
    issuer_id: "inspector",
    issuer_name: "Inspector",
    ledger_reference: "a-1",
    document_url: "https://example.org/accept",
    observed_at: "2025-01-03T01:00:00+01:00",
    covers_through: "2025-01-02T23:00:00Z",
    note: "Accepted after inspection.",
  });
  assert.equal(p.currency, null);
  assert.equal(p.transfer_id, null);
  assert.equal(p.observed_at, "2025-01-03T00:00:00.000Z");
  assert.equal(p.covers_through, "2025-01-02T23:00:00.000Z");
});
test("obligation intake separates delivery, service and budget, with no implicit outcome or payment", () => {
  const form = {
    reference: "o-1",
    title: "Water obligation",
    sector: "Water",
    country: "GH",
    origin_country: "",
    community: "Communities",
    promise: "Deliver and accept pumps",
    owner: "Programme",
    recipient: "Authority",
    baseline_url: "https://example.org/contract",
    due_at: "2025-01-01T00:00:00Z",
    target: "100",
    unit: "pump",
    outcome_target: "",
    outcome_unit: "household",
    budget: "",
    currency: "USD",
  };
  const p = obligationPayload(form);
  assert.deepEqual(p.delivery_target, { value: "100", unit: "pump" });
  assert.equal(p.outcome_target, null);
  assert.equal(p.budget, null);
  assert.equal(p.currency, null);
  assert.equal(p.synthetic, false);
  const defined = obligationPayload({
    ...form,
    outcome_target: "20",
    budget: "1000.01",
  });
  assert.deepEqual(defined.outcome_target, { value: "20", unit: "household" });
  assert.equal(defined.budget, "1000.01");
});
test("visual progress distinguishes absent from zero and never changes ledger values", () => {
  assert.equal(progress({ observed: null, target: { value: "100" } }), null);
  assert.equal(progress({ observed: "0", target: { value: "100" } }), 0);
  assert.equal(progress({ observed: "73", target: { value: "100" } }), 73);
  assert.equal(progress({ observed: "130", target: { value: "100" } }), 100);
  assert.equal(localInput("invalid"), "");
});
