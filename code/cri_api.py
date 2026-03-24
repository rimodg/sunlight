"""
SUNLIGHT CRI API
FastAPI wrapper around the batch CRI pipeline.
Endpoints:
  POST /scan         — scan a country's OCDS data, return scored contracts
  GET  /scan/{id}    — retrieve a previous scan result
  GET  /countries    — list supported countries
  GET  /health       — health check
"""

from __future__ import annotations

import hashlib
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# --- SUNLIGHT imports ---
from ocds_fetcher import OCDSFetcher, OCDS_SOURCES
from batch_pipeline import BatchPipeline, JurisdictionConfig, JURISDICTION_CONFIGS
from evidence_report import generate_json_report as generate_evidence_report

# Compatibility shim — API uses fetch_releases() / SUPPORTED_COUNTRIES
SUPPORTED_COUNTRIES = {
    code: {"name": src.country_name, "url": src.base_url}
    for code, src in OCDS_SOURCES.items()
}

def fetch_releases(country: str, limit: int = 500) -> list[dict]:
    """Fetch OCDS releases for a country using OCDSFetcher."""
    fetcher = OCDSFetcher(country)
    return fetcher.fetch(limit=limit)

logger = logging.getLogger("sunlight.api")

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="SUNLIGHT",
    description="Procurement Integrity Infrastructure — OCDS in, scored risk intelligence out.",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# In-memory scan store (swap for Redis/Postgres in production)
# ---------------------------------------------------------------------------
SCAN_STORE: dict[str, dict] = {}

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class ScanRequest(BaseModel):
    country: str = Field(..., description="ISO 3166-1 alpha-2 country code, e.g. 'GB'")
    limit: int = Field(500, ge=10, le=5000, description="Max releases to fetch")


class ContractResult(BaseModel):
    ocid: Optional[str]
    buyer_name: Optional[str]
    buyer_id: Optional[str]
    supplier_name: Optional[str]
    supplier_id: Optional[str]
    value: Optional[float]
    currency: Optional[str]
    procurement_method: Optional[str]
    tier: str
    cri: float
    likelihood_ratio: float
    n_indicators_available: int
    n_indicators_flagged: int
    flags: dict
    explanations: list[str]


class ScanSummary(BaseModel):
    scan_id: str
    country: str
    status: str  # "running" | "complete" | "error"
    started_at: str
    completed_at: Optional[str] = None
    total_releases_fetched: int = 0
    total_contracts_scored: int = 0
    mean_cri: Optional[float] = None
    median_cri: Optional[float] = None
    tier_counts: dict = {}
    indicator_breakdown: dict = {}
    top_risk_contracts: list[ContractResult] = []
    top_risk_buyers: list[dict] = []
    error_message: Optional[str] = None


class CountryInfo(BaseModel):
    code: str
    name: str
    source_url: str
    config: dict


# ---------------------------------------------------------------------------
# Background scan runner
# ---------------------------------------------------------------------------

def _run_scan(scan_id: str, country: str, limit: int):
    """Execute the full SUNLIGHT pipeline in background."""
    record = SCAN_STORE[scan_id]

    try:
        # 1. Fetch
        logger.info(f"[{scan_id}] Fetching {limit} releases for {country}")
        releases = fetch_releases(country, limit=limit)
        record["total_releases_fetched"] = len(releases)

        if not releases:
            record["status"] = "error"
            record["error_message"] = f"No releases returned for {country}"
            record["completed_at"] = datetime.now(timezone.utc).isoformat()
            return

        # 2. Analyze
        logger.info(f"[{scan_id}] Analyzing {len(releases)} releases")
        config = JURISDICTION_CONFIGS.get(country, JurisdictionConfig())
        pipeline = BatchPipeline(config=config)
        pipeline.analyze(releases)
        scores = pipeline.scores

        record["total_contracts_scored"] = len(scores)

        # 3. Build summary stats
        cri_values = [s.cri_score for s in scores if s.cri_score is not None]
        if cri_values:
            record["mean_cri"] = round(sum(cri_values) / len(cri_values), 3)
            sorted_cri = sorted(cri_values)
            mid = len(sorted_cri) // 2
            record["median_cri"] = round(
                sorted_cri[mid] if len(sorted_cri) % 2 else
                (sorted_cri[mid - 1] + sorted_cri[mid]) / 2, 3
            )

        # Tier counts
        tiers = {"RED": 0, "YELLOW": 0, "GREEN": 0, "GRAY": 0}
        for s in scores:
            tiers[s.cri_tier] = tiers.get(s.cri_tier, 0) + 1
        record["tier_counts"] = tiers

        # Indicator breakdown
        INDICATOR_FIELDS = [
            "single_bidding_flag", "tender_period_flag", "procedure_type_flag",
            "decision_period_flag", "amendment_flag", "buyer_concentration_flag",
        ]
        indicator_stats: dict[str, dict] = {}
        for s in scores:
            for ind_name in INDICATOR_FIELDS:
                val = getattr(s, ind_name, None)
                if ind_name not in indicator_stats:
                    indicator_stats[ind_name] = {"flagged": 0, "clean": 0, "no_data": 0}
                if val is None:
                    indicator_stats[ind_name]["no_data"] += 1
                elif val is True:
                    indicator_stats[ind_name]["flagged"] += 1
                else:
                    indicator_stats[ind_name]["clean"] += 1
        record["indicator_breakdown"] = indicator_stats

        # Top risk contracts (top 25)
        sorted_scores = sorted(scores, key=lambda s: (s.cri_score or 0, s.combined_lr or 0), reverse=True)
        top_contracts = []
        for s in sorted_scores[:25]:
            flags = {ind: getattr(s, ind, None) for ind in INDICATOR_FIELDS}
            top_contracts.append(ContractResult(
                ocid=s.ocid,
                buyer_name=s.buyer_name,
                buyer_id=s.buyer_id,
                supplier_name=s.supplier_name,
                supplier_id=s.supplier_id,
                value=s.award_value,
                currency=s.currency,
                procurement_method=s.procurement_method,
                tier=s.cri_tier,
                cri=round(s.cri_score or 0, 3),
                likelihood_ratio=round(s.combined_lr or 1.0, 1),
                n_indicators_available=s.n_indicators_available,
                n_indicators_flagged=s.n_indicators_flagged,
                flags={k: bool(v) if v is not None else None for k, v in flags.items()},
                explanations=s.explanations or [],
            ))
        record["top_risk_contracts"] = [c.model_dump() for c in top_contracts]

        # Top risk buyers
        buyer_scores: dict[str, list] = {}
        buyer_names: dict[str, str] = {}
        for s in scores:
            bid = s.buyer_id
            if bid:
                buyer_scores.setdefault(bid, []).append(s.cri_score or 0)
                if not buyer_names.get(bid):
                    buyer_names[bid] = s.buyer_name or bid
        top_buyers = []
        for bid, cris in buyer_scores.items():
            avg = sum(cris) / len(cris)
            top_buyers.append({
                "buyer_id": bid,
                "buyer_name": buyer_names.get(bid, bid),
                "avg_cri": round(avg, 3),
                "contracts": len(cris),
            })
        top_buyers.sort(key=lambda b: b["avg_cri"], reverse=True)
        record["top_risk_buyers"] = top_buyers[:15]

        record["status"] = "complete"
        record["completed_at"] = datetime.now(timezone.utc).isoformat()
        logger.info(f"[{scan_id}] Complete — {len(scores)} contracts scored")

    except Exception as e:
        logger.exception(f"[{scan_id}] Scan failed")
        record["status"] = "error"
        record["error_message"] = str(e)
        record["completed_at"] = datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "sunlight",
        "version": "0.2.0",
        "scans_in_memory": len(SCAN_STORE),
    }


@app.get("/countries", response_model=list[CountryInfo])
def list_countries():
    """List all supported OCDS data sources."""
    result = []
    for code, info in SUPPORTED_COUNTRIES.items():
        config = JURISDICTION_CONFIGS.get(code, JurisdictionConfig())
        result.append(CountryInfo(
            code=code,
            name=info.get("name", code),
            source_url=info.get("url", ""),
            config={
                "concentration_threshold": config.concentration_threshold,
                "tender_period_minimum": config.tender_period_minimum,
                "cri_red_threshold": config.cri_red_threshold,
                "cri_yellow_threshold": config.cri_yellow_threshold,
            },
        ))
    return result


@app.post("/scan", response_model=ScanSummary)
def start_scan(req: ScanRequest, background_tasks: BackgroundTasks):
    """Start a new SUNLIGHT scan. Returns immediately with scan_id; poll GET /scan/{id} for results."""
    country = req.country.upper()
    if country not in SUPPORTED_COUNTRIES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported country: {country}. Supported: {list(SUPPORTED_COUNTRIES.keys())}",
        )

    scan_id = str(uuid.uuid4())[:8]
    record = {
        "scan_id": scan_id,
        "country": country,
        "status": "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "total_releases_fetched": 0,
        "total_contracts_scored": 0,
    }
    SCAN_STORE[scan_id] = record

    background_tasks.add_task(_run_scan, scan_id, country, req.limit)

    return ScanSummary(**record)


@app.get("/scan/{scan_id}", response_model=ScanSummary)
def get_scan(scan_id: str):
    """Get scan results by ID."""
    if scan_id not in SCAN_STORE:
        raise HTTPException(status_code=404, detail=f"Scan {scan_id} not found")
    return ScanSummary(**SCAN_STORE[scan_id])


@app.get("/scans", response_model=list[ScanSummary])
def list_scans():
    """List all scans."""
    return [
        ScanSummary(**{k: v for k, v in record.items()
                      if k in ScanSummary.model_fields})
        for record in SCAN_STORE.values()
    ]


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
