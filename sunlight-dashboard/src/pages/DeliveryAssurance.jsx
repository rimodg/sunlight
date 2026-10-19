import { useCallback, useEffect, useRef, useState } from "react";
import { countryCatalog } from "./watchOverview";
import { humanApiError } from "./apiErrors";
import {
  actionPayload,
  evidencePayload,
  financialKinds,
  localInput,
  obligationPayload,
  pretty,
  progress,
  stageNames,
} from "./assuranceForms";
import "./DeliveryAssurance.css";

const at = (v) => (v ? new Date(v).toLocaleString() : "Not recorded");
const countryName = (code) =>
  countryCatalog.find((c) => c.code === code)?.name || code;
const stateLabel = {
  reported_chain_complete: "Reported chain complete",
  attention_required: "Evidence or action needed",
  reconciled_claims: "Reported amounts reconcile",
  unexplained_difference: "Unexplained difference",
  arrival_unobserved: "Arrival evidence missing",
  sender_unobserved: "Sender evidence missing",
  issuer_separation_missing: "Separate receiving issuer needed",
  not_comparable: "Comparison blocked",
  awaiting_settlement: "Settlement open",
  reported_target_met: "Reported target met",
  shortfall: "Measured shortfall",
  evidence_missing: "Evidence missing",
  deadline_evidence_needed: "Deadline coverage needed",
  not_due: "Not due",
  conflicting_observations: "Reports disagree",
  target_not_defined: "Target not defined",
  excess_arrival: "Excess recorded arrival",
  overage: "Reported overage",
};
const label = (v) => stateLabel[v] || pretty(v);
async function api(path, body, signal) {
  const r = await fetch(
    "/assurance" + path,
    body === undefined
      ? { signal }
      : {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
          signal,
        },
  );
  const d = await r.json();
  if (!r.ok) throw new Error(humanApiError(d));
  return d;
}
function Source({ url, children }) {
  return (
    <a href={url} target="_blank" rel="noreferrer">
      {children} ↗
    </a>
  );
}
function Field({ name, form, set, children, ...props }) {
  return (
    <label>
      {children}
      <input
        aria-label={children}
        {...props}
        value={form[name] ?? ""}
        onChange={(e) => set((f) => ({ ...f, [name]: e.target.value }))}
      />
    </label>
  );
}
function Memo({ name = "note", form, set, children }) {
  return (
    <label className="da-wide">
      {children}
      <textarea
        aria-label={children}
        required
        minLength="3"
        maxLength="4000"
        value={form[name] ?? ""}
        onChange={(e) => set((f) => ({ ...f, [name]: e.target.value }))}
      />
    </label>
  );
}
function Countries({ name, form, set, optional = false, children }) {
  return (
    <label>
      {children}
      <select
        aria-label={children}
        required={!optional}
        value={form[name]}
        onChange={(e) => set((f) => ({ ...f, [name]: e.target.value }))}
      >
        <option value="">
          {optional ? "Unspecified" : "Select country or territory"}
        </option>
        {countryCatalog.map((c) => (
          <option key={c.code} value={c.code}>
            {c.name}
          </option>
        ))}
      </select>
    </label>
  );
}
function Modal({ title, children, onClose, busy }) {
  const ref = useRef(null);
  useEffect(() => {
    ref.current.showModal();
  }, []);
  return (
    <dialog
      ref={ref}
      className="da-dialog"
      onCancel={(e) => {
        e.preventDefault();
        if (!busy) onClose();
      }}
    >
      <div className="da-dialog-title">
        <h2>{title}</h2>
        <button
          type="button"
          disabled={busy}
          aria-label="Close form"
          onClick={onClose}
        >
          Close ×
        </button>
      </div>
      {children}
    </dialog>
  );
}
function Stage({ title, value, caption, state, onClick, bar }) {
  return (
    <button className={"da-stage " + (state || "")} onClick={onClick}>
      <span>{title}</span>
      <strong>{value}</strong>
      <small>{caption}</small>
      {bar !== null && bar !== undefined && (
        <span className="da-track" aria-hidden="true">
          <i style={{ width: bar + "%" }} />
        </span>
      )}
      <em>{state ? label(state) : "Inspect baseline"} ↗</em>
    </button>
  );
}
const newObligation = (country) => ({
  reference: "",
  title: "",
  sector: "Health",
  country: country || "",
  origin_country: "",
  community: "",
  promise: "",
  owner: "",
  recipient: "",
  baseline_url: "",
  due_at: "",
  target: "",
  unit: "",
  outcome_target: "",
  outcome_unit: "",
  budget: "",
  currency: "USD",
});

export default function DeliveryAssurance({
  profiles,
  scopeCountry,
  active,
  onInvestigate,
  onWatch,
  onChanged,
}) {
  const [portfolio, setPortfolio] = useState(null),
    [detail, setDetail] = useState(null),
    [selected, setSelected] = useState(() =>
      new URLSearchParams(window.location.search).get("obligation"),
    );
  const [query, setQuery] = useState(""),
    [examples, setExamples] = useState(false),
    [attention, setAttention] = useState(false),
    [page, setPage] = useState(0),
    [view, setView] = useState("chain"),
    [stageFilter, setStageFilter] = useState("");
  const [formType, setFormType] = useState(null),
    [form, setForm] = useState({}),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [formError, setFormError] = useState(""),
    [notice, setNotice] = useState("");
  const [profile, setProfile] = useState("");
  const requestSeq = useRef(0),
    formId = useRef(null);
  formId.current = formType;
  const load = useCallback(
    async (signal) => {
      const seq = ++requestSeq.current;
      const params = new URLSearchParams({
        country: scopeCountry || "",
        q: query,
        synthetic: String(examples),
        attention: String(attention),
        limit: "30",
        offset: String(page * 30),
      });
      const [p, d] = await Promise.all([
        api("/obligations?" + params, undefined, signal),
        selected
          ? api("/obligations/" + selected, undefined, signal)
          : Promise.resolve(null),
      ]);
      if (!signal?.aborted && seq === requestSeq.current) {
        setPortfolio(p);
        if (d) {
          setDetail((previous) =>
            previous?.id === d.id && previous.version > d.version
              ? previous
              : d,
          );
          if (d.obligation.synthetic !== examples)
            setExamples(d.obligation.synthetic);
        }
      }
    },
    [scopeCountry, query, examples, attention, page, selected],
  );
  useEffect(() => {
    if (!active) return;
    const controller = new AbortController();
    const refresh = () => {
      if (!document.hidden)
        load(controller.signal).catch((e) => {
          if (e.name !== "AbortError") setError(e.message);
        });
    };
    refresh();
    const timer = setInterval(refresh, 20000);
    return () => {
      controller.abort();
      clearInterval(timer);
    };
  }, [active, load]);
  useEffect(() => {
    setPage(0);
  }, [query, scopeCountry, examples, attention]);
  useEffect(() => {
    if (
      scopeCountry &&
      detail &&
      ![detail.obligation.country, detail.obligation.origin_country].includes(
        scopeCountry,
      )
    ) {
      setSelected(null);
      setDetail(null);
    }
  }, [scopeCountry]);
  useEffect(() => {
    if (!selected) return;
    const url = new URL(window.location.href);
    url.searchParams.set("obligation", selected);
    history.replaceState(null, "", url);
  }, [selected]);
  function show(record) {
    setSelected(record.id);
    setDetail(record);
    setView("chain");
    setStageFilter("");
    setError("");
  }
  async function act(fn) {
    setBusy(true);
    setError("");
    setFormError("");
    try {
      await fn();
    } catch (e) {
      if (formId.current) setFormError(e.message);
      else setError(e.message);
      if (selected)
        try {
          setDetail(await api("/obligations/" + selected));
        } catch {
          /* Keep the last retained evidence visible. */
        }
    } finally {
      setBusy(false);
    }
  }
  async function updated(record, message) {
    requestSeq.current++;
    setSelected(record.id);
    setDetail(record);
    setFormType(null);
    setNotice(message);
    onChanged?.();
    const p = await api(
      "/obligations?" +
        new URLSearchParams({
          country: scopeCountry || "",
          q: query,
          synthetic: String(examples),
          attention: String(attention),
          limit: "30",
          offset: String(page * 30),
        }),
    );
    setPortfolio(p);
  }
  function openEvidence(kind = "funds_sent", prior = null) {
    const transfer = detail.assessment.transfers[0],
      target =
        kind === "outcome"
          ? detail.obligation.outcome_target
          : detail.obligation.delivery_target;
    setForm({
      expected_version: detail.version,
      kind,
      value: "",
      unit: target?.unit || "",
      currency: detail.obligation.currency || transfer?.currency || "USD",
      issuer_id: "",
      issuer_name: "",
      ledger_reference: "",
      document_url: "",
      observed_at: localInput(),
      covers_through: localInput(),
      transfer_id: transfer?.transfer_id || "",
      sender_id: transfer?.sender_id || "",
      recipient_id: transfer?.recipient_id || "",
      settlement_due_at: "",
      note: "",
      ...(prior
        ? {
            ...prior,
            expected_version: detail.version,
            supersedes: prior.id,
            observed_at: localInput(prior.observed_at),
            covers_through: prior.covers_through
              ? localInput(prior.covers_through)
              : localInput(),
            settlement_due_at: prior.settlement_due_at
              ? localInput(prior.settlement_due_at)
              : "",
          }
        : {}),
    });
    setFormError("");
    setFormType("evidence");
  }
  function follow(signal) {
    setForm({
      expected_version: detail.version,
      title: signal?.title || "",
      kind: signal?.stage === "funds" ? "financial_review" : "evidence_request",
      owner: detail.obligation.owner,
      due_at: localInput(new Date(Date.now() + 7 * 86400000)),
      note: signal?.next_step || "",
      signal_key: signal?.key || "",
    });
    setFormError("");
    setFormType("action");
  }
  function editAction(action) {
    setForm({
      expected_version: detail.version,
      action_id: action.id,
      status: action.status,
      note: "",
      completion_evidence_id: action.completion_evidence_id || "",
    });
    setFormError("");
    setFormType("update");
  }
  function inspectStage(kind) {
    setView("evidence");
    setStageFilter(kind);
    document
      .getElementById("da-body")
      ?.scrollIntoView({ behavior: "smooth", block: "start" });
  }
  async function save(e) {
    e.preventDefault();
    await act(async () => {
      if (formType === "new") {
        const r = await api("/obligations", obligationPayload(form));
        setExamples(false);
        await updated(
          r,
          "Obligation registered. Add independently attributable records to follow its delivery.",
        );
      } else if (formType === "evidence") {
        await updated(
          await api(
            "/obligations/" + selected + "/evidence",
            evidencePayload(form),
          ),
          form.supersedes
            ? "Correction retained; comparisons recalculated. Original evidence remains in the history."
            : "Evidence retained and comparisons recalculated.",
        );
      } else if (formType === "action") {
        await updated(
          await api(
            "/obligations/" + selected + "/actions",
            actionPayload(form),
          ),
          "Follow-up assigned. This records responsibility; no external institution was contacted.",
        );
        setView("actions");
      } else {
        await updated(
          await api("/obligations/" + selected + "/actions/" + form.action_id, {
            expected_version: form.expected_version,
            status: form.status,
            note: form.note,
            completion_evidence_id:
              form.status === "completed" ? form.completion_evidence_id : null,
          }),
          "Follow-up updated. Evidence comparisons remain independently calculated.",
        );
        setView("actions");
      }
    });
  }
  const current = detail?.obligation,
    a = detail?.assessment,
    activeEvidence = detail?.evidence.filter((e) => !e.superseded_by) || [],
    transfers = a?.transfers || [],
    single = transfers.length === 1 ? transfers[0] : null;
  const stage = (kind) => a?.stages.find((s) => s.kind === kind);
  const visibleEvidence = (detail?.evidence || []).filter(
    (e) => !stageFilter || e.kind === stageFilter,
  );
  const financial = formType === "evidence" && financialKinds.has(form.kind);
  const stale =
    formType &&
    formType !== "new" &&
    detail &&
    form.expected_version !== detail.version;
  return (
    <section className="da" aria-label="Delivery assurance workspace">
      <header className="da-header">
        <div>
          <p className="da-eyebrow">PUBLIC PROMISE → EVIDENCE → RESPONSE</p>
          <h1>Delivery assurance</h1>
          <p>Follow resources through to the people they are meant to serve.</p>
        </div>
        <div className="da-buttons">
          <button
            disabled={busy}
            onClick={() => {
              setForm(newObligation(scopeCountry));
              setFormError("");
              setFormType("new");
            }}
            className="da-primary"
          >
            Register an obligation +
          </button>
          <button
            disabled={busy}
            onClick={() =>
              act(async () => {
                const r = await api("/example", {});
                setExamples(true);
                show(r);
                setNotice(
                  "Synthetic worked example. These values describe no actual institution or event.",
                );
                onChanged?.();
              })
            }
          >
            Open worked example ↗
          </button>
        </div>
      </header>
      <div className="da-scope-line">
        <span>
          {examples ? "SYNTHETIC EXAMPLES" : "REGISTERED INSTITUTIONAL RECORDS"}{" "}
          /{" "}
          {scopeCountry
            ? countryName(scopeCountry)
            : "ALL REGISTERED COUNTRIES"}
        </span>
        <span>Submitted evidence · issuer authentication not connected</span>
      </div>
      {error && (
        <p className="da-error" role="alert">
          {error}
        </p>
      )}
      {notice && (
        <p className="da-notice" role="status">
          {notice}
        </p>
      )}
      <div className="da-layout">
        <aside className="da-register">
          <h2>Obligations</h2>
          <label>
            Find an obligation
            <input
              type="search"
              maxLength="200"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Programme, reference or community"
            />
          </label>
          <label className="da-check">
            <input
              type="checkbox"
              checked={attention}
              onChange={(e) => setAttention(e.target.checked)}
            />
            Evidence or action needed
          </label>
          <label className="da-check">
            <input
              type="checkbox"
              checked={examples}
              onChange={(e) => {
                setExamples(e.target.checked);
                setSelected(null);
                setDetail(null);
              }}
            />
            Show synthetic examples
          </label>
          <p className="da-count">
            {portfolio?.total ?? "…"} matching obligations ·{" "}
            {portfolio?.scope_count ?? "…"} in scope
          </p>
          <div className="da-register-list">
            {portfolio?.obligations.map((r) => (
              <button
                key={r.id}
                aria-pressed={selected === r.id}
                onClick={() => show(r)}
              >
                <span>{r.obligation.reference}</span>
                <strong>{r.obligation.title}</strong>
                <small>
                  {countryName(r.obligation.country)} · {r.obligation.sector}
                </small>
                <em>
                  {r.assessment.signals.length} evidence issues ·{" "}
                  {r.assessment.open_actions} open follow-ups
                </em>
              </button>
            ))}
          </div>
          {portfolio && !portfolio.total && (
            <p>
              No obligations match. Register a public promise with its baseline,
              or explore the worked example.
            </p>
          )}
          <div className="da-buttons">
            <button disabled={!page} onClick={() => setPage((p) => p - 1)}>
              Previous
            </button>
            <button
              disabled={!portfolio || (page + 1) * 30 >= portfolio.total}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </button>
          </div>
          <small>
            Coverage includes only registered obligations. This is not a census
            of public spending.
          </small>
        </aside>
        <main className="da-main">
          {!detail ? (
            <div className="da-empty">
              <span className="da-empty-orbit" aria-hidden="true">
                ◎
              </span>
              <p className="da-eyebrow">FOLLOW ONE PROMISE THROUGH</p>
              <h2>
                What should people receive?
                <br />
                What has the evidence established?
              </h2>
              <p>
                Start with a funded programme or contract. Link its sender and
                recipient records, physical delivery and service evidence.
                Investigate the breaks and assign the response.
              </p>
              <ol>
                <li>Define the obligation and deadline.</li>
                <li>Record origin, arrival and acceptance evidence.</li>
                <li>Follow the response through to a documented result.</li>
              </ol>
              <button
                className="da-primary"
                onClick={() =>
                  act(async () => {
                    const r = await api("/example", {});
                    setExamples(true);
                    show(r);
                  })
                }
              >
                Explore the worked chain →
              </button>
            </div>
          ) : (
            <>
              {current.synthetic && (
                <p className="da-example">
                  SYNTHETIC WORKED EXAMPLE · Fictional amounts, organizations
                  and delivery records. Excluded from institutional records.
                </p>
              )}
              <header className="da-mission">
                <div>
                  <p className="da-eyebrow">
                    {current.sector.toUpperCase()} / {current.reference}
                  </p>
                  <h2>{current.title}</h2>
                  <p className="da-promise">{current.promise}</p>
                  <p>
                    {current.community} · {countryName(current.country)} ·
                    Owner: {current.owner}
                  </p>
                </div>
                <span className="da-version">
                  VERSION {detail.version}
                  <small>Assessed {at(a.as_of)}</small>
                </span>
              </header>
              <div className="da-mission-tools">
                <span>
                  Due {at(current.due_at)} · Recipient: {current.recipient}
                </span>
                <div className="da-buttons">
                  <Source url={current.baseline_url}>Baseline</Source>
                  <button onClick={() => onWatch(current.country)}>
                    Locate on watch ↗
                  </button>
                  <Source
                    url={"/assurance/obligations/" + selected + "/report"}
                  >
                    Readable brief / PDF
                  </Source>
                </div>
              </div>
              <div className="da-chain" aria-label="Obligation evidence chain">
                <Stage
                  title="01 / Promise"
                  value={`${current.delivery_target.value} ${pretty(current.delivery_target.unit)}`}
                  caption={
                    current.budget !== null
                      ? `Budget context: ${current.budget} ${current.currency}`
                      : "Baseline target and deadline"
                  }
                  onClick={() => setView("chain")}
                />
                <Stage
                  title="02 / Released"
                  value={
                    single?.sent !== null && single?.sent !== undefined
                      ? `${single.sent} ${single.currency || ""}`
                      : transfers.length
                        ? `${transfers.length} transfer identities`
                        : "Unobserved"
                  }
                  caption="Executed debit evidence"
                  state={single?.state}
                  onClick={() => inspectStage("funds_sent")}
                />
                <Stage
                  title="03 / Arrival"
                  value={
                    single?.received !== null && single?.received !== undefined
                      ? `${single.received} ${single.currency || ""}`
                      : transfers.length > 1
                        ? "Inspect transfers"
                        : "Unobserved"
                  }
                  caption="Recipient credit evidence"
                  state={single?.state}
                  onClick={() => inspectStage("funds_received")}
                />
                <Stage
                  title="04 / Dispatch"
                  value={
                    stage("dispatched").observed !== null
                      ? `${stage("dispatched").observed} ${pretty(current.delivery_target.unit)}`
                      : "Unobserved"
                  }
                  caption="Cumulative dispatch"
                  state={stage("dispatched").state}
                  onClick={() => inspectStage("dispatched")}
                />
                <Stage
                  title="05 / Acceptance"
                  value={
                    a.accepted.observed !== null
                      ? `${a.accepted.observed} ${pretty(current.delivery_target.unit)}`
                      : "Unobserved"
                  }
                  caption={
                    a.accepted.shortfall !== null
                      ? `${a.accepted.shortfall} ${pretty(current.delivery_target.unit)} shortfall`
                      : "Receiving inspection evidence"
                  }
                  state={a.accepted.state}
                  onClick={() => inspectStage("accepted")}
                  bar={progress(a.accepted)}
                />
                <Stage
                  title="06 / Public benefit"
                  value={
                    a.outcome.observed !== null
                      ? `${a.outcome.observed} ${pretty(current.outcome_target?.unit)}`
                      : current.outcome_target
                        ? "Unobserved"
                        : "Target undefined"
                  }
                  caption={
                    current.outcome_target
                      ? `Target: ${current.outcome_target.value} ${pretty(current.outcome_target.unit)}`
                      : "Define at registration"
                  }
                  state={a.outcome.state}
                  onClick={() => inspectStage("outcome")}
                  bar={progress(a.outcome)}
                />
              </div>
              <nav className="da-view-tabs" aria-label="Obligation views">
                {[
                  ["chain", "Evidence & breaks"],
                  ["evidence", `Source register (${detail.evidence.length})`],
                  [
                    "actions",
                    `Response & follow-up (${detail.actions.length})`,
                  ],
                ].map(([id, text]) => (
                  <button
                    key={id}
                    aria-pressed={view === id}
                    onClick={() => setView(id)}
                  >
                    {text}
                  </button>
                ))}
                <button
                  className="da-add-evidence"
                  onClick={() => openEvidence()}
                >
                  Record evidence +
                </button>
              </nav>
              <div id="da-body">
                {view === "chain" && (
                  <>
                    <div className="da-section-heading">
                      <div>
                        <p className="da-eyebrow">TRACE / EXPLAIN / RESPOND</p>
                        <h3>Where to look next</h3>
                      </div>
                      <button
                        onClick={() =>
                          onInvestigate({
                            question: `Investigate ${current.title}. Where does its funding-to-delivery chain break, what explanations fit the recorded evidence, and what evidence is needed next?`,
                            country_codes: [current.country],
                            sources: [
                              "delivery_assurance",
                              "operations",
                              "procurement",
                            ],
                            obligation_ids: [selected],
                          })
                        }
                      >
                        Investigate this obligation →
                      </button>
                    </div>
                    {!a.signals.length && (
                      <p className="da-notice">
                        The recorded chain meets its comparison conditions.
                        Independent issuer authentication and field verification
                        remain separate requirements.
                      </p>
                    )}
                    <div className="da-signals">
                      {a.signals.map((s, i) => (
                        <article key={s.key}>
                          <span className="da-signal-number">
                            {String(i + 1).padStart(2, "0")}
                          </span>
                          <div>
                            <small>{pretty(s.stage).toUpperCase()}</small>
                            <h4>{s.title}</h4>
                            <p>{s.reason}</p>
                            <details>
                              <summary>Evidence to obtain</summary>
                              <p>{s.next_step}</p>
                            </details>
                          </div>
                          <button onClick={() => follow(s)}>
                            Assign follow-up →
                          </button>
                        </article>
                      ))}
                    </div>
                    <section className="da-finance">
                      <div className="da-section-heading">
                        <h3>Origin → recorded arrival</h3>
                        <button onClick={() => openEvidence("funds_received")}>
                          Add recipient credit +
                        </button>
                      </div>
                      <p>
                        Match the same transfer and parties. Debits are
                        individual entries; credits may arrive in parts.
                        Deductions here apply before credit, within the same
                        currency.
                      </p>
                      {transfers.length ? (
                        <div className="da-table-wrap">
                          <table>
                            <thead>
                              <tr>
                                <th>Transfer / counterparties</th>
                                <th>Sent</th>
                                <th>Recorded arrival</th>
                                <th>Pre-credit deductions</th>
                                <th>Difference / basis</th>
                              </tr>
                            </thead>
                            <tbody>
                              {transfers.map((t, i) => (
                                <tr key={i}>
                                  <td>
                                    <strong>{t.transfer_id}</strong>
                                    <small>
                                      {t.sender_id} → {t.recipient_id}
                                    </small>
                                    <small>{label(t.state)}</small>
                                  </td>
                                  <td>
                                    {t.sent ?? "Unobserved"}
                                    <small>
                                      {t.currency || "Mixed currencies"}
                                    </small>
                                  </td>
                                  <td>{t.received ?? "Unobserved"}</td>
                                  <td>{t.deductions ?? "Not comparable"}</td>
                                  <td>
                                    <strong>
                                      {t.residual ?? "Not calculable"}
                                    </strong>
                                    {t.raw_difference !== null && (
                                      <small>
                                        Before deductions: {t.raw_difference}
                                      </small>
                                    )}
                                    <details>
                                      <summary>Calculation & sources</summary>
                                      <p>{t.reason}</p>
                                      <p>{t.assurance}</p>
                                      <p>
                                        Settlement due:{" "}
                                        {at(t.settlement_due_at)}
                                      </p>
                                      {t.evidence_ids.map((id) => {
                                        const e = detail.evidence.find(
                                          (x) => x.id === id,
                                        );
                                        return (
                                          e && (
                                            <p key={id}>
                                              <Source url={e.document_url}>
                                                {stageNames[e.kind]} ·{" "}
                                                {e.issuer_name} ·{" "}
                                                {e.ledger_reference}
                                              </Source>
                                            </p>
                                          )
                                        );
                                      })}
                                    </details>
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      ) : (
                        <p>
                          No executed transfer evidence. The obligation budget
                          is not treated as money sent or received.
                        </p>
                      )}
                    </section>
                    <section className="da-outcomes">
                      <h3>Receipt, acceptance and use</h3>
                      <div>
                        {a.stages
                          .filter((s) => s.kind !== "dispatched")
                          .map((s) => (
                            <article key={s.kind}>
                              <span>{stageNames[s.kind]}</span>
                              <strong>
                                {s.observed ?? "Unobserved"}{" "}
                                <small>{pretty(s.target?.unit)}</small>
                              </strong>
                              <p>
                                {label(s.state)}
                                {s.shortfall !== null
                                  ? ` · ${s.shortfall} shortfall`
                                  : ""}
                              </p>
                              <small>
                                Coverage through {at(s.covers_through)}
                              </small>
                              <button
                                disabled={s.state === "target_not_defined"}
                                onClick={() => openEvidence(s.kind)}
                              >
                                Record{" "}
                                {s.kind === "outcome"
                                  ? "service evidence"
                                  : s.kind}{" "}
                                +
                              </button>
                            </article>
                          ))}
                      </div>
                      <p>
                        Payment does not establish delivery. Receipt does not
                        establish acceptance. A service observation does not by
                        itself establish that this programme caused the outcome.
                      </p>
                    </section>
                    <section className="da-engine">
                      <h3>Calibrated delivery checks</h3>
                      <p>
                        Run SUNLIGHT’s existing delivery rules on the comparable
                        accepted quantity. Choose the calibration explicitly;
                        exact ledger arithmetic remains separate from the
                        engine’s numerical thresholds.
                      </p>
                      <div className="da-buttons">
                        <label>
                          Delivery calibration profile
                          <select
                            aria-label="Delivery calibration profile"
                            value={profile}
                            onChange={(e) => setProfile(e.target.value)}
                          >
                            <option value="">Select a calibration…</option>
                            {profiles.map((p) => (
                              <option key={p.name} value={p.name}>
                                {pretty(p.name)}
                              </option>
                            ))}
                          </select>
                        </label>
                        <button
                          disabled={
                            busy || !profile || a.accepted.shortfall === null
                          }
                          onClick={() =>
                            act(async () =>
                              updated(
                                await api(
                                  "/obligations/" +
                                    selected +
                                    "/delivery-analysis",
                                  { expected_version: detail.version, profile },
                                ),
                                "Calibrated delivery analysis retained with its evidence basis.",
                              ),
                            )
                          }
                        >
                          Run calibrated delivery checks
                        </button>
                      </div>
                      {a.accepted.shortfall === null && (
                        <p>
                          Comparable acceptance evidence covering the deadline
                          is required.
                        </p>
                      )}
                      {detail.analyses.map((run) => (
                        <article key={run.id}>
                          <h4>
                            {pretty(run.profile)} · {run.result.rules_fired}{" "}
                            rules fired
                          </h4>
                          <p>
                            {run.basis_current
                              ? "Current acceptance evidence"
                              : "Earlier evidence basis — rerun after reviewing corrections"}{" "}
                            · {at(run.created_at)}
                          </p>
                          {run.result.fired_rules.map((r, i) => (
                            <p key={i}>
                              <strong>{r.rule_id}</strong> ·{" "}
                              {r.evidence || r.description}
                            </p>
                          ))}
                          <details>
                            <summary>Analysis scope & limitations</summary>
                            <p>{run.scope}</p>
                            {run.result.errors?.length > 0 && (
                              <p>
                                Engine reported errors; review the readable
                                brief before relying on this run.
                              </p>
                            )}
                          </details>
                        </article>
                      ))}
                    </section>
                  </>
                )}
                {view === "evidence" && (
                  <section className="da-evidence">
                    <div className="da-section-heading">
                      <h3>Attributable evidence register</h3>
                      <label>
                        Stage filter
                        <select
                          aria-label="Stage filter"
                          value={stageFilter}
                          onChange={(e) => setStageFilter(e.target.value)}
                        >
                          <option value="">All stages</option>
                          {Object.entries(stageNames).map(([k, v]) => (
                            <option key={k} value={k}>
                              {v}
                            </option>
                          ))}
                        </select>
                      </label>
                    </div>
                    <p>
                      Each entry retains its declared issuer, reference, dates
                      and source. Corrections supersede entries without deleting
                      history. Issuer identity is not authenticated by a
                      document URL.
                    </p>
                    {!visibleEvidence.length && (
                      <p>
                        No evidence at this stage.{" "}
                        <button
                          onClick={() =>
                            openEvidence(stageFilter || "funds_sent")
                          }
                        >
                          Record evidence +
                        </button>
                      </p>
                    )}
                    {visibleEvidence.map((e) => (
                      <article
                        key={e.id}
                        className={e.superseded_by ? "superseded" : ""}
                      >
                        <div className="da-section-heading">
                          <div>
                            <span className="da-eyebrow">
                              {stageNames[e.kind]} /{" "}
                              {e.superseded_by ? "SUPERSEDED" : "CURRENT CLAIM"}
                            </span>
                            <h4>
                              {e.value} {pretty(e.currency || e.unit)}
                            </h4>
                          </div>
                          {!e.superseded_by && (
                            <button onClick={() => openEvidence(e.kind, e)}>
                              Record correction
                            </button>
                          )}
                        </div>
                        <p>
                          {e.issuer_name} · {e.issuer_id} · Ledger entry:{" "}
                          {e.ledger_reference}
                        </p>
                        <p>
                          Observed {at(e.observed_at)}
                          {e.covers_through
                            ? " · Covers through " + at(e.covers_through)
                            : ""}
                        </p>
                        <p>{e.note}</p>
                        <Source url={e.document_url}>Supporting record</Source>
                        <details>
                          <summary>Evidence identity & history</summary>
                          <p>Reference: {e.id}</p>
                          <p>Received: {at(e.created_at)}</p>
                          <p>SHA-256: {e.payload_hash}</p>
                          {e.superseded_by && (
                            <p>Superseded by {e.superseded_by}</p>
                          )}
                        </details>
                      </article>
                    ))}
                  </section>
                )}
                {view === "actions" && (
                  <section className="da-response">
                    <div className="da-section-heading">
                      <div>
                        <h3>Who acts, by when, with what result?</h3>
                        <p>
                          {a.open_actions} open follow-ups · {a.overdue_actions}{" "}
                          past their deadline
                        </p>
                      </div>
                      <button onClick={() => follow()}>
                        Assign follow-up +
                      </button>
                    </div>
                    <p>
                      These are local investigation records. External requests,
                      payment holds and redirection require an authorized
                      institutional connection.
                    </p>
                    {!detail.actions.length && (
                      <p>
                        No follow-up assigned. Open an evidence issue to assign
                        a specific next step.
                      </p>
                    )}
                    {detail.actions.map((x) => (
                      <article key={x.id}>
                        <div className="da-section-heading">
                          <h4>{x.title}</h4>
                          <strong>{pretty(x.status)}</strong>
                        </div>
                        <p>
                          {pretty(x.kind)} · Responsible: {x.owner} · Due{" "}
                          {at(x.due_at)}
                        </p>
                        <p>{x.note}</p>
                        {x.completion_evidence_id && (
                          <p>
                            Completion evidence:{" "}
                            {activeEvidence.find(
                              (e) => e.id === x.completion_evidence_id,
                            )?.ledger_reference ||
                              "Superseded — review correction"}
                          </p>
                        )}
                        <button onClick={() => editAction(x)}>
                          Update follow-up
                        </button>
                      </article>
                    ))}
                    <p>
                      A completed task does not mark goods as delivered or make
                      a financial discrepancy disappear.
                    </p>
                  </section>
                )}
              </div>
              <details className="da-audit">
                <summary>
                  Retained history, evidence scope & integration status
                </summary>
                <p>{a.limitations}</p>
                <p>
                  Obligation baseline is retained as registered. Corrections to
                  source entries preserve their earlier versions. Shared
                  deployment access currently provides no individual
                  investigator authentication.
                </p>
                <p>
                  Updated {at(detail.updated_at)} · version {detail.version}
                </p>
                <Source url={"/assurance/obligations/" + selected + "/export"}>
                  Advanced audit packet
                </Source>
              </details>
            </>
          )}
        </main>
      </div>
      {formType && (
        <Modal
          title={
            formType === "new"
              ? "Register a public obligation"
              : formType === "evidence"
                ? form.supersedes
                  ? "Correct retained evidence"
                  : "Record attributable evidence"
                : formType === "action"
                  ? "Assign an accountable follow-up"
                  : "Record follow-up progress"
          }
          onClose={() => setFormType(null)}
          busy={busy}
        >
          <form onSubmit={save}>
            <fieldset disabled={busy}>
              {formType === "new" && (
                <>
                  <p>
                    Define one delivery obligation and its intended benefit. Use
                    a stable reference so the same obligation is not counted
                    twice.
                  </p>
                  <div className="da-form-grid">
                    <Field
                      name="reference"
                      form={form}
                      set={setForm}
                      required
                      maxLength="160"
                    >
                      Obligation reference
                    </Field>
                    <Field
                      name="title"
                      form={form}
                      set={setForm}
                      required
                      minLength="3"
                      maxLength="240"
                    >
                      Programme / contract title
                    </Field>
                    <label>
                      Sector
                      <select
                        aria-label="Sector"
                        value={form.sector}
                        onChange={(e) =>
                          setForm((f) => ({ ...f, sector: e.target.value }))
                        }
                      >
                        {[
                          "Health",
                          "Water",
                          "Food",
                          "Education",
                          "Infrastructure",
                          "Energy",
                          "Humanitarian assistance",
                          "Other",
                        ].map((v) => (
                          <option key={v}>{v}</option>
                        ))}
                      </select>
                    </label>
                    <Countries name="country" form={form} set={setForm}>
                      Receiving country / territory
                    </Countries>
                    <Countries
                      name="origin_country"
                      form={form}
                      set={setForm}
                      optional
                    >
                      Origin country (if known)
                    </Countries>
                    <Field
                      name="community"
                      form={form}
                      set={setForm}
                      required
                      maxLength="240"
                    >
                      Intended communities / facilities
                    </Field>
                    <Field
                      name="owner"
                      form={form}
                      set={setForm}
                      required
                      maxLength="160"
                    >
                      Responsible programme owner
                    </Field>
                    <Field
                      name="recipient"
                      form={form}
                      set={setForm}
                      required
                      maxLength="200"
                    >
                      Receiving organization
                    </Field>
                    <Memo name="promise" form={form} set={setForm}>
                      What should people receive, and what counts as accepted
                      delivery?
                    </Memo>
                    <Field
                      name="baseline_url"
                      form={form}
                      set={setForm}
                      type="url"
                      required
                    >
                      Baseline / contract document URL
                    </Field>
                    <Field
                      name="due_at"
                      form={form}
                      set={setForm}
                      type="datetime-local"
                      required
                    >
                      Delivery & service deadline
                    </Field>
                    <Field
                      name="target"
                      form={form}
                      set={setForm}
                      required
                      inputMode="decimal"
                    >
                      Delivery target quantity
                    </Field>
                    <Field
                      name="unit"
                      form={form}
                      set={setForm}
                      required
                      maxLength="60"
                      placeholder="medical_kit, pump, school"
                    >
                      Delivery unit
                    </Field>
                    <Field
                      name="outcome_target"
                      form={form}
                      set={setForm}
                      inputMode="decimal"
                    >
                      Service outcome target (optional)
                    </Field>
                    <Field
                      name="outcome_unit"
                      form={form}
                      set={setForm}
                      required={Boolean(form.outcome_target)}
                      maxLength="60"
                      placeholder="clinic_operational, household_served"
                    >
                      Service outcome unit
                    </Field>
                    <Field
                      name="budget"
                      form={form}
                      set={setForm}
                      inputMode="decimal"
                    >
                      Budget context (optional)
                    </Field>
                    <Field
                      name="currency"
                      form={form}
                      set={setForm}
                      required={Boolean(form.budget)}
                      maxLength="3"
                      pattern="[A-Za-z]{3}"
                    >
                      Budget currency (ISO code)
                    </Field>
                  </div>
                  <p>
                    A budget is context. Executed payments and receiving
                    evidence are recorded separately.
                  </p>
                </>
              )}
              {formType === "evidence" && (
                <>
                  <p>
                    {form.supersedes
                      ? "This correction preserves stage, issuer and entry identity. The original remains retained."
                      : "Enter one financial ledger entry, or one cumulative snapshot for this obligation. Do not enter a repeated running balance as a new financial transaction."}
                  </p>
                  <div className="da-form-grid">
                    <label>
                      Evidence stage
                      <select
                        aria-label="Evidence stage"
                        value={form.kind}
                        disabled={Boolean(form.supersedes)}
                        onChange={(e) => {
                          const kind = e.target.value,
                            target =
                              kind === "outcome"
                                ? current.outcome_target
                                : current.delivery_target;
                          setForm((f) => ({
                            ...f,
                            kind,
                            unit: target?.unit || "",
                            value: "",
                          }));
                        }}
                      >
                        {Object.entries(stageNames).map(([k, v]) => (
                          <option
                            key={k}
                            value={k}
                            disabled={
                              k === "outcome" && !current.outcome_target
                            }
                          >
                            {v}
                          </option>
                        ))}
                      </select>
                    </label>
                    <Field
                      name="value"
                      form={form}
                      set={setForm}
                      required
                      inputMode="decimal"
                    >
                      {financial
                        ? "Ledger entry amount"
                        : "Cumulative quantity"}
                    </Field>
                    {financial ? (
                      <>
                        <Field
                          name="currency"
                          form={form}
                          set={setForm}
                          required
                          pattern="[A-Za-z]{3}"
                          maxLength="3"
                        >
                          Currency (ISO code)
                        </Field>
                        <Field
                          name="transfer_id"
                          form={form}
                          set={setForm}
                          required
                          disabled={Boolean(form.supersedes)}
                          maxLength="160"
                        >
                          Shared transfer reference
                        </Field>
                        <Field
                          name="sender_id"
                          form={form}
                          set={setForm}
                          required
                          disabled={Boolean(form.supersedes)}
                          maxLength="160"
                        >
                          Sender party ID
                        </Field>
                        <Field
                          name="recipient_id"
                          form={form}
                          set={setForm}
                          required
                          disabled={Boolean(form.supersedes)}
                          maxLength="160"
                        >
                          Recipient party ID
                        </Field>
                        {form.kind === "funds_sent" && (
                          <Field
                            name="settlement_due_at"
                            form={form}
                            set={setForm}
                            type="datetime-local"
                            required
                          >
                            Settlement deadline
                          </Field>
                        )}
                      </>
                    ) : (
                      <>
                        <Field
                          name="unit"
                          form={form}
                          set={setForm}
                          required
                          maxLength="60"
                        >
                          Snapshot unit
                        </Field>
                        <Field
                          name="covers_through"
                          form={form}
                          set={setForm}
                          type="datetime-local"
                          required
                        >
                          Cumulative coverage through
                        </Field>
                      </>
                    )}
                    <Field
                      name="issuer_id"
                      form={form}
                      set={setForm}
                      required
                      disabled={Boolean(form.supersedes)}
                      maxLength="160"
                    >
                      Declared issuer party ID
                    </Field>
                    <Field
                      name="issuer_name"
                      form={form}
                      set={setForm}
                      required
                      maxLength="200"
                    >
                      Declared issuer name
                    </Field>
                    <Field
                      name="ledger_reference"
                      form={form}
                      set={setForm}
                      required
                      disabled={Boolean(form.supersedes)}
                      maxLength="160"
                    >
                      Unique issuer entry / snapshot reference
                    </Field>
                    <Field
                      name="observed_at"
                      form={form}
                      set={setForm}
                      type="datetime-local"
                      required
                    >
                      Observation / value time
                    </Field>
                    <Field
                      name="document_url"
                      form={form}
                      set={setForm}
                      type="url"
                      required
                    >
                      Supporting document URL
                    </Field>
                    <Memo form={form} set={setForm}>
                      Evidence basis, scope and limitations
                    </Memo>
                  </div>
                  {form.kind === "settlement_deduction" && (
                    <p>
                      Deductions must be documented amounts withheld before
                      recipient credit, in the same currency. Post-credit
                      refunds and foreign-exchange settlements require a
                      different reconciliation and are not supported here.
                    </p>
                  )}
                  <p>
                    Submission records a claim; a URL or a different issuer
                    label does not authenticate it.
                  </p>
                </>
              )}
              {formType === "action" && (
                <div className="da-form-grid">
                  <Field
                    name="title"
                    form={form}
                    set={setForm}
                    required
                    minLength="3"
                    maxLength="240"
                  >
                    Follow-up title
                  </Field>
                  <label>
                    Response type
                    <select
                      aria-label="Response type"
                      value={form.kind}
                      onChange={(e) =>
                        setForm((f) => ({ ...f, kind: e.target.value }))
                      }
                    >
                      {[
                        "evidence_request",
                        "financial_review",
                        "inspection",
                        "delivery_followup",
                      ].map((v) => (
                        <option key={v} value={v}>
                          {pretty(v)}
                        </option>
                      ))}
                    </select>
                  </label>
                  <Field
                    name="owner"
                    form={form}
                    set={setForm}
                    required
                    maxLength="160"
                  >
                    Responsible person / team label
                  </Field>
                  <Field
                    name="due_at"
                    form={form}
                    set={setForm}
                    type="datetime-local"
                    required
                  >
                    Response deadline
                  </Field>
                  <Memo form={form} set={setForm}>
                    Required response and evidence to obtain
                  </Memo>
                </div>
              )}
              {formType === "update" && (
                <div className="da-form-grid">
                  <label>
                    Follow-up status
                    <select
                      aria-label="Follow-up status"
                      value={form.status}
                      onChange={(e) =>
                        setForm((f) => ({ ...f, status: e.target.value }))
                      }
                    >
                      {["open", "in_progress", "completed"].map((v) => (
                        <option key={v} value={v}>
                          {pretty(v)}
                        </option>
                      ))}
                    </select>
                  </label>
                  {form.status === "completed" && (
                    <label>
                      Completion evidence (required)
                      <select
                        aria-label="Completion evidence (required)"
                        required
                        value={form.completion_evidence_id}
                        onChange={(e) =>
                          setForm((f) => ({
                            ...f,
                            completion_evidence_id: e.target.value,
                          }))
                        }
                      >
                        <option value="">Select a retained record…</option>
                        {activeEvidence.map((x) => (
                          <option key={x.id} value={x.id}>
                            {stageNames[x.kind]} · {x.issuer_name} ·{" "}
                            {x.ledger_reference}
                          </option>
                        ))}
                      </select>
                    </label>
                  )}
                  <Memo form={form} set={setForm}>
                    Progress / result and its evidence basis
                  </Memo>
                </div>
              )}
              <p className="da-timezone">
                Dates use this browser’s timezone (
                {Intl.DateTimeFormat().resolvedOptions().timeZone}); stored in
                UTC.
              </p>
              {stale && (
                <p className="da-error">
                  New evidence or history is available. Review the updated
                  record before using this draft.
                  <button
                    type="button"
                    onClick={() =>
                      setForm((f) => ({
                        ...f,
                        expected_version: detail.version,
                      }))
                    }
                  >
                    Use latest version and retain draft
                  </button>
                </p>
              )}
              {formError && (
                <p className="da-error" role="alert">
                  {formError}
                </p>
              )}
              <div className="da-buttons">
                <button className="da-primary" disabled={busy || stale}>
                  {busy
                    ? "Saving…"
                    : formType === "new"
                      ? "Register obligation"
                      : formType === "evidence"
                        ? "Retain evidence & reconcile"
                        : formType === "action"
                          ? "Assign follow-up"
                          : "Save progress"}
                </button>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => setFormType(null)}
                >
                  Cancel
                </button>
              </div>
            </fieldset>
          </form>
        </Modal>
      )}
    </section>
  );
}
