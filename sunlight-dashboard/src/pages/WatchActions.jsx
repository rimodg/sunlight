import "./WatchActions.css";

export default function WatchActions({
  data,
  error,
  country,
  compact,
  onQueue,
  onRecord,
  onMoney,
  onDelivery,
  onOperations,
  onRetry,
}) {
  const next = data?.items?.[0];
  const registered = data
    ? data.registered.delivery + data.registered.operations
    : 0;
  return (
    <section
      className={`watch-actions ${compact ? "is-compact" : ""}`}
      aria-label="Watch actions"
    >
      <div className="wa-heading">
        <h2>{error ? "Review status unavailable" : "What needs attention"}</h2>
        <span>
          {country || "Global"} · Registered evidence
          {error
            ? " · Status unavailable"
            : data
              ? ` · Checked ${new Date(data.as_of).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`
              : " · Checking…"}
        </span>
        <button onClick={() => onQueue(false)}>Review priorities →</button>
      </div>
      <div className="wa-workflow" aria-label="Evidence workflow">
        <button aria-label="Explore money flows" onClick={onMoney}>
          <span className="wa-step" aria-hidden="true">
            01
          </span>
          <span>
            <strong>Explore money flows ↗</strong>
            <small>Countries, amounts, periods & sources</small>
          </span>
        </button>
        <button aria-label="Verify funds & delivery" onClick={onDelivery}>
          <span className="wa-step" aria-hidden="true">
            02
          </span>
          <span>
            <strong>Verify funds & delivery ↗</strong>
            <small>Release → arrival → acceptance → public benefit</small>
          </span>
        </button>
        <button onClick={() => onQueue(false)}>
          <span className="wa-step">03</span>
          <span>
            <strong>
              {data
                ? registered
                  ? `${data.total.toLocaleString()} review records`
                  : "Start evidence review"
                : "Review evidence gaps"}{" "}
              →
            </strong>
            <small>
              {data?.overdue_actions
                ? `${data.overdue_actions} overdue follow-ups · Inspect & assign`
                : "Inspect the evidence. Assign the next check."}
            </small>
          </span>
        </button>
      </div>
      {error ? (
        <div className="wa-state" role="alert">
          <p>
            Review status unavailable.{" "}
            {data
              ? "Previous results are retained; refresh before acting."
              : "No current review counts can be shown."}
          </p>
          <button onClick={onRetry}>Retry review status</button>
        </div>
      ) : !data ? (
        <p className="wa-state" role="status">
          Checking registered funding, delivery and follow-up records…
        </p>
      ) : next ? (
        <div className="wa-next">
          <div className="wa-next-copy">
            <span className="wa-priority">
              Next evidence check · {next.priority_label}
            </span>
            <h3>{next.title}</h3>
            <p>{next.next_step}</p>
            <span className="wa-basis">
              {next.measurements?.[0] && (
                <b>
                  {next.measurements[0].label}: {next.measurements[0].value}{" "}
                  {next.measurements[0].currency || next.measurements[0].unit}{" "}
                  ·{" "}
                </b>
              )}
              {next.owners.length
                ? `Assigned: ${next.owners.join(", ")}`
                : "No follow-up owner assigned"}{" "}
              · Submitted evidence; requires verification.
            </span>
          </div>
          <div className="wa-next-controls">
            <button className="wa-open" onClick={() => onRecord(next)}>
              Open evidence & next steps →
            </button>
            <button onClick={() => onQueue(true)}>
              {data.unassigned.toLocaleString()} need assignment →
            </button>
          </div>
        </div>
      ) : (
        <div className="wa-state">
          <div>
            <strong>
              {registered
                ? "No open review records in this scope"
                : "Arrival and delivery checks start with evidence"}
            </strong>
            <p>
              {registered
                ? `${registered} registered records assessed. Completed case reviews remain available in the queue.`
                : "Published flows are visible on the globe. Submit source records or register a delivery to compare what was promised with what arrived."}
            </p>
          </div>
          <button onClick={onOperations}>Open source intake →</button>
          <button onClick={onDelivery}>Open delivery checks →</button>
        </div>
      )}
    </section>
  );
}
