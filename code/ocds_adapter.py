"""
OCDS Adapter — Open Contracting Data Standard normalization layer.

Transforms raw OCDS JSON releases into SUNLIGHT's internal contract schema.
Handles all OCDS release tags: planning, tender, award, contract, implementation.
Includes field mapping, validation, and graceful handling of missing fields.

OCDS spec: https://standard.open-contracting.org/latest/en/
"""

import hashlib
import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional

logger = logging.getLogger("sunlight.ocds_adapter")


# ---------------------------------------------------------------------------
# OCDS release tags
# ---------------------------------------------------------------------------

OCDS_TAGS = {
    "planning",
    "planningUpdate",
    "tender",
    "tenderAmendment",
    "tenderUpdate",
    "tenderCancellation",
    "award",
    "awardUpdate",
    "awardCancellation",
    "contract",
    "contractUpdate",
    "contractAmendment",
    "implementation",
    "implementationUpdate",
}


# ---------------------------------------------------------------------------
# SUNLIGHT internal contract schema
# ---------------------------------------------------------------------------

@dataclass
class SunlightContract:
    """SUNLIGHT's internal contract representation."""

    contract_id: str
    award_amount: float = 0.0
    vendor_name: str = ""
    agency_name: str = ""
    description: str = ""
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    award_type: Optional[str] = None
    num_offers: Optional[int] = None
    extent_competed: Optional[str] = None
    currency: str = "USD"
    raw_data_hash: str = ""
    source: str = "ocds"
    ocds_id: str = ""
    ocds_tag: str = ""
    procurement_method: Optional[str] = None
    tender_status: Optional[str] = None
    amendments: list = field(default_factory=list)
    validation_warnings: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    def is_valid(self) -> bool:
        """Minimum validity: has contract_id, vendor, and positive amount."""
        return bool(self.contract_id and self.vendor_name and self.award_amount > 0)


# ---------------------------------------------------------------------------
# Field extraction helpers
# ---------------------------------------------------------------------------

def _safe_get(obj: dict, *keys, default=None):
    """Safely navigate nested dict keys."""
    current = obj
    for key in keys:
        if isinstance(current, dict):
            current = current.get(key)
        elif isinstance(current, list) and isinstance(key, int) and key < len(current):
            current = current[key]
        else:
            return default
        if current is None:
            return default
    return current


def _extract_amount(value_obj) -> tuple:
    """Extract amount and currency from an OCDS Value object.

    OCDS Value: {"amount": 1000000, "currency": "USD"}
    """
    if not isinstance(value_obj, dict):
        return 0.0, "USD"
    amount = value_obj.get("amount", 0)
    currency = value_obj.get("currency", "USD")
    try:
        amount = float(amount) if amount is not None else 0.0
    except (ValueError, TypeError):
        amount = 0.0
    return amount, currency


def _extract_date(date_str) -> Optional[str]:
    """Normalize an OCDS date string to ISO format."""
    if not date_str:
        return None
    if isinstance(date_str, str):
        # Handle various date formats
        for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(date_str[:len(fmt.replace("%", "x"))], fmt)
                return dt.strftime("%Y-%m-%d")
            except (ValueError, IndexError):
                continue
        # Return as-is if it looks like a date
        if len(date_str) >= 10 and date_str[4] == "-":
            return date_str[:10]
    return None


def _extract_organization_name(org) -> str:
    """Extract name from an OCDS Organization object."""
    if isinstance(org, dict):
        return org.get("name", "") or org.get("legalName", "") or ""
    if isinstance(org, str):
        return org
    return ""


def _compute_hash(data: dict) -> str:
    """Compute SHA-256 hash of the raw OCDS release."""
    raw = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Release tag handlers
# ---------------------------------------------------------------------------

def _map_planning(release: dict) -> list:
    """Extract contracts from a planning release (budget allocations)."""
    contracts = []
    planning = release.get("planning", {})
    budget = planning.get("budget", {})
    amount, currency = _extract_amount(budget.get("amount"))

    if amount > 0:
        c = SunlightContract(
            contract_id=release.get("ocid", "") + "-planning",
            award_amount=amount,
            currency=currency,
            description=budget.get("description", "") or planning.get("rationale", ""),
            agency_name=_extract_buyer_name(release),
            ocds_id=release.get("ocid", ""),
            ocds_tag="planning",
            raw_data_hash=_compute_hash(release),
        )
        c.validation_warnings.append("Planning stage — amount is budgeted, not awarded")
        contracts.append(c)

    return contracts


def _map_tender(release: dict) -> list:
    """Extract contracts from a tender release."""
    contracts = []
    tender = release.get("tender", {})
    amount, currency = _extract_amount(tender.get("value"))

    c = SunlightContract(
        contract_id=release.get("ocid", "") + "-tender",
        award_amount=amount,
        currency=currency,
        description=tender.get("description", "") or tender.get("title", ""),
        agency_name=_extract_buyer_name(release),
        procurement_method=tender.get("procurementMethod", ""),
        tender_status=tender.get("status", ""),
        num_offers=tender.get("numberOfTenderers"),
        ocds_id=release.get("ocid", ""),
        ocds_tag="tender",
        raw_data_hash=_compute_hash(release),
    )

    # Map procurement method to extent_competed
    method = (tender.get("procurementMethod") or "").lower()
    if method == "open":
        c.extent_competed = "FULL AND OPEN COMPETITION"
    elif method == "selective":
        c.extent_competed = "FULL AND OPEN COMPETITION AFTER EXCLUSION OF SOURCES"
    elif method in ("limited", "direct"):
        c.extent_competed = "NOT COMPETED"
    elif method:
        c.extent_competed = method.upper()

    # Timeline
    tender_period = tender.get("tenderPeriod", {})
    c.start_date = _extract_date(tender_period.get("startDate"))
    c.end_date = _extract_date(tender_period.get("endDate"))

    if amount > 0 or c.description:
        contracts.append(c)

    return contracts


def _map_award(release: dict) -> list:
    """Extract contracts from an award release."""
    contracts = []
    awards = release.get("awards", [])
    if not isinstance(awards, list):
        awards = [awards]

    for idx, award in enumerate(awards):
        if not isinstance(award, dict):
            continue

        amount, currency = _extract_amount(award.get("value"))

        # Get winning vendor
        suppliers = award.get("suppliers", [])
        vendor_name = ""
        if suppliers and isinstance(suppliers, list):
            vendor_name = _extract_organization_name(suppliers[0])

        award_id = award.get("id", str(idx))
        c = SunlightContract(
            contract_id=f"{release.get('ocid', '')}-award-{award_id}",
            award_amount=amount,
            currency=currency,
            vendor_name=vendor_name,
            agency_name=_extract_buyer_name(release),
            description=award.get("description", "") or award.get("title", ""),
            start_date=_extract_date(award.get("date")),
            award_type=award.get("status", ""),
            ocds_id=release.get("ocid", ""),
            ocds_tag="award",
            raw_data_hash=_compute_hash(release),
        )
        contracts.append(c)

    return contracts


def _map_contract(release: dict) -> list:
    """Extract contracts from a contract release."""
    contracts_list = []
    raw_contracts = release.get("contracts", [])
    if not isinstance(raw_contracts, list):
        raw_contracts = [raw_contracts]

    for idx, contract in enumerate(raw_contracts):
        if not isinstance(contract, dict):
            continue

        amount, currency = _extract_amount(contract.get("value"))

        # Get vendor from linked award or contract
        vendor_name = ""
        award_id = contract.get("awardID")
        if award_id:
            awards = release.get("awards", [])
            for a in (awards if isinstance(awards, list) else []):
                if isinstance(a, dict) and a.get("id") == award_id:
                    suppliers = a.get("suppliers", [])
                    if suppliers:
                        vendor_name = _extract_organization_name(suppliers[0])
                    break

        period = contract.get("period", {})
        cid = contract.get("id", str(idx))

        # Amendments
        amendments = []
        for amend in contract.get("amendments", []) or []:
            if isinstance(amend, dict):
                amendments.append({
                    "date": _extract_date(amend.get("date")),
                    "description": amend.get("description", ""),
                    "amount_change": amend.get("value", {}).get("amount", 0) if isinstance(amend.get("value"), dict) else 0,
                })

        c = SunlightContract(
            contract_id=f"{release.get('ocid', '')}-contract-{cid}",
            award_amount=amount,
            currency=currency,
            vendor_name=vendor_name,
            agency_name=_extract_buyer_name(release),
            description=contract.get("description", "") or contract.get("title", ""),
            start_date=_extract_date(period.get("startDate")),
            end_date=_extract_date(period.get("endDate")),
            ocds_id=release.get("ocid", ""),
            ocds_tag="contract",
            raw_data_hash=_compute_hash(release),
            amendments=amendments,
        )
        contracts_list.append(c)

    return contracts_list


def _map_implementation(release: dict) -> list:
    """Extract data from an implementation release (updates existing contracts)."""
    contracts = []
    raw_contracts = release.get("contracts", [])
    if not isinstance(raw_contracts, list):
        raw_contracts = [raw_contracts]

    for idx, contract in enumerate(raw_contracts):
        if not isinstance(contract, dict):
            continue

        impl = contract.get("implementation", {})
        if not isinstance(impl, dict):
            continue

        # Sum transactions as actual spend
        transactions = impl.get("transactions", [])
        total_spent = 0.0
        currency = "USD"
        for tx in (transactions if isinstance(transactions, list) else []):
            if isinstance(tx, dict):
                amt, cur = _extract_amount(tx.get("value"))
                total_spent += amt
                currency = cur

        amount, _ = _extract_amount(contract.get("value"))
        cid = contract.get("id", str(idx))

        c = SunlightContract(
            contract_id=f"{release.get('ocid', '')}-impl-{cid}",
            award_amount=amount if amount > 0 else total_spent,
            currency=currency,
            vendor_name="",  # Vendor info usually in award, not implementation
            agency_name=_extract_buyer_name(release),
            description=contract.get("description", ""),
            ocds_id=release.get("ocid", ""),
            ocds_tag="implementation",
            raw_data_hash=_compute_hash(release),
        )
        if total_spent > 0:
            c.validation_warnings.append(
                f"Implementation: actual spend ${total_spent:,.2f} vs contract value ${amount:,.2f}"
            )
        contracts.append(c)

    return contracts


def _extract_buyer_name(release: dict) -> str:
    """Extract the buyer/procuring entity name from a release."""
    buyer = release.get("buyer")
    if buyer:
        return _extract_organization_name(buyer)

    # Fallback: check parties with "buyer" role
    parties = release.get("parties", [])
    if isinstance(parties, list):
        for party in parties:
            if isinstance(party, dict):
                roles = party.get("roles", [])
                if isinstance(roles, list) and "buyer" in roles:
                    return _extract_organization_name(party)

    return ""


# ---------------------------------------------------------------------------
# Main adapter
# ---------------------------------------------------------------------------

TAG_HANDLERS = {
    "planning": _map_planning,
    "planningUpdate": _map_planning,
    "tender": _map_tender,
    "tenderAmendment": _map_tender,
    "tenderUpdate": _map_tender,
    "tenderCancellation": _map_tender,
    "award": _map_award,
    "awardUpdate": _map_award,
    "awardCancellation": _map_award,
    "contract": _map_contract,
    "contractUpdate": _map_contract,
    "contractAmendment": _map_contract,
    "implementation": _map_implementation,
    "implementationUpdate": _map_implementation,
}


def transform_release(release: dict) -> list:
    """Transform a single OCDS release into SUNLIGHT contracts.

    Dispatches to the appropriate handler based on release tag(s).
    A single release can produce multiple contracts (e.g., multiple awards).

    Args:
        release: Raw OCDS release JSON dict.

    Returns:
        List of SunlightContract objects.
    """
    if not isinstance(release, dict):
        logger.warning(f"Invalid release: expected dict, got {type(release)}")
        return []

    tags = release.get("tag", [])
    if isinstance(tags, str):
        tags = [tags]
    if not isinstance(tags, list):
        tags = []

    contracts = []
    handled = False

    for tag in tags:
        handler = TAG_HANDLERS.get(tag)
        if handler:
            handled = True
            try:
                result = handler(release)
                contracts.extend(result)
            except Exception as e:
                logger.error(f"Error processing tag '{tag}' for release {release.get('ocid', '?')}: {e}")
                continue

    if not handled and tags:
        logger.warning(f"Unrecognized OCDS tag(s): {tags} for release {release.get('ocid', '?')}")

    # If no tag but has awards or contracts, try to extract anyway
    if not handled:
        if release.get("awards"):
            contracts.extend(_map_award(release))
        if release.get("contracts"):
            contracts.extend(_map_contract(release))

    return contracts


def transform_releases(releases: list, validate: bool = True) -> list:
    """Transform multiple OCDS releases into SUNLIGHT contracts.

    Args:
        releases: List of OCDS release dicts.
        validate: If True, filter out invalid contracts and add warnings.

    Returns:
        List of SunlightContract objects.
    """
    all_contracts = []
    for release in releases:
        contracts = transform_release(release)
        all_contracts.extend(contracts)

    if validate:
        valid = []
        for c in all_contracts:
            if c.is_valid():
                valid.append(c)
            else:
                missing = []
                if not c.contract_id:
                    missing.append("contract_id")
                if not c.vendor_name:
                    missing.append("vendor_name")
                if c.award_amount <= 0:
                    missing.append("award_amount")
                logger.info(
                    f"Skipping invalid contract {c.contract_id or '?'}: missing {', '.join(missing)}"
                )
        return valid

    return all_contracts


def transform_record(record: dict) -> list:
    """Transform an OCDS record (compiled releases) into SUNLIGHT contracts.

    An OCDS record contains a compiledRelease which is the latest state.
    """
    compiled = record.get("compiledRelease")
    if compiled:
        return transform_release(compiled)

    # Fallback: process individual releases
    releases = record.get("releases", [])
    if releases:
        return transform_releases(releases)

    return []
