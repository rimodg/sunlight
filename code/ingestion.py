"""
SUNLIGHT Contract Ingestion Engine
====================================

Accepts raw procurement documents (PDF, CSV, JSON), extracts structured
contract data, inserts into the database, and queues for async scoring.

Supported formats:
- JSON: Direct structured contract data (single or array)
- CSV: Tabular contract data with header row
- PDF: Text extraction and field parsing (best-effort)
"""

import csv
import hashlib
import io
import json
import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

from sunlight_logging import get_logger

logger = get_logger("ingestion")


# ---------------------------------------------------------------------------
# Ingestion job tracking
# ---------------------------------------------------------------------------

def init_ingestion_schema(db_path: str):
    """Create ingestion tracking tables if they don't exist."""
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS ingestion_jobs (
            job_id          TEXT PRIMARY KEY,
            status          TEXT NOT NULL DEFAULT 'PENDING',
            source_filename TEXT,
            source_format   TEXT NOT NULL,
            source_hash     TEXT,
            submitted_at    TEXT NOT NULL,
            completed_at    TEXT,
            total_records   INTEGER DEFAULT 0,
            inserted        INTEGER DEFAULT 0,
            duplicates      INTEGER DEFAULT 0,
            errors          INTEGER DEFAULT 0,
            scored          INTEGER DEFAULT 0,
            error_details   TEXT,
            client_name     TEXT
        )
    """)
    conn.commit()
    conn.close()


def create_job(db_path: str, source_filename: str, source_format: str,
               source_hash: str, client_name: str = "anonymous") -> str:
    """Create a new ingestion job and return its ID."""
    job_id = f"ingest_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute(
        "INSERT INTO ingestion_jobs (job_id, status, source_filename, source_format, "
        "source_hash, submitted_at, client_name) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (job_id, "PENDING", source_filename, source_format, source_hash,
         datetime.now(timezone.utc).isoformat(), client_name),
    )
    conn.commit()
    conn.close()
    logger.info("Ingestion job created",
                extra={"job_id": job_id, "source_format": source_format, "source_file": source_filename})
    return job_id


_ALLOWED_JOB_COLUMNS = frozenset({
    'status', 'completed_at', 'total_records', 'inserted',
    'duplicates', 'errors', 'scored', 'error_details',
})


def update_job(db_path: str, job_id: str, **kwargs):
    """Update job fields (only allowlisted columns)."""
    from sql_allowlist import validate_column
    # Validate column names against allowlist to prevent SQL injection
    for key in kwargs:
        if key not in _ALLOWED_JOB_COLUMNS:
            raise ValueError(f"Invalid column name: {key}")
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    sets = ", ".join(f"{validate_column(k)} = ?" for k in kwargs)
    vals = list(kwargs.values()) + [job_id]
    c.execute(f"UPDATE ingestion_jobs SET {sets} WHERE job_id = ?", vals)
    conn.commit()
    conn.close()


def get_job(db_path: str, job_id: str) -> Optional[Dict]:
    """Get job status."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM ingestion_jobs WHERE job_id = ?", (job_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None


# ---------------------------------------------------------------------------
# Extractors
# ---------------------------------------------------------------------------

def extract_from_json(content: bytes) -> List[Dict]:
    """Extract contracts from JSON content (single object or array)."""
    data = json.loads(content.decode('utf-8'))
    if isinstance(data, dict):
        # Single contract or wrapped in a key
        if 'contracts' in data:
            records = data['contracts']
        elif 'contract_id' in data or 'id' in data:
            records = [data]
        else:
            records = [data]
    elif isinstance(data, list):
        records = data
    else:
        raise ValueError("JSON must be an object or array")

    return [_normalize_record(r) for r in records]


def extract_from_csv(content: bytes) -> List[Dict]:
    """Extract contracts from CSV content with header row."""
    text = content.decode('utf-8')
    reader = csv.DictReader(io.StringIO(text))
    records = []
    for row in reader:
        records.append(_normalize_record(dict(row)))
    return records


def extract_from_pdf(content: bytes) -> List[Dict]:
    """
    Extract contracts from PDF content using text parsing.

    This is best-effort extraction. For production use, structured formats
    (JSON, CSV) are strongly recommended.
    """
    # Extract text from PDF bytes
    text = _extract_pdf_text(content)
    if not text.strip():
        raise ValueError("Could not extract text from PDF. Use JSON or CSV format for reliable ingestion.")

    records = _parse_procurement_text(text)
    if not records:
        raise ValueError(
            "Could not parse structured contract data from PDF text. "
            "Use JSON or CSV format for reliable ingestion."
        )
    return records


def _extract_pdf_text(content: bytes) -> str:
    """Extract text from PDF bytes using basic parsing."""
    # Try reportlab/pdfplumber if available, fall back to basic extraction
    try:
        import pdfplumber
        pdf = pdfplumber.open(io.BytesIO(content))
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        pdf.close()
        return text
    except ImportError:
        pass

    # Basic PDF text extraction (handles simple PDFs)
    text_parts = []
    pdf_str = content.decode('latin-1', errors='replace')
    # Find text between BT and ET markers
    for match in re.finditer(r'\((.*?)\)', pdf_str):
        text_parts.append(match.group(1))
    return " ".join(text_parts)


def _parse_procurement_text(text: str) -> List[Dict]:
    """Parse procurement text into structured records."""
    records = []

    # Pattern: look for contract-like blocks with amounts and vendor names
    # Common patterns in procurement documents
    amount_pattern = re.compile(r'\$[\d,]+(?:\.\d{2})?')
    contract_id_pattern = re.compile(r'(?:Contract|Award|Order)\s*(?:#|No\.?|Number)?\s*[:.]?\s*([A-Z0-9][\w-]+)', re.I)

    # Try to parse as a table or structured text
    lines = text.split('\n')
    current_record = {}

    for line in lines:
        line = line.strip()
        if not line:
            if current_record.get('contract_id') and current_record.get('award_amount'):
                records.append(_normalize_record(current_record))
                current_record = {}
            continue

        # Look for contract ID
        cid_match = contract_id_pattern.search(line)
        if cid_match and not current_record.get('contract_id'):
            current_record['contract_id'] = cid_match.group(1)

        # Look for amounts
        amt_match = amount_pattern.search(line)
        if amt_match and not current_record.get('award_amount'):
            amt_str = amt_match.group().replace('$', '').replace(',', '')
            try:
                current_record['award_amount'] = float(amt_str)
            except ValueError:
                pass

        # Look for vendor/contractor
        vendor_match = re.search(r'(?:Vendor|Contractor|Awardee|Company)\s*[:.]?\s*(.+)', line, re.I)
        if vendor_match:
            current_record['vendor_name'] = vendor_match.group(1).strip()

        # Look for agency
        agency_match = re.search(r'(?:Agency|Department|Organization)\s*[:.]?\s*(.+)', line, re.I)
        if agency_match:
            current_record['agency_name'] = agency_match.group(1).strip()

        # Look for description
        desc_match = re.search(r'(?:Description|Purpose|Subject)\s*[:.]?\s*(.+)', line, re.I)
        if desc_match:
            current_record['description'] = desc_match.group(1).strip()

    # Don't forget the last record
    if current_record.get('contract_id') and current_record.get('award_amount'):
        records.append(_normalize_record(current_record))

    return records


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

# Common column name mappings
FIELD_ALIASES = {
    'contract_id': ['contract_id', 'id', 'contract_number', 'award_id', 'piid'],
    'award_amount': ['award_amount', 'amount', 'total_amount', 'value', 'award_value',
                     'contract_value', 'total_value', 'obligated_amount'],
    'vendor_name': ['vendor_name', 'vendor', 'contractor', 'awardee', 'company',
                    'recipient', 'supplier'],
    'agency_name': ['agency_name', 'agency', 'department', 'organization', 'awarding_agency'],
    'description': ['description', 'desc', 'title', 'purpose', 'subject',
                    'product_description', 'award_description'],
    'start_date': ['start_date', 'date', 'award_date', 'effective_date', 'period_start'],
}


def _normalize_record(raw: Dict) -> Dict:
    """Normalize a raw record to the expected schema."""
    normalized = {}
    raw_lower = {k.lower().strip(): v for k, v in raw.items()}

    for field, aliases in FIELD_ALIASES.items():
        for alias in aliases:
            if alias in raw_lower and raw_lower[alias]:
                val = raw_lower[alias]
                if field == 'award_amount':
                    if isinstance(val, str):
                        val = val.replace('$', '').replace(',', '').strip()
                    try:
                        val = float(val)
                    except (ValueError, TypeError):
                        val = None
                normalized[field] = val
                break

    # Generate contract_id if missing
    if not normalized.get('contract_id'):
        content = json.dumps(raw, sort_keys=True)
        normalized['contract_id'] = f"INGEST_{hashlib.md5(content.encode()).hexdigest()[:12].upper()}"

    # Default empty fields
    normalized.setdefault('vendor_name', 'Unknown')
    normalized.setdefault('agency_name', 'Unknown')
    normalized.setdefault('description', '')
    normalized.setdefault('start_date', None)

    return normalized


# ---------------------------------------------------------------------------
# Insert + Score
# ---------------------------------------------------------------------------

def insert_contracts(db_path: str, records: List[Dict]) -> Dict[str, int]:
    """Insert extracted contracts into the database. Returns counts."""
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    inserted = 0
    duplicates = 0
    errors = 0
    error_details = []

    for record in records:
        try:
            if record.get('award_amount') is None or record['award_amount'] <= 0:
                errors += 1
                error_details.append(f"{record.get('contract_id', '?')}: invalid award_amount")
                continue

            # Check for duplicate
            c.execute("SELECT 1 FROM contracts WHERE contract_id = ?",
                      (record['contract_id'],))
            if c.fetchone():
                duplicates += 1
                continue

            raw_hash = hashlib.sha256(
                f"{record['contract_id']}:{record['award_amount']}:{record['vendor_name']}".encode()
            ).hexdigest()

            c.execute(
                "INSERT INTO contracts (contract_id, award_amount, vendor_name, agency_name, "
                "description, start_date, raw_data_hash) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    record['contract_id'],
                    record['award_amount'],
                    record['vendor_name'],
                    record['agency_name'],
                    record.get('description', ''),
                    record.get('start_date'),
                    raw_hash,
                ),
            )
            inserted += 1

        except Exception as e:
            errors += 1
            error_details.append(f"{record.get('contract_id', '?')}: {str(e)}")

    conn.commit()
    conn.close()

    return {
        'inserted': inserted,
        'duplicates': duplicates,
        'errors': errors,
        'error_details': error_details[:50],  # Cap error details
    }


def score_ingested_contracts(db_path: str, contract_ids: List[str]) -> int:
    """Score newly ingested contracts through the detection pipeline."""
    import sys
    sys.path.insert(0, os.path.dirname(__file__))
    from institutional_statistical_rigor import BootstrapAnalyzer
    from institutional_pipeline import score_contract, assign_tier, select_comparables_from_cache, derive_contract_seed

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # Build agency cache for comparables
    c.execute("SELECT contract_id, agency_name, award_amount FROM contracts WHERE award_amount > 0")
    agency_cache = {}
    for row in c.fetchall():
        agency = row['agency_name']
        if agency not in agency_cache:
            agency_cache[agency] = []
        agency_cache[agency].append((row['contract_id'], row['award_amount']))

    ba = BootstrapAnalyzer(n_iterations=1000)
    config = {'confidence_level': 0.95, 'min_comparables': 3}
    scored = 0
    run_seed = int(datetime.now(timezone.utc).timestamp())

    for cid in contract_ids:
        try:
            c.execute(
                "SELECT contract_id, award_amount, vendor_name, agency_name, description "
                "FROM contracts WHERE contract_id = ?", (cid,)
            )
            row = c.fetchone()
            if not row:
                continue

            contract = dict(row)
            comparables = select_comparables_from_cache(
                cid, contract['agency_name'], contract['award_amount'], agency_cache
            )
            contract['comparables'] = comparables
            contract['is_sole_source'] = False
            contract['has_donations'] = False

            seed = derive_contract_seed(run_seed, cid)
            score = score_contract(contract, seed, config, ba)
            tier, priority = assign_tier(score, score.get('raw_pvalue', 1.0), False)

            # Insert score
            score_id = hashlib.sha256(
                f"ingest:{cid}:{run_seed}".encode()
            ).hexdigest()[:16]

            c.execute("""
                INSERT OR REPLACE INTO contract_scores
                (score_id, contract_id, run_id, fraud_tier, confidence_score,
                 markup_pct, markup_ci_lower, markup_ci_upper,
                 raw_zscore, log_zscore,
                 bayesian_prior, bayesian_posterior, bayesian_likelihood_ratio,
                 bootstrap_percentile, raw_pvalue,
                 fdr_adjusted_pvalue, survives_fdr,
                 comparable_count, insufficient_comparables, triage_priority)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                score_id, cid, f"ingest_{run_seed}",
                tier, score.get('confidence_score', 0),
                score.get('markup_pct'), score.get('markup_ci_lower'), score.get('markup_ci_upper'),
                score.get('raw_zscore'), score.get('log_zscore'),
                score.get('bayesian_prior'), score.get('bayesian_posterior'),
                score.get('bayesian_likelihood_ratio'),
                score.get('bootstrap_percentile'), score.get('raw_pvalue'),
                score.get('raw_pvalue'), 0,  # No FDR for single-contract scoring
                score.get('comparable_count', 0), 1 if score.get('comparable_count', 0) < 3 else 0,
                priority,
            ))
            scored += 1
        except Exception as e:
            logger.warning("Failed to score ingested contract",
                          extra={"contract_id": cid, "error": str(e)})

    conn.commit()
    conn.close()
    return scored


def process_ingestion(db_path: str, job_id: str, content: bytes,
                      source_format: str, filename: str):
    """Full ingestion pipeline: extract → insert → score → update job."""
    try:
        update_job(db_path, job_id, status="PROCESSING")

        # Extract
        if source_format == 'json':
            records = extract_from_json(content)
        elif source_format == 'csv':
            records = extract_from_csv(content)
        elif source_format == 'pdf':
            records = extract_from_pdf(content)
        else:
            raise ValueError(f"Unsupported format: {source_format}")

        update_job(db_path, job_id, total_records=len(records))

        # Insert
        result = insert_contracts(db_path, records)

        # Score newly inserted contracts
        inserted_ids = [r['contract_id'] for r in records
                       if r.get('award_amount') and r['award_amount'] > 0]
        scored = score_ingested_contracts(db_path, inserted_ids)

        update_job(
            db_path, job_id,
            status="COMPLETED",
            completed_at=datetime.now(timezone.utc).isoformat(),
            inserted=result['inserted'],
            duplicates=result['duplicates'],
            errors=result['errors'],
            scored=scored,
            error_details=json.dumps(result['error_details']) if result['error_details'] else None,
        )

        logger.info("Ingestion job completed",
                    extra={"job_id": job_id, "inserted": result['inserted'],
                           "duplicates": result['duplicates'], "scored": scored})

    except Exception as e:
        logger.error("Ingestion job failed",
                    extra={"job_id": job_id, "error": str(e)})
        update_job(
            db_path, job_id,
            status="FAILED",
            completed_at=datetime.now(timezone.utc).isoformat(),
            error_details=str(e),
        )
