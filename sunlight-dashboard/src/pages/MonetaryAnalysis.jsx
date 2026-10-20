import { useEffect, useMemo, useState } from "react";
import { countryCatalog } from "./watchOverview";
import { compactUSD, measureKinds } from "./moneyAtlas";
import "./MonetaryWorkbench.css";

const names = new Map(countryCatalog.map((c) => [c.code, c.name]));
const statusLabels = {
  comparable: "Same measure and source basis",
  missing_observation: "An observation is missing",
  coverage_changed: "Coverage changed; no comparable aggregate change",
  basis_changed: "Source basis changed",
  same_period: "Choose an earlier baseline to compare",
};
const colors = ["#91d7b5", "#e9cd89", "#a8c7f2", "#c9b7df"];
const years = Array.from({ length: 8 }, (_, i) => 2019 + i);
function initialPeers() {
  return [
    ...new Set(
      (new URLSearchParams(location.search).get("compare") || "").split(","),
    ),
  ]
    .filter((c) => names.has(c))
    .slice(0, 4);
}

function Trend({ series, onInspectYear }) {
  const [focus, setFocus] = useState(null);
  const plotted = series.length > 1 ? series.slice(1) : series;
  const values = plotted.flatMap((s) =>
    s.points.filter((p) => p.value !== null).map((p) => Number(p.value)),
  );
  if (!values.length)
    return (
      <p>
        No retained annual observations for these countries. Missing is unknown.
      </p>
    );
  const lo = Math.min(0, ...values),
    hi = Math.max(0, ...values),
    span = hi - lo || 1;
  const x = (year) => 42 + ((year - 2019) / 7) * 420;
  const y = (value) => 154 - ((Number(value) - lo) / span) * 125;
  return (
    <div className="mw-trend">
      <svg
        viewBox="0 0 500 196"
        role="img"
        aria-label="Annual monetary observations. Missing years break the line; current USD, not inflation adjusted."
      >
        <text x="8" y="17">
          {compactUSD(hi)}
        </text>
        <text x="8" y="172">
          {compactUSD(lo)}
        </text>
        <line x1="42" x2="462" y1={y(0)} y2={y(0)} stroke="#4a616d" />
        {years.map((year) => (
          <text key={year} x={x(year)} y="189" textAnchor="middle">
            {year}
          </text>
        ))}
        {plotted.map((s, i) => (
          <g key={s.country} stroke={colors[i % colors.length]}>
            {s.points
              .slice(1)
              .map(
                (p, j) =>
                  p.value !== null &&
                  s.points[j].value !== null && (
                    <line
                      key={p.year}
                      x1={x(s.points[j].year)}
                      x2={x(p.year)}
                      y1={y(s.points[j].value)}
                      y2={y(p.value)}
                      strokeWidth="1.8"
                    />
                  ),
              )}
            {s.points
              .filter((p) => p.value !== null)
              .map((p) => (
                <circle
                  key={p.year}
                  cx={x(p.year)}
                  cy={y(p.value)}
                  r="4"
                  fill={colors[i % colors.length]}
                  tabIndex="0"
                  role="button"
                  aria-label={`${s.name}, ${p.year}, ${compactUSD(p.value)}. Inspect observation.`}
                  onClick={() => setFocus({ ...p, name: s.name })}
                  onKeyDown={(e) => {
                    if (["Enter", " "].includes(e.key)) {
                      e.preventDefault();
                      setFocus({ ...p, name: s.name });
                    }
                  }}
                >
                  <title>
                    {s.name} · {p.year} · USD {p.value} · {p.basis}
                  </title>
                </circle>
              ))}
          </g>
        ))}
      </svg>
      <div className="mw-legend">
        {plotted.map((s, i) => (
          <span key={s.country}>
            <i style={{ background: colors[i % colors.length] }} />
            {s.name}
          </span>
        ))}
      </div>
      {focus && (
        <div className="mw-point" role="status">
          <span>
            {focus.name} · {focus.year} · {compactUSD(focus.value)}
            <small>
              {focus.basis.replaceAll("_", " ")} · {focus.coverage_count}{" "}
              covered observations
            </small>
          </span>
          <button onClick={() => onInspectYear(focus.year)}>
            Show {focus.year} on map →
          </button>
        </div>
      )}
      <p className="mw-caption">
        Current USD · lines connect consecutive observed years only. Covered
        totals can change when reporting coverage changes.
      </p>
    </div>
  );
}

export default function MonetaryAnalysis({
  measure,
  selectedYear,
  country,
  onCountry,
  onYear,
  onExplore,
  onInvestigate,
}) {
  const [peers, setPeers] = useState(initialPeers),
    [candidate, setCandidate] = useState("");
  const [baseline, setBaseline] = useState(() => {
    const value = Number(
      new URLSearchParams(location.search).get("compare_from"),
    );
    return value >= 2019 && value <= selectedYear
      ? value
      : Math.max(2019, selectedYear - 1);
  });
  const [direction, setDirection] = useState(() =>
    new URLSearchParams(location.search).get("aid_direction") === "outward"
      ? "outward"
      : "inward",
  );
  const [data, setData] = useState(null),
    [error, setError] = useState(""),
    [retry, setRetry] = useState(0);
  const codes = useMemo(
    () => [...new Set([country?.code, ...peers].filter(Boolean))].slice(0, 4),
    [country?.code, peers],
  );
  const effectiveBaseline = Math.min(baseline, selectedYear);
  const params = useMemo(
    () =>
      new URLSearchParams({
        measure,
        countries: codes.join(","),
        baseline: String(effectiveBaseline),
        year: String(selectedYear),
        direction,
      }),
    [measure, codes.join(","), effectiveBaseline, selectedYear, direction],
  );
  useEffect(() => {
    const url = new URL(location.href);
    codes.length
      ? url.searchParams.set("compare", codes.join(","))
      : url.searchParams.delete("compare");
    url.searchParams.set("compare_from", effectiveBaseline);
    measure === "aid"
      ? url.searchParams.set("aid_direction", direction)
      : url.searchParams.delete("aid_direction");
    history.replaceState(null, "", url);
  }, [codes.join(","), effectiveBaseline, direction, measure]);
  useEffect(() => {
    const controller = new AbortController();
    setData(null);
    setError("");
    fetch("/watch-data/money/analysis?" + params, { signal: controller.signal })
      .then(async (r) => {
        if (!r.ok)
          throw new Error(
            "The selected monetary analysis could not be loaded.",
          );
        const result = await r.json();
        if (!controller.signal.aborted) setData(result);
      })
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => controller.abort();
  }, [params, retry]);
  function investigate() {
    onInvestigate({
      question: `Compare ${data.measure.label} for ${codes.map((c) => names.get(c)).join(", ") || "the published world / covered total"} between ${effectiveBaseline} and ${selectedYear}. Check definitions, changes in reporting coverage, and the evidence needed to verify recipient arrival. Statistical changes are not lost payments.`,
      country_codes: codes,
      year_start: effectiveBaseline,
      year_end: selectedYear,
      sources: ["monetary", "operations", "delivery_assurance"],
    });
  }
  return (
    <section
      className="mw-analysis"
      aria-label="Monetary comparison and history"
    >
      <h2>Compare & history</h2>
      <p>
        Compare the same measure across countries and source years. Keep
        economic changes separate from delivery discrepancies.
      </p>
      {data && (
        <div className="mw-analysis-headline">
          <span>
            {data.measure.label} · {selectedYear} · World / covered figure
          </span>
          <strong>{compactUSD(data.series[0].current.value)}</strong>
          <span>
            {data.series[0].current.basis.replaceAll("_", " ")} ·{" "}
            {measureKinds[data.measure.kind]}
          </span>
        </div>
      )}
      <div className="mw-compare-filters">
        <label>
          Baseline year
          <select
            aria-label="Comparison baseline year"
            value={effectiveBaseline}
            onChange={(e) => setBaseline(Number(e.target.value))}
          >
            {years
              .filter((y) => y <= selectedYear)
              .map((y) => (
                <option key={y}>{y}</option>
              ))}
          </select>
        </label>
        <label>
          Comparison / map year
          <select
            aria-label="Comparison map year"
            value={selectedYear}
            onChange={(e) => onYear(e.target.value)}
          >
            {years.map((y) => (
              <option key={y}>{y}</option>
            ))}
          </select>
        </label>
        <label className="mw-add-country">
          Add a comparison country
          <select
            aria-label="Comparison country"
            value={candidate}
            onChange={(e) => setCandidate(e.target.value)}
          >
            <option value="">Choose a country or territory</option>
            {countryCatalog
              .filter((c) => !codes.includes(c.code))
              .map((c) => (
                <option key={c.code} value={c.code}>
                  {c.name} · {c.code}
                </option>
              ))}
          </select>
        </label>
        <button
          disabled={!candidate || codes.length >= 4}
          onClick={() => {
            setPeers([...codes, candidate]);
            setCandidate("");
          }}
        >
          Add country
        </button>
        {measure === "aid" && (
          <label>
            Aid country role
            <select
              aria-label="Aid comparison role"
              value={direction}
              onChange={(e) => setDirection(e.target.value)}
            >
              <option value="inward">
                Net disbursements reported to recipient
              </option>
              <option value="outward">
                Net disbursements reported by donor
              </option>
            </select>
          </label>
        )}
      </div>
      <div className="mw-country-chips">
        {codes.map((c) => (
          <span key={c}>
            {names.get(c)}
            {country?.code === c ? (
              <small>Map focus</small>
            ) : (
              <button
                aria-label={`Remove ${names.get(c)} from comparison`}
                onClick={() => setPeers(codes.filter((v) => v !== c))}
              >
                ×
              </button>
            )}
          </span>
        ))}
        {!codes.length && (
          <p>
            World / covered series shown. Add up to four countries to compare.
          </p>
        )}
      </div>
      {codes.length === 4 && (
        <p className="mw-caption">
          Four-country comparison limit. Remove a comparison country to add
          another.
        </p>
      )}
      {error ? (
        <p role="alert">
          {error}{" "}
          <button onClick={() => setRetry((v) => v + 1)}>Retry analysis</button>
        </p>
      ) : !data ? (
        <p role="status">Loading comparable observations…</p>
      ) : (
        <>
          {data.measure.kind === "stock" && (
            <div className="mw-analysis-basis">
              <p>
                Changes describe the recorded position. They do not measure
                payments made during the year.
              </p>
            </div>
          )}
          <Trend
            key={measure + codes.join(",")}
            series={data.series}
            onInspectYear={(year) => {
              onYear(String(year));
              onExplore();
            }}
          />
          <div className="mw-comparisons">
            {data.series.map((s) => (
              <article key={s.country}>
                <header>
                  <h3>{s.name}</h3>
                  <span>{s.current.basis.replaceAll("_", " ")}</span>
                </header>
                <div className="mw-compare-values">
                  <span>
                    {effectiveBaseline}
                    <strong title={s.baseline.value ?? "No observation"}>
                      {compactUSD(s.baseline.value)}
                    </strong>
                  </span>
                  <span>
                    {selectedYear}
                    <strong title={s.current.value ?? "No observation"}>
                      {compactUSD(s.current.value)}
                    </strong>
                  </span>
                  <span>
                    Change
                    <strong
                      title={
                        s.change.difference ?? statusLabels[s.change.status]
                      }
                    >
                      {compactUSD(s.change.difference)}
                    </strong>
                  </span>
                </div>
                <p>
                  {statusLabels[s.change.status]}
                  {s.change.percent !== null
                    ? ` · ${s.change.percent}%`
                    : s.change.status === "comparable"
                      ? " · Percentage unavailable for a zero or negative baseline"
                      : ""}
                </p>
                {s.country !== "WLD" && s.country !== country?.code && (
                  <button
                    onClick={() =>
                      onCountry(
                        countryCatalog.find((c) => c.code === s.country),
                      )
                    }
                  >
                    Focus {s.name} on globe →
                  </button>
                )}
              </article>
            ))}
          </div>
          <p className="mw-caption">{data.comparison_rule}</p>
          <div className="mw-export-actions">
            <a
              href={"/watch-data/money/analysis/report?" + params}
              target="_blank"
              rel="noreferrer"
            >
              Readable analysis / PDF ↗
            </a>
            <a href={"/watch-data/money/analysis.csv?" + params} download>
              Download exact observations CSV ↓
            </a>
            <button onClick={investigate}>Investigate this comparison →</button>
          </div>
          <details>
            <summary>Exact observations & source basis</summary>
            <p>
              Source decimals are preserved. Their precision is not an accuracy
              claim. Spreadsheet applications may round imported numbers.
            </p>
            <div className="mw-table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Scope</th>
                    <th>Year</th>
                    <th>Published / covered USD</th>
                    <th>Basis</th>
                  </tr>
                </thead>
                <tbody>
                  {data.series.flatMap((s) =>
                    s.points.map((p) => (
                      <tr key={s.country + p.year}>
                        <td>{s.name}</td>
                        <td>{p.year}</td>
                        <td>{p.value ?? "No observation"}</td>
                        <td>{p.basis.replaceAll("_", " ")}</td>
                      </tr>
                    )),
                  )}
                </tbody>
              </table>
            </div>
          </details>
          <p className="mw-caption">{data.interpretation}</p>
        </>
      )}
    </section>
  );
}
