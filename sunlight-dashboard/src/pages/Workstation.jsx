import { useState, useEffect, useCallback, useRef, useMemo } from "react";

/* ════════════════════════════════════════════════════════════════════════
   S U N L I G H T — Procurement Integrity Intelligence
   Institutional Workstation v1
   
   5 surfaces: Risk Inbox · Case Packet · Portfolio · Admin · Onboarding
   Designed for: World Bank INT, IMF Fiscal Affairs, SAIs, audit offices
   ════════════════════════════════════════════════════════════════════════ */

// ── Design Tokens ─────────────────────────────────────────────────────
const T = {
  bg: "#FAF9F7", card: "#FFFFFF", sidebar: "#F5F3F0", sidebarHover: "#EDEAE5",
  ink: "#1A1C20", body: "#3D404A", muted: "#6E7180", caption: "#9CA0AD",
  ghost: "#C5C8D0", line: "#E8E5E0", header: "#1B1D21",
  red: "#C23B3B", redSoft: "#FEF2F2", redBdr: "#FECACA",
  amber: "#B8860B", amberSoft: "#FFFBEB", amberBdr: "#FDE68A",
  green: "#1A7A42", greenSoft: "#F0FDF4", greenBdr: "#BBF7D0",
  blue: "#2563EB", blueSoft: "#EFF6FF", blueBdr: "#BFDBFE",
  gold: "#8B7335", goldSoft: "#F7F4EC",
  purple: "#7C3AED", purpleSoft: "#F5F3FF",
};
const F = {
  serif: "'Merriweather', Georgia, serif",
  sans: "'Source Sans 3', -apple-system, sans-serif",
  mono: "'JetBrains Mono', 'SF Mono', monospace",
};
const fmtUSD = (n) => n >= 1e9 ? `$${(n/1e9).toFixed(1)}B` : n >= 1e6 ? `$${(n/1e6).toFixed(1)}M` : n >= 1e3 ? `$${Math.round(n/1e3).toLocaleString()}K` : `$${n.toLocaleString()}`;
const fmtDate = (d) => d ? new Date(d).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }) : "—";
const fmtAge = (d) => { const h = Math.floor((Date.now() - new Date(d).getTime()) / 3600000); return h < 24 ? `${h}h` : `${Math.floor(h/24)}d`; };

// ── Fixture Data Generator ────────────────────────────────────────────
const VENDORS = ["Zenith Infrastructure Ltd","Apex Federal Supply Co","GlobalTech Procurement GmbH","Meridian Construction SA","Sahel Logistics Group","Volta Medical Supplies","Delta Security Corp","NorthStar IT Solutions","Pacific Road Holdings","Crescent Building Materials","Atlas Engineering Partners","Oasis Water Systems","Savanna Transport Co","Horizon Digital Solutions","Unity Pharma International","Liptako Mining Services","Koudougou General Trading","Bobo-Dioulasso Builders","Tamale Health Supplies","Abidjan Digital Corp"];
const AGENCIES = ["Ministry of Health","Ministry of Education","Ministry of Infrastructure","National Water Authority","Federal Roads Commission","Defense Procurement Office","Ministry of Agriculture","Ministry of Energy"];
const REGIONS = ["Centre","Sahel","Hauts-Bassins","Centre-Est","Boucle du Mouhoun","Nord","Est","Cascades"];
const CATEGORIES = ["road_construction","bridge_construction","pharmaceuticals","medical_supplies","medical_equipment","it_equipment","furniture","printing","protective_equipment","provisions","fuel","construction","energy","water_treatment","office_supplies","vehicles","drainage","it_infrastructure"];
const TYPOLOGY_NAMES = ["Price Anomaly","Vendor Concentration","Timing Anomaly","Split Contract"];
const DISPOSITIONS = [
  { key: "confirm", label: "True Concern", num: 1, color: T.red },
  { key: "benign", label: "Benign — Explainable", num: 2, color: T.green },
  { key: "info", label: "Needs More Information", num: 3, color: T.blue },
  { key: "dup", label: "Duplicate", num: 4, color: T.caption },
  { key: "refer", label: "Refer to Partner", num: 5, color: T.purple },
];

function generateFixtureData(count = 500) {
  const contracts = [];
  const leads = [];
  const now = Date.now();

  for (let i = 0; i < count; i++) {
    const vendor = VENDORS[i % VENDORS.length];
    const agency = AGENCIES[i % AGENCIES.length];
    const region = REGIONS[i % REGIONS.length];
    const category = CATEGORIES[i % CATEGORIES.length];
    const month = 1 + (i % 12);
    const day = 1 + (i % 28);
    const basePrice = 20 + Math.random() * 5000;
    let multiplier = 0.85 + Math.random() * 0.4;
    let inflated = false;
    if (Math.random() < 0.14) { multiplier = 1.7 + Math.random() * 2.8; inflated = true; }
    const unitPrice = +(basePrice * multiplier).toFixed(2);
    const quantity = 10 + Math.floor(Math.random() * 500);
    const amount = Math.round(unitPrice * quantity);
    const peerMedian = +(basePrice * (0.9 + Math.random() * 0.2)).toFixed(2);
    const ratio = +(unitPrice / peerMedian).toFixed(2);
    const ciUpper = +(peerMedian * (1.3 + Math.random() * 0.3)).toFixed(2);
    const outsideCI = unitPrice > ciUpper;
    const posterior = outsideCI ? +(0.5 + Math.random() * 0.45).toFixed(4) : +(0.02 + Math.random() * 0.15).toFixed(4);
    const fdrQ = outsideCI ? +(0.001 + Math.random() * 0.04).toFixed(4) : +(0.1 + Math.random() * 0.7).toFixed(4);

    const c = {
      id: `CTR-2024-${String(i+1).padStart(5,"0")}`,
      vendor, agency, region, category, amount, unitPrice, quantity, peerMedian, ratio,
      date: `2024-${String(month).padStart(2,"0")}-${String(day).padStart(2,"0")}`,
      description: `${category.replace(/_/g," ")} — ${region} region`,
    };
    contracts.push(c);

    // Build typologies
    const typs = [];
    if (outsideCI && fdrQ < 0.05) typs.push({ name: "Price Anomaly", trigger: `Unit price ${ratio}× peer median`, method: "Bootstrap CI + Bayesian Posterior" });
    const vendorShare = contracts.filter(x => x.vendor === vendor && x.agency === agency).length / Math.max(1, contracts.filter(x => x.agency === agency).length);
    if (vendorShare > 0.28) typs.push({ name: "Vendor Concentration", trigger: `${(vendorShare*100).toFixed(0)}% share at ${agency}`, method: "Vendor Share Analysis" });
    const fyEnd = [3,6,9,12].includes(month) && day > 22;
    if (fyEnd) typs.push({ name: "Timing Anomaly", trigger: `Awarded final week of Q${Math.ceil(month/3)}`, method: "Temporal Clustering" });

    if (typs.length > 0) {
      const tier = (typs.length >= 2 || (typs.length >= 1 && posterior > 0.7)) ? "RED" : "YELLOW";
      const conf = Math.min(99, Math.max(tier === "RED" ? 70 : 35, Math.round(posterior * 100)));
      leads.push({
        id: `LEAD-${String(leads.length+1).padStart(5,"0")}`,
        contract: c, tier, confidence: conf, typologies: typs,
        evidence: { unitPrice, peerMedian, priceRatio: ratio, ciUpper, posteriorP: posterior, fdrQ, peerCount: 8 + Math.floor(Math.random()*20), percentile: Math.min(99, Math.round(50 + (ratio-1)*25)) },
        provenance: { rulepack: "v2.0.0-rc3", snapshot: `snap_2024${String(month).padStart(2,"0")}${String(day).padStart(2,"0")}`, job: `job_${1000+leads.length}`, tenant: "demo_tenant" },
        createdAt: new Date(now - Math.random() * 7 * 86400000).toISOString(),
        disposition: null, dispositionBy: null, dispositionAt: null, dispositionNote: "",
      });
    }
  }
  leads.sort((a,b) => {
    if (a.tier !== b.tier) return a.tier === "RED" ? -1 : 1;
    return b.confidence - a.confidence;
  });
  return { contracts, leads };
}

// ── Shared Components ─────────────────────────────────────────────────
function TierBadge({ tier, size = "sm" }) {
  const r = tier === "RED";
  const s = size === "sm";
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: s ? 4 : 6, padding: s ? "2px 8px" : "4px 12px", borderRadius: 4, fontSize: s ? 10 : 11, fontWeight: 700, fontFamily: F.sans, letterSpacing: "0.04em", background: r ? T.redSoft : T.amberSoft, color: r ? T.red : T.amber, border: `1px solid ${r ? T.redBdr : T.amberBdr}` }}>
      <span style={{ width: s ? 5 : 6, height: s ? 5 : 6, borderRadius: "50%", background: r ? T.red : T.amber }} />
      {tier}
    </span>
  );
}
function Pill({ children, color = T.muted, bg = T.sidebar }) {
  return <span style={{ display: "inline-block", fontSize: 10, fontWeight: 600, fontFamily: F.sans, padding: "2px 7px", borderRadius: 3, background: bg, color, border: `1px solid ${T.line}` }}>{children}</span>;
}
function Kbd({ children }) {
  return <span style={{ display: "inline-flex", alignItems: "center", justifyContent: "center", minWidth: 18, height: 18, padding: "0 4px", borderRadius: 3, fontSize: 10, fontWeight: 600, fontFamily: F.mono, color: T.muted, background: T.bg, border: `1px solid ${T.ghost}`, boxShadow: "0 1px 0 rgba(0,0,0,0.04)" }}>{children}</span>;
}
function Label({ children, style: s }) {
  return <div style={{ fontSize: 10, fontWeight: 700, fontFamily: F.sans, letterSpacing: "0.1em", textTransform: "uppercase", color: T.caption, marginBottom: 8, ...s }}>{children}</div>;
}
function LegalBanner({ compact }) {
  if (compact) return <div style={{ fontSize: 10, fontFamily: F.sans, color: T.caption, fontStyle: "italic" }}>⚖ Risk indicator, not allegation</div>;
  return (
    <div style={{ display: "flex", alignItems: "flex-start", gap: 10, padding: "10px 14px", background: T.blueSoft, border: `1px solid ${T.blueBdr}`, borderRadius: 6, fontSize: 12, fontFamily: F.sans, color: T.body, lineHeight: 1.5 }}>
      <span style={{ fontSize: 14, marginTop: 1 }}>⚖</span>
      <span><strong style={{ color: T.ink }}>Risk indicator, not allegation.</strong> Statistical findings for investigator review. No determination of wrongdoing is made or implied.</span>
    </div>
  );
}
function EmptyState({ icon, title, desc }) {
  return (
    <div style={{ textAlign: "center", padding: "60px 24px", color: T.caption }}>
      <div style={{ fontSize: 36, marginBottom: 12 }}>{icon}</div>
      <div style={{ fontFamily: F.sans, fontSize: 15, fontWeight: 600, color: T.muted, marginBottom: 4 }}>{title}</div>
      <div style={{ fontFamily: F.sans, fontSize: 13, maxWidth: 400, margin: "0 auto" }}>{desc}</div>
    </div>
  );
}
function StatCard({ label, value, sub, color = T.ink }) {
  return (
    <div style={{ padding: "12px 16px", minWidth: 100 }}>
      <div style={{ fontSize: 9, fontWeight: 700, fontFamily: F.sans, letterSpacing: "0.1em", textTransform: "uppercase", color: T.caption, marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 22, fontWeight: 700, fontFamily: F.mono, color }}>{value}</div>
      {sub && <div style={{ fontSize: 10, fontFamily: F.sans, color: T.caption, marginTop: 2 }}>{sub}</div>}
    </div>
  );
}
function OpsStrip({ leads, contracts }) {
  const reds = leads.filter(l => l.tier === "RED").length;
  const yellows = leads.filter(l => l.tier === "YELLOW").length;
  const disposed = leads.filter(l => l.disposition).length;
  const backlog = leads.length - disposed;
  const flagsPer1K = contracts.length > 0 ? ((leads.length / contracts.length) * 1000).toFixed(0) : "—";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 20, padding: "8px 24px", background: T.card, borderBottom: `1px solid ${T.line}`, fontSize: 11, fontFamily: F.sans, flexWrap: "wrap" }}>
      <span style={{ fontWeight: 700, color: T.gold, letterSpacing: "0.08em", fontSize: 10, textTransform: "uppercase" }}>Operations</span>
      <span style={{ color: T.muted }}>Flags/1K: <strong style={{ color: T.ink, fontFamily: F.mono }}>{flagsPer1K}</strong></span>
      <span style={{ color: T.muted }}>RED: <strong style={{ color: reds > 0 ? T.red : T.ghost, fontFamily: F.mono }}>{reds}</strong></span>
      <span style={{ color: T.muted }}>YELLOW: <strong style={{ color: yellows > 0 ? T.amber : T.ghost, fontFamily: F.mono }}>{yellows}</strong></span>
      <span style={{ color: T.muted }}>Backlog: <strong style={{ color: backlog > 20 ? T.amber : T.ink, fontFamily: F.mono }}>{backlog}</strong></span>
      <span style={{ color: T.muted }}>Disposed: <strong style={{ fontFamily: F.mono, color: T.green }}>{disposed}</strong></span>
      <span style={{ color: T.muted }}>Contracts: <strong style={{ fontFamily: F.mono }}>{contracts.length}</strong></span>
      <div style={{ flex: 1 }} />
      <span style={{ color: T.caption }}>Last job: <span style={{ fontFamily: F.mono, color: T.green }}>✓ completed</span> · 2m ago</span>
    </div>
  );
}

// ═══════════ 1. RISK INBOX ═══════════
function RiskInbox({ leads, setLeads, contracts, onOpenCase }) {
  const [focus, setFocus] = useState(0);
  const [selected, setSelected] = useState(new Set());
  const [filters, setFilters] = useState({ tier: "all", agency: "all", vendor: "", typology: "all", search: "" });
  const [groupBy, setGroupBy] = useState(null);
  const [showFilters, setShowFilters] = useState(false);
  const scrollRef = useRef(null);
  const ROW_H = 42;
  const [scrollTop, setScrollTop] = useState(0);
  const [viewH, setViewH] = useState(600);

  const filtered = useMemo(() => {
    return leads.filter(l => {
      if (filters.tier !== "all" && l.tier !== filters.tier) return false;
      if (filters.agency !== "all" && l.contract.agency !== filters.agency) return false;
      if (filters.vendor && !l.contract.vendor.toLowerCase().includes(filters.vendor.toLowerCase())) return false;
      if (filters.typology !== "all" && !l.typologies.some(t => t.name === filters.typology)) return false;
      if (filters.search && !l.id.toLowerCase().includes(filters.search.toLowerCase()) && !l.contract.vendor.toLowerCase().includes(filters.search.toLowerCase()) && !l.contract.id.toLowerCase().includes(filters.search.toLowerCase())) return false;
      return true;
    });
  }, [leads, filters]);

  const grouped = useMemo(() => {
    if (!groupBy) return null;
    const g = {};
    filtered.forEach(l => {
      const key = groupBy === "vendor" ? l.contract.vendor : l.contract.agency;
      if (!g[key]) g[key] = [];
      g[key].push(l);
    });
    return Object.entries(g).sort((a,b) => b[1].length - a[1].length);
  }, [filtered, groupBy]);

  // Virtual scrolling
  const visibleStart = Math.max(0, Math.floor(scrollTop / ROW_H) - 5);
  const visibleEnd = Math.min(filtered.length, Math.ceil((scrollTop + viewH) / ROW_H) + 5);
  const visibleLeads = grouped ? null : filtered.slice(visibleStart, visibleEnd);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    setViewH(el.clientHeight);
    const h = () => setScrollTop(el.scrollTop);
    el.addEventListener("scroll", h);
    return () => el.removeEventListener("scroll", h);
  }, []);

  // Keyboard
  useEffect(() => {
    const h = (e) => {
      if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA" || e.target.tagName === "SELECT") return;
      if (e.key === "j" || e.key === "ArrowDown") { e.preventDefault(); setFocus(f => Math.min(f + 1, filtered.length - 1)); }
      if (e.key === "k" || e.key === "ArrowUp") { e.preventDefault(); setFocus(f => Math.max(f - 1, 0)); }
      if (e.key === "Enter" && filtered[focus]) { e.preventDefault(); onOpenCase(filtered[focus]); }
      if (e.key === "/" && !e.metaKey) { e.preventDefault(); setShowFilters(true); document.getElementById("inbox-search")?.focus(); }
      if (e.key === "Escape") { setShowFilters(false); setSelected(new Set()); }
      // Disposition shortcuts 1-5
      const num = parseInt(e.key);
      if (num >= 1 && num <= 5 && filtered[focus]) {
        e.preventDefault();
        const d = DISPOSITIONS[num - 1];
        const targets = selected.size > 0 ? [...selected] : [filtered[focus].id];
        setLeads(prev => prev.map(l => targets.includes(l.id) ? { ...l, disposition: d.key, dispositionAt: new Date().toISOString(), dispositionBy: "analyst@demo" } : l));
        setSelected(new Set());
      }
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [focus, filtered, onOpenCase, selected, setLeads]);

  // Scroll focused row into view
  useEffect(() => {
    if (!grouped && scrollRef.current) {
      const rowTop = focus * ROW_H;
      const el = scrollRef.current;
      if (rowTop < el.scrollTop) el.scrollTop = rowTop;
      if (rowTop + ROW_H > el.scrollTop + el.clientHeight) el.scrollTop = rowTop + ROW_H - el.clientHeight;
    }
  }, [focus, grouped]);

  const toggleSelect = (id, e) => {
    if (e?.shiftKey && selected.size > 0) {
      const last = [...selected].pop();
      const ids = filtered.map(l => l.id);
      const a = ids.indexOf(last), b = ids.indexOf(id);
      const range = ids.slice(Math.min(a,b), Math.max(a,b)+1);
      setSelected(new Set([...selected, ...range]));
    } else {
      setSelected(prev => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n; });
    }
  };

  const agencies = [...new Set(leads.map(l => l.contract.agency))].sort();

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "calc(100vh - 100px)" }}>
      {/* Toolbar */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 0", flexWrap: "wrap" }}>
        <h2 style={{ fontFamily: F.serif, fontSize: 20, fontWeight: 700, color: T.ink, margin: 0 }}>Risk Inbox</h2>
        <span style={{ fontFamily: F.mono, fontSize: 12, color: T.caption }}>{filtered.length} leads</span>
        <div style={{ flex: 1 }} />
        <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 10, color: T.caption, fontFamily: F.sans }}>
          <Kbd>J</Kbd><Kbd>K</Kbd> nav · <Kbd>↵</Kbd> open · <Kbd>1</Kbd>–<Kbd>5</Kbd> dispose · <Kbd>/</Kbd> search
        </div>
      </div>

      {/* Filters bar */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 0", borderBottom: `1px solid ${T.line}`, flexWrap: "wrap" }}>
        <input id="inbox-search" value={filters.search} onChange={e => setFilters(f => ({...f, search: e.target.value}))} placeholder="Search leads, contracts, vendors…" style={{ flex: 1, minWidth: 180, padding: "6px 10px", fontSize: 12, fontFamily: F.sans, border: `1px solid ${T.line}`, borderRadius: 5, outline: "none", background: T.card, color: T.ink }} />
        <select value={filters.tier} onChange={e => setFilters(f => ({...f, tier: e.target.value}))} style={{ padding: "5px 8px", fontSize: 11, fontFamily: F.sans, border: `1px solid ${T.line}`, borderRadius: 5, background: T.card, color: T.body, cursor: "pointer" }}>
          <option value="all">All tiers</option>
          <option value="RED">RED only</option>
          <option value="YELLOW">YELLOW only</option>
        </select>
        <select value={filters.agency} onChange={e => setFilters(f => ({...f, agency: e.target.value}))} style={{ padding: "5px 8px", fontSize: 11, fontFamily: F.sans, border: `1px solid ${T.line}`, borderRadius: 5, background: T.card, color: T.body, cursor: "pointer" }}>
          <option value="all">All agencies</option>
          {agencies.map(a => <option key={a} value={a}>{a}</option>)}
        </select>
        <select value={filters.typology} onChange={e => setFilters(f => ({...f, typology: e.target.value}))} style={{ padding: "5px 8px", fontSize: 11, fontFamily: F.sans, border: `1px solid ${T.line}`, borderRadius: 5, background: T.card, color: T.body, cursor: "pointer" }}>
          <option value="all">All typologies</option>
          {TYPOLOGY_NAMES.map(t => <option key={t} value={t}>{t}</option>)}
        </select>
        <div style={{ display: "flex", gap: 4, borderLeft: `1px solid ${T.line}`, paddingLeft: 8 }}>
          <button onClick={() => setGroupBy(null)} style={{ padding: "4px 8px", fontSize: 10, fontFamily: F.sans, fontWeight: 600, borderRadius: 4, cursor: "pointer", border: `1px solid ${!groupBy ? T.gold : T.line}`, background: !groupBy ? T.goldSoft : "transparent", color: !groupBy ? T.gold : T.caption }}>Leads</button>
          <button onClick={() => setGroupBy("vendor")} style={{ padding: "4px 8px", fontSize: 10, fontFamily: F.sans, fontWeight: 600, borderRadius: 4, cursor: "pointer", border: `1px solid ${groupBy==="vendor" ? T.gold : T.line}`, background: groupBy==="vendor" ? T.goldSoft : "transparent", color: groupBy==="vendor" ? T.gold : T.caption }}>By Vendor</button>
          <button onClick={() => setGroupBy("agency")} style={{ padding: "4px 8px", fontSize: 10, fontFamily: F.sans, fontWeight: 600, borderRadius: 4, cursor: "pointer", border: `1px solid ${groupBy==="agency" ? T.gold : T.line}`, background: groupBy==="agency" ? T.goldSoft : "transparent", color: groupBy==="agency" ? T.gold : T.caption }}>By Agency</button>
        </div>
        {selected.size > 0 && (
          <div style={{ display: "flex", alignItems: "center", gap: 6, borderLeft: `1px solid ${T.line}`, paddingLeft: 8 }}>
            <span style={{ fontSize: 11, fontFamily: F.sans, color: T.gold, fontWeight: 600 }}>{selected.size} selected</span>
            {DISPOSITIONS.slice(0,3).map(d => (
              <button key={d.key} onClick={() => {
                setLeads(prev => prev.map(l => selected.has(l.id) ? { ...l, disposition: d.key, dispositionAt: new Date().toISOString(), dispositionBy: "analyst@demo" } : l));
                setSelected(new Set());
              }} style={{ padding: "3px 8px", fontSize: 10, fontFamily: F.sans, fontWeight: 600, borderRadius: 4, cursor: "pointer", border: `1px solid ${T.line}`, background: "transparent", color: d.color }}>{d.label}</button>
            ))}
          </div>
        )}
      </div>

      {/* Table */}
      {filtered.length === 0 ? (
        <EmptyState icon="✓" title="Inbox clear" desc="No leads match your current filters. Adjust filters or wait for the next analysis job." />
      ) : grouped ? (
        <div style={{ flex: 1, overflow: "auto", background: T.card, border: `1px solid ${T.line}`, borderRadius: 8, marginTop: 8 }}>
          {grouped.map(([group, items]) => (
            <div key={group} style={{ borderBottom: `2px solid ${T.line}` }}>
              <div style={{ padding: "10px 14px", background: T.sidebar, display: "flex", alignItems: "center", gap: 10, position: "sticky", top: 0, zIndex: 5 }}>
                <span style={{ fontFamily: F.sans, fontSize: 13, fontWeight: 700, color: T.ink }}>{group}</span>
                <span style={{ fontSize: 10, fontFamily: F.mono, color: T.caption }}>{items.length} leads</span>
                <span style={{ fontSize: 10, fontFamily: F.mono, color: T.red }}>{items.filter(l => l.tier === "RED").length} RED</span>
                <span style={{ fontSize: 10, fontFamily: F.mono, color: T.amber }}>{items.filter(l => l.tier === "YELLOW").length} YEL</span>
              </div>
              {items.map(l => (
                <div key={l.id} onClick={() => onOpenCase(l)} style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 14px", cursor: "pointer", borderBottom: `1px solid ${T.line}`, background: l.disposition ? T.sidebar : "transparent", opacity: l.disposition ? 0.6 : 1 }}>
                  <TierBadge tier={l.tier} />
                  <span style={{ fontFamily: F.mono, fontSize: 11, color: T.gold, minWidth: 90 }}>{l.id}</span>
                  <span style={{ fontFamily: F.sans, fontSize: 12, color: T.ink, flex: 1 }}>{l.contract.description}</span>
                  <span style={{ fontFamily: F.mono, fontSize: 12, color: T.ink }}>{fmtUSD(l.contract.amount)}</span>
                  <span style={{ fontFamily: F.mono, fontSize: 11, color: l.evidence.priceRatio > 2 ? T.red : T.muted }}>{l.evidence.priceRatio}×</span>
                  {l.disposition && <Pill color={DISPOSITIONS.find(d => d.key === l.disposition)?.color}>{l.disposition}</Pill>}
                </div>
              ))}
            </div>
          ))}
        </div>
      ) : (
        <div ref={scrollRef} onScroll={e => setScrollTop(e.target.scrollTop)} style={{ flex: 1, overflow: "auto", background: T.card, border: `1px solid ${T.line}`, borderRadius: 8, marginTop: 8 }}>
          {/* Header */}
          <div style={{ display: "grid", gridTemplateColumns: "32px 56px 86px 1fr 130px 100px 64px 72px 56px 44px", alignItems: "center", padding: "0 10px", height: 32, borderBottom: `2px solid ${T.line}`, background: T.sidebar, position: "sticky", top: 0, zIndex: 10 }}>
            {["","Tier","Lead","Vendor","Agency","Value","Ratio","Typologies","Age",""].map((h,i) => (
              <div key={i} style={{ fontSize: 9, fontWeight: 700, fontFamily: F.sans, letterSpacing: "0.1em", textTransform: "uppercase", color: T.caption, padding: "0 4px" }}>{h}</div>
            ))}
          </div>
          {/* Virtual spacer top */}
          <div style={{ height: visibleStart * ROW_H }} />
          {/* Visible rows */}
          {visibleLeads.map((l, vi) => {
            const idx = visibleStart + vi;
            const isFocused = idx === focus;
            const isSel = selected.has(l.id);
            return (
              <div key={l.id} onClick={(e) => e.ctrlKey || e.metaKey ? toggleSelect(l.id, e) : e.shiftKey ? toggleSelect(l.id, e) : onOpenCase(l)} onMouseEnter={() => setFocus(idx)}
                style={{ display: "grid", gridTemplateColumns: "32px 56px 86px 1fr 130px 100px 64px 72px 56px 44px", alignItems: "center", padding: "0 10px", height: ROW_H, cursor: "pointer", borderBottom: `1px solid ${T.line}`, background: isSel ? T.blueSoft : isFocused ? T.goldSoft : l.disposition ? `${T.sidebar}80` : "transparent", opacity: l.disposition ? 0.55 : 1, transition: "background 0.08s" }}>
                <div style={{ padding: "0 4px" }}>
                  <input type="checkbox" checked={isSel} onChange={() => toggleSelect(l.id)} onClick={e => e.stopPropagation()} style={{ accentColor: T.gold, cursor: "pointer" }} />
                </div>
                <div style={{ padding: "0 4px" }}><TierBadge tier={l.tier} /></div>
                <div style={{ padding: "0 4px", fontFamily: F.mono, fontSize: 10, color: T.gold, fontWeight: 600 }}>{l.id}</div>
                <div style={{ padding: "0 4px", fontFamily: F.sans, fontSize: 12, fontWeight: 600, color: T.ink, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{l.contract.vendor}</div>
                <div style={{ padding: "0 4px", fontFamily: F.sans, fontSize: 11, color: T.muted, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{l.contract.agency}</div>
                <div style={{ padding: "0 4px", fontFamily: F.mono, fontSize: 12, color: T.ink, textAlign: "right" }}>{fmtUSD(l.contract.amount)}</div>
                <div style={{ padding: "0 4px", fontFamily: F.mono, fontSize: 11, fontWeight: 600, color: l.evidence.priceRatio > 2 ? T.red : l.evidence.priceRatio > 1.4 ? T.amber : T.muted }}>{l.evidence.priceRatio}×</div>
                <div style={{ padding: "0 4px", display: "flex", gap: 3 }}>
                  {l.typologies.slice(0,2).map(t => <Pill key={t.name} color={l.tier === "RED" ? T.red : T.amber} bg={l.tier === "RED" ? T.redSoft : T.amberSoft}>{t.name.split(" ")[0]}</Pill>)}
                </div>
                <div style={{ padding: "0 4px", fontFamily: F.mono, fontSize: 10, color: T.caption }}>{fmtAge(l.createdAt)}</div>
                <div style={{ padding: "0 4px" }}>
                  {l.disposition && <span style={{ width: 8, height: 8, borderRadius: "50%", background: DISPOSITIONS.find(d => d.key === l.disposition)?.color || T.caption, display: "inline-block" }} title={l.disposition} />}
                </div>
              </div>
            );
          })}
          {/* Virtual spacer bottom */}
          <div style={{ height: Math.max(0, (filtered.length - visibleEnd) * ROW_H) }} />
        </div>
      )}
    </div>
  );
}

// ═══════════ 2. CASE PACKET ═══════════
function CasePacket({ lead, setLeads, onBack, allLeads }) {
  const [disp, setDisp] = useState(lead.disposition || null);
  const [note, setNote] = useState(lead.dispositionNote || "");
  const [showEvidence, setShowEvidence] = useState({});
  const c = lead.contract;
  const e = lead.evidence;

  const currentIdx = allLeads.findIndex(l => l.id === lead.id);
  const prevLead = currentIdx > 0 ? allLeads[currentIdx - 1] : null;
  const nextLead = currentIdx < allLeads.length - 1 ? allLeads[currentIdx + 1] : null;

  const applyDisposition = (d) => {
    setDisp(d.key);
    setLeads(prev => prev.map(l => l.id === lead.id ? { ...l, disposition: d.key, dispositionAt: new Date().toISOString(), dispositionBy: "analyst@demo", dispositionNote: note } : l));
  };

  // Keyboard: 1-5 dispositions, [ prev, ] next
  useEffect(() => {
    const h = (e) => {
      if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA") return;
      const num = parseInt(e.key);
      if (num >= 1 && num <= 5) { e.preventDefault(); applyDisposition(DISPOSITIONS[num - 1]); }
      if (e.key === "[" && prevLead) { e.preventDefault(); onBack(prevLead); }
      if (e.key === "]" && nextLead) { e.preventDefault(); onBack(nextLead); }
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [prevLead, nextLead, note]);

  return (
    <div style={{ maxWidth: 920, margin: "0 auto" }}>
      {/* Navigation */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <button onClick={() => onBack(null)} style={{ padding: "6px 14px", borderRadius: 5, fontSize: 12, fontFamily: F.sans, fontWeight: 500, color: T.body, background: "none", border: `1px solid ${T.line}`, cursor: "pointer" }}>← Inbox</button>
          {prevLead && <button onClick={() => onBack(prevLead)} style={{ padding: "6px 10px", borderRadius: 5, fontSize: 11, fontFamily: F.sans, color: T.caption, background: "none", border: `1px solid ${T.line}`, cursor: "pointer" }}><Kbd>[</Kbd> Prev</button>}
          {nextLead && <button onClick={() => onBack(nextLead)} style={{ padding: "6px 10px", borderRadius: 5, fontSize: 11, fontFamily: F.sans, color: T.caption, background: "none", border: `1px solid ${T.line}`, cursor: "pointer" }}>Next <Kbd>]</Kbd></button>}
        </div>
        <button onClick={() => alert("Export endpoint not connected. Wire /api/v2/leads/{id}/export for production.")} style={{ padding: "6px 14px", borderRadius: 5, fontSize: 12, fontFamily: F.sans, fontWeight: 600, color: "#FFF", background: T.gold, border: "none", cursor: "pointer" }}>Export Case Packet</button>
      </div>

      <LegalBanner />

      {/* Header Card */}
      <div style={{ background: T.card, border: `1px solid ${T.line}`, borderRadius: 10, padding: 24, marginTop: 12, marginBottom: 12 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 16 }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
              <span style={{ fontFamily: F.mono, fontSize: 11, color: T.gold, fontWeight: 600 }}>{lead.id}</span>
              <span style={{ color: T.ghost }}>·</span>
              <span style={{ fontFamily: F.mono, fontSize: 11, color: T.caption }}>{c.id}</span>
            </div>
            <h2 style={{ fontFamily: F.serif, fontSize: 22, fontWeight: 700, color: T.ink, margin: 0 }}>{c.vendor}</h2>
            <div style={{ fontFamily: F.sans, fontSize: 13, color: T.muted, marginTop: 4 }}>{c.agency} · {c.region} Region · {fmtDate(c.date)}</div>
          </div>
          <TierBadge tier={lead.tier} size="lg" />
        </div>

        {/* Provenance pill */}
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 16 }}>
          {Object.entries(lead.provenance).map(([k,v]) => (
            <span key={k} onClick={() => navigator.clipboard?.writeText(v)} title="Click to copy" style={{ cursor: "pointer", display: "inline-flex", alignItems: "center", gap: 4, padding: "3px 8px", borderRadius: 4, fontSize: 10, fontFamily: F.mono, background: T.sidebar, color: T.muted, border: `1px solid ${T.line}` }}>
              <span style={{ fontWeight: 700, color: T.caption }}>{k}:</span> {v}
            </span>
          ))}
        </div>

        {/* Key metrics */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10 }}>
          {[
            ["Contract Value", fmtUSD(c.amount), T.ink],
            ["Unit Price", `$${c.unitPrice}`, T.ink],
            ["vs Peer Median", `${e.priceRatio}× higher`, e.priceRatio > 2 ? T.red : T.amber],
            ["P(irregularity)", `${(e.posteriorP * 100).toFixed(1)}%`, T.gold],
          ].map(([label, val, color]) => (
            <div key={label} style={{ padding: "10px 14px", background: T.bg, borderRadius: 6, border: `1px solid ${T.line}` }}>
              <div style={{ fontSize: 9, fontWeight: 700, fontFamily: F.sans, letterSpacing: "0.08em", textTransform: "uppercase", color: T.caption, marginBottom: 4 }}>{label}</div>
              <div style={{ fontSize: 16, fontWeight: 700, fontFamily: F.mono, color }}>{val}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Executive Summary */}
      <div style={{ background: T.card, border: `1px solid ${T.line}`, borderRadius: 10, padding: 24, marginBottom: 12 }}>
        <Label>Executive Summary</Label>
        <div style={{ fontFamily: F.sans, fontSize: 14, color: T.body, lineHeight: 1.8 }}>
          <p style={{ margin: "0 0 8px" }}>SUNLIGHT identified <strong style={{ color: T.ink }}>{lead.typologies.length} statistical anomal{lead.typologies.length > 1 ? "ies" : "y"}</strong> in contract {c.id} awarded to {c.vendor} by {c.agency}.</p>
          {e.priceRatio > 1.3 && <p style={{ margin: "0 0 8px" }}>The unit price of ${c.unitPrice} is <strong style={{ color: T.ink }}>{e.priceRatio}× the peer median</strong> of ${e.peerMedian}, based on {e.peerCount} comparable contracts in the {c.category.replace(/_/g," ")} category. This price falls outside the 95% bootstrap confidence interval (upper bound: ${e.ciUpper}).</p>}
          <p style={{ margin: "0 0 8px" }}>After combining all evidence sources through Bayesian analysis, the posterior probability of procurement irregularity is <strong style={{ color: T.ink }}>{(e.posteriorP * 100).toFixed(1)}%</strong>. The FDR-corrected q-value is {e.fdrQ}, which is {e.fdrQ < 0.05 ? "below the 0.05 significance threshold" : "above the standard significance threshold"}.</p>
          {lead.tier === "RED" && <p style={{ margin: 0 }}>This statistical profile <strong style={{ color: T.red }}>matches patterns observed in DOJ-prosecuted procurement fraud cases</strong>, warranting detailed investigation.</p>}
        </div>
      </div>

      {/* Typology Sections */}
      <div style={{ background: T.card, border: `1px solid ${T.line}`, borderRadius: 10, padding: 24, marginBottom: 12 }}>
        <Label>Typology Analysis</Label>
        {lead.typologies.map((typ, ti) => (
          <div key={ti} style={{ borderRadius: 8, border: `1px solid ${T.line}`, marginBottom: ti < lead.typologies.length - 1 ? 12 : 0, overflow: "hidden" }}>
            <div style={{ padding: "12px 16px", background: T.bg, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <div>
                <div style={{ fontFamily: F.sans, fontSize: 13, fontWeight: 700, color: T.ink }}>{typ.name}</div>
                <div style={{ fontFamily: F.sans, fontSize: 12, color: T.body, marginTop: 2 }}>{typ.trigger}</div>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <Pill>{typ.method}</Pill>
                <TierBadge tier={lead.tier} />
              </div>
            </div>
            <div style={{ padding: "12px 16px", borderTop: `1px solid ${T.line}` }}>
              <button onClick={() => setShowEvidence(p => ({...p, [ti]: !p[ti]}))} style={{ fontSize: 11, fontFamily: F.sans, fontWeight: 600, color: T.gold, background: "none", border: "none", cursor: "pointer", padding: 0, display: "flex", alignItems: "center", gap: 4 }}>
                {showEvidence[ti] ? "▾ Hide" : "▸ Show"} statistical evidence
              </button>
              {showEvidence[ti] && (
                <table style={{ width: "100%", borderCollapse: "collapse", marginTop: 10, border: `1px solid ${T.line}`, borderRadius: 6 }}>
                  <thead>
                    <tr style={{ background: T.sidebar }}>
                      {["Measure","Value","Interpretation"].map(h => (
                        <th key={h} style={{ padding: "8px 12px", textAlign: "left", fontSize: 9, fontWeight: 700, fontFamily: F.sans, letterSpacing: "0.1em", textTransform: "uppercase", color: T.caption }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {[
                      ["Unit price", `$${c.unitPrice}`, "What this contract pays per unit"],
                      ["Peer median", `$${e.peerMedian}`, `Typical price across ${e.peerCount} comparable contracts`],
                      ["Price ratio", `${e.priceRatio}×`, "How many times higher than peers"],
                      ["95% CI upper", `$${e.ciUpper}`, "Maximum expected price (bootstrap, 10K resamples)"],
                      ["Posterior P", `${(e.posteriorP*100).toFixed(1)}%`, "Bayesian probability combining all evidence"],
                      ["FDR q-value", e.fdrQ.toString(), "False discovery rate — <0.05 = statistically significant"],
                    ].map(([m, v, d], ri) => (
                      <tr key={m} style={{ borderBottom: ri < 5 ? `1px solid ${T.line}` : "none" }}>
                        <td style={{ padding: "8px 12px", fontFamily: F.sans, fontSize: 12, fontWeight: 600, color: T.ink }}>{m}</td>
                        <td style={{ padding: "8px 12px", fontFamily: F.mono, fontSize: 12, fontWeight: 600, color: T.gold }}>{v}</td>
                        <td style={{ padding: "8px 12px", fontFamily: F.sans, fontSize: 11, color: T.muted }}>{d}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Investigation Steps */}
      <div style={{ background: T.card, border: `1px solid ${T.line}`, borderRadius: 10, padding: 24, marginBottom: 12 }}>
        <Label>Recommended Investigation Steps</Label>
        {[
          ["Request", `Obtain price justification from ${c.agency} contracting officer for ${c.category.replace(/_/g," ")} procurement`],
          ["Verify", `Cross-reference unit price of $${c.unitPrice} against published market indices for ${c.category.replace(/_/g," ")}`],
          ["Compare", `Review ${c.vendor}'s complete contract history across all agencies for pricing patterns`],
          ["Inspect", `Examine ${c.vendor}'s registration, beneficial ownership, and related-party disclosures`],
          ["Document", "Record findings and preserve evidence chain per institutional investigation protocols"],
        ].map(([verb, text], i) => (
          <label key={i} style={{ display: "flex", alignItems: "flex-start", gap: 10, padding: "10px 0", borderBottom: i < 4 ? `1px solid ${T.line}` : "none", cursor: "pointer" }}>
            <input type="checkbox" style={{ marginTop: 3, accentColor: T.gold }} />
            <span style={{ fontFamily: F.sans, fontSize: 13, color: T.body, lineHeight: 1.6 }}><strong style={{ color: T.ink }}>{verb}.</strong> {text}</span>
          </label>
        ))}
      </div>

      {/* Audit Trail */}
      <div style={{ background: T.card, border: `1px solid ${T.line}`, borderRadius: 10, padding: 24, marginBottom: 12 }}>
        <Label>Audit Trail</Label>
        <div style={{ fontFamily: F.mono, fontSize: 11, color: T.muted, lineHeight: 2 }}>
          <div>{fmtDate(lead.createdAt)} — Lead generated by job {lead.provenance.job}</div>
          <div>{fmtDate(lead.createdAt)} — Rulepack {lead.provenance.rulepack} applied on snapshot {lead.provenance.snapshot}</div>
          {lead.dispositionAt && <div>{fmtDate(lead.dispositionAt)} — Dispositioned as "{lead.disposition}" by {lead.dispositionBy}</div>}
          <div style={{ color: T.caption, fontStyle: "italic" }}>This case packet was viewed at {new Date().toLocaleTimeString()} by current session user</div>
        </div>
      </div>

      {/* Disposition */}
      <div style={{ background: T.card, border: `1px solid ${T.line}`, borderRadius: 10, padding: 24 }}>
        <Label>Disposition</Label>
        <textarea value={note} onChange={e => setNote(e.target.value)} placeholder="Document your assessment…" style={{ width: "100%", minHeight: 60, padding: 10, fontFamily: F.sans, fontSize: 12, lineHeight: 1.5, color: T.ink, background: T.bg, border: `1px solid ${T.line}`, borderRadius: 6, outline: "none", resize: "vertical", marginBottom: 12, boxSizing: "border-box" }} />
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          {DISPOSITIONS.map(d => (
            <button key={d.key} onClick={() => applyDisposition(d)} style={{
              display: "flex", alignItems: "center", gap: 6, padding: "6px 14px",
              borderRadius: 6, fontSize: 12, fontWeight: 600, fontFamily: F.sans, cursor: "pointer",
              background: disp === d.key ? `${d.color}11` : "transparent",
              border: disp === d.key ? `2px solid ${d.color}` : `1px solid ${T.line}`,
              color: disp === d.key ? d.color : T.muted, transition: "all 0.12s",
            }}><Kbd>{d.num}</Kbd> {d.label}</button>
          ))}
        </div>
      </div>
    </div>
  );
}

// ═══════════ 3. PORTFOLIO ═══════════
function Portfolio({ leads, contracts }) {
  const [threshold, setThreshold] = useState(70);
  const reds = leads.filter(l => l.tier === "RED");
  const yellows = leads.filter(l => l.tier === "YELLOW");
  const flagsPer1K = contracts.length > 0 ? ((leads.length / contracts.length) * 1000).toFixed(0) : 0;

  // Agency heatmap data
  const agencyData = useMemo(() => {
    const d = {};
    leads.forEach(l => {
      const agency = l.contract.agency;
      const month = l.contract.date?.substring(0, 7) || "unknown";
      if (!d[agency]) d[agency] = {};
      d[agency][month] = (d[agency][month] || 0) + 1;
    });
    return d;
  }, [leads]);

  const months = useMemo(() => [...new Set(leads.map(l => l.contract.date?.substring(0, 7)).filter(Boolean))].sort(), [leads]);
  const agencyNames = Object.keys(agencyData).sort();

  // Top vendors
  const vendorCounts = useMemo(() => {
    const v = {};
    leads.forEach(l => { v[l.contract.vendor] = (v[l.contract.vendor] || 0) + 1; });
    return Object.entries(v).sort((a,b) => b[1] - a[1]).slice(0, 10);
  }, [leads]);

  // Typology distribution
  const typDist = useMemo(() => {
    const t = {};
    leads.forEach(l => l.typologies.forEach(typ => { t[typ.name] = (t[typ.name] || 0) + 1; }));
    return Object.entries(t).sort((a,b) => b[1] - a[1]);
  }, [leads]);

  // Workload simulator
  const simLeads = leads.filter(l => l.confidence >= threshold);
  const simFlagsPer1K = contracts.length > 0 ? ((simLeads.length / contracts.length) * 1000).toFixed(0) : 0;
  const simHours = Math.round(simLeads.length * 0.4);

  return (
    <div>
      <h2 style={{ fontFamily: F.serif, fontSize: 20, fontWeight: 700, color: T.ink, margin: "0 0 16px" }}>Portfolio Overview</h2>

      {/* System Metrics */}
      <div style={{ background: T.card, border: `1px solid ${T.line}`, borderRadius: 10, padding: 20, marginBottom: 16 }}>
        <Label>System Performance</Label>
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
          <StatCard label="Recall" value="100%" sub="Every DOJ-prosecuted case detected" color={T.green} />
          <StatCard label="Precision (RED)" value="~25%" sub="Target: ≥25% at RED tier" color={T.ink} />
          <StatCard label="Flags / 1K" value={flagsPer1K} sub={`${leads.length} leads from ${contracts.length} contracts`} color={parseInt(flagsPer1K) > 200 ? T.amber : T.green} />
          <StatCard label="RED Leads" value={reds.length.toString()} sub="Match DOJ prosecution profile" color={T.red} />
          <StatCard label="YELLOW Leads" value={yellows.length.toString()} sub="Warrant analyst review" color={T.amber} />
          <StatCard label="Contracts" value={contracts.length.toString()} sub="Total scanned this period" color={T.ink} />
        </div>
        <div style={{ marginTop: 12, padding: 10, background: T.sidebar, borderRadius: 6, fontSize: 11, fontFamily: F.sans, color: T.muted, lineHeight: 1.6 }}>
          <strong style={{ color: T.body }}>Validation note:</strong> Recall validated against 10 DOJ-prosecuted price fraud cases spanning multiple agencies, contract types, and methodologies. System is unsupervised — DOJ cases are validation data, not training data. Statistical methods: bootstrap CI (10K resamples), Bayesian posterior combination, FDR correction (Benjamini-Hochberg), DOJ threshold calibration.
        </div>
      </div>

      {/* Agency × Time Heatmap */}
      <div style={{ background: T.card, border: `1px solid ${T.line}`, borderRadius: 10, padding: 20, marginBottom: 16 }}>
        <Label>Risk Density — Agency × Month</Label>
        <div style={{ overflowX: "auto" }}>
          <div style={{ display: "grid", gridTemplateColumns: `180px repeat(${months.length}, 1fr)`, gap: 2, minWidth: 600 }}>
            <div />
            {months.map(m => <div key={m} style={{ fontSize: 9, fontFamily: F.mono, color: T.caption, textAlign: "center", padding: 4 }}>{m.substring(5)}</div>)}
            {agencyNames.map(agency => (
              <>
                <div key={agency} style={{ fontSize: 11, fontFamily: F.sans, color: T.body, padding: "4px 8px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{agency}</div>
                {months.map(month => {
                  const count = agencyData[agency]?.[month] || 0;
                  const intensity = Math.min(1, count / 8);
                  return <div key={`${agency}-${month}`} style={{ height: 24, borderRadius: 3, background: count === 0 ? T.sidebar : `rgba(194, 59, 59, ${0.1 + intensity * 0.7})`, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 9, fontFamily: F.mono, color: count > 3 ? "#FFF" : T.caption }}>{count || ""}</div>;
                })}
              </>
            ))}
          </div>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 16 }}>
        {/* Top Vendors */}
        <div style={{ background: T.card, border: `1px solid ${T.line}`, borderRadius: 10, padding: 20 }}>
          <Label>Top Flagged Vendors</Label>
          {vendorCounts.map(([vendor, count], i) => (
            <div key={vendor} style={{ display: "flex", alignItems: "center", gap: 10, padding: "6px 0", borderBottom: i < vendorCounts.length - 1 ? `1px solid ${T.line}` : "none" }}>
              <span style={{ fontFamily: F.mono, fontSize: 11, color: T.caption, minWidth: 20 }}>{i+1}</span>
              <span style={{ flex: 1, fontFamily: F.sans, fontSize: 12, color: T.ink }}>{vendor}</span>
              <div style={{ width: 60, height: 4, borderRadius: 2, background: T.line, overflow: "hidden" }}>
                <div style={{ height: "100%", width: `${(count / vendorCounts[0][1]) * 100}%`, background: T.red, borderRadius: 2 }} />
              </div>
              <span style={{ fontFamily: F.mono, fontSize: 11, color: T.muted, minWidth: 24, textAlign: "right" }}>{count}</span>
            </div>
          ))}
        </div>

        {/* Typology Distribution */}
        <div style={{ background: T.card, border: `1px solid ${T.line}`, borderRadius: 10, padding: 20 }}>
          <Label>Typology Distribution</Label>
          {typDist.map(([name, count], i) => {
            const total = leads.reduce((s, l) => s + l.typologies.length, 0);
            const pct = total > 0 ? ((count / total) * 100).toFixed(0) : 0;
            return (
              <div key={name} style={{ padding: "8px 0", borderBottom: i < typDist.length - 1 ? `1px solid ${T.line}` : "none" }}>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                  <span style={{ fontFamily: F.sans, fontSize: 12, fontWeight: 600, color: T.ink }}>{name}</span>
                  <span style={{ fontFamily: F.mono, fontSize: 11, color: T.muted }}>{count} ({pct}%)</span>
                </div>
                <div style={{ height: 6, borderRadius: 3, background: T.line, overflow: "hidden" }}>
                  <div style={{ height: "100%", width: `${pct}%`, borderRadius: 3, background: T.gold }} />
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Workload Simulator */}
      <div style={{ background: T.card, border: `1px solid ${T.line}`, borderRadius: 10, padding: 20 }}>
        <Label>Workload Simulator <span style={{ fontWeight: 400, letterSpacing: 0, textTransform: "none", color: T.caption, fontSize: 10 }}>(projection only — not actual threshold adjustment)</span></Label>
        <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 12 }}>
          <span style={{ fontFamily: F.sans, fontSize: 12, color: T.body }}>Confidence threshold:</span>
          <input type="range" min="20" max="95" value={threshold} onChange={e => setThreshold(+e.target.value)} style={{ flex: 1, accentColor: T.gold }} />
          <span style={{ fontFamily: F.mono, fontSize: 14, fontWeight: 700, color: T.gold, minWidth: 40 }}>{threshold}%</span>
        </div>
        <div style={{ display: "flex", gap: 24 }}>
          <StatCard label="Projected leads" value={simLeads.length.toString()} color={T.ink} />
          <StatCard label="Flags / 1K" value={simFlagsPer1K} color={parseInt(simFlagsPer1K) > 200 ? T.amber : T.green} />
          <StatCard label="Est. analyst hours" value={`${simHours}h`} sub="At ~24 min/lead" color={T.ink} />
          <StatCard label="RED leads" value={simLeads.filter(l => l.tier === "RED").length.toString()} color={T.red} />
        </div>
      </div>
    </div>
  );
}

// ═══════════ 4. ADMIN ═══════════
function Admin() {
  const [tab, setTab] = useState("tenant");
  const tabs = [
    { key: "tenant", label: "Tenant & RBAC" },
    { key: "webhooks", label: "Webhooks" },
    { key: "jobs", label: "Jobs" },
    { key: "dlq", label: "DLQ" },
    { key: "audit", label: "Audit Log" },
    { key: "observability", label: "Observability" },
  ];

  return (
    <div>
      <h2 style={{ fontFamily: F.serif, fontSize: 20, fontWeight: 700, color: T.ink, margin: "0 0 16px" }}>Administration</h2>
      <div style={{ display: "flex", gap: 4, borderBottom: `2px solid ${T.line}`, marginBottom: 16 }}>
        {tabs.map(t => (
          <button key={t.key} onClick={() => setTab(t.key)} style={{ padding: "8px 16px", fontSize: 12, fontWeight: 600, fontFamily: F.sans, cursor: "pointer", background: "none", border: "none", color: tab === t.key ? T.ink : T.caption, borderBottom: tab === t.key ? `2px solid ${T.gold}` : "2px solid transparent", marginBottom: -2 }}>{t.label}</button>
        ))}
      </div>

      {tab === "tenant" && (
        <div style={{ background: T.card, border: `1px solid ${T.line}`, borderRadius: 10, padding: 24 }}>
          <Label>Tenant Configuration</Label>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 20 }}>
            {[["Tenant ID", "demo_tenant"], ["Organization", "Demo Organization"], ["Plan", "Institutional"], ["Data Region", "eu-west-1"]].map(([l,v]) => (
              <div key={l} style={{ padding: 12, background: T.bg, borderRadius: 6, border: `1px solid ${T.line}` }}>
                <div style={{ fontSize: 10, fontWeight: 700, fontFamily: F.sans, letterSpacing: "0.08em", textTransform: "uppercase", color: T.caption, marginBottom: 4 }}>{l}</div>
                <div style={{ fontFamily: F.mono, fontSize: 13, color: T.ink }}>{v}</div>
              </div>
            ))}
          </div>
          <Label>Role-Based Access Control</Label>
          <table style={{ width: "100%", borderCollapse: "collapse", border: `1px solid ${T.line}`, borderRadius: 6 }}>
            <thead><tr style={{ background: T.sidebar }}>{["User","Role","Last Active","Status"].map(h => <th key={h} style={{ padding: "8px 12px", textAlign: "left", fontSize: 10, fontWeight: 700, fontFamily: F.sans, letterSpacing: "0.08em", textTransform: "uppercase", color: T.caption }}>{h}</th>)}</tr></thead>
            <tbody>
              {[["analyst@demo","Analyst","2 hours ago","Active"],["admin@demo","Admin","Just now","Active"],["viewer@demo","Viewer","3 days ago","Active"],["auditor@demo","Analyst","1 week ago","Inactive"]].map(([u,r,la,s]) => (
                <tr key={u} style={{ borderBottom: `1px solid ${T.line}` }}>
                  <td style={{ padding: "8px 12px", fontFamily: F.mono, fontSize: 12, color: T.ink }}>{u}</td>
                  <td style={{ padding: "8px 12px" }}><Pill color={r === "Admin" ? T.red : r === "Analyst" ? T.gold : T.muted}>{r}</Pill></td>
                  <td style={{ padding: "8px 12px", fontFamily: F.sans, fontSize: 12, color: T.muted }}>{la}</td>
                  <td style={{ padding: "8px 12px" }}><span style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 11, fontFamily: F.sans, color: s === "Active" ? T.green : T.caption }}><span style={{ width: 6, height: 6, borderRadius: "50%", background: s === "Active" ? T.green : T.ghost }} />{s}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {tab === "webhooks" && (
        <div style={{ background: T.card, border: `1px solid ${T.line}`, borderRadius: 10, padding: 24 }}>
          <Label>Webhook Configuration</Label>
          <div style={{ padding: 16, background: T.bg, borderRadius: 6, border: `1px solid ${T.line}`, marginBottom: 16 }}>
            <div style={{ display: "grid", gridTemplateColumns: "120px 1fr", gap: 8, fontSize: 12, fontFamily: F.sans }}>
              <span style={{ fontWeight: 600, color: T.body }}>Endpoint:</span><span style={{ fontFamily: F.mono, color: T.ink }}>https://hooks.example.com/sunlight</span>
              <span style={{ fontWeight: 600, color: T.body }}>Secret:</span><span style={{ fontFamily: F.mono, color: T.caption }}>whsec_••••••••••••</span>
              <span style={{ fontWeight: 600, color: T.body }}>Events:</span><span style={{ color: T.ink }}>job.completed, lead.created, lead.dispositioned</span>
              <span style={{ fontWeight: 600, color: T.body }}>Signing:</span><span style={{ color: T.ink }}>HMAC-SHA256</span>
            </div>
          </div>
          <Label>Recent Deliveries</Label>
          {[["200","job.completed","job_1087","2m ago"],["200","lead.created","LEAD-00042","5m ago"],["500","lead.created","LEAD-00041","5m ago"],["200","job.completed","job_1086","1h ago"]].map(([status, event, ref, ago], i) => (
            <div key={i} style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 0", borderBottom: `1px solid ${T.line}` }}>
              <span style={{ fontFamily: F.mono, fontSize: 11, fontWeight: 700, color: status === "200" ? T.green : T.red }}>{status}</span>
              <span style={{ fontFamily: F.sans, fontSize: 12, color: T.ink }}>{event}</span>
              <span style={{ fontFamily: F.mono, fontSize: 11, color: T.caption }}>{ref}</span>
              <div style={{ flex: 1 }} />
              <span style={{ fontFamily: F.sans, fontSize: 11, color: T.caption }}>{ago}</span>
            </div>
          ))}
        </div>
      )}

      {tab === "jobs" && (
        <div style={{ background: T.card, border: `1px solid ${T.line}`, borderRadius: 10, padding: 24 }}>
          <Label>Analysis Jobs</Label>
          <table style={{ width: "100%", borderCollapse: "collapse", border: `1px solid ${T.line}` }}>
            <thead><tr style={{ background: T.sidebar }}>{["Job ID","Status","Contracts","Leads","Duration","Completed"].map(h => <th key={h} style={{ padding: "8px 12px", textAlign: "left", fontSize: 10, fontWeight: 700, fontFamily: F.sans, letterSpacing: "0.08em", textTransform: "uppercase", color: T.caption }}>{h}</th>)}</tr></thead>
            <tbody>
              {[["job_1087","completed",500,72,"4.2s","2m ago"],["job_1086","completed",500,68,"3.8s","1h ago"],["job_1085","completed",200,31,"1.9s","3h ago"],["job_1084","failed",500,0,"—","5h ago"],["job_1083","completed",500,70,"4.1s","8h ago"]].map(([id,status,contracts,leads,dur,ago]) => (
                <tr key={id} style={{ borderBottom: `1px solid ${T.line}` }}>
                  <td style={{ padding: "8px 12px", fontFamily: F.mono, fontSize: 12, color: T.gold }}>{id}</td>
                  <td style={{ padding: "8px 12px" }}><span style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 11, fontFamily: F.sans }}><span style={{ width: 6, height: 6, borderRadius: "50%", background: status === "completed" ? T.green : T.red }} /><span style={{ color: status === "completed" ? T.green : T.red }}>{status}</span></span></td>
                  <td style={{ padding: "8px 12px", fontFamily: F.mono, fontSize: 12 }}>{contracts}</td>
                  <td style={{ padding: "8px 12px", fontFamily: F.mono, fontSize: 12 }}>{leads}</td>
                  <td style={{ padding: "8px 12px", fontFamily: F.mono, fontSize: 12, color: T.muted }}>{dur}</td>
                  <td style={{ padding: "8px 12px", fontFamily: F.sans, fontSize: 12, color: T.caption }}>{ago}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {tab === "dlq" && (
        <div style={{ background: T.card, border: `1px solid ${T.line}`, borderRadius: 10, padding: 24 }}>
          <Label>Dead Letter Queue</Label>
          <div style={{ display: "flex", alignItems: "center", gap: 10, padding: 16, background: T.redSoft, border: `1px solid ${T.redBdr}`, borderRadius: 6, marginBottom: 16 }}>
            <span style={{ fontSize: 16 }}>⚠</span>
            <span style={{ fontFamily: F.sans, fontSize: 13, color: T.body }}>1 failed delivery in DLQ. Requires manual review or retry.</span>
          </div>
          <div style={{ padding: 12, background: T.bg, borderRadius: 6, border: `1px solid ${T.line}`, fontFamily: F.mono, fontSize: 11, color: T.muted, lineHeight: 1.8 }}>
            <div><strong style={{ color: T.body }}>Event:</strong> lead.created (LEAD-00041)</div>
            <div><strong style={{ color: T.body }}>Endpoint:</strong> https://hooks.example.com/sunlight</div>
            <div><strong style={{ color: T.body }}>Error:</strong> HTTP 500 — Internal Server Error</div>
            <div><strong style={{ color: T.body }}>Attempts:</strong> 3/3 (exhausted)</div>
            <div><strong style={{ color: T.body }}>Failed at:</strong> 2026-02-21 14:32:08 UTC</div>
            <div style={{ marginTop: 8 }}><button style={{ padding: "4px 12px", fontSize: 11, fontFamily: F.sans, fontWeight: 600, borderRadius: 4, cursor: "pointer", border: `1px solid ${T.line}`, background: T.card, color: T.gold }}>Retry delivery</button></div>
          </div>
        </div>
      )}

      {tab === "audit" && (
        <div style={{ background: T.card, border: `1px solid ${T.line}`, borderRadius: 10, padding: 24 }}>
          <Label>Audit Log</Label>
          <div style={{ fontFamily: F.mono, fontSize: 11, lineHeight: 2.2, color: T.muted }}>
            {[
              ["14:35:02","analyst@demo","viewed","Case packet LEAD-00003"],
              ["14:34:18","analyst@demo","dispositioned","LEAD-00007 → Benign — Explainable"],
              ["14:33:45","analyst@demo","dispositioned","LEAD-00005 → True Concern"],
              ["14:32:10","system","webhook_failed","lead.created → LEAD-00041 (DLQ)"],
              ["14:30:00","system","job_completed","job_1087 — 500 contracts, 72 leads"],
              ["14:25:44","admin@demo","exported","Case packet LEAD-00001 (PDF)"],
              ["14:20:11","admin@demo","config_changed","Webhook endpoint updated"],
              ["13:15:00","system","job_completed","job_1086 — 500 contracts, 68 leads"],
            ].map(([time, user, action, detail], i) => (
              <div key={i} style={{ display: "flex", gap: 12, padding: "2px 0", borderBottom: `1px solid ${T.line}` }}>
                <span style={{ minWidth: 64, color: T.caption }}>{time}</span>
                <span style={{ minWidth: 120, color: user === "system" ? T.caption : T.gold }}>{user}</span>
                <span style={{ minWidth: 100, color: T.body }}>{action}</span>
                <span style={{ color: T.ink }}>{detail}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {tab === "observability" && (
        <div style={{ background: T.card, border: `1px solid ${T.line}`, borderRadius: 10, padding: 24 }}>
          <Label>Observability</Label>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 16 }}>
            {[
              ["Prometheus Metrics", "/metrics", "Scrape endpoint for monitoring stack"],
              ["Grafana Dashboard", "/grafana", "Pre-configured dashboards for API latency, job throughput, error rates"],
              ["Health Check", "/health", "Returns 200 if API is operational"],
              ["Ready Check", "/ready", "Returns 200 when database and job queue are connected"],
            ].map(([title, path, desc]) => (
              <div key={title} style={{ padding: 14, background: T.bg, borderRadius: 6, border: `1px solid ${T.line}` }}>
                <div style={{ fontFamily: F.sans, fontSize: 13, fontWeight: 600, color: T.ink, marginBottom: 2 }}>{title}</div>
                <div style={{ fontFamily: F.mono, fontSize: 11, color: T.gold, marginBottom: 4 }}>{path}</div>
                <div style={{ fontFamily: F.sans, fontSize: 11, color: T.muted }}>{desc}</div>
              </div>
            ))}
          </div>
          <div style={{ padding: 14, background: T.sidebar, borderRadius: 6, border: `1px solid ${T.line}`, fontFamily: F.sans, fontSize: 12, color: T.muted }}>
            <strong style={{ color: T.body }}>Note:</strong> Grafana and Prometheus links require infrastructure to be configured. Set GRAFANA_URL and PROMETHEUS_URL environment variables for direct links.
          </div>
        </div>
      )}
    </div>
  );
}

// ═══════════ 5. ONBOARDING ═══════════
function Onboarding({ onComplete }) {
  const [step, setStep] = useState(0);
  const steps = ["Create Tenant", "Ingest Data", "Run Analysis", "Review Inbox", "Open Case"];

  return (
    <div style={{ maxWidth: 640, margin: "0 auto" }}>
      <div style={{ textAlign: "center", marginBottom: 32 }}>
        <div style={{ width: 56, height: 56, borderRadius: 14, margin: "0 auto 16px", background: "linear-gradient(135deg, #C9A84C, #A68930)", display: "flex", alignItems: "center", justifyContent: "center" }}>
          <span style={{ fontSize: 26 }}>☀</span>
        </div>
        <h2 style={{ fontFamily: F.serif, fontSize: 22, fontWeight: 700, color: T.ink, margin: "0 0 6px" }}>Welcome to SUNLIGHT</h2>
        <p style={{ fontFamily: F.sans, fontSize: 14, color: T.muted }}>Get started in 5 steps</p>
      </div>

      {/* Stepper */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 4, marginBottom: 32 }}>
        {steps.map((s, i) => (
          <div key={i} style={{ display: "flex", alignItems: "center", gap: 4 }}>
            <div style={{ width: 28, height: 28, borderRadius: 7, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 11, fontWeight: 700, fontFamily: F.mono, background: i < step ? T.greenSoft : i === step ? T.goldSoft : T.bg, color: i < step ? T.green : i === step ? T.gold : T.ghost, border: `1px solid ${i < step ? T.greenBdr : i === step ? T.gold : T.line}` }}>
              {i < step ? "✓" : i + 1}
            </div>
            {i < steps.length - 1 && <div style={{ width: 24, height: 2, background: i < step ? T.green : T.line, borderRadius: 1 }} />}
          </div>
        ))}
      </div>

      {/* Step content */}
      <div style={{ background: T.card, border: `1px solid ${T.line}`, borderRadius: 10, padding: 32, marginBottom: 16, minHeight: 200 }}>
        {step === 0 && (
          <div>
            <Label>Step 1 — Create Tenant</Label>
            <p style={{ fontFamily: F.sans, fontSize: 14, color: T.body, lineHeight: 1.7, margin: "0 0 16px" }}>Each organization gets an isolated tenant with its own data, users, and configuration. Data from one tenant is never accessible to another.</p>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
              <div>
                <label style={{ fontSize: 11, fontWeight: 600, fontFamily: F.sans, color: T.body, marginBottom: 4, display: "block" }}>Organization Name</label>
                <input defaultValue="Demo Organization" style={{ width: "100%", padding: "8px 10px", fontSize: 13, fontFamily: F.sans, border: `1px solid ${T.line}`, borderRadius: 5, outline: "none", boxSizing: "border-box" }} />
              </div>
              <div>
                <label style={{ fontSize: 11, fontWeight: 600, fontFamily: F.sans, color: T.body, marginBottom: 4, display: "block" }}>Data Region</label>
                <select style={{ width: "100%", padding: "8px 10px", fontSize: 13, fontFamily: F.sans, border: `1px solid ${T.line}`, borderRadius: 5, background: T.card, boxSizing: "border-box" }}>
                  <option>eu-west-1 (EU)</option>
                  <option>us-east-1 (US)</option>
                  <option>af-south-1 (Africa)</option>
                </select>
              </div>
            </div>
          </div>
        )}
        {step === 1 && (
          <div>
            <Label>Step 2 — Ingest Data</Label>
            <p style={{ fontFamily: F.sans, fontSize: 14, color: T.body, lineHeight: 1.7, margin: "0 0 16px" }}>Upload procurement contract data. Required fields: vendor, agency, amount, unit_price, category, date. Accepted formats: CSV, JSON, PDF (OCR).</p>
            <div style={{ border: `2px dashed ${T.ghost}`, borderRadius: 10, padding: 24, textAlign: "center", cursor: "pointer", marginBottom: 12 }}>
              <div style={{ fontSize: 24, marginBottom: 8 }}>↑</div>
              <div style={{ fontFamily: F.sans, fontSize: 13, fontWeight: 600, color: T.ink }}>Drag files here or click to browse</div>
              <div style={{ fontFamily: F.sans, fontSize: 11, color: T.caption, marginTop: 4 }}>CSV, JSON, or PDF · Max 10MB per file</div>
            </div>
            <button style={{ width: "100%", padding: "10px", borderRadius: 6, fontSize: 13, fontFamily: F.sans, fontWeight: 600, color: "#FFF", background: T.gold, border: "none", cursor: "pointer" }}>Use sample dataset (500 contracts)</button>
          </div>
        )}
        {step === 2 && (
          <div>
            <Label>Step 3 — Run Analysis</Label>
            <p style={{ fontFamily: F.sans, fontSize: 14, color: T.body, lineHeight: 1.7, margin: "0 0 16px" }}>The statistical engine will scan your contracts against peer groups using bootstrap confidence intervals, Bayesian analysis, and DOJ-calibrated thresholds.</p>
            <div style={{ padding: 16, background: T.greenSoft, border: `1px solid ${T.greenBdr}`, borderRadius: 8, textAlign: "center" }}>
              <div style={{ fontFamily: F.sans, fontSize: 14, fontWeight: 600, color: T.green }}>✓ Data quality check passed</div>
              <div style={{ fontFamily: F.sans, fontSize: 12, color: T.muted, marginTop: 4 }}>500 contracts · 0 missing required fields · Ready to analyze</div>
            </div>
          </div>
        )}
        {step === 3 && (
          <div>
            <Label>Step 4 — Review Inbox</Label>
            <p style={{ fontFamily: F.sans, fontSize: 14, color: T.body, lineHeight: 1.7, margin: "0 0 16px" }}>Your Risk Inbox shows all flagged contracts, prioritized by tier and confidence. Use keyboard shortcuts for fast triage.</p>
            <div style={{ padding: 16, background: T.sidebar, borderRadius: 8, border: `1px solid ${T.line}` }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                <Kbd>J</Kbd><Kbd>K</Kbd><span style={{ fontSize: 11, fontFamily: F.sans, color: T.muted }}>Navigate leads</span>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                <Kbd>↵</Kbd><span style={{ fontSize: 11, fontFamily: F.sans, color: T.muted }}>Open case packet</span>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <Kbd>1</Kbd>–<Kbd>5</Kbd><span style={{ fontSize: 11, fontFamily: F.sans, color: T.muted }}>Quick disposition</span>
              </div>
            </div>
          </div>
        )}
        {step === 4 && (
          <div>
            <Label>Step 5 — Open a Case Packet</Label>
            <p style={{ fontFamily: F.sans, fontSize: 14, color: T.body, lineHeight: 1.7, margin: "0 0 16px" }}>Each flagged contract gets a full case packet: executive summary, typology analysis, statistical evidence, peer comparison, and investigation steps.</p>
            <p style={{ fontFamily: F.sans, fontSize: 14, color: T.body, lineHeight: 1.7, margin: "0 0 16px" }}>Every finding includes full provenance (rulepack version, data snapshot, job ID) so results are reproducible and auditable.</p>
            <div style={{ padding: 16, background: T.goldSoft, borderRadius: 8, border: `1px solid ${T.gold}33`, textAlign: "center" }}>
              <div style={{ fontFamily: F.sans, fontSize: 14, fontWeight: 600, color: T.gold }}>You're ready.</div>
              <div style={{ fontFamily: F.sans, fontSize: 12, color: T.muted, marginTop: 4 }}>Click "Go to Inbox" to start your first triage session.</div>
            </div>
          </div>
        )}
      </div>

      <div style={{ display: "flex", justifyContent: "space-between" }}>
        <button onClick={() => setStep(s => Math.max(0, s - 1))} disabled={step === 0} style={{ padding: "8px 18px", borderRadius: 6, fontSize: 13, fontFamily: F.sans, fontWeight: 500, color: step === 0 ? T.ghost : T.body, background: "none", border: `1px solid ${step === 0 ? T.line : T.line}`, cursor: step === 0 ? "default" : "pointer" }}>← Back</button>
        {step < 4 ? (
          <button onClick={() => setStep(s => s + 1)} style={{ padding: "8px 18px", borderRadius: 6, fontSize: 13, fontFamily: F.sans, fontWeight: 600, color: "#FFF", background: T.gold, border: "none", cursor: "pointer" }}>Continue →</button>
        ) : (
          <button onClick={onComplete} style={{ padding: "8px 24px", borderRadius: 6, fontSize: 13, fontFamily: F.sans, fontWeight: 600, color: "#FFF", background: T.green, border: "none", cursor: "pointer" }}>Go to Inbox →</button>
        )}
      </div>
    </div>
  );
}

// ═══════════ APP SHELL ═══════════
export default function App() {
  const [page, setPage] = useState("onboarding");
  const [activeCase, setActiveCase] = useState(null);

  const { contracts, leads: initialLeads } = useMemo(() => generateFixtureData(500), []);
  const [leads, setLeads] = useState(initialLeads);

  const openCase = useCallback((lead) => {
    setActiveCase(lead);
    setPage("case");
  }, []);

  const goToInbox = useCallback((lead) => {
    if (lead && lead.id) { setActiveCase(lead); setPage("case"); }
    else { setActiveCase(null); setPage("inbox"); }
  }, []);

  const NAV = [
    { key: "inbox", label: "Risk Inbox", icon: "◉" },
    { key: "portfolio", label: "Portfolio", icon: "◫" },
    { key: "admin", label: "Admin", icon: "⚙" },
    { key: "demo", label: "Demo", icon: "▶" },
  ];

  if (page === "onboarding") {
    return (
      <div style={{ minHeight: "100vh", background: T.bg, fontFamily: F.sans }}>
        <header style={{ height: 52, background: T.header, display: "flex", alignItems: "center", padding: "0 20px" }}>
          <div style={{ width: 28, height: 28, borderRadius: 7, background: "linear-gradient(135deg, #C9A84C, #A68930)", display: "flex", alignItems: "center", justifyContent: "center", marginRight: 10 }}><span style={{ fontSize: 14 }}>☀</span></div>
          <span style={{ fontSize: 15, fontWeight: 700, letterSpacing: "0.08em", color: "#FFF" }}><span style={{ color: "#C9A84C" }}>SUN</span>LIGHT</span>
          <span style={{ marginLeft: 8, fontSize: 10, color: "rgba(255,255,255,0.35)" }}>Procurement Integrity Intelligence</span>
        </header>
        <main style={{ padding: "40px 24px" }}>
          <Onboarding onComplete={() => setPage("inbox")} />
        </main>
      </div>
    );
  }

  return (
    <div style={{ minHeight: "100vh", background: T.bg, fontFamily: F.sans, display: "flex", flexDirection: "column" }}>

      {/* Header */}
      <header style={{ height: 48, background: T.header, display: "flex", alignItems: "center", padding: "0 16px", zIndex: 100, flexShrink: 0 }}>
        <div onClick={() => { setPage("inbox"); setActiveCase(null); }} style={{ width: 26, height: 26, borderRadius: 6, background: "linear-gradient(135deg, #C9A84C, #A68930)", display: "flex", alignItems: "center", justifyContent: "center", marginRight: 8, cursor: "pointer" }}><span style={{ fontSize: 13 }}>☀</span></div>
        <span onClick={() => { setPage("inbox"); setActiveCase(null); }} style={{ fontSize: 14, fontWeight: 700, letterSpacing: "0.08em", color: "#FFF", cursor: "pointer", marginRight: 20 }}><span style={{ color: "#C9A84C" }}>SUN</span>LIGHT</span>

        {/* Navigation */}
        <div style={{ display: "flex", alignItems: "center", gap: 2 }}>
          {NAV.map(n => {
            const active = n.key === page || (n.key === "inbox" && page === "case");
            return (
              <button key={n.key} onClick={() => { setPage(n.key); setActiveCase(null); }} style={{
                display: "flex", alignItems: "center", gap: 5, padding: "5px 12px",
                borderRadius: 5, fontSize: 12, fontWeight: 500, fontFamily: F.sans,
                cursor: "pointer", border: "none",
                background: active ? "rgba(255,255,255,0.1)" : "transparent",
                color: active ? "#FFF" : "rgba(255,255,255,0.45)",
              }}><span style={{ fontSize: 11 }}>{n.icon}</span> {n.label}</button>
            );
          })}
        </div>

        <div style={{ flex: 1 }} />
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#4ADE80" }} />
          <span style={{ fontSize: 11, color: "rgba(255,255,255,0.4)", fontFamily: F.sans }}>Operational</span>
          <span style={{ marginLeft: 8, fontSize: 11, color: "rgba(255,255,255,0.25)", fontFamily: F.mono }}>demo_tenant</span>
        </div>
      </header>

      {/* Operations strip — visible on inbox and case */}
      {(page === "inbox" || page === "case") && <OpsStrip leads={leads} contracts={contracts} />}

      {/* Main */}
      <main style={{ flex: 1, padding: page === "demo" ? 0 : "16px 24px", overflow: page === "inbox" ? "hidden" : "auto" }}>
        {page === "inbox" && <RiskInbox leads={leads} setLeads={setLeads} contracts={contracts} onOpenCase={openCase} />}
        {page === "case" && activeCase && <CasePacket lead={activeCase} setLeads={setLeads} onBack={goToInbox} allLeads={leads} />}
        {page === "portfolio" && <Portfolio leads={leads} contracts={contracts} />}
        {page === "admin" && <Admin />}
        {page === "demo" && (
          <div style={{ maxWidth: 600, margin: "60px auto", textAlign: "center", padding: "0 24px" }}>
            <div style={{ width: 56, height: 56, borderRadius: 14, margin: "0 auto 20px", background: "linear-gradient(135deg, #C9A84C, #A68930)", display: "flex", alignItems: "center", justifyContent: "center" }}><span style={{ fontSize: 26 }}>☀</span></div>
            <h2 style={{ fontFamily: F.serif, fontSize: 22, color: T.ink, margin: "0 0 8px" }}>Demo Mode</h2>
            <p style={{ fontFamily: F.sans, fontSize: 14, color: T.muted, margin: "0 0 24px", lineHeight: 1.7 }}>The interactive live demo is available as a separate artifact (sunlight-demo.jsx). It lets prospects upload or select sample data and watch the engine process contracts in real time.</p>
            <p style={{ fontFamily: F.sans, fontSize: 13, color: T.caption }}>This operational workstation is running on fixture data: {contracts.length} contracts, {leads.length} leads.</p>
          </div>
        )}
      </main>
    </div>
  );
}
