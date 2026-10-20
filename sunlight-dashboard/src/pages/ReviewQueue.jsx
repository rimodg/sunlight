import { useCallback, useEffect, useRef, useState } from "react";
import { humanApiError } from "./apiErrors";
import { countryCatalog } from "./watchOverview";
import "./ReviewQueue.css";
const names = new Map(countryCatalog.map((c) => [c.code, c.name]));
const pretty = (value) => String(value || "").replaceAll("_", " ");
const time = (value) => new Date(value).toLocaleString();
async function request(url, options) {
  const r = await fetch(url, options),
    data = await r.json();
  if (!r.ok) throw new Error(humanApiError(data));
  return data;
}
export default function ReviewQueue({
  active,
  country,
  refreshToken,
  onChanged,
  onDelivery,
  onOperations,
  onCountry,
  onInvestigate,
}) {
  const [data, setData] = useState(null),
    [q, setQ] = useState(""),
    [lens, setLens] = useState("all"),
    [source, setSource] = useState("all"),
    [unassigned, setUnassigned] = useState(false),
    [reviewed, setReviewed] = useState(false),
    [examples, setExamples] = useState(false),
    [page, setPage] = useState(0),
    [error, setError] = useState(""),
    [notice, setNotice] = useState("");
  const [assignment, setAssignment] = useState(null),
    [busy, setBusy] = useState(false),
    [formError, setFormError] = useState("");
  const generation = useRef(0);
  useEffect(() => {
    if (assignment)
      requestAnimationFrame(() =>
        document.querySelector(".rq-assignment")?.scrollIntoView({
          block: "start",
          behavior: window.matchMedia("(prefers-reduced-motion: reduce)")
            .matches
            ? "auto"
            : "smooth",
        }),
      );
  }, [assignment?.record.id]);
  const load = useCallback(
    async (signal) => {
      const id = ++generation.current;
      const params = new URLSearchParams({
        country: country || "",
        q,
        lens,
        source,
        unassigned: String(unassigned),
        include_reviewed: String(reviewed),
        synthetic: String(examples),
        limit: "20",
        offset: String(page * 20),
      });
      const result = await request("/workbench/review-queue?" + params, {
        signal,
      });
      if (!signal?.aborted && id === generation.current) {
        setData(result);
        setError("");
      }
    },
    [
      country,
      q,
      lens,
      source,
      unassigned,
      reviewed,
      examples,
      page,
      refreshToken,
    ],
  );
  useEffect(() => {
    if (data && page > 0 && data.total <= page * 20)
      setPage(Math.max(0, Math.ceil(data.total / 20) - 1));
  }, [data?.total, page]);
  useEffect(() => {
    setPage(0);
  }, [country, q, lens, source, unassigned, reviewed, examples]);
  useEffect(() => {
    if (!active) return;
    const controller = new AbortController();
    const update = () => {
      if (!document.hidden)
        load(controller.signal).catch((e) => {
          if (e.name !== "AbortError") setError(e.message);
        });
    };
    update();
    const timer = setInterval(update, 20000);
    document.addEventListener("visibilitychange", update);
    return () => {
      controller.abort();
      clearInterval(timer);
      document.removeEventListener("visibilitychange", update);
    };
  }, [active, load]);
  function assign(item) {
    if (assignment) {
      setNotice(
        "Your current follow-up draft is retained. Save or cancel it before starting another.",
      );
      return;
    }
    const signal = item.issues[0];
    setAssignment({
      record: item,
      signal_key: signal?.key || "",
      owner: item.programme_owner || "",
      title: signal?.title || "Review retained evidence",
      due_at: "",
      note: signal?.next_step || item.next_step,
      expected_version: item.version,
    });
    setFormError("");
    setNotice("");
  }
  function edit(field, value) {
    setAssignment((a) => ({ ...a, [field]: value }));
  }
  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setFormError("");
    try {
      const signal = assignment.record.issues.find(
        (s) => s.key === assignment.signal_key,
      );
      await request(
        "/assurance/obligations/" + assignment.record.id + "/actions",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            expected_version: assignment.expected_version,
            title: assignment.title,
            kind:
              signal?.stage === "funds"
                ? "financial_review"
                : "evidence_request",
            owner: assignment.owner,
            due_at: new Date(assignment.due_at).toISOString(),
            note: assignment.note,
            signal_key: assignment.signal_key,
          }),
        },
      );
      setAssignment(null);
      setNotice(
        "Follow-up recorded with owner, deadline and evidence request. No external message or payment action was sent.",
      );
      onChanged?.();
      await load();
    } catch (e) {
      setFormError(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function updateVersion() {
    setBusy(true);
    try {
      const current = await request(
        "/assurance/obligations/" + assignment.record.id,
      );
      if (
        assignment.signal_key &&
        !current.assessment.signals.some((s) => s.key === assignment.signal_key)
      )
        throw new Error(
          "This issue changed or cleared. Cancel this draft and inspect the current record before assigning it.",
        );
      setAssignment((a) => ({ ...a, expected_version: current.version }));
      setFormError(
        "Current record version loaded. Your draft is retained; review it before saving.",
      );
    } catch (e) {
      setFormError(e.message);
    } finally {
      setBusy(false);
    }
  }
  const reportURL =
    "/workbench/review-queue/report?" +
    new URLSearchParams({
      country: country || "",
      q,
      lens,
      source,
      unassigned: String(unassigned),
      include_reviewed: String(reviewed),
      synthetic: String(examples),
    });
  return (
    <section className="rq" aria-label="Institutional review queue">
      <header>
        <p className="ev-eyebrow">REGISTERED EVIDENCE → RESPONSIBLE REVIEW</p>
        <h1>Review queue</h1>
        <p>What needs a check, what supports it, and who acts next.</p>
      </header>
      <div className="rq-filters">
        <label>
          Work focus
          <select
            aria-label="Work focus"
            value={lens}
            onChange={(e) => setLens(e.target.value)}
          >
            <option value="all">All review work</option>
            <option value="finance">Treasury & financial control</option>
            <option value="delivery">Programme & receiving teams</option>
            <option value="procurement">Procurement & trade review</option>
            <option value="oversight">Audit & oversight</option>
          </select>
        </label>
        <label>
          Record type
          <select
            aria-label="Record type"
            value={source}
            onChange={(e) => setSource(e.target.value)}
          >
            <option value="all">All registered records</option>
            <option value="delivery">Delivery obligations</option>
            <option value="operations">Source comparison cases</option>
          </select>
        </label>
        <label>
          Find record, owner or evidence issue
          <input
            type="search"
            maxLength="200"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Reference, programme, owner…"
          />
        </label>
      </div>
      <div className="rq-checks">
        <label>
          <input
            type="checkbox"
            checked={unassigned}
            onChange={(e) => setUnassigned(e.target.checked)}
          />
          Needs assignment
        </label>
        <label>
          <input
            type="checkbox"
            checked={reviewed}
            onChange={(e) => setReviewed(e.target.checked)}
          />
          Include completed case reviews
        </label>
        <label>
          <input
            type="checkbox"
            checked={examples}
            onChange={(e) => setExamples(e.target.checked)}
          />
          Synthetic examples only
        </label>
      </div>
      <div className="rq-refresh">
        <button
          disabled={busy}
          onClick={() => load().catch((e) => setError(e.message))}
        >
          Recalculate queue
        </button>
        <a href={reportURL} target="_blank" rel="noreferrer">
          Review meeting brief / PDF ↗
        </a>
        <span>
          {data
            ? "Assessed " + time(data.as_of)
            : "Loading registered evidence…"}
        </span>
      </div>
      {error && (
        <p className="rq-error" role="alert">
          Queue refresh failed: {error}.{" "}
          {data
            ? "The retained queue below is from " + time(data.as_of) + "."
            : "No current queue is available."}
        </p>
      )}
      {notice && (
        <p role="status" className="rq-notice">
          {notice}
        </p>
      )}
      {data && (
        <>
          <div className="rq-summary">
            <div>
              <strong>{data.total}</strong>
              <span>Matching review records</span>
            </div>
            <div>
              <strong>{data.unassigned}</strong>
              <span>Without assigned follow-up/reviewer</span>
            </div>
            <div>
              <strong>{data.overdue_actions}</strong>
              <span>Overdue follow-ups</span>
            </div>
          </div>
          <p className="rq-scope">
            {examples
              ? "ISOLATED SYNTHETIC EXAMPLES"
              : country
                ? names.get(country) + " / REGISTERED SCOPE"
                : "REGISTERED DEPLOYMENT SCOPE"}{" "}
            · {data.registered.delivery} obligations ·{" "}
            {data.registered.operations} source cases assessed before
            pagination.
          </p>
          <details className="rq-rule">
            <summary>How priorities and evidence are interpreted</summary>
            <p>{data.ranking_rule}</p>
            <p>{data.coverage}</p>
            <p>{data.authority}</p>
            <p>
              Work focus filters are task views, not access roles. A current
              engine state refers to retained record/acceptance inputs. It does
              not authenticate an issuer or establish that a source is correct.
            </p>
          </details>
          {data.reviewed_source_conditions > 0 && !reviewed && (
            <p>
              {data.reviewed_source_conditions} completed case review(s) retain
              source conditions. Include completed reviews to inspect them; no
              discrepancy was erased.
            </p>
          )}
          {!data.total && (
            <div className="rq-empty">
              <h2>
                {q || unassigned || lens !== "all"
                  ? "No records match these filters"
                  : "No review records in this scope"}
              </h2>
              <p>
                {examples
                  ? "Use the isolated worked example in Delivery assurance to exercise the workflow."
                  : "Global statistics alone do not supply contract baselines, recipient credits or acceptance evidence. Register an obligation or submit an attributed source record to begin checking an actual chain."}
              </p>
              <button onClick={() => onDelivery(null)}>
                Open delivery assurance →
              </button>
              <button onClick={() => onOperations(null)}>
                Open Records & review →
              </button>
            </div>
          )}
          {assignment && (
            <form
              className="rq-assignment"
              aria-label="Assign evidence follow-up"
              onSubmit={submit}
            >
              <h2>Assign evidence follow-up</h2>
              <p>
                {assignment.record.title} · record version{" "}
                {assignment.expected_version}
              </p>
              <label>
                Evidence issue
                <select
                  value={assignment.signal_key}
                  onChange={(e) => {
                    const s = assignment.record.issues.find(
                      (s) => s.key === e.target.value,
                    );
                    setAssignment((a) => ({
                      ...a,
                      signal_key: e.target.value,
                      title: s.title,
                      note: s.next_step,
                    }));
                  }}
                >
                  {assignment.record.issues.map((s) => (
                    <option key={s.key} value={s.key}>
                      {s.title}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Follow-up title
                <input
                  required
                  minLength="3"
                  maxLength="240"
                  value={assignment.title}
                  onChange={(e) => edit("title", e.target.value)}
                />
              </label>
              <label>
                Responsible owner
                <input
                  required
                  maxLength="160"
                  value={assignment.owner}
                  onChange={(e) => edit("owner", e.target.value)}
                />
              </label>
              <label>
                Follow-up deadline
                <input
                  required
                  type="datetime-local"
                  value={assignment.due_at}
                  onChange={(e) => edit("due_at", e.target.value)}
                />
              </label>
              <label>
                Required evidence and review note
                <textarea
                  required
                  minLength="3"
                  maxLength="4000"
                  value={assignment.note}
                  onChange={(e) => edit("note", e.target.value)}
                />
              </label>
              {formError && (
                <p className="rq-error" role="alert">
                  {formError}
                </p>
              )}
              <div className="rq-actions">
                <button disabled={busy}>Record follow-up</button>
                <button type="button" disabled={busy} onClick={updateVersion}>
                  Refresh record version; retain draft
                </button>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => setAssignment(null)}
                >
                  Cancel draft
                </button>
              </div>
            </form>
          )}
          <div className="rq-items">
            {data.items.map((item) => (
              <article
                key={item.kind + item.id}
                className={"rq-item rq-" + item.priority}
              >
                <div className="rq-item-head">
                  <span>{item.priority_label}</span>
                  <small>
                    {item.synthetic ? "SYNTHETIC · " : ""}
                    {item.kind === "delivery"
                      ? "DELIVERY OBLIGATION"
                      : "SOURCE CASE"}{" "}
                    · v{item.version}
                  </small>
                </div>
                <h2>{item.title}</h2>
                <p>
                  {item.reference} · {names.get(item.country) || item.country}
                </p>
                <p className="rq-next">
                  <strong>Next evidence:</strong> {item.next_step}
                </p>
                <dl>
                  <dt>Deadline / earliest overdue follow-up</dt>
                  <dd>{time(item.due_at)}</dd>
                  <dt>Assigned responsibility</dt>
                  <dd>
                    {item.owners.join(", ") || "No follow-up/reviewer assigned"}
                    {item.programme_owner && (
                      <small>Programme owner: {item.programme_owner}</small>
                    )}
                  </dd>
                  <dt>Engine check</dt>
                  <dd>
                    {pretty(item.engine_state)}
                    <small>{item.engine_note}</small>
                  </dd>
                  <dt>Current review</dt>
                  <dd>
                    {pretty(item.review_state)} · {item.issue_count} evidence
                    issues · {item.open_actions} open follow-ups
                  </dd>
                </dl>
                {item.measurements.map((m, index) => (
                  <p className="rq-measure" key={index}>
                    <span>{m.label}</span>
                    <strong>
                      {m.value} {m.currency || m.unit}
                    </strong>
                    <small>
                      {m.reference} · retained claim-based comparison; no
                      cross-record sum
                    </small>
                  </p>
                ))}
                <details>
                  <summary>Evidence condition & issue basis</summary>
                  <p>{item.evidence_basis}</p>
                  {item.issues.map((s) => (
                    <div key={s.key}>
                      <strong>{s.title}</strong>
                      <p>{s.reason}</p>
                    </div>
                  ))}
                </details>
                <div className="rq-actions">
                  <button
                    onClick={() =>
                      item.kind === "delivery"
                        ? onDelivery(item)
                        : onOperations(item)
                    }
                  >
                    Open record & engine findings →
                  </button>
                  {item.kind === "delivery" && item.issues.length > 0 && (
                    <button disabled={busy} onClick={() => assign(item)}>
                      Assign evidence follow-up
                    </button>
                  )}
                  <button onClick={() => onCountry(item.country)}>
                    Locate country on watch
                  </button>
                  <a href={item.report_url} target="_blank" rel="noreferrer">
                    Readable review brief / PDF ↗
                  </a>
                  {item.kind === "delivery" && (
                    <button
                      onClick={() =>
                        onInvestigate({
                          question: `Review registered obligation ${item.reference}: ${item.next_step}`,
                          country_codes: [item.country],
                          obligation_ids: [item.id],
                          sources: ["delivery_assurance"],
                        })
                      }
                    >
                      Investigate selected obligation →
                    </button>
                  )}
                </div>
              </article>
            ))}
          </div>
          {data.total > 0 && (
            <div className="rq-pagination">
              <button disabled={!page} onClick={() => setPage((p) => p - 1)}>
                Previous
              </button>
              <span>
                {page * 20 + 1}–{Math.min((page + 1) * 20, data.total)} of{" "}
                {data.total}
              </span>
              <button
                disabled={(page + 1) * 20 >= data.total}
                onClick={() => setPage((p) => p + 1)}
              >
                Next
              </button>
            </div>
          )}
          <p className="rq-boundary">
            This queue measures review work in registered records. World totals,
            source discrepancies and missing evidence are separate concepts; no
            global theft number or automatic stop order is inferred.
          </p>
        </>
      )}
    </section>
  );
}
