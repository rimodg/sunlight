export default function ProcurementEngineEvidence({ result }) {
  if (!result) return null;
  const gate = result.gate_outcome;
  return (
    <section
      className="ops-engine-basis"
      aria-label="Procurement decision basis"
    >
      <dl>
        <dt>Applicable profile</dt>
        <dd>{result.profile_used || "Not recorded"}</dd>
        <dt>Structural verdict</dt>
        <dd>{result.structure?.verdict || "Structural stage not reached"}</dd>
        <dt>Structural confidence</dt>
        <dd>{result.structure?.confidence ?? "Not available"}</dd>
        <dt>Investigation recommendation</dt>
        <dd>
          {result.recommended_for_investigation
            ? "Recommended by the attached statistical check"
            : "No recommendation in this output"}
        </dd>
        <dt>Evidence gate</dt>
        <dd>
          {result.gate_verdict || "Not evaluated"}
          {gate && (
            <small>
              Threshold parameters: {gate.global_params_version} ·{" "}
              {gate.dimensions_fired} dimensions fired
            </small>
          )}
        </dd>
      </dl>
      <p>
        A single-contract recommendation has no portfolio-capacity context.
        Structural confidence and gate outputs are checks on supplied evidence;
        they do not establish a probability of theft or authenticate delivery.
      </p>
      {gate && (
        <details>
          <summary>Inspect evidence dimensions and thresholds</summary>
          {gate.dimension_results.map((d) => (
            <article key={d.dimension}>
              <strong>
                {d.dimension} ·{" "}
                {d.fired ? "Threshold exceeded" : "Threshold not exceeded"}
              </strong>
              <p>
                Observed: {d.observed_value ?? "Not available"} · threshold:{" "}
                {d.threshold ?? "Not available"}
              </p>
              <p>{d.detail}</p>
            </article>
          ))}
        </details>
      )}
    </section>
  );
}
