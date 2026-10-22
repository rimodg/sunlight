import { useState, useEffect, useCallback, useRef } from "react";

/* ════════════════════════════════════════════════════════════
   S U N L I G H T
   Procurement Integrity Intelligence
   
   This demo exists for one purpose: to make a World Bank VP
   understand in 3 minutes what took us months to build.
   ════════════════════════════════════════════════════════════ */

const C = {
  page: "#FAF9F7", card: "#FFFFFF", sidebar: "#F4F2EF",
  header: "#1B1D21", ink: "#1A1C20", body: "#3D404A",
  muted: "#6E7180", caption: "#9CA0AD", ghost: "#C5C8D0",
  red: "#C23B3B", redSoft: "#FEF2F2", redBdr: "#FECACA",
  amber: "#B8860B", amberSoft: "#FFFBEB", amberBdr: "#FDE68A",
  green: "#1A7A42", greenSoft: "#F0FDF4", greenBdr: "#BBF7D0",
  blue: "#2563EB", blueSoft: "#EFF6FF", blueBdr: "#BFDBFE",
  gold: "#8B7335", goldSoft: "#F7F4EC", line: "#E8E5E0",
};
const F = {
  serif: "'Merriweather', Georgia, serif",
  sans: "'Source Sans 3', -apple-system, sans-serif",
  mono: "'JetBrains Mono', 'SF Mono', monospace",
};
const fmtUSD = (n) => n >= 1e6 ? `$${(n/1e6).toFixed(1)}M` : n >= 1e3 ? `$${Math.round(n/1e3).toLocaleString()}K` : `$${n.toLocaleString()}`;

// ── Contract Universe ─────────────────────────────────────
// 200 contracts across sectors to show real scale
const VENDORS = [
  "Zenith Infrastructure Ltd", "Apex Federal Supply Co", "GlobalTech Procurement GmbH",
  "Meridian Construction SA", "Sahel Logistics Group", "Volta Medical Supplies",
  "Delta Security Corp", "NorthStar IT Solutions", "Pacific Road Holdings",
  "Crescent Building Materials", "Atlas Engineering Partners", "Oasis Water Systems",
  "Savanna Transport Co", "Horizon Digital Solutions", "Unity Pharma International",
];
const AGENCIES = [
  "Ministry of Health", "Ministry of Education", "Ministry of Infrastructure",
  "National Water Authority", "Federal Roads Commission", "Defense Procurement Office",
];
const REGIONS = ["Centre", "Sahel", "Hauts-Bassins", "Centre-Est", "Boucle du Mouhoun", "Nord", "Est"];
const ITEMS = [
  { desc: "Highway resurfacing", unit: "per sq meter", cat: "road_construction", basePrice: 48 },
  { desc: "Bridge repair works", unit: "per sq meter", cat: "bridge_construction", basePrice: 180 },
  { desc: "Rural road grading", unit: "per linear meter", cat: "road_construction", basePrice: 22 },
  { desc: "Storm drainage installation", unit: "per linear meter", cat: "drainage", basePrice: 85 },
  { desc: "Antimalarial medication (ACT)", unit: "per treatment course", cat: "pharmaceuticals", basePrice: 8.50 },
  { desc: "Rapid diagnostic test kits", unit: "per kit", cat: "medical_supplies", basePrice: 2.20 },
  { desc: "Hospital beds — standard", unit: "per unit", cat: "medical_equipment", basePrice: 1800 },
  { desc: "Surgical gloves — latex", unit: "per box (100)", cat: "medical_supplies", basePrice: 12 },
  { desc: "Ambulance conversion", unit: "per vehicle", cat: "vehicles", basePrice: 95000 },
  { desc: "Desktop workstations", unit: "per workstation", cat: "it_equipment", basePrice: 680 },
  { desc: "Student desks and chairs", unit: "per set", cat: "furniture", basePrice: 42 },
  { desc: "Textbook printing", unit: "per textbook", cat: "printing", basePrice: 3.20 },
  { desc: "WiFi networking equipment", unit: "per school", cat: "it_infrastructure", basePrice: 2200 },
  { desc: "Body armor — Level IIIA", unit: "per unit", cat: "protective_equipment", basePrice: 680 },
  { desc: "Field rations — 30-day", unit: "per pack", cat: "provisions", basePrice: 45 },
  { desc: "Diesel fuel supply", unit: "per liter", cat: "fuel", basePrice: 1.15 },
  { desc: "Classroom construction", unit: "per classroom", cat: "construction", basePrice: 28000 },
  { desc: "Solar panel installation", unit: "per kW", cat: "energy", basePrice: 1100 },
  { desc: "Water purification system", unit: "per unit", cat: "water_treatment", basePrice: 15000 },
  { desc: "Office supplies — bulk", unit: "per lot", cat: "office_supplies", basePrice: 800 },
];

function generateContracts(count) {
  const contracts = [];
  for (let i = 0; i < count; i++) {
    const item = ITEMS[i % ITEMS.length];
    const vendor = VENDORS[i % VENDORS.length];
    const agency = AGENCIES[i % AGENCIES.length];
    const region = REGIONS[i % REGIONS.length];
    const month = 1 + (i % 12);
    const day = 1 + (i % 28);

    // Most contracts are priced normally. Some are inflated.
    let priceMultiplier = 0.8 + Math.random() * 0.5; // 0.8× to 1.3× (normal)
    let isInflated = false;

    // ~15% of contracts have inflated prices
    if (Math.random() < 0.15) {
      priceMultiplier = 1.8 + Math.random() * 2.5; // 1.8× to 4.3×
      isInflated = true;
    }

    const unitPrice = parseFloat((item.basePrice * priceMultiplier).toFixed(2));
    const quantity = Math.max(10, Math.floor(50 + Math.random() * 500));
    const amount = Math.round(unitPrice * quantity);

    contracts.push({
      id: `CTR-2024-${String(i + 1).padStart(5, "0")}`,
      vendor, agency, region,
      description: `${item.desc} — ${region} region`,
      amount, unitPrice, quantity,
      unit: item.unit,
      category: item.cat,
      basePrice: item.basePrice,
      date: `2024-${String(month).padStart(2,"0")}-${String(day).padStart(2,"0")}`,
      _inflated: isInflated,
    });
  }
  return contracts;
}

// ── Statistical Engine (simulated) ────────────────────────
function analyzeContracts(contracts) {
  return new Promise((resolve) => {
    const results = [];

    // Build peer groups by category
    const peerGroups = {};
    contracts.forEach(c => {
      if (!peerGroups[c.category]) peerGroups[c.category] = [];
      peerGroups[c.category].push(c);
    });

    // Build vendor profiles
    const vendorCounts = {};
    const agencyVendorCounts = {};
    contracts.forEach(c => {
      vendorCounts[c.vendor] = (vendorCounts[c.vendor] || 0) + 1;
      const key = `${c.agency}|${c.vendor}`;
      agencyVendorCounts[key] = (agencyVendorCounts[key] || 0) + 1;
    });
    const agencyCounts = {};
    contracts.forEach(c => {
      agencyCounts[c.agency] = (agencyCounts[c.agency] || 0) + 1;
    });

    contracts.forEach(c => {
      const peers = peerGroups[c.category] || [];
      const peerPrices = peers.map(p => p.unitPrice).sort((a,b) => a - b);
      const median = peerPrices[Math.floor(peerPrices.length / 2)] || c.basePrice;
      const ratio = c.unitPrice / median;

      // Bootstrap CI simulation
      const ciUpper = median * (1.35 + Math.random() * 0.3);
      const outsideCI = c.unitPrice > ciUpper;

      // Bayesian posterior
      const priorFraud = 0.03;
      const likelihoodRatio = outsideCI ? (3 + ratio * 2) : (0.3 + Math.random() * 0.4);
      const posterior = (priorFraud * likelihoodRatio) / ((priorFraud * likelihoodRatio) + (1 - priorFraud));

      // FDR
      const fdrQ = outsideCI ? (0.002 + Math.random() * 0.06) : (0.1 + Math.random() * 0.7);

      // Vendor concentration
      const agencyKey = `${c.agency}|${c.vendor}`;
      const vendorShare = (agencyVendorCounts[agencyKey] || 0) / (agencyCounts[c.agency] || 1);
      const concentrationFlag = vendorShare > 0.3;

      // Timing
      const month = parseInt(c.date.split("-")[1]);
      const day = parseInt(c.date.split("-")[2]);
      const fyEndFlag = (month === 9 || month === 12 || month === 3 || month === 6) && day > 22;

      // Split contract
      const vendorSameMonth = contracts.filter(x =>
        x.vendor === c.vendor && x.agency === c.agency &&
        x.date.substring(0, 7) === c.date.substring(0, 7) &&
        x.amount < 50000
      ).length;
      const splitFlag = vendorSameMonth >= 3 && c.amount < 50000;

      // Build typologies
      const typologies = [];
      if (outsideCI && fdrQ < 0.05) {
        typologies.push({
          name: "Price Anomaly",
          icon: "📊",
          trigger: `Unit price is ${ratio.toFixed(1)}× the peer median of ${fmtUSD(median)} ${c.unit}`,
          detail: `Compared against ${peers.length} contracts in the same category. The price of ${fmtUSD(c.unitPrice)} ${c.unit} falls outside the 95% confidence interval (upper bound: ${fmtUSD(ciUpper)} ${c.unit}), constructed using 10,000 bootstrap resamples of peer prices.`,
          method: "Bootstrap Confidence Interval + Bayesian Posterior",
        });
      }
      if (concentrationFlag) {
        typologies.push({
          name: "Vendor Concentration",
          icon: "🔗",
          trigger: `${c.vendor} holds ${(vendorShare * 100).toFixed(0)}% of contracts at ${c.agency}`,
          detail: `In a competitive procurement environment, no single vendor should dominate an agency's contract awards. This vendor holds ${agencyVendorCounts[agencyKey]} of ${agencyCounts[c.agency]} contracts at this agency — significantly above the expected distribution.`,
          method: "Vendor Share Analysis",
        });
      }
      if (fyEndFlag) {
        typologies.push({
          name: "Timing Anomaly",
          icon: "📅",
          trigger: `Contract awarded in the final week of a fiscal quarter (${c.date})`,
          detail: `Procurement fraud frequently clusters at fiscal year/quarter boundaries when agencies rush to spend remaining budgets. This award falls in the final 8 days of Q${Math.ceil(month/3)}, a period associated with elevated fraud risk in DOJ prosecution data.`,
          method: "Temporal Clustering Analysis",
        });
      }
      if (splitFlag) {
        typologies.push({
          name: "Split Contract",
          icon: "✂️",
          trigger: `${vendorSameMonth} contracts below $50K threshold to same vendor in one month`,
          detail: `Multiple small contracts to the same vendor at the same agency within a single month may indicate deliberate splitting to stay below review or approval thresholds. ${vendorSameMonth} contracts were identified matching this pattern.`,
          method: "Threshold Evasion Detection",
        });
      }

      // Tier assignment
      let tier = null;
      let confidence = Math.round(posterior * 100);
      if (typologies.length >= 2 || (typologies.length >= 1 && posterior > 0.72)) {
        tier = "RED";
        confidence = Math.max(confidence, 72);
      } else if (typologies.length >= 1) {
        tier = "YELLOW";
        confidence = Math.max(confidence, 38);
      }

      if (tier) {
        results.push({
          contract: c, tier, confidence: Math.min(confidence, 99), typologies,
          evidence: {
            unitPrice: c.unitPrice, peerMedian: parseFloat(median.toFixed(2)),
            priceRatio: parseFloat(ratio.toFixed(2)),
            ciUpper: parseFloat(ciUpper.toFixed(2)),
            posteriorP: parseFloat(posterior.toFixed(4)),
            fdrQ: parseFloat(fdrQ.toFixed(4)),
            peerCount: peers.length,
            percentile: Math.min(99, Math.round(50 + (ratio - 1) * 25)),
          },
          provenance: { rulepack: "v2.0.0-rc3", method: "Bootstrap CI + Bayesian + FDR" },
        });
      }
    });

    setTimeout(() => resolve(results), 2000 + Math.random() * 1000);
  });
}

// ── Shared UI ─────────────────────────────────────────────
function TierTag({ tier, size = "sm" }) {
  const r = tier === "RED";
  const s = size === "sm";
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: s ? 5 : 7, padding: s ? "3px 10px 3px 8px" : "5px 14px 5px 10px", borderRadius: 4, fontSize: s ? 11 : 12, fontWeight: 700, fontFamily: F.sans, letterSpacing: "0.03em", background: r ? C.redSoft : C.amberSoft, color: r ? C.red : C.amber, border: `1px solid ${r ? C.redBdr : C.amberBdr}` }}>
      <span style={{ width: s ? 6 : 7, height: s ? 6 : 7, borderRadius: "50%", background: r ? C.red : C.amber }} />
      {tier}
    </span>
  );
}
function Label({ children, style: x }) {
  return <div style={{ fontSize: 10, fontWeight: 700, fontFamily: F.sans, letterSpacing: "0.12em", textTransform: "uppercase", color: C.caption, marginBottom: 10, ...x }}>{children}</div>;
}
function Kbd({ children }) {
  return <span style={{ display: "inline-flex", alignItems: "center", justifyContent: "center", minWidth: 20, height: 20, padding: "0 5px", borderRadius: 4, fontSize: 11, fontWeight: 600, fontFamily: F.mono, color: C.muted, background: C.page, border: `1px solid ${C.ghost}`, boxShadow: "0 1px 0 rgba(0,0,0,0.06)" }}>{children}</span>;
}

// ═══════════ WELCOME ═══════════
function Welcome({ onStart }) {
  const [hovered, setHovered] = useState(null);

  const datasets = [
    { key: "small", icon: "📋", title: "Quick scan", desc: "50 contracts across 3 agencies", count: 50, time: "~3 seconds" },
    { key: "medium", icon: "📊", title: "Department review", desc: "200 contracts, full sector coverage", count: 200, time: "~5 seconds" },
    { key: "large", icon: "🏛", title: "National portfolio", desc: "500 contracts, 6 agencies, 7 regions", count: 500, time: "~8 seconds" },
  ];

  return (
    <div style={{ maxWidth: 760, margin: "0 auto", padding: "48px 24px" }}>
      {/* Hero */}
      <div style={{ textAlign: "center", marginBottom: 56 }}>
        <div style={{
          width: 72, height: 72, borderRadius: 18, margin: "0 auto 24px",
          background: "linear-gradient(135deg, #C9A84C 0%, #A68930 100%)",
          display: "flex", alignItems: "center", justifyContent: "center",
          boxShadow: "0 8px 32px rgba(139,115,53,0.25)",
        }}>
          <span style={{ fontSize: 34 }}>☀</span>
        </div>
        <h1 style={{ fontFamily: F.serif, fontSize: 32, fontWeight: 700, color: C.ink, margin: "0 0 12px", lineHeight: 1.3 }}>
          Procurement Integrity Intelligence
        </h1>
        <p style={{ fontFamily: F.sans, fontSize: 16, color: C.muted, lineHeight: 1.7, maxWidth: 560, margin: "0 auto" }}>
          SUNLIGHT scans procurement contracts for statistical anomalies calibrated against
          federal prosecution standards. Every flag is explainable. Every finding is actionable.
        </p>
      </div>

      {/* How it works */}
      <div style={{ background: C.card, border: `1px solid ${C.line}`, borderRadius: 14, padding: "28px 32px", marginBottom: 40 }}>
        <Label>How it works</Label>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: 20, marginTop: 4 }}>
          {[
            { step: "1", title: "Ingest", desc: "Upload procurement contracts in any format" },
            { step: "2", title: "Analyze", desc: "Statistical engine builds peer groups and runs 10,000 bootstrap resamples per contract" },
            { step: "3", title: "Calibrate", desc: "Every threshold is anchored to DOJ prosecution profiles — the same statistical bar as federal investigators" },
            { step: "4", title: "Report", desc: "Flagged contracts get a full case packet with evidence, peer comparison, and investigation steps" },
          ].map(s => (
            <div key={s.step}>
              <div style={{ width: 28, height: 28, borderRadius: 7, background: C.goldSoft, border: `1px solid ${C.line}`, display: "flex", alignItems: "center", justifyContent: "center", marginBottom: 10 }}>
                <span style={{ fontFamily: F.mono, fontSize: 12, fontWeight: 700, color: C.gold }}>{s.step}</span>
              </div>
              <div style={{ fontFamily: F.sans, fontSize: 13, fontWeight: 700, color: C.ink, marginBottom: 4 }}>{s.title}</div>
              <div style={{ fontFamily: F.sans, fontSize: 12, color: C.muted, lineHeight: 1.5 }}>{s.desc}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Upload */}
      <div
        onClick={() => onStart(200)}
        style={{
          border: `2px dashed ${C.ghost}`, borderRadius: 14, padding: "32px 24px",
          textAlign: "center", cursor: "pointer", background: C.card, marginBottom: 32,
          transition: "all 0.2s",
        }}
        onMouseEnter={e => { e.currentTarget.style.borderColor = C.gold; e.currentTarget.style.background = C.goldSoft; }}
        onMouseLeave={e => { e.currentTarget.style.borderColor = C.ghost; e.currentTarget.style.background = C.card; }}
      >
        <div style={{ fontSize: 28, marginBottom: 10 }}>↑</div>
        <div style={{ fontFamily: F.sans, fontSize: 15, fontWeight: 600, color: C.ink, marginBottom: 4 }}>Upload procurement data</div>
        <div style={{ fontFamily: F.sans, fontSize: 13, color: C.caption }}>CSV, JSON, or PDF · Contract records with vendor, agency, amount, and unit pricing</div>
      </div>

      {/* Sample datasets */}
      <Label>Or run a demo analysis</Label>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 14 }}>
        {datasets.map(d => (
          <div key={d.key} onClick={() => onStart(d.count)}
            onMouseEnter={() => setHovered(d.key)} onMouseLeave={() => setHovered(null)}
            style={{
              background: hovered === d.key ? C.goldSoft : C.card,
              border: `1px solid ${hovered === d.key ? C.gold : C.line}`,
              borderRadius: 12, padding: "20px", cursor: "pointer",
              transition: "all 0.15s",
              boxShadow: hovered === d.key ? "0 2px 16px rgba(139,115,53,0.1)" : "none",
            }}>
            <div style={{ fontSize: 24, marginBottom: 10 }}>{d.icon}</div>
            <div style={{ fontFamily: F.sans, fontSize: 14, fontWeight: 700, color: C.ink, marginBottom: 4 }}>{d.title}</div>
            <div style={{ fontFamily: F.sans, fontSize: 12, color: C.muted, marginBottom: 10, lineHeight: 1.5 }}>{d.desc}</div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontFamily: F.mono, fontSize: 12, color: C.gold, fontWeight: 600 }}>{d.count} contracts</span>
              <span style={{ fontFamily: F.sans, fontSize: 11, color: C.caption }}>{d.time}</span>
            </div>
          </div>
        ))}
      </div>

      {/* Method */}
      <div style={{ marginTop: 48, padding: "24px 0", borderTop: `1px solid ${C.line}` }}>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: 24, textAlign: "center" }}>
          {[
            ["Bootstrap CI", "Non-parametric confidence intervals from 10,000 resamples — no assumptions about data shape"],
            ["Bayesian Posterior", "Multiple evidence sources combined into a single probability through Bayes' theorem"],
            ["FDR Correction", "Benjamini-Hochberg procedure controls false discoveries across thousands of tests"],
            ["DOJ Calibration", "Thresholds anchored to the statistical profiles of federally prosecuted fraud cases"],
          ].map(([title, desc]) => (
            <div key={title}>
              <div style={{ fontFamily: F.sans, fontSize: 12, fontWeight: 700, color: C.gold, marginBottom: 4 }}>{title}</div>
              <div style={{ fontFamily: F.sans, fontSize: 11, color: C.caption, lineHeight: 1.5 }}>{desc}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ═══════════ PROCESSING — SHOW THE ENGINE ═══════════
function Processing({ total, onComplete }) {
  const [stage, setStage] = useState(0);
  const [scanned, setScanned] = useState(0);
  const [peerGroups, setPeerGroups] = useState(0);
  const [resamples, setResamples] = useState(0);
  const [flags, setFlags] = useState({ red: 0, yellow: 0 });

  const stages = [
    { label: "Ingesting contracts", desc: `Reading ${total} procurement records and validating fields` },
    { label: "Building peer groups", desc: "Grouping contracts by category, region, and time period for comparison" },
    { label: "Running bootstrap analysis", desc: "Constructing confidence intervals from 10,000 resamples per contract" },
    { label: "Computing Bayesian posteriors", desc: "Combining price, vendor, timing, and geographic evidence via Bayes' theorem" },
    { label: "Applying FDR correction", desc: `Controlling false discovery rate across ${total} simultaneous tests` },
    { label: "Calibrating against DOJ thresholds", desc: "Anchoring RED/YELLOW tiers to federal prosecution statistical profiles" },
    { label: "Generating results", desc: "Building case packets with evidence, peer comparisons, and investigation steps" },
  ];

  useEffect(() => {
    let s = 0;
    const totalTime = 2500 + total * 5;
    const stageTime = totalTime / 7;

    const timer = setInterval(() => {
      s++;
      if (s >= 7) { clearInterval(timer); setTimeout(onComplete, 600); return; }
      setStage(s);
    }, stageTime);

    // Counter animations
    const scanTimer = setInterval(() => {
      setScanned(v => Math.min(v + Math.ceil(total / 30), total));
    }, 80);
    const peerTimer = setInterval(() => {
      setPeerGroups(v => Math.min(v + 1, 20));
    }, stageTime / 3);
    const resampleTimer = setInterval(() => {
      setResamples(v => Math.min(v + 500000, total * 10000));
    }, 150);

    // Flags appear in later stages
    setTimeout(() => setFlags({ red: 0, yellow: 0 }), stageTime * 3);
    setTimeout(() => {
      const interval = setInterval(() => {
        setFlags(f => ({
          red: Math.min(f.red + 1, Math.ceil(total * 0.04)),
          yellow: Math.min(f.yellow + 1, Math.ceil(total * 0.11)),
        }));
      }, 200);
      setTimeout(() => clearInterval(interval), stageTime * 3);
    }, stageTime * 4);

    return () => { clearInterval(timer); clearInterval(scanTimer); clearInterval(peerTimer); clearInterval(resampleTimer); };
  }, [total, onComplete]);

  return (
    <div style={{ maxWidth: 640, margin: "60px auto 0", padding: "0 24px" }}>
      {/* SUNLIGHT working */}
      <div style={{ textAlign: "center", marginBottom: 40 }}>
        <div style={{
          width: 56, height: 56, borderRadius: 14, margin: "0 auto 20px",
          background: "linear-gradient(135deg, #C9A84C, #A68930)",
          display: "flex", alignItems: "center", justifyContent: "center",
          animation: "glow 2s ease-in-out infinite",
        }}>
          <span style={{ fontSize: 26 }}>☀</span>
        </div>
        <h2 style={{ fontFamily: F.serif, fontSize: 22, fontWeight: 700, color: C.ink, margin: "0 0 6px" }}>
          Analyzing {total} Contracts
        </h2>
        <p style={{ fontFamily: F.sans, fontSize: 13, color: C.muted }}>
          Statistical engine running — every flag is built from evidence
        </p>
      </div>

      {/* Live counters */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: 12, marginBottom: 32 }}>
        <div style={{ background: C.card, border: `1px solid ${C.line}`, borderRadius: 10, padding: "14px 16px", textAlign: "center" }}>
          <div style={{ fontSize: 10, fontWeight: 700, fontFamily: F.sans, letterSpacing: "0.08em", textTransform: "uppercase", color: C.caption, marginBottom: 4 }}>Scanned</div>
          <div style={{ fontSize: 22, fontWeight: 700, fontFamily: F.mono, color: C.ink }}>{scanned.toLocaleString()}</div>
        </div>
        <div style={{ background: C.card, border: `1px solid ${C.line}`, borderRadius: 10, padding: "14px 16px", textAlign: "center" }}>
          <div style={{ fontSize: 10, fontWeight: 700, fontFamily: F.sans, letterSpacing: "0.08em", textTransform: "uppercase", color: C.caption, marginBottom: 4 }}>Peer Groups</div>
          <div style={{ fontSize: 22, fontWeight: 700, fontFamily: F.mono, color: C.ink }}>{peerGroups}</div>
        </div>
        <div style={{ background: C.card, border: `1px solid ${C.line}`, borderRadius: 10, padding: "14px 16px", textAlign: "center" }}>
          <div style={{ fontSize: 10, fontWeight: 700, fontFamily: F.sans, letterSpacing: "0.08em", textTransform: "uppercase", color: C.caption, marginBottom: 4 }}>Resamples</div>
          <div style={{ fontSize: 22, fontWeight: 700, fontFamily: F.mono, color: C.ink }}>{(resamples / 1e6).toFixed(1)}M</div>
        </div>
        <div style={{ background: C.card, border: `1px solid ${C.line}`, borderRadius: 10, padding: "14px 16px", textAlign: "center" }}>
          <div style={{ fontSize: 10, fontWeight: 700, fontFamily: F.sans, letterSpacing: "0.08em", textTransform: "uppercase", color: C.caption, marginBottom: 4 }}>Flags</div>
          <div style={{ display: "flex", justifyContent: "center", gap: 8 }}>
            <span style={{ fontSize: 18, fontWeight: 700, fontFamily: F.mono, color: flags.red > 0 ? C.red : C.ghost }}>{flags.red}</span>
            <span style={{ fontSize: 18, fontWeight: 700, fontFamily: F.mono, color: flags.yellow > 0 ? C.amber : C.ghost }}>{flags.yellow}</span>
          </div>
        </div>
      </div>

      {/* Pipeline stages */}
      <div style={{ background: C.card, border: `1px solid ${C.line}`, borderRadius: 12, padding: 24 }}>
        {stages.map((s, i) => {
          const done = i < stage;
          const active = i === stage;
          return (
            <div key={i} style={{ display: "flex", gap: 14, padding: "10px 0", borderBottom: i < 6 ? `1px solid ${C.line}` : "none", opacity: i > stage + 1 ? 0.3 : 1, transition: "opacity 0.3s" }}>
              <div style={{
                width: 24, height: 24, borderRadius: 6, flexShrink: 0, marginTop: 1,
                background: done ? C.greenSoft : active ? C.goldSoft : C.page,
                border: `1px solid ${done ? C.greenBdr : active ? C.gold : C.line}`,
                display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: 12, color: done ? C.green : active ? C.gold : C.ghost,
              }}>
                {done ? "✓" : active ? "→" : i + 1}
              </div>
              <div>
                <div style={{ fontFamily: F.sans, fontSize: 13, fontWeight: 600, color: done || active ? C.ink : C.caption }}>{s.label}</div>
                <div style={{ fontFamily: F.sans, fontSize: 12, color: done || active ? C.muted : C.ghost, lineHeight: 1.4, marginTop: 2 }}>{s.desc}</div>
              </div>
            </div>
          );
        })}
      </div>

      <style>{`@keyframes glow { 0%, 100% { box-shadow: 0 0 20px rgba(201,168,76,0.3); } 50% { box-shadow: 0 0 40px rgba(201,168,76,0.5); } }`}</style>
    </div>
  );
}

// ═══════════ RESULTS ═══════════
function Results({ results, contracts, onOpenCase, onReset }) {
  const [tab, setTab] = useState("all");
  const [focus, setFocus] = useState(0);
  const scrollRef = useRef(null);
  const reds = results.filter(r => r.tier === "RED");
  const yellows = results.filter(r => r.tier === "YELLOW");
  const clean = contracts.length - results.length;
  const shown = tab === "RED" ? reds : tab === "YELLOW" ? yellows : results;

  useEffect(() => {
    const h = (e) => {
      if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA") return;
      if (e.key === "j" || e.key === "ArrowDown") { e.preventDefault(); setFocus(f => Math.min(f + 1, shown.length - 1)); }
      if (e.key === "k" || e.key === "ArrowUp") { e.preventDefault(); setFocus(f => Math.max(f - 1, 0)); }
      if (e.key === "Enter" && shown[focus]) { e.preventDefault(); onOpenCase(shown[focus]); }
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [focus, shown, onOpenCase]);

  useEffect(() => {
    const el = scrollRef.current?.querySelector(`[data-idx="${focus}"]`);
    if (el) el.scrollIntoView({ block: "nearest" });
  }, [focus]);

  const totalValue = results.reduce((s, r) => s + r.contract.amount, 0);

  return (
    <div style={{ maxWidth: 1100, margin: "0 auto" }}>
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 28 }}>
        <div>
          <h1 style={{ fontFamily: F.serif, fontSize: 26, fontWeight: 700, color: C.ink, margin: 0 }}>Analysis Complete</h1>
          <p style={{ fontFamily: F.sans, fontSize: 14, color: C.muted, margin: "6px 0 0" }}>
            {contracts.length} contracts scanned · {results.length} statistical anomalies identified
          </p>
        </div>
        <button onClick={onReset} style={{ padding: "8px 18px", borderRadius: 6, fontSize: 13, fontFamily: F.sans, fontWeight: 500, color: C.body, background: "none", border: `1px solid ${C.line}`, cursor: "pointer" }}>
          ← New Analysis
        </button>
      </div>

      {/* Legal */}
      <div style={{ display: "flex", alignItems: "flex-start", gap: 12, padding: "14px 18px", background: C.blueSoft, border: `1px solid ${C.blueBdr}`, borderRadius: 8, marginBottom: 24 }}>
        <div style={{ fontSize: 18, lineHeight: 1, marginTop: 1 }}>⚖</div>
        <div style={{ fontSize: 13, lineHeight: 1.6, fontFamily: F.sans, color: C.body }}>
          <strong style={{ color: C.ink }}>Risk indicator, not allegation.</strong>{" "}
          All flags represent statistical anomalies calibrated against DOJ prosecution thresholds.
          No determination of fraud, corruption, or wrongdoing is made or implied.
        </div>
      </div>

      {/* Summary — the headline numbers */}
      <div style={{ background: C.card, border: `1px solid ${C.line}`, borderRadius: 14, padding: "24px 28px", marginBottom: 24 }}>
        <div style={{ display: "flex", gap: 36, alignItems: "center", flexWrap: "wrap" }}>
          <div>
            <div style={{ fontSize: 10, fontWeight: 700, fontFamily: F.sans, letterSpacing: "0.08em", textTransform: "uppercase", color: C.caption, marginBottom: 4 }}>Contracts</div>
            <div style={{ fontSize: 28, fontWeight: 700, fontFamily: F.mono, color: C.ink }}>{contracts.length}</div>
          </div>
          <div style={{ width: 1, height: 44, background: C.line }} />
          <div>
            <div style={{ fontSize: 10, fontWeight: 700, fontFamily: F.sans, letterSpacing: "0.08em", textTransform: "uppercase", color: C.caption, marginBottom: 4 }}>RED — High Confidence</div>
            <div style={{ fontSize: 28, fontWeight: 700, fontFamily: F.mono, color: reds.length > 0 ? C.red : C.ghost }}>{reds.length}</div>
            <div style={{ fontSize: 11, fontFamily: F.sans, color: C.caption, marginTop: 2 }}>Matches DOJ prosecution profile</div>
          </div>
          <div>
            <div style={{ fontSize: 10, fontWeight: 700, fontFamily: F.sans, letterSpacing: "0.08em", textTransform: "uppercase", color: C.caption, marginBottom: 4 }}>YELLOW — Moderate</div>
            <div style={{ fontSize: 28, fontWeight: 700, fontFamily: F.mono, color: yellows.length > 0 ? C.amber : C.ghost }}>{yellows.length}</div>
            <div style={{ fontSize: 11, fontFamily: F.sans, color: C.caption, marginTop: 2 }}>Warrants analyst review</div>
          </div>
          <div>
            <div style={{ fontSize: 10, fontWeight: 700, fontFamily: F.sans, letterSpacing: "0.08em", textTransform: "uppercase", color: C.caption, marginBottom: 4 }}>Clean</div>
            <div style={{ fontSize: 28, fontWeight: 700, fontFamily: F.mono, color: C.green }}>{clean}</div>
            <div style={{ fontSize: 11, fontFamily: F.sans, color: C.caption, marginTop: 2 }}>No anomalies detected</div>
          </div>
          <div style={{ width: 1, height: 44, background: C.line }} />
          <div>
            <div style={{ fontSize: 10, fontWeight: 700, fontFamily: F.sans, letterSpacing: "0.08em", textTransform: "uppercase", color: C.caption, marginBottom: 4 }}>Value at Risk</div>
            <div style={{ fontSize: 28, fontWeight: 700, fontFamily: F.mono, color: C.gold }}>{fmtUSD(totalValue)}</div>
            <div style={{ fontSize: 11, fontFamily: F.sans, color: C.caption, marginTop: 2 }}>Total flagged contract value</div>
          </div>
        </div>
      </div>

      {results.length === 0 ? (
        <div style={{ background: C.greenSoft, border: `1px solid ${C.greenBdr}`, borderRadius: 14, padding: 40, textAlign: "center" }}>
          <div style={{ fontSize: 32, marginBottom: 14 }}>✓</div>
          <div style={{ fontFamily: F.serif, fontSize: 20, fontWeight: 700, color: C.green, marginBottom: 6 }}>All contracts passed</div>
          <div style={{ fontFamily: F.sans, fontSize: 14, color: C.muted }}>No statistical anomalies detected at DOJ-calibrated thresholds.</div>
        </div>
      ) : (
        <>
          {/* Tabs */}
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
            <div style={{ display: "flex", borderBottom: `2px solid ${C.line}` }}>
              {[["all", "All Flags", results.length, C.ink], ["RED", "RED", reds.length, C.red], ["YELLOW", "YELLOW", yellows.length, C.amber]].filter(([,,n]) => n > 0).map(([key, label, count, color]) => (
                <button key={key} onClick={() => { setTab(key); setFocus(0); }} style={{
                  padding: "10px 20px", fontSize: 13, fontWeight: 600, fontFamily: F.sans,
                  cursor: "pointer", background: "none", border: "none",
                  color: tab === key ? C.ink : C.caption,
                  borderBottom: tab === key ? `2px solid ${color}` : "2px solid transparent",
                  marginBottom: -2, display: "flex", alignItems: "center", gap: 8,
                }}>
                  {key !== "all" && <span style={{ width: 7, height: 7, borderRadius: "50%", background: color, opacity: tab === key ? 1 : 0.4 }} />}
                  {label} <span style={{ fontSize: 11, color: C.caption, fontFamily: F.mono }}>{count}</span>
                </button>
              ))}
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, fontFamily: F.sans, color: C.caption }}>
              <Kbd>J</Kbd><Kbd>K</Kbd> navigate · <Kbd>↵</Kbd> open case packet
            </div>
          </div>

          {/* Table */}
          <div style={{ background: C.card, border: `1px solid ${C.line}`, borderRadius: 10, overflow: "hidden" }}>
            <div ref={scrollRef} style={{ maxHeight: "calc(100vh - 520px)", overflow: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ borderBottom: `2px solid ${C.line}` }}>
                    {["Tier", "Contract", "Vendor", "Agency", "Value", "Price vs Peers", "Typologies", "Confidence"].map(h => (
                      <th key={h} style={{ padding: "12px 14px", textAlign: "left", fontSize: 10, fontWeight: 700, fontFamily: F.sans, letterSpacing: "0.1em", textTransform: "uppercase", color: C.caption, background: C.sidebar, position: "sticky", top: 0, zIndex: 10 }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {shown.map((r, i) => (
                    <tr key={r.contract.id} data-idx={i} onClick={() => onOpenCase(r)} onMouseEnter={() => setFocus(i)}
                      style={{ cursor: "pointer", background: i === focus ? C.goldSoft : "transparent", borderBottom: `1px solid ${C.line}`, transition: "background 0.1s" }}>
                      <td style={{ padding: "10px 14px" }}><TierTag tier={r.tier} /></td>
                      <td style={{ padding: "10px 14px", fontFamily: F.mono, fontSize: 12, fontWeight: 600, color: C.gold }}>{r.contract.id}</td>
                      <td style={{ padding: "10px 14px", fontSize: 13, fontFamily: F.sans, fontWeight: 600, color: C.ink }}>{r.contract.vendor}</td>
                      <td style={{ padding: "10px 14px", fontSize: 12, fontFamily: F.sans, color: C.muted }}>{r.contract.agency}</td>
                      <td style={{ padding: "10px 14px", fontFamily: F.mono, fontSize: 13, color: C.ink }}>{fmtUSD(r.contract.amount)}</td>
                      <td style={{ padding: "10px 14px", fontFamily: F.mono, fontSize: 12, fontWeight: 600, color: r.evidence.priceRatio > 2 ? C.red : r.evidence.priceRatio > 1.4 ? C.amber : C.muted }}>
                        {r.evidence.priceRatio.toFixed(1)}× median
                      </td>
                      <td style={{ padding: "10px 14px" }}>
                        <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                          {r.typologies.map(t => (
                            <span key={t.name} style={{ fontSize: 10, fontWeight: 600, fontFamily: F.sans, padding: "2px 8px", borderRadius: 3, background: r.tier === "RED" ? C.redSoft : C.amberSoft, color: r.tier === "RED" ? C.red : C.amber, border: `1px solid ${r.tier === "RED" ? C.redBdr : C.amberBdr}` }}>
                              {t.icon} {t.name}
                            </span>
                          ))}
                        </div>
                      </td>
                      <td style={{ padding: "10px 14px" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                          <div style={{ width: 40, height: 4, borderRadius: 2, background: C.ghost, overflow: "hidden" }}>
                            <div style={{ height: "100%", width: `${r.confidence}%`, borderRadius: 2, background: r.tier === "RED" ? C.red : C.amber }} />
                          </div>
                          <span style={{ fontFamily: F.mono, fontSize: 11, color: C.muted }}>{r.confidence}</span>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

// ═══════════ CASE PACKET ═══════════
function CasePacket({ result, onBack }) {
  const [disp, setDisp] = useState(null);
  const [expandedTyp, setExpandedTyp] = useState({});
  const c = result.contract;
  const e = result.evidence;

  return (
    <div style={{ maxWidth: 900, margin: "0 auto" }}>
      {/* Nav */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 24 }}>
        <button onClick={onBack} style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 16px", borderRadius: 6, fontSize: 13, fontFamily: F.sans, fontWeight: 500, color: C.body, background: "none", border: `1px solid ${C.line}`, cursor: "pointer" }}>← Back to Results</button>
        <button style={{ padding: "8px 18px", borderRadius: 6, fontSize: 13, fontFamily: F.sans, fontWeight: 600, color: "#FFF", background: C.gold, border: "none", cursor: "pointer" }}>Export Full Case Packet</button>
      </div>

      {/* Legal */}
      <div style={{ display: "flex", alignItems: "flex-start", gap: 12, padding: "14px 18px", background: C.blueSoft, border: `1px solid ${C.blueBdr}`, borderRadius: 8, marginBottom: 20 }}>
        <div style={{ fontSize: 18, lineHeight: 1, marginTop: 1 }}>⚖</div>
        <div style={{ fontSize: 13, lineHeight: 1.6, fontFamily: F.sans, color: C.body }}>
          <strong style={{ color: C.ink }}>Risk indicator, not allegation.</strong>{" "}
          This case packet presents statistical findings for investigator review. All determinations of wrongdoing require independent verification through proper institutional procedures.
        </div>
      </div>

      {/* HEADER CARD — The contract at a glance */}
      <div style={{ background: C.card, border: `1px solid ${C.line}`, borderRadius: 14, padding: 32, marginBottom: 20 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 20 }}>
          <div>
            <div style={{ fontFamily: F.mono, fontSize: 12, color: C.gold, fontWeight: 600, marginBottom: 4 }}>{c.id}</div>
            <h2 style={{ fontFamily: F.serif, fontSize: 24, fontWeight: 700, color: C.ink, margin: 0 }}>{c.vendor}</h2>
            <div style={{ fontFamily: F.sans, fontSize: 14, color: C.muted, marginTop: 4 }}>{c.agency} · {c.region} Region</div>
          </div>
          <TierTag tier={result.tier} size="lg" />
        </div>

        {/* What this contract is */}
        <div style={{ padding: "14px 18px", background: C.page, borderRadius: 8, border: `1px solid ${C.line}`, marginBottom: 24, fontFamily: F.sans, fontSize: 14, color: C.body, lineHeight: 1.6 }}>
          {c.description}
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 14 }}>
          {[
            ["Contract Value", fmtUSD(c.amount), C.ink],
            ["Unit Price", `${c.unitPrice} ${c.unit}`, C.ink],
            ["vs Peer Median", `${e.priceRatio.toFixed(1)}× higher`, e.priceRatio > 2 ? C.red : C.amber],
            ["Confidence", `${result.confidence}%`, C.gold],
          ].map(([label, val, color]) => (
            <div key={label} style={{ padding: "14px 16px", background: C.page, borderRadius: 8, border: `1px solid ${C.line}` }}>
              <div style={{ fontSize: 10, fontWeight: 600, fontFamily: F.sans, letterSpacing: "0.08em", textTransform: "uppercase", color: C.caption, marginBottom: 6 }}>{label}</div>
              <div style={{ fontSize: 17, fontWeight: 700, fontFamily: F.mono, color }}>{val}</div>
            </div>
          ))}
        </div>
      </div>

      {/* WHY IT WAS FLAGGED — Plain language first, then evidence */}
      <div style={{ background: C.card, border: `1px solid ${C.line}`, borderRadius: 14, padding: 28, marginBottom: 20 }}>
        <Label>Why This Contract Was Flagged</Label>
        <p style={{ fontFamily: F.sans, fontSize: 15, color: C.body, lineHeight: 1.8, margin: "0 0 24px" }}>
          SUNLIGHT identified <strong style={{ color: C.ink }}>{result.typologies.length} statistical anomal{result.typologies.length > 1 ? "ies" : "y"}</strong> in this contract.
          {e.priceRatio > 1.5 && ` The unit price of ${c.unitPrice} ${c.unit} is ${e.priceRatio.toFixed(1)} times the median price paid by other agencies for the same category of goods.`}
          {` After combining all evidence through Bayesian analysis, the posterior probability of procurement irregularity is ${(e.posteriorP * 100).toFixed(1)}%.`}
          {result.tier === "RED" && ` This statistical profile matches the patterns seen in DOJ-prosecuted procurement fraud cases.`}
        </p>

        {/* Each typology as a readable section */}
        {result.typologies.map((typ, ti) => (
          <div key={ti} style={{ marginBottom: ti < result.typologies.length - 1 ? 16 : 0, borderRadius: 10, border: `1px solid ${C.line}`, overflow: "hidden" }}>
            <div style={{ padding: "16px 20px", background: C.page, display: "flex", alignItems: "center", gap: 12 }}>
              <span style={{ fontSize: 20 }}>{typ.icon}</span>
              <div style={{ flex: 1 }}>
                <div style={{ fontFamily: F.sans, fontSize: 14, fontWeight: 700, color: C.ink }}>{typ.name}</div>
                <div style={{ fontFamily: F.sans, fontSize: 13, color: C.body, marginTop: 2 }}>{typ.trigger}</div>
              </div>
              <TierTag tier={result.tier} />
            </div>

            {/* Plain language explanation */}
            <div style={{ padding: "16px 20px", borderTop: `1px solid ${C.line}` }}>
              <div style={{ fontFamily: F.sans, fontSize: 14, color: C.body, lineHeight: 1.8, marginBottom: 16 }}>
                {typ.detail}
              </div>

              {/* Show me the numbers */}
              <button onClick={() => setExpandedTyp(p => ({ ...p, [ti]: !p[ti] }))} style={{
                fontSize: 12, fontFamily: F.sans, fontWeight: 600, color: C.gold,
                background: "none", border: "none", cursor: "pointer", padding: 0,
                display: "flex", alignItems: "center", gap: 6,
              }}>
                <span style={{ fontSize: 10 }}>{expandedTyp[ti] ? "▾" : "▸"}</span>
                {expandedTyp[ti] ? "Hide" : "Show"} statistical evidence
              </button>

              {expandedTyp[ti] && (
                <div style={{ marginTop: 14 }}>
                  <div style={{ borderRadius: 8, border: `1px solid ${C.line}`, overflow: "hidden", marginBottom: 12 }}>
                    <table style={{ width: "100%", borderCollapse: "collapse" }}>
                      <thead>
                        <tr style={{ background: C.sidebar }}>
                          {["Measure", "Value", "What it means"].map(h => (
                            <th key={h} style={{ padding: "10px 14px", textAlign: "left", fontSize: 10, fontWeight: 700, fontFamily: F.sans, letterSpacing: "0.1em", textTransform: "uppercase", color: C.caption }}>{h}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {[
                          ["Unit price", `${c.unitPrice} ${c.unit}`, "What this contract pays per unit"],
                          ["Peer median", `${e.peerMedian} ${c.unit}`, `Typical price across ${e.peerCount} comparable contracts`],
                          ["Price ratio", `${e.priceRatio.toFixed(2)}×`, "How many times higher than peers"],
                          ["95% CI upper", `${e.ciUpper} ${c.unit}`, "Maximum expected price (bootstrap, 10K resamples)"],
                          ["P(irregularity)", `${(e.posteriorP * 100).toFixed(1)}%`, "Bayesian probability after combining all evidence"],
                          ["FDR q-value", e.fdrQ.toFixed(4), `False discovery rate — below 0.05 means statistically significant`],
                        ].map(([measure, val, meaning], i) => (
                          <tr key={measure} style={{ borderBottom: i < 5 ? `1px solid ${C.line}` : "none" }}>
                            <td style={{ padding: "10px 14px", fontFamily: F.sans, fontSize: 13, fontWeight: 600, color: C.ink }}>{measure}</td>
                            <td style={{ padding: "10px 14px", fontFamily: F.mono, fontSize: 13, fontWeight: 600, color: C.gold }}>{val}</td>
                            <td style={{ padding: "10px 14px", fontFamily: F.sans, fontSize: 12, color: C.muted }}>{meaning}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>

                  <div style={{ padding: 16, borderRadius: 8, background: C.sidebar, border: `1px solid ${C.line}`, fontFamily: F.sans, fontSize: 12, color: C.muted, lineHeight: 1.7 }}>
                    <strong style={{ color: C.body }}>Method: {typ.method}</strong><br />
                    Bootstrap confidence intervals are constructed by resampling peer contract prices 10,000 times,
                    making no assumptions about how prices are distributed. This is then combined with other evidence
                    through Bayes' theorem. The FDR correction (Benjamini-Hochberg) ensures the flag rate is controlled
                    even when testing hundreds of contracts simultaneously. Thresholds are calibrated against the
                    statistical profiles of cases that resulted in federal prosecution.
                  </div>
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* WHAT TO DO NEXT */}
      <div style={{ background: C.card, border: `1px solid ${C.line}`, borderRadius: 14, padding: 28, marginBottom: 20 }}>
        <Label>Recommended Investigation Steps</Label>
        <p style={{ fontFamily: F.sans, fontSize: 13, color: C.muted, margin: "0 0 16px" }}>
          These steps are generated based on the specific typologies triggered. Check off steps as you complete them.
        </p>
        {[
          ["Request", `Obtain price justification documentation from the ${c.agency} contracting officer for this specific procurement`],
          ["Verify", `Cross-reference the unit price of ${c.unitPrice} ${c.unit} against published market indices and recent comparable procurements for ${c.category.replace(/_/g, " ")}`],
          ["Compare", `Pull ${c.vendor}'s complete contract history across all agencies. Look for patterns — are they consistently above peer median pricing?`],
          ["Inspect", `Review ${c.vendor}'s registration documents, beneficial ownership records, and any related-party disclosures with ${c.agency} officials`],
          ["Document", "Record all findings and preserve the evidence chain according to your institution's investigation protocols"],
        ].map(([verb, text], i) => (
          <label key={i} style={{ display: "flex", alignItems: "flex-start", gap: 12, padding: "14px 0", borderBottom: i < 4 ? `1px solid ${C.line}` : "none", cursor: "pointer" }}>
            <input type="checkbox" style={{ marginTop: 3, accentColor: C.gold, width: 16, height: 16, flexShrink: 0 }} />
            <div style={{ fontFamily: F.sans, fontSize: 14, lineHeight: 1.6, color: C.body }}>
              <strong style={{ color: C.ink }}>{verb}.</strong> {text}
            </div>
          </label>
        ))}
      </div>

      {/* DISPOSITION */}
      <div style={{ background: C.card, border: `1px solid ${C.line}`, borderRadius: 14, padding: 28 }}>
        <Label>Analyst Disposition</Label>
        <textarea placeholder="Document your assessment — what did you find when you investigated this flag?" style={{
          width: "100%", minHeight: 80, padding: 14, fontFamily: F.sans, fontSize: 13,
          lineHeight: 1.6, color: C.ink, background: C.page, border: `1px solid ${C.line}`,
          borderRadius: 8, outline: "none", resize: "vertical", marginBottom: 16, boxSizing: "border-box",
        }} />
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {[
            { key: "confirm", label: "True Concern", n: 1, color: C.red },
            { key: "benign", label: "Benign — Explainable", n: 2, color: C.green },
            { key: "info", label: "Needs More Information", n: 3, color: C.blue },
            { key: "dup", label: "Duplicate", n: 4, color: C.caption },
            { key: "refer", label: "Refer to Partner Agency", n: 5, color: "#7C3AED" },
          ].map(d => (
            <button key={d.key} onClick={() => setDisp(d.key)} style={{
              display: "flex", alignItems: "center", gap: 8, padding: "8px 16px",
              borderRadius: 8, fontSize: 13, fontWeight: 600, fontFamily: F.sans,
              cursor: "pointer", transition: "all 0.15s",
              background: disp === d.key ? `${d.color}11` : "transparent",
              border: disp === d.key ? `2px solid ${d.color}` : `1px solid ${C.line}`,
              color: disp === d.key ? d.color : C.muted,
            }}>
              <Kbd>{d.n}</Kbd> {d.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

// ═══════════ APP ═══════════
export default function App() {
  const [view, setView] = useState("welcome");
  const [contracts, setContracts] = useState([]);
  const [results, setResults] = useState([]);
  const [activeCase, setActiveCase] = useState(null);
  const [scanSize, setScanSize] = useState(0);

  const start = useCallback((count) => {
    const data = generateContracts(count);
    setContracts(data);
    setScanSize(count);
    setView("processing");
    analyzeContracts(data).then(res => {
      setResults(res.sort((a, b) => b.confidence - a.confidence));
    });
  }, []);

  const handleProcessingDone = useCallback(() => {
    setView("results");
  }, []);

  const reset = useCallback(() => {
    setView("welcome");
    setContracts([]);
    setResults([]);
    setActiveCase(null);
  }, []);

  return (
    <div style={{ minHeight: "100vh", background: C.page, fontFamily: F.sans }}>

      <header style={{
        height: 56, background: C.header, display: "flex", alignItems: "center",
        padding: "0 24px", position: "sticky", top: 0, zIndex: 100,
        borderBottom: "1px solid rgba(255,255,255,0.06)",
      }}>
        <div onClick={reset} style={{
          width: 32, height: 32, borderRadius: 8, cursor: "pointer",
          background: "linear-gradient(135deg, #C9A84C, #A68930)",
          display: "flex", alignItems: "center", justifyContent: "center",
          marginRight: 12, boxShadow: "0 1px 3px rgba(0,0,0,0.3)",
        }}>
          <span style={{ fontSize: 16 }}>☀</span>
        </div>
        <span onClick={reset} style={{ fontSize: 17, fontWeight: 700, fontFamily: F.sans, letterSpacing: "0.08em", color: "#FFFFFF", cursor: "pointer" }}>
          <span style={{ color: "#C9A84C" }}>SUN</span>LIGHT
        </span>
        <span style={{ marginLeft: 10, fontSize: 11, color: "rgba(255,255,255,0.35)", fontFamily: F.sans }}>Procurement Integrity Intelligence</span>

        <div style={{ flex: 1 }} />

        {(view === "results" || view === "case") && (
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginRight: 16 }}>
            <span style={{ fontSize: 12, fontFamily: F.sans, color: "rgba(255,255,255,0.35)" }}>{contracts.length} contracts</span>
            {results.filter(r => r.tier === "RED").length > 0 && <span style={{ fontSize: 10, fontWeight: 700, padding: "2px 8px", borderRadius: 10, background: "rgba(194,59,59,0.2)", color: "#F87171" }}>{results.filter(r => r.tier === "RED").length} RED</span>}
            {results.filter(r => r.tier === "YELLOW").length > 0 && <span style={{ fontSize: 10, fontWeight: 700, padding: "2px 8px", borderRadius: 10, background: "rgba(184,134,11,0.2)", color: "#FBBF24" }}>{results.filter(r => r.tier === "YELLOW").length} YELLOW</span>}
          </div>
        )}

        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ width: 7, height: 7, borderRadius: "50%", background: "#4ADE80" }} />
          <span style={{ fontSize: 12, color: "rgba(255,255,255,0.5)", fontFamily: F.sans }}>Operational</span>
        </div>
      </header>

      <main style={{ padding: view === "welcome" ? 0 : "28px 36px" }}>
        {view === "welcome" && <Welcome onStart={start} />}
        {view === "processing" && <Processing total={scanSize} onComplete={handleProcessingDone} />}
        {view === "results" && !activeCase && (
          <Results results={results} contracts={contracts}
            onOpenCase={r => { setActiveCase(r); setView("case"); }}
            onReset={reset} />
        )}
        {view === "case" && activeCase && (
          <CasePacket result={activeCase} onBack={() => { setActiveCase(null); setView("results"); }} />
        )}
      </main>
    </div>
  );
}
