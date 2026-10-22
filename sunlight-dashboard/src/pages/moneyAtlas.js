import { countryCatalog } from "./watchOverview.js";
const countries = new Map(countryCatalog.map((c) => [c.code, c]));
export const measureKinds = {
  annual_flow: "Annual flow",
  net_flow: "Net flow · signed",
  stock: "Stock · point in time",
  economic_context: "Economic context",
};
export function monetaryRows(layer, country = null) {
  return (layer?.rows || [])
    .filter(
      (r) =>
        countries.has(r.country) && (!country || r.country === country.code),
    )
    .map((r) => ({ ...r, countryInfo: countries.get(r.country) }))
    .sort(
      (a, b) =>
        Math.abs(Number(b.value)) - Math.abs(Number(a.value)) ||
        a.country.localeCompare(b.country),
    );
}
export function aidLinks(snapshot, country = null) {
  return (snapshot?.aid?.rows || []).flatMap((r) => {
    const a = countries.get(r.from),
      b = countries.get(r.to),
      v = Number(r.usd);
    if (
      !a ||
      !b ||
      !Number.isFinite(v) ||
      v <= 0 ||
      (country && ![a.code, b.code].includes(country.code))
    )
      return [];
    return [
      {
        kind: "aid",
        from: a.center,
        to: b.center,
        reporter: a,
        partner: b,
        usd: v,
        exactUSD: r.usd,
        period: String(r.year),
        indicator: r.indicator,
        sourceURL: r.source_url,
        mirrorURL: r.mirror_url,
        label: `${a.name} → ${b.name} · net bilateral aid`,
      },
    ];
  });
}
export const compactUSD = (value) =>
  value === null || value === undefined
    ? "Unavailable"
    : new Intl.NumberFormat("en", {
        style: "currency",
        currency: "USD",
        notation: "compact",
        maximumFractionDigits: 2,
      }).format(Number(value));
export const totalBasis = (layer) =>
  layer?.total_basis === "publisher_world"
    ? "Publisher world aggregate"
    : layer?.total_basis === "covered_economies_sum"
      ? "Covered economies · partial total"
      : "No observation for this year";
