import { useEffect, useMemo, useState } from "react";
import {
  aidLinks,
  compactUSD,
  measureKinds,
  monetaryRows,
  totalBasis,
} from "./moneyAtlas";
import { money, safeURL } from "./watchOverview";

export default function MonetaryAtlas({
  snapshot,
  error,
  year,
  onYear,
  selected,
  onSelected,
  country,
  onCountry,
  onTrace,
  onInvestigate,
}) {
  const [query, setQuery] = useState(""),
    [countryQuery, setCountryQuery] = useState(""),
    [page, setPage] = useState(0),
    [kind, setKind] = useState("");
  const layer = snapshot?.layers?.find((l) => l.id === selected),
    aid = selected === "aid";
  const rows = useMemo(
    () =>
      monetaryRows(layer, country).filter((r) =>
        `${r.countryInfo.name} ${r.country}`
          .toLowerCase()
          .includes(countryQuery.toLowerCase()),
      ),
    [layer, country, countryQuery],
  );
  const routes = useMemo(
    () =>
      aidLinks(snapshot, country).filter((r) =>
        `${r.label} ${r.reporter.code} ${r.partner.code}`
          .toLowerCase()
          .includes(countryQuery.toLowerCase()),
      ),
    [snapshot, country, countryQuery],
  );
  useEffect(() => setPage(0), [selected, country, countryQuery, year]);
  const layers = (snapshot?.layers || []).filter(
    (l) =>
      (!kind || l.kind === kind) &&
      `${l.label} ${l.indicator}`.toLowerCase().includes(query.toLowerCase()),
  );
  function choose(id) {
    onSelected(id);
    requestAnimationFrame(() =>
      document.querySelector(".ev-money-selected")?.scrollIntoView({
        block: "start",
        behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
          ? "auto"
          : "smooth",
      }),
    );
  }
  function investigate() {
    onInvestigate?.({
      question: `Investigate ${layer?.label || "bilateral development assistance"} ${country?.name || "worldwide"} in ${layer?.year || snapshot.aid.year}. Identify reporting coverage, attribution, overlap and the evidence required to verify recipient arrival.`,
      country_codes: country ? [country.code] : [],
      year: layer?.year || snapshot.aid.year,
      sources: ["monetary"],
    });
  }
  return (
    <section className="ev-money-desk" aria-label="Monetary atlas">
      <header>
        <p className="ev-eyebrow">MONEY / SOURCE / DESTINATION / EVIDENCE</p>
        <h1>Monetary atlas</h1>
        <p>
          Global figures and country evidence, with each measure kept on its own
          accounting basis.
        </p>
      </header>
      {error ? (
        <p role="alert">
          Monetary source unavailable. Existing watch layers remain available.
        </p>
      ) : !snapshot ? (
        <p role="status">Loading source-dated monetary observations…</p>
      ) : (
        <>
          <div className="ev-money-filters">
            <label>
              Source period
              <select
                aria-label="Monetary source period"
                value={year}
                onChange={(e) => onYear(e.target.value)}
              >
                <option value="">Default source periods</option>
                {snapshot.years.map((y) => (
                  <option key={y} value={y}>
                    {y}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Measure basis
              <select value={kind} onChange={(e) => setKind(e.target.value)}>
                <option value="">All accounting bases</option>
                {Object.entries(measureKinds).map(([v, n]) => (
                  <option key={v} value={v}>
                    {n}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Find a monetary domain
              <input
                type="search"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Remittances, services, debt, investment…"
              />
            </label>
          </div>
          <p className="ev-money-rule">{snapshot.total_rule}</p>
          {query && layers.length === 0 && (
            <p>
              No connected measure matches this search.{" "}
              <button
                onClick={() => {
                  const inventory = document.querySelector(".ev-money-missing");
                  inventory.open = true;
                  inventory.scrollIntoView({ block: "start" });
                }}
              >
                Check the missing-domain inventory →
              </button>
            </p>
          )}
          {country && (
            <section
              className="ev-money-country-overview"
              aria-label="Country monetary profile"
            >
              <h2>{country.name} · monetary profile</h2>
              <p>
                Country observations follow the selected source period. Missing
                is unknown. The global figures below retain their own world or
                covered basis.
              </p>
              {snapshot.layers.map((l) => {
                const observation = l.rows.find(
                  (r) => r.country === country.code,
                );
                return (
                  <button key={l.id} onClick={() => choose(l.id)}>
                    <span>
                      {l.label}
                      <small>
                        {l.year} · {measureKinds[l.kind]}
                      </small>
                    </span>
                    <strong>{compactUSD(observation?.value)}</strong>
                  </button>
                );
              })}
              <button onClick={() => onCountry(null)}>
                Return to all countries →
              </button>
            </section>
          )}
          <div
            className="ev-money-totals"
            aria-label="Global monetary measures"
          >
            {layers.map((l) => (
              <button
                key={l.id}
                aria-pressed={selected === l.id}
                onClick={() => choose(l.id)}
              >
                <span>{l.label}</span>
                <strong>{compactUSD(l.total)}</strong>
                <small>
                  {l.year} · {measureKinds[l.kind]}
                  <br />
                  {totalBasis(l)} · {l.country_count} economies
                </small>
              </button>
            ))}
            {(!kind || kind === "net_flow") &&
              (!query ||
                "bilateral development assistance net".includes(
                  query.toLowerCase(),
                )) && (
                <button aria-pressed={aid} onClick={() => choose("aid")}>
                  <span>Bilateral development assistance · net</span>
                  <strong>{compactUSD(snapshot.aid.total)}</strong>
                  <small>
                    {snapshot.aid.year} · covered pairs only
                    <br />
                    {snapshot.aid.donors} donors → {snapshot.aid.recipients}{" "}
                    recipients · overlaps ODA
                  </small>
                </button>
              )}
          </div>
          {(layer || aid) && (
            <section
              className="ev-money-selected"
              aria-label="Selected monetary measure"
            >
              <p className="ev-eyebrow">
                {aid
                  ? "DONOR → RECIPIENT / NET DISBURSEMENTS"
                  : measureKinds[layer.kind]}
              </p>
              <h2>{layer?.label || "Bilateral development assistance"}</h2>
              <strong className="ev-money-value">
                {compactUSD(aid ? snapshot.aid.total : layer.total)}
              </strong>
              <p>
                {aid
                  ? `${snapshot.aid.year} · covered bilateral total`
                  : `${layer.year} · ${totalBasis(layer)}`}
                . USD figures are displayed rounded; published source values are
                retained.
              </p>
              {layer && (
                <>
                  <p>{layer.definition}</p>
                  <p>
                    Map: country reference circles; logarithmic size by absolute
                    value. Outline circles mark negative net observations. Gray
                    reference points indicate no selected observation. No
                    sending/receiving counterpart is inferred.
                  </p>
                  <p>
                    Original compiler: {layer.source}. Licence: {layer.license}.
                  </p>
                  <a
                    href={safeURL(layer.source_url)}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Publisher indicator {layer.indicator} ↗
                  </a>
                  <br />
                  <a
                    href={safeURL(layer.mirror_url)}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Pinned data extract ↗
                  </a>
                </>
              )}
              {aid && (
                <p>
                  {snapshot.aid.basis} Positive net pairs are directed from
                  donor to recipient; negative net entries remain in the source
                  table below, with no reverse-payment claim. These are
                  statistical disbursement reports, not independently verified
                  bank credits.
                </p>
              )}
              {country && (
                <p>
                  Country scope: {country.name}. The figure above retains its
                  global/covered basis; rows below follow your country
                  selection.{" "}
                  <button onClick={() => onCountry(null)}>All countries</button>
                </p>
              )}
              <button onClick={investigate}>Investigate this measure →</button>
              <label>
                Find a country or connection
                <input
                  type="search"
                  value={countryQuery}
                  onChange={(e) => setCountryQuery(e.target.value)}
                  placeholder="Country name or ISO code"
                />
              </label>
              {!aid && (
                <>
                  <p>
                    {rows.length} matching country observations · no mixed-year
                    substitution.
                  </p>
                  <div className="ev-money-country-list">
                    {rows.slice(page * 30, (page + 1) * 30).map((r) => (
                      <button
                        key={r.country}
                        onClick={() => onCountry(r.countryInfo)}
                      >
                        <span>
                          {r.countryInfo.name}
                          <small>
                            {r.year} · {r.country}
                          </small>
                        </span>
                        <strong>{money(Number(r.value), "USD")}</strong>
                      </button>
                    ))}
                  </div>
                  {!rows.length && (
                    <p>
                      No retained country observation for this measure and year.
                      This does not mean zero.
                    </p>
                  )}
                </>
              )}
              {aid && (
                <>
                  <p>
                    {routes.length} positive matching relationships. Click a
                    pair to trace its direction and source on the globe.
                  </p>
                  {routes.slice(page * 30, (page + 1) * 30).map((r) => (
                    <button
                      className="ev-money-pair"
                      key={r.label}
                      onClick={() => onTrace(r)}
                    >
                      <span>
                        {r.reporter.name} → {r.partner.name}
                      </span>
                      <strong>
                        {money(r.usd, "USD")} · {r.period} ↗
                      </strong>
                    </button>
                  ))}
                  <details>
                    <summary>
                      Zero and negative net entries · source evidence
                    </summary>
                    {snapshot.aid.rows
                      .filter(
                        (r) =>
                          Number(r.usd) <= 0 &&
                          (!country || [r.from, r.to].includes(country.code)),
                      )
                      .map((r) => (
                        <p key={`${r.from}-${r.to}`}>
                          <a
                            href={safeURL(r.mirror_url)}
                            target="_blank"
                            rel="noreferrer"
                          >
                            {r.from} → {r.to}
                          </a>{" "}
                          · {r.year} · {money(Number(r.usd), "USD")}
                        </p>
                      ))}
                  </details>
                </>
              )}
              <div className="ev-money-pagination">
                <button disabled={!page} onClick={() => setPage((p) => p - 1)}>
                  Previous
                </button>
                <span>Page {page + 1}</span>
                <button
                  disabled={(page + 1) * 30 >= (aid ? routes : rows).length}
                  onClick={() => setPage((p) => p + 1)}
                >
                  Next
                </button>
              </div>
            </section>
          )}
          <details className="ev-money-missing">
            <summary>
              {snapshot.unconnected.length} domains still require source
              integrations
            </summary>
            <p>
              These sources are researched integration targets. No amount or
              corridor is invented for an unconnected domain.
            </p>
            {snapshot.unconnected.map((m) => (
              <article key={m.label}>
                <h3>{m.label}</h3>
                <a href={safeURL(m.url)} target="_blank" rel="noreferrer">
                  {m.publisher} ↗
                </a>
                <p>{m.requirement}</p>
              </article>
            ))}
          </details>
          <details>
            <summary>Provenance and accounting limits</summary>
            <p>{snapshot.provenance}</p>
            <p>{snapshot.default_period_rule}</p>
            <p>
              Mirror updated {snapshot.mirror_updated_at}; retrieved{" "}
              {snapshot.retrieved_at}; revision {snapshot.source_revision}.
              Country coverage and reporting years differ. Net flows may be
              negative; no totals across measures are computed. Statistical
              residuals and discrepancies are not theft findings.
            </p>
            <p>
              Current-dollar values and geographic centers do not establish
              transport routes, actual settlement, payer/payee identity or final
              public benefit. Trace an obligation in Delivery assurance to
              compare attributed release, arrival and acceptance evidence.
            </p>
            <a
              href={safeURL(
                snapshot.source_repository +
                  "/tree/" +
                  snapshot.source_revision,
              )}
              target="_blank"
              rel="noreferrer"
            >
              Inspect pinned source repository ↗
            </a>
          </details>
        </>
      )}
    </section>
  );
}
