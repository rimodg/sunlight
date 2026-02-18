"""
SUNLIGHT Data Normalization & Confidence Scoring
===================================================

Normalizes messy input fields and assigns confidence scores.
If evidence confidence is low, severity is downgraded and
"insufficient data" is shown instead of asserting.

Handles:
  - Vendor name normalization (case, suffixes, whitespace, punctuation)
  - Contract ID validation and normalization
  - Date parsing (multiple formats)
  - Amount parsing (currency symbols, commas, text)
  - Address normalization (basic)
  - Field confidence scoring (0-100)
"""

import re
import hashlib
from datetime import datetime
from typing import Dict, Optional, Tuple, Any

# ---------------------------------------------------------------------------
# Vendor Name Normalization
# ---------------------------------------------------------------------------

_VENDOR_SUFFIXES = {
    'llc', 'l.l.c.', 'l.l.c', 'inc', 'inc.', 'incorporated',
    'corp', 'corp.', 'corporation', 'co', 'co.', 'company',
    'ltd', 'ltd.', 'limited', 'lp', 'l.p.', 'plc', 'p.l.c.',
    'gmbh', 'ag', 'sa', 's.a.', 'pty', 'pvt',
    'group', 'holdings', 'enterprises', 'services', 'solutions',
    'international', 'intl', "int'l", 'associates', 'partners',
}

_NOISE_WORDS = {'the', 'a', 'an', 'of', 'and', '&'}


def normalize_vendor_name(name: str) -> Tuple[str, int]:
    """
    Normalize a vendor name and return (normalized_name, confidence).

    Confidence:
      100 — No normalization needed
       90 — Minor normalization (case, whitespace)
       70 — Suffix removal or significant normalization
       50 — Heavily normalized (short result, potential data loss)
       30 — Very short or ambiguous result
    """
    if not name or not name.strip():
        return '', 0

    original = name.strip()
    confidence = 100

    # Uppercase for comparison
    working = original.upper()

    # Remove extra whitespace
    working = re.sub(r'\s+', ' ', working).strip()
    if working != original.upper():
        confidence = min(confidence, 90)

    # Remove common punctuation noise
    working = working.replace('"', '').replace("'", '').replace('`', '')
    working = re.sub(r'[,;]+$', '', working).strip()

    # Remove trailing suffixes
    words = working.split()
    cleaned_words = []
    suffix_removed = False
    for word in words:
        if word.lower().rstrip('.') in _VENDOR_SUFFIXES:
            suffix_removed = True
            continue
        if word in _NOISE_WORDS:
            continue
        cleaned_words.append(word)

    if suffix_removed:
        confidence = min(confidence, 70)

    if cleaned_words:
        working = ' '.join(cleaned_words)
    # else keep original if cleaning removed everything

    # Remove trailing/leading dashes and dots
    working = working.strip('.-_ ')

    # Final length check
    if len(working) < 3:
        confidence = min(confidence, 30)
    elif len(working) < 6:
        confidence = min(confidence, 50)

    return working, confidence


# ---------------------------------------------------------------------------
# Contract ID Validation
# ---------------------------------------------------------------------------

_CONTRACT_ID_PATTERN = re.compile(r'^[A-Za-z0-9\-_./: ]{1,100}$')


def normalize_contract_id(contract_id: str) -> Tuple[str, int]:
    """
    Validate and normalize a contract ID.

    Confidence:
      100 — Valid, well-formed ID
       80 — Valid after trimming whitespace
       50 — Contains unusual characters (sanitized)
       20 — Empty or extremely short
    """
    if not contract_id or not contract_id.strip():
        return '', 0

    original = contract_id.strip()
    confidence = 100

    if original != contract_id:
        confidence = min(confidence, 80)

    working = original.upper()
    working = re.sub(r'\s+', '-', working)

    if not _CONTRACT_ID_PATTERN.match(working):
        # Remove non-alphanumeric except dashes
        working = re.sub(r'[^A-Z0-9\-_.]', '', working)
        confidence = min(confidence, 50)

    if len(working) < 3:
        confidence = min(confidence, 20)

    return working, confidence


# ---------------------------------------------------------------------------
# Date Parsing
# ---------------------------------------------------------------------------

_DATE_FORMATS = [
    '%Y-%m-%d',           # 2026-01-15
    '%m/%d/%Y',           # 01/15/2026
    '%m-%d-%Y',           # 01-15-2026
    '%d/%m/%Y',           # 15/01/2026 (ambiguous)
    '%Y/%m/%d',           # 2026/01/15
    '%B %d, %Y',          # January 15, 2026
    '%b %d, %Y',          # Jan 15, 2026
    '%d %B %Y',           # 15 January 2026
    '%d %b %Y',           # 15 Jan 2026
    '%Y%m%d',             # 20260115
    '%m/%d/%y',           # 01/15/26
]


def normalize_date(date_str: str) -> Tuple[Optional[str], int]:
    """
    Parse a date string into ISO format (YYYY-MM-DD).

    Confidence:
      100 — Unambiguous ISO format
       90 — Parsed from common format
       60 — Parsed but format is ambiguous (e.g., DD/MM vs MM/DD)
       30 — Parsed from unusual format
        0 — Could not parse
    """
    if not date_str or not date_str.strip():
        return None, 0

    s = date_str.strip()

    # ISO format — highest confidence
    if re.match(r'^\d{4}-\d{2}-\d{2}$', s):
        try:
            datetime.strptime(s, '%Y-%m-%d')
            return s, 100
        except ValueError:
            pass

    for i, fmt in enumerate(_DATE_FORMATS):
        try:
            dt = datetime.strptime(s, fmt)
            iso = dt.strftime('%Y-%m-%d')
            if i <= 1:
                confidence = 90
            elif i <= 4:
                confidence = 60  # Ambiguous day/month
            else:
                confidence = 30
            return iso, confidence
        except ValueError:
            continue

    return None, 0


# ---------------------------------------------------------------------------
# Amount Parsing
# ---------------------------------------------------------------------------

_CURRENCY_SYMBOLS = {'$', '\u00a3', '\u20ac', '\u00a5'}  # $, pound, euro, yen

_MULTIPLIER_SUFFIXES = {
    'k': 1_000, 'K': 1_000, 'thousand': 1_000,
    'm': 1_000_000, 'M': 1_000_000, 'million': 1_000_000, 'mil': 1_000_000,
    'b': 1_000_000_000, 'B': 1_000_000_000, 'billion': 1_000_000_000,
}


def normalize_amount(amount_str: str) -> Tuple[Optional[float], int, str]:
    """
    Parse a monetary amount from various formats.

    Returns: (amount_float, confidence, currency)

    Confidence:
      100 — Clean numeric
       90 — Parsed after removing currency symbol/commas
       70 — Parsed with multiplier suffix (e.g., "5M")
       50 — Parsed but ambiguous (e.g., different decimal conventions)
       30 — Very rough parsing
        0 — Could not parse
    """
    if amount_str is None:
        return None, 0, ''

    if isinstance(amount_str, (int, float)):
        return float(amount_str), 100, 'USD'

    s = str(amount_str).strip()
    if not s:
        return None, 0, ''

    # Detect currency
    currency = 'USD'
    for sym in _CURRENCY_SYMBOLS:
        if sym in s:
            if sym == '\u00a3':
                currency = 'GBP'
            elif sym == '\u20ac':
                currency = 'EUR'
            elif sym == '\u00a5':
                currency = 'JPY'
            s = s.replace(sym, '')
            break

    s = s.strip()

    # Check for multiplier suffixes
    multiplier = 1
    confidence = 100
    for suffix, mult in _MULTIPLIER_SUFFIXES.items():
        if s.endswith(suffix):
            s = s[:-len(suffix)].strip()
            multiplier = mult
            confidence = 70
            break

    # Remove commas and spaces in numbers
    s = s.replace(',', '').replace(' ', '')

    # Remove trailing currency codes
    for code in ['USD', 'EUR', 'GBP', 'JPY', 'CAD', 'AUD']:
        if s.upper().endswith(code):
            s = s[:-3].strip()
            confidence = min(confidence, 90)

    # Handle parentheses for negative
    if s.startswith('(') and s.endswith(')'):
        s = '-' + s[1:-1]
        confidence = min(confidence, 90)

    try:
        value = float(s) * multiplier
        if multiplier == 1 and confidence == 100:
            confidence = 90 if currency != 'USD' else 100
        return value, confidence, currency
    except ValueError:
        return None, 0, ''


# ---------------------------------------------------------------------------
# Composite Normalization
# ---------------------------------------------------------------------------

def normalize_record(record: Dict) -> Tuple[Dict, Dict]:
    """
    Normalize all fields in a contract record.

    Returns: (normalized_record, confidence_scores)
    where confidence_scores maps field names to 0-100 confidence.
    """
    normalized = {}
    confidences = {}

    # Contract ID
    if 'contract_id' in record and record['contract_id']:
        normalized['contract_id'], confidences['contract_id'] = \
            normalize_contract_id(str(record['contract_id']))
    else:
        normalized['contract_id'] = ''
        confidences['contract_id'] = 0

    # Vendor name
    if 'vendor_name' in record and record['vendor_name']:
        normalized['vendor_name'], confidences['vendor_name'] = \
            normalize_vendor_name(str(record['vendor_name']))
        normalized['vendor_name_raw'] = str(record['vendor_name']).strip()
    else:
        normalized['vendor_name'] = ''
        normalized['vendor_name_raw'] = ''
        confidences['vendor_name'] = 0

    # Agency name
    if 'agency_name' in record and record['agency_name']:
        agency = str(record['agency_name']).strip().upper()
        normalized['agency_name'] = agency
        confidences['agency_name'] = 90 if len(agency) > 5 else 50
    else:
        normalized['agency_name'] = ''
        confidences['agency_name'] = 0

    # Award amount
    if 'award_amount' in record and record['award_amount'] is not None:
        amt, conf, curr = normalize_amount(record['award_amount'])
        normalized['award_amount'] = amt
        normalized['currency'] = curr
        confidences['award_amount'] = conf
    else:
        normalized['award_amount'] = None
        normalized['currency'] = ''
        confidences['award_amount'] = 0

    # Description
    if 'description' in record and record['description']:
        desc = str(record['description']).strip()
        normalized['description'] = desc[:10000]
        confidences['description'] = 90 if len(desc) > 10 else 50
    else:
        normalized['description'] = ''
        confidences['description'] = 0

    # Date
    if 'start_date' in record and record['start_date']:
        dt, conf = normalize_date(str(record['start_date']))
        normalized['start_date'] = dt
        confidences['start_date'] = conf
    else:
        normalized['start_date'] = None
        confidences['start_date'] = 0

    # Overall confidence
    required_fields = ['contract_id', 'vendor_name', 'award_amount', 'agency_name']
    required_confs = [confidences.get(f, 0) for f in required_fields]
    overall = sum(required_confs) / len(required_confs) if required_confs else 0
    confidences['overall'] = round(overall)

    return normalized, confidences


def should_downgrade_severity(confidences: Dict, current_tier: str) -> Tuple[str, str]:
    """
    If data confidence is low, downgrade severity and return reason.

    Returns: (adjusted_tier, reason_or_empty_string)
    """
    overall = confidences.get('overall', 0)

    if overall < 30:
        return 'GRAY', (
            f'Evidence confidence too low ({overall}/100) for reliable assessment. '
            f'Key fields are missing or could not be parsed. '
            f'Original tier ({current_tier}) downgraded to GRAY (insufficient data).'
        )

    if overall < 50 and current_tier in ('RED', 'YELLOW'):
        return 'YELLOW' if current_tier == 'RED' else current_tier, (
            f'Evidence confidence is moderate ({overall}/100). '
            f'Some input fields required significant normalization. '
            f'Findings should be verified against source documents.'
        )

    return current_tier, ''
