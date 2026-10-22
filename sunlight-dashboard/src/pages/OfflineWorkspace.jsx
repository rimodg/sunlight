import { useEffect, useState } from "react";
import "./OfflineWorkspace.css";
const time = (value) =>
  !value
    ? "No record received"
    : /^\d{4}-\d{2}-\d{2}$/.test(value)
      ? new Date(value + "T00:00:00").toLocaleDateString()
      : new Date(value).toLocaleString();
export default function OfflineWorkspace({ active, onOpen }) {
  const [data, setData] = useState(null),
    [error, setError] = useState(""),
    [refresh, setRefresh] = useState(0);
  useEffect(() => {
    if (!active) return;
    const c = new AbortController();
    fetch("/offline/status", { signal: c.signal })
      .then(async (r) => {
        if (!r.ok) throw new Error("Local capability status unavailable");
        const result = await r.json();
        if (!c.signal.aborted) {
          setData(result);
          setError("");
        }
      })
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => c.abort();
  }, [active, refresh]);
  return (
    <section className="of-workspace" aria-label="Offline workspace">
      <p className="ev-eyebrow">CONTINUITY / LOCAL EVIDENCE / TRACEABILITY</p>
      <h1>Work without internet</h1>
      <p>
        Keep analysis, evidence and decisions available on your computer or
        institutional local network.
      </p>
      {error && (
        <p role="alert">
          {error}.{" "}
          <button onClick={() => setRefresh((v) => v + 1)}>Retry status</button>
        </p>
      )}
      {!data ? (
        <p role="status">Checking this instance…</p>
      ) : (
        <>
          <div className="of-mode">
            <strong>
              {data.offline_policy
                ? "Offline policy active"
                : "Connected deployment mode"}
            </strong>
            <p>
              {data.offline_policy
                ? "The engines run here. External refreshes and cloud AI are disabled; retained evidence stays usable."
                : "This website still needs a connection to its server. A local installation lets the full engines work when that connection is unavailable."}
            </p>
          </div>
          <div className="of-actions">
            <a href="/offline/guide" target="_blank" rel="noreferrer">
              Local installation guide / PDF ↗
            </a>
            <button onClick={() => setRefresh((v) => v + 1)}>
              Refresh local status
            </button>
          </div>
          <h2>What keeps working</h2>
          <ul>
            {data.capabilities.map((c) => (
              <li key={c}>{c}</li>
            ))}
          </ul>
          <h2>Evidence held by this instance</h2>
          <div className="of-counts">
            {[
              ["obligations", "Obligations"],
              ["evidence_entries", "Delivery / funds entries"],
              ["source_revisions", "Source revisions"],
              ["investigations", "Saved investigations"],
              ["documents", "Stored documents"],
            ].map(([key, label]) => (
              <div key={key}>
                <strong>{data.records[key].toLocaleString()}</strong>
                <span>{label}</span>
              </div>
            ))}
          </div>
          <dl>
            <dt>Last source record received here</dt>
            <dd>{time(data.last_source_record_received_at)}</dd>
            <dt>Latest publisher date among submitted source records</dt>
            <dd>{time(data.last_source_record_published_at)}</dd>
            <dt>Packaged monetary extract retrieved</dt>
            <dd>{time(data.monetary_extract.retrieved_at)}</dd>
          </dl>
          <p className="of-note">
            New events require records delivered to this instance. Data can
            arrive through a local system, a file carried to the site, or a
            later connection. A missing arrival remains unknown; the clock does
            not create new observations.
          </p>
          <p>{data.clock_note}</p>
          <h2>Follow an existing trace</h2>
          <p>{data.traceability}</p>
          <div className="of-journey">
            {[
              ["operations", "01 · Source and transaction references"],
              ["delivery", "02 · Debit, arrival and accepted delivery"],
              ["research", "03 · Documents, calculations and inquiry"],
              ["queue", "04 · Owner, evidence request and follow-up"],
            ].map(([id, label]) => (
              <button key={id} onClick={() => onOpen(id)}>
                {label} →
              </button>
            ))}
          </div>
          <h2>Carry the evidence with you</h2>
          <p>
            A checkpoint retains the ledger, PDF originals, saved
            investigations, review history, calibration sidecars and cached
            trade previews. Its file hashes are verified before restoration into
            a new local data directory.
          </p>
          <p className="of-note">
            {data.checkpoint_scope} Store the archive privately. Restoration
            never merges or overwrites a running ledger. It does not synchronize
            changes back to the hosted service.
          </p>
          <a className="of-download" href="/offline/checkpoint" download>
            Download full evidence checkpoint ↓
          </a>
          <p>{data.restart_limit}</p>
          <details>
            <summary>Network and data-age policy</summary>
            <p>{data.external_services}</p>
            <p>{data.arrival_limit}</p>
            <p>
              Packaged monetary source revision:{" "}
              {data.monetary_extract.revision}. Local hashes demonstrate content
              consistency; they do not replace authenticated bank or issuer
              evidence.
            </p>
          </details>
        </>
      )}
    </section>
  );
}
