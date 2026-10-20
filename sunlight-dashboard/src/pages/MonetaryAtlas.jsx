import { useEffect, useMemo, useState } from "react";
import {
  aidLinks,
  compactUSD,
  measureKinds,
  monetaryRows,
  totalBasis,
} from "./moneyAtlas";
import {
  countryCatalog,
  money,
  resolveCountry,
  safeURL,
} from "./watchOverview";
import MonetaryAnalysis from "./MonetaryAnalysis";
import "./MonetaryWorkbench.css";

const views = ["explore", "history", "coverage"];
const years = Array.from({ length: 8 }, (_, i) => 2019 + i);
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
  onRetry,
  reviewOverview,
  onReview,
  onDelivery,
  onConnections,
}) {
  const [query, setQuery] = useState(""),
    [countryQuery, setCountryQuery] = useState(""),
    [focusQuery, setFocusQuery] = useState("");
  const [page, setPage] = useState(0),
    [kind, setKind] = useState(""),
    [order, setOrder] = useState("amount"),
    [role, setRole] = useState("all");
  const [focusError, setFocusError] = useState(""),
    [shareMessage, setShareMessage] = useState(""),
    [shareURL, setShareURL] = useState("");
  const [view, setView] = useState(() => {
    const v = new URLSearchParams(location.search).get("money_view");
    return views.includes(v) ? v : "explore";
  });
  const layer = snapshot?.layers?.find((l) => l.id === selected),
    aid = selected === "aid";
  const effectiveYear = aid ? snapshot?.aid?.year : layer?.year;
  const rows = useMemo(
    () =>
      monetaryRows(layer, country)
        .filter((r) =>
          `${r.countryInfo.name} ${r.country}`
            .toLowerCase()
            .includes(countryQuery.toLowerCase()),
        )
        .sort((a, b) =>
          order === "name"
            ? a.countryInfo.name.localeCompare(b.countryInfo.name)
            : order === "lowest"
              ? Number(a.value) - Number(b.value)
              : Math.abs(Number(b.value)) - Math.abs(Number(a.value)),
        ),
    [layer, country, countryQuery, order],
  );
  const routes = useMemo(
    () =>
      aidLinks(snapshot, country).filter(
        (r) =>
          (!country ||
            role === "all" ||
            r[role === "inward" ? "partner" : "reporter"].code ===
              country.code) &&
          `${r.label} ${r.reporter.code} ${r.partner.code}`
            .toLowerCase()
            .includes(countryQuery.toLowerCase()),
      ),
    [snapshot, country, countryQuery, role],
  );
  const layers = (snapshot?.layers || []).filter(
    (l) =>
      (!kind || l.kind === kind) &&
      `${l.label} ${l.indicator}`.toLowerCase().includes(query.toLowerCase()),
  );
  const countryValue =
    country && layer?.rows.find((r) => r.country === country.code)?.value;
  const reportParams = new URLSearchParams({
    measure: selected,
    countries: country?.code || "",
    year: String(effectiveYear || 2025),
  });
  useEffect(
    () => setPage(0),
    [selected, country?.code, countryQuery, year, order, role],
  );
  useEffect(() => {
    setFocusQuery(country?.name || "");
    setFocusError("");
  }, [country?.code]);
  useEffect(() => {
    const url = new URL(location.href);
    url.searchParams.set("money_view", view);
    history.replaceState(null, "", url);
  }, [view]);
  function choose(id) {
    onSelected(id);
    setView("explore");
    requestAnimationFrame(() =>
      document.querySelector(".ev-money-selected")?.scrollIntoView({
        block: "start",
        behavior: matchMedia("(prefers-reduced-motion: reduce)").matches
          ? "auto"
          : "smooth",
      }),
    );
  }
  function investigate() {
    onInvestigate?.({
      question: `Investigate ${layer?.label || "bilateral development assistance"} ${country?.name || "worldwide"} in ${effectiveYear}. Identify source coverage, counterpart evidence and the records needed to compare released funds with recipient arrival and accepted delivery. Distinguish statistical totals from individually reconciled transfers.`,
      country_codes: country ? [country.code] : [],
      year: effectiveYear,
      sources: ["monetary", "operations", "delivery_assurance"],
    });
  }
  async function share() {
    const current = new URL(location.href),
      url = new URL(import.meta.env.BASE_URL, location.origin);
    for (const key of [
      "country",
      "money_measure",
      "money_year",
      "money_view",
      "compare",
      "compare_from",
      "aid_direction",
    ])
      if (current.searchParams.has(key))
        url.searchParams.set(key, current.searchParams.get(key));
    url.hash = "money";
    url.searchParams.set("money_revision", snapshot.source_revision);
    if (effectiveYear)
      url.searchParams.set("money_year", String(effectiveYear));
    setShareURL(url.href);
    try {
      await navigator.clipboard.writeText(url.href);
      setShareMessage(
        "Workspace link copied. It preserves the selected view and source period.",
      );
    } catch {
      setShareMessage(
        "Copy the workspace link below. It preserves the selected view and source period.",
      );
    }
  }
  return (
    <section className="ev-money-desk" aria-label="Monetary atlas">
      <header>
        <p className="ev-eyebrow">GLOBAL MONEY / COUNTRY / PERIOD / EVIDENCE</p>
        <h1>Monetary atlas</h1>
        <p>
          {view === "history"
            ? "Compare one measure and its reporting coverage across years."
            : view === "coverage"
              ? "Inspect connected publishers, definitions and missing integrations."
              : "Explore a monetary measure, then verify the evidence behind a specific transfer."}
        </p>
      </header>
      {error ? (
        <p role="alert">
          Monetary source unavailable.{" "}
          <button onClick={onRetry}>Retry monetary source</button>
        </p>
      ) : !snapshot ? (
        <p role="status">Loading source-dated monetary observations…</p>
      ) : (
        <>
          <div
            className="mw-tabs"
            role="group"
            aria-label="Monetary work views"
          >
            {[
              ["explore", "Explore"],
              ["history", "Compare & history"],
              ["coverage", "Coverage & sources"],
            ].map(([id, label]) => (
              <button
                key={id}
                aria-pressed={view === id}
                onClick={() => setView(id)}
              >
                {label}
              </button>
            ))}
          </div>
          <div className="ev-money-filters">
            <label>
              Map measure
              <select
                aria-label="Monetary map measure"
                value={selected}
                onChange={(e) => choose(e.target.value)}
              >
                <option value="">Choose a measure</option>
                {snapshot.layers.map((l) => (
                  <option key={l.id} value={l.id}>
                    {l.label}
                  </option>
                ))}
                <option value="aid">
                  Bilateral development assistance · net
                </option>
              </select>
            </label>
            <label>
              Source period
              <select
                aria-label="Monetary source period"
                value={year}
                onChange={(e) => onYear(e.target.value)}
              >
                <option value="">Default source periods</option>
                {years.map((y) => (
                  <option key={y}>{y}</option>
                ))}
              </select>
            </label>
          </div>
          {new URLSearchParams(location.search).get("money_revision") &&
            new URLSearchParams(location.search).get("money_revision") !==
              snapshot.source_revision && (
              <p role="status" className="ev-money-rule">
                This shared view refers to a different source revision. The
                figures shown use this deployment’s current extract (
                {snapshot.source_revision.slice(0, 12)}). The readable brief
                records the source actually used.
              </p>
            )}
          {view === "explore" && (
            <form
              className="mw-country-focus"
              onSubmit={(e) => {
                e.preventDefault();
                const c = resolveCountry(focusQuery);
                if (c) onCountry(c);
                else
                  setFocusError(
                    "Select a recognized country name or ISO code.",
                  );
              }}
            >
              <label>
                Focus a country
                <input
                  aria-label="Monetary country focus"
                  type="search"
                  value={focusQuery}
                  onChange={(e) => {
                    setFocusQuery(e.target.value);
                    setFocusError("");
                  }}
                  list="money-country-options"
                  placeholder="Country name or ISO code"
                />
                <datalist id="money-country-options">
                  {countryCatalog.map((c) => (
                    <option key={c.code} value={c.name}>
                      {c.code}
                    </option>
                  ))}
                </datalist>
              </label>
              <button>Focus on globe →</button>
            </form>
          )}
          {view === "explore" && focusError && <p role="alert">{focusError}</p>}
          {view === "explore" && country && (
            <button onClick={() => onCountry(null)}>
              Return to all countries →
            </button>
          )}
          {view === "explore" && (layer || aid) && (
            <section
              className="ev-money-selected"
              aria-label="Selected monetary measure"
            >
              <div className="mw-focus">
                <p className="ev-eyebrow">
                  {aid
                    ? "DONOR → RECIPIENT / NET DISBURSEMENTS"
                    : measureKinds[layer.kind]}
                </p>
                <h2>{layer?.label || "Bilateral development assistance"}</h2>
                <strong className="ev-money-value">
                  {compactUSD(aid ? snapshot.aid.total : layer.total)}
                </strong>
                <div className="mw-focus-meta">
                  <span>{effectiveYear}</span>
                  <span>
                    {aid ? "Covered bilateral total" : totalBasis(layer)}
                  </span>
                  {layer?.aggregation_method && (
                    <span>Publisher method: {layer.aggregation_method}</span>
                  )}
                  <span>
                    {aid
                      ? `${snapshot.aid.donors} donors → ${snapshot.aid.recipients} recipients`
                      : `${layer.country_count} / ${countryCatalog.length} catalogue economies observed`}
                  </span>
                </div>
                <p className="mw-caption">
                  Global / covered figure. Country selection does not change its
                  accounting perimeter.
                </p>
                {country && !aid && (
                  <div className="mw-country-value">
                    <span>
                      {country.name} · {effectiveYear}
                    </span>
                    <strong>{compactUSD(countryValue)}</strong>
                    <p className="mw-caption">
                      {countryValue === undefined
                        ? "No retained observation. This does not mean zero."
                        : "Selected country observation; no sending or receiving counterpart is inferred."}
                    </p>
                  </div>
                )}
                <div className="mw-focus-actions">
                  <button onClick={() => setView("history")}>
                    Compare countries & history →
                  </button>
                  <button onClick={investigate}>
                    Investigate this measure →
                  </button>
                  <button onClick={onConnections}>
                    Explore source-dated corridors →
                  </button>
                </div>
                <div className="mw-export-actions">
                  <a
                    href={"/watch-data/money/analysis/report?" + reportParams}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Readable measure brief / PDF ↗
                  </a>
                  <a
                    href={"/watch-data/money/analysis.csv?" + reportParams}
                    download
                  >
                    Exact observations CSV ↓
                  </a>
                </div>
              </div>
              <section
                className="mw-evidence-bridge"
                aria-label="From monetary context to recipient evidence"
              >
                <h3>What reached the recipient?</h3>
                <p>
                  Statistical totals do not verify recipient credits. Match an
                  identified transfer to its debit, credit, acceptance and
                  public benefit evidence.
                </p>
                {reviewOverview ? (
                  <p>
                    <strong>
                      {reviewOverview.registered.delivery} delivery obligations
                      · {reviewOverview.registered.operations} source cases
                    </strong>
                    <br />
                    {country?.name || "Deployment-wide"} registered evidence ·
                    all record periods. These records are not automatically
                    linked to the selected statistical measure.
                  </p>
                ) : (
                  <p>
                    Registered evidence status is unavailable. Open the review
                    desk to check its current scope.
                  </p>
                )}
                <button onClick={onReview}>
                  Review {reviewOverview?.total ?? "registered"} evidence
                  records →
                </button>
                <button onClick={onDelivery}>
                  Open arrival & delivery checks →
                </button>
              </section>
              <h2>{aid ? "Source → destination" : "Country observations"}</h2>
              {aid && (
                <p>
                  {snapshot.aid.basis} Positive net pairs can be traced on the
                  globe. Negative and zero source entries remain inspectable
                  below.
                </p>
              )}
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
                <label>
                  Order observations
                  <select
                    aria-label="Monetary observation order"
                    value={order}
                    onChange={(e) => setOrder(e.target.value)}
                  >
                    <option value="amount">Largest absolute amounts</option>
                    <option value="lowest">Smallest signed amounts</option>
                    <option value="name">Country name</option>
                  </select>
                </label>
              )}
              {aid && country && (
                <label>
                  Country role
                  <select
                    aria-label="Aid route role"
                    value={role}
                    onChange={(e) => setRole(e.target.value)}
                  >
                    <option value="all">All available relationships</option>
                    <option value="inward">Reported to this recipient</option>
                    <option value="outward">Reported by this donor</option>
                  </select>
                </label>
              )}
              {!aid ? (
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
                        <strong title={r.value}>
                          {money(Number(r.value), "USD")}
                        </strong>
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
              ) : (
                <>
                  <p>
                    {routes.length} positive matching relationships. Trace a
                    pair to inspect its direction and source.
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
                          (!country ||
                            country.code ===
                              r[
                                role === "inward"
                                  ? "to"
                                  : role === "outward"
                                    ? "from"
                                    : country.code === r.from
                                      ? "from"
                                      : "to"
                              ]),
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
              {country && (
                <details>
                  <summary>{country.name} · all monetary measures</summary>
                  <section
                    className="ev-money-country-overview"
                    aria-label="Country monetary profile"
                  >
                    <h2>{country.name} · monetary profile</h2>
                    <p>
                      Each observation retains its selected source period.
                      Missing is unknown.
                    </p>
                    {snapshot.layers.map((l) => (
                      <button key={l.id} onClick={() => choose(l.id)}>
                        <span>
                          {l.label}
                          <small>
                            {l.year} · {measureKinds[l.kind]}
                          </small>
                        </span>
                        <strong>
                          {compactUSD(
                            l.rows.find((r) => r.country === country.code)
                              ?.value,
                          )}
                        </strong>
                      </button>
                    ))}
                    <button onClick={() => onCountry(null)}>
                      Return to all countries →
                    </button>
                  </section>
                </details>
              )}
              <details>
                <summary>Selected definition & source evidence</summary>
                {layer ? (
                  <>
                    <p>{layer.definition}</p>
                    <p>
                      Original compiler: {layer.source}. Licence:{" "}
                      {layer.license}.
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
                    <p>
                      Map circles are country reference observations, sized
                      logarithmically. Outline circles mark negative values;
                      gray marks show missing observations. No bilateral
                      counterpart is inferred.
                    </p>
                  </>
                ) : (
                  <p>
                    {snapshot.aid.basis} Statistical disbursement reports do not
                    independently authenticate recipient bank credits.
                  </p>
                )}
              </details>
            </section>
          )}
          {view === "history" && (layer || aid) && (
            <MonetaryAnalysis
              measure={selected}
              selectedYear={effectiveYear}
              country={country}
              onCountry={onCountry}
              onYear={onYear}
              onExplore={() => setView("explore")}
              onInvestigate={onInvestigate}
            />
          )}
          {view === "explore" && (
            <details
              className="mw-catalog"
              open={Boolean(query || kind || (!layer && !aid))}
            >
              <summary>
                Browse all {snapshot.layers.length + 1} monetary measures
              </summary>
              <div className="ev-money-filters">
                <label>
                  Measure basis
                  <select
                    value={kind}
                    onChange={(e) => setKind(e.target.value)}
                  >
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
              {query && !layers.length && (
                <p>
                  No connected measure matches. Open Coverage & sources to check
                  missing integrations.
                </p>
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
            </details>
          )}
          {view === "coverage" && (
            <section aria-label="Monetary coverage and sources">
              <h2>What is connected?</h2>
              <p>
                {snapshot.layers.length} monetary measures and one bilateral aid
                layer from a pinned statistical extract. This is source-dated
                public context, not a live global payments ledger.
              </p>
              <div className="mw-table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Measure</th>
                      <th>Year</th>
                      <th>Observed economies</th>
                      <th>World basis</th>
                    </tr>
                  </thead>
                  <tbody>
                    {snapshot.layers.map((l) => (
                      <tr key={l.id}>
                        <td>
                          <button onClick={() => choose(l.id)}>
                            {l.label}
                          </button>
                        </td>
                        <td>{l.year}</td>
                        <td>
                          {l.country_count} / {countryCatalog.length}
                        </td>
                        <td>{totalBasis(l)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <h2>What still needs a source?</h2>
              <section className="ev-money-missing">
                <p>
                  These are researched integration targets. No amount or
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
              </section>
            </section>
          )}
          <p className="ev-money-rule">{snapshot.total_rule}</p>
          <div className="mw-share">
            <button onClick={share}>Copy workspace link</button>
            {shareMessage && (
              <>
                <p role="status">{shareMessage}</p>
                <input
                  aria-label="Shareable monetary workspace link"
                  readOnly
                  value={shareURL}
                  onFocus={(e) => e.target.select()}
                />
              </>
            )}
          </div>
          <details>
            <summary>Provenance and accounting limits</summary>
            <p>{snapshot.provenance}</p>
            <p>{snapshot.default_period_rule}</p>
            <p>
              Mirror updated {snapshot.mirror_updated_at}; retrieved{" "}
              {snapshot.retrieved_at}; revision {snapshot.source_revision}.
              Country coverage and reporting years differ. Current-dollar
              amounts are not inflation-adjusted.
            </p>
            <p>
              Geographic centers and animations do not establish transport
              paths, settlement, payer/payee identity or public benefit. No
              totals across measures or global theft figure are computed.
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
