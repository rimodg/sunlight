"""
SUNLIGHT OCDS Live Feed Integration
Polls Open Contracting Data Standard feeds from 50+ countries
and runs TCA structural analysis on new contracts in real-time.

Resolves UNDP Problem #9: No Real-Time Monitoring
"""

import json
import time
import hashlib
import logging
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

logger = logging.getLogger("sunlight.ocds_feed")


class FeedStatus(Enum):
    ACTIVE = "active"
    DEGRADED = "degraded"  # Responding but with errors
    OFFLINE = "offline"
    RATE_LIMITED = "rate_limited"


@dataclass
class OCDSSource:
    """A registered OCDS data source."""
    country_code: str
    country_name: str
    feed_url: str
    api_type: str  # "rest", "bulk", "webhook"
    poll_interval_seconds: int = 3600  # Default: 1 hour
    last_polled: Optional[str] = None
    last_release_id: Optional[str] = None
    status: FeedStatus = FeedStatus.ACTIVE
    contracts_processed: int = 0
    findings_generated: int = 0
    auth_token: Optional[str] = None


@dataclass
class OCDSRelease:
    """A single OCDS release (contract event)."""
    ocid: str  # Open Contracting ID
    release_id: str
    country_code: str
    buyer_name: str
    buyer_id: str
    procurement_method: str
    tender_value: float
    currency: str
    suppliers: List[Dict]
    tender_start: Optional[str] = None
    tender_end: Optional[str] = None
    award_date: Optional[str] = None
    contract_period_start: Optional[str] = None
    contract_period_end: Optional[str] = None
    items: List[Dict] = field(default_factory=list)
    raw_data: Optional[Dict] = None


# ═══ KNOWN OCDS SOURCES ═══
# Production would have 50+ countries. These are the active, high-quality feeds.
KNOWN_SOURCES = [
    OCDSSource("PY", "Paraguay", "https://www.contrataciones.gov.py/datos/api/v3/", "rest", 1800),
    OCDSSource("CO", "Colombia", "https://api.colombiacompra.gov.co/", "rest", 3600),
    OCDSSource("UA", "Ukraine", "https://public.api.openprocurement.org/api/2.5/", "rest", 1800),
    OCDSSource("GB", "United Kingdom", "https://www.contractsfinder.service.gov.uk/Published/", "rest", 3600),
    OCDSSource("MX", "Mexico", "https://api.datos.gob.mx/v1/contrataciones/", "rest", 3600),
    OCDSSource("NG", "Nigeria", "https://nocopo.bpp.gov.ng/api/", "rest", 7200),
    OCDSSource("SN", "Senegal", "https://marches.armp.sn/api/ocds/", "rest", 7200),
    OCDSSource("US", "United States", "https://api.sam.gov/opportunities/v2/", "rest", 1800),
    OCDSSource("GE", "Georgia", "https://tenders.procurement.gov.ge/api/", "rest", 3600),
    OCDSSource("MD", "Moldova", "https://public.mtender.gov.md/tenders/", "rest", 7200),
]


class OCDSNormalizer:
    """
    Normalizes raw OCDS data into SUNLIGHT's internal format.
    Handles variations across different country implementations.
    """
    
    @staticmethod
    def normalize_release(raw: Dict, country_code: str) -> Optional[OCDSRelease]:
        """Convert raw OCDS JSON to normalized OCDSRelease."""
        try:
            # OCDS 1.1 standard fields
            ocid = raw.get("ocid", "")
            release_id = raw.get("id", hashlib.sha256(json.dumps(raw, sort_keys=True).encode()).hexdigest()[:16])
            
            # Buyer
            buyer = raw.get("buyer", {})
            buyer_name = buyer.get("name", buyer.get("legalName", "Unknown"))
            buyer_id = buyer.get("id", buyer.get("identifier", {}).get("id", ""))
            
            # Tender
            tender = raw.get("tender", {})
            procurement_method = tender.get("procurementMethod", tender.get("procurementMethodType", "unknown"))
            tender_value_obj = tender.get("value", {})
            tender_value = float(tender_value_obj.get("amount", 0))
            currency = tender_value_obj.get("currency", "USD")
            
            # If tender value is 0, try award value
            if tender_value == 0:
                awards = raw.get("awards", [])
                if awards:
                    award_value = awards[0].get("value", {})
                    tender_value = float(award_value.get("amount", 0))
                    currency = award_value.get("currency", currency)
            
            # Suppliers
            suppliers = []
            for award in raw.get("awards", []):
                for supplier in award.get("suppliers", []):
                    suppliers.append({
                        "name": supplier.get("name", ""),
                        "id": supplier.get("id", supplier.get("identifier", {}).get("id", "")),
                        "address": supplier.get("address", {}),
                    })
            
            # Dates
            tender_period = tender.get("tenderPeriod", {})
            contract_period = raw.get("contracts", [{}])[0].get("period", {}) if raw.get("contracts") else {}
            
            return OCDSRelease(
                ocid=ocid,
                release_id=release_id,
                country_code=country_code,
                buyer_name=buyer_name,
                buyer_id=buyer_id,
                procurement_method=procurement_method,
                tender_value=tender_value,
                currency=currency,
                suppliers=suppliers,
                tender_start=tender_period.get("startDate"),
                tender_end=tender_period.get("endDate"),
                award_date=raw.get("awards", [{}])[0].get("date") if raw.get("awards") else None,
                contract_period_start=contract_period.get("startDate"),
                contract_period_end=contract_period.get("endDate"),
                items=tender.get("items", []),
                raw_data=raw,
            )
        except Exception as e:
            logger.error(f"Failed to normalize OCDS release from {country_code}: {e}")
            return None


class OCDSToTCAMapper:
    """
    Maps normalized OCDS data to TCA graph format.
    This is the critical translation layer — OCDS fields become typed directed edges.
    """
    
    @staticmethod
    def build_graph(release: OCDSRelease) -> Dict:
        """
        Convert an OCDS release into a TCA-ready graph.
        
        The mapping logic:
        - Buyer → Award: EXPRESSES (buyer produces the award decision)
        - Process → Award: EXPRESSES (process produces the award)
        - Award → Budget: VERIFIES or REMOVES (based on price analysis)
        - Oversight → Award: VERIFIES or SEEKS (based on oversight presence)
        - Vendor → Buyer: EXPRESSES or BOUNDS (based on concentration)
        - Multiple vendors: MIRRORS if independent, INHERITS if linked
        """
        nodes = []
        edges = []
        
        # Core nodes
        nodes.append({"id": "buyer", "label": release.buyer_name[:30]})
        nodes.append({"id": "award", "label": "Award Decision"})
        nodes.append({"id": "process", "label": f"{release.procurement_method}"})
        nodes.append({"id": "budget", "label": f"Budget ({release.currency} {release.tender_value:,.0f})"})
        
        # Supplier nodes
        for i, supplier in enumerate(release.suppliers[:5]):  # Cap at 5 suppliers
            sid = f"vendor_{i}"
            nodes.append({"id": sid, "label": supplier.get("name", f"Vendor {i+1}")[:25]})
        
        # Core structural edges
        # Buyer → Process: EXPRESSES (buyer initiates procurement)
        edges.append({"source": "buyer", "target": "process", "type": "EXPRESSES", "weight": 1.0})
        
        # Process → Award: EXPRESSES (process produces award)
        edges.append({"source": "process", "target": "award", "type": "EXPRESSES", "weight": 1.0})
        
        # Award → Budget: Default VERIFIES, but may become REMOVES if price is anomalous
        edges.append({"source": "award", "target": "budget", "type": "VERIFIES", "weight": 0.8})
        
        # Detect structural issues from OCDS fields
        
        # 1. Single bidder in competitive tender
        if len(release.suppliers) == 1 and release.procurement_method in ("open", "selective", "competitive"):
            edges.append({"source": "award", "target": "process", "type": "REMOVES", "weight": 1.0,
                         "description": "Single bidder in nominally competitive tender"})
        
        # 2. Sole source / direct award
        if release.procurement_method in ("direct", "limited", "sole_source"):
            if release.tender_value > 100_000:  # Threshold for competitive requirement
                edges.append({"source": "award", "target": "process", "type": "REMOVES", "weight": 0.9,
                             "description": f"Direct award of {release.currency} {release.tender_value:,.0f} — typically requires competition"})
        
        # 3. Fiscal year-end timing
        if release.award_date:
            try:
                award_dt = datetime.fromisoformat(release.award_date.replace("Z", "+00:00"))
                fiscal_end_months = [3, 6, 9, 12]  # Common fiscal year-end months
                if award_dt.month in fiscal_end_months and award_dt.day > 20:
                    nodes.append({"id": "fiscal", "label": "Fiscal Pressure"})
                    edges.append({"source": "fiscal", "target": "award", "type": "BOUNDS", "weight": 0.8,
                                 "description": f"Award date {award_dt.strftime('%Y-%m-%d')} — fiscal year-end timing"})
            except (ValueError, TypeError):
                pass
        
        # 4. Contract duration vs emergency classification
        if release.contract_period_start and release.contract_period_end and release.procurement_method in ("direct", "limited", "emergency"):
            try:
                start = datetime.fromisoformat(release.contract_period_start.replace("Z", "+00:00"))
                end = datetime.fromisoformat(release.contract_period_end.replace("Z", "+00:00"))
                duration_days = (end - start).days
                if duration_days > 180:  # Emergency but > 6 months
                    edges.append({"source": "award", "target": "process", "type": "REMOVES", "weight": 0.9,
                                 "description": f"Emergency/direct procedure with {duration_days}-day contract duration"})
            except (ValueError, TypeError):
                pass
        
        # 5. Vendor relationships
        if len(release.suppliers) >= 2:
            # Check for shared addresses
            addresses = [s.get("address", {}).get("streetAddress", "") for s in release.suppliers]
            if len(set(a for a in addresses if a)) < len([a for a in addresses if a]):
                for i in range(1, len(release.suppliers)):
                    edges.append({"source": "vendor_0", "target": f"vendor_{i}", "type": "INHERITS", "weight": 0.9,
                                 "description": "Vendors share address — potential linked entities"})
            else:
                for i in range(1, min(len(release.suppliers), 3)):
                    edges.append({"source": "vendor_0", "target": f"vendor_{i}", "type": "MIRRORS", "weight": 0.6})
        
        # Primary vendor → award
        if release.suppliers:
            edges.append({"source": "vendor_0", "target": "award", "type": "EXPRESSES", "weight": 0.8})
        
        # Oversight — check if oversight body is mentioned
        # In OCDS, this comes from the reviewBody field or parties with role "reviewBody"
        parties = release.raw_data.get("parties", []) if release.raw_data else []
        has_oversight = any("review" in p.get("roles", []) or "oversight" in str(p.get("roles", [])).lower() for p in parties)
        
        if has_oversight:
            nodes.append({"id": "oversight", "label": "Oversight Body"})
            edges.append({"source": "oversight", "target": "award", "type": "VERIFIES", "weight": 0.8})
        else:
            nodes.append({"id": "oversight", "label": "Oversight (Absent)"})
            edges.append({"source": "award", "target": "oversight", "type": "SEEKS", "weight": 0.7,
                         "description": "No review body identified in procurement record"})
        
        return {
            "name": f"{release.ocid} — {release.buyer_name}",
            "nodes": nodes,
            "edges": edges,
            "metadata": {
                "ocid": release.ocid,
                "country": release.country_code,
                "value": release.tender_value,
                "currency": release.currency,
                "method": release.procurement_method,
                "suppliers": len(release.suppliers),
            }
        }


class FeedMonitor:
    """
    Orchestrates continuous monitoring of OCDS feeds.
    In production, this runs as a Stork campaign.
    """
    
    def __init__(
        self,
        sources: List[OCDSSource] = None,
        tca_callback: Optional[Callable] = None,
        finding_callback: Optional[Callable] = None,
    ):
        self.sources = sources or KNOWN_SOURCES
        self.normalizer = OCDSNormalizer()
        self.mapper = OCDSToTCAMapper()
        self.tca_callback = tca_callback  # Called with graph JSON for TCA analysis
        self.finding_callback = finding_callback  # Called when a finding is generated
        self.processed_ids = set()
        self.stats = {
            "total_polled": 0,
            "total_processed": 0,
            "total_findings": 0,
            "findings_by_country": {},
            "last_run": None,
        }
    
    def process_release(self, raw: Dict, source: OCDSSource) -> Optional[Dict]:
        """Process a single OCDS release through the TCA pipeline."""
        # Normalize
        release = self.normalizer.normalize_release(raw, source.country_code)
        if not release:
            return None
        
        # Deduplicate
        if release.release_id in self.processed_ids:
            return None
        self.processed_ids.add(release.release_id)
        
        # Skip zero-value contracts
        if release.tender_value <= 0:
            return None
        
        # Map to TCA graph
        graph = self.mapper.build_graph(release)
        
        # Count REMOVES and SEEKS edges to pre-filter
        removes = sum(1 for e in graph["edges"] if e["type"] == "REMOVES")
        seeks = sum(1 for e in graph["edges"] if e["type"] == "SEEKS")
        
        result = {
            "release": release,
            "graph": graph,
            "pre_filter": {
                "removes_count": removes,
                "seeks_count": seeks,
                "requires_tca": removes > 0 or seeks > 2,
            }
        }
        
        # Only run full TCA on contracts with structural indicators
        if result["pre_filter"]["requires_tca"] and self.tca_callback:
            tca_result = self.tca_callback(json.dumps(graph))
            result["tca_analysis"] = tca_result
            
            # Check if this is a finding
            if tca_result and tca_result.get("confidence", 1.0) < 0.5:
                self.stats["total_findings"] += 1
                country = source.country_code
                self.stats["findings_by_country"][country] = self.stats["findings_by_country"].get(country, 0) + 1
                
                if self.finding_callback:
                    self.finding_callback(result)
        
        self.stats["total_processed"] += 1
        source.contracts_processed += 1
        
        return result
    
    def generate_sitrep(self) -> str:
        """Generate a monitoring status report."""
        lines = []
        lines.append("═" * 60)
        lines.append("SUNLIGHT OCDS FEED MONITOR — STATUS REPORT")
        lines.append("═" * 60)
        lines.append(f"Timestamp: {datetime.utcnow().isoformat()}Z")
        lines.append(f"Sources monitored: {len(self.sources)}")
        lines.append(f"Contracts processed: {self.stats['total_processed']}")
        lines.append(f"Structural findings: {self.stats['total_findings']}")
        lines.append("")
        
        lines.append("FINDINGS BY COUNTRY:")
        for country, count in sorted(self.stats["findings_by_country"].items(), key=lambda x: -x[1]):
            source = next((s for s in self.sources if s.country_code == country), None)
            name = source.country_name if source else country
            lines.append(f"  {country} ({name}): {count} findings")
        
        lines.append("")
        lines.append("SOURCE STATUS:")
        for source in self.sources:
            lines.append(f"  {source.country_code} ({source.country_name}): {source.status.value} — {source.contracts_processed} processed")
        
        lines.append("═" * 60)
        return "\n".join(lines)


# ═══ DEMO ═══
if __name__ == "__main__":
    monitor = FeedMonitor()
    
    # Simulate processing a Senegal OCDS release
    sample_release = {
        "ocid": "ocds-SN-ARMP-2025-0847",
        "id": "release-001",
        "buyer": {"name": "Agence Routière du Sénégal", "id": "SN-ARMP"},
        "tender": {
            "procurementMethod": "direct",
            "value": {"amount": 2450000, "currency": "USD"},
            "tenderPeriod": {"startDate": "2025-11-01", "endDate": "2025-11-14"},
            "items": [{"description": "Road Infrastructure Rehabilitation — Thiès Region"}],
        },
        "awards": [{
            "date": "2025-11-14",
            "value": {"amount": 2450000, "currency": "USD"},
            "suppliers": [{"name": "SGT SA", "id": "SN-RCCM-SGT", "address": {"streetAddress": "Dakar"}}],
        }],
        "contracts": [{"period": {"startDate": "2025-11-20", "endDate": "2027-05-20"}}],
        "parties": [],
    }
    
    source = next(s for s in KNOWN_SOURCES if s.country_code == "SN")
    result = monitor.process_release(sample_release, source)
    
    if result:
        print("OCDS → TCA Graph:")
        print(json.dumps(result["graph"], indent=2))
        print(f"\nPre-filter: {result['pre_filter']}")
        print(f"\n{monitor.generate_sitrep()}")
