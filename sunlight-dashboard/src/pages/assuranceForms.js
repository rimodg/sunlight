// Amounts remain strings from input through the API. Number is only used for a visual bar.
export const financialKinds = new Set([
  "funds_sent",
  "funds_received",
  "settlement_deduction",
]);
export const stageNames = {
  funds_sent: "Funds sent",
  funds_received: "Recipient credit",
  settlement_deduction: "Pre-credit deduction",
  dispatched: "Dispatched",
  received: "Received",
  accepted: "Accepted delivery",
  outcome: "Service outcome",
};
export const pretty = (value) => String(value || "").replaceAll("_", " ");
export function localInput(value = new Date()) {
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return "";
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 16);
}
function iso(value) {
  const d = new Date(value);
  if (!value || !Number.isFinite(d.getTime()))
    throw new Error("Supply a valid date and time.");
  return d.toISOString();
}
function amount(value) {
  const text = String(value ?? "").trim();
  if (!/^\d+(?:\.\d{1,6})?$/.test(text))
    throw new Error(
      "Enter a nonnegative amount with at most six decimal places.",
    );
  return text;
}
export function obligationPayload(form) {
  const budget = form.budget.trim();
  return {
    reference: form.reference.trim(),
    title: form.title.trim(),
    sector: form.sector,
    country: form.country,
    origin_country: form.origin_country || null,
    community: form.community.trim(),
    promise: form.promise.trim(),
    owner: form.owner.trim(),
    recipient: form.recipient.trim(),
    baseline_url: form.baseline_url.trim(),
    due_at: iso(form.due_at),
    delivery_target: { value: amount(form.target), unit: form.unit.trim() },
    outcome_target: form.outcome_target.trim()
      ? { value: amount(form.outcome_target), unit: form.outcome_unit.trim() }
      : null,
    budget: budget ? amount(budget) : null,
    currency: budget ? form.currency.trim().toUpperCase() : null,
    synthetic: false,
  };
}
export function evidencePayload(form) {
  const financial = financialKinds.has(form.kind);
  return {
    expected_version: form.expected_version,
    kind: form.kind,
    value: amount(form.value),
    unit: financial ? "currency" : form.unit.trim(),
    currency: financial ? form.currency.trim().toUpperCase() : null,
    issuer_id: form.issuer_id.trim(),
    issuer_name: form.issuer_name.trim(),
    ledger_reference: form.ledger_reference.trim(),
    document_url: form.document_url.trim(),
    observed_at: iso(form.observed_at),
    note: form.note.trim(),
    covers_through: financial ? null : iso(form.covers_through),
    transfer_id: financial ? form.transfer_id.trim() : null,
    sender_id: financial ? form.sender_id.trim() : null,
    recipient_id: financial ? form.recipient_id.trim() : null,
    settlement_due_at:
      form.kind === "funds_sent" ? iso(form.settlement_due_at) : null,
    supersedes: form.supersedes || null,
  };
}
export function actionPayload(form) {
  return {
    expected_version: form.expected_version,
    title: form.title.trim(),
    kind: form.kind,
    owner: form.owner.trim(),
    due_at: iso(form.due_at),
    note: form.note.trim(),
    signal_key: form.signal_key || "",
  };
}
export function progress(stage) {
  if (
    stage?.observed === null ||
    stage?.observed === undefined ||
    !stage?.target
  )
    return null;
  const ratio = Number(stage.observed) / Number(stage.target.value);
  return Number.isFinite(ratio)
    ? Math.min(100, Math.max(0, ratio * 100))
    : null;
}
