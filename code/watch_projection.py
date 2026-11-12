"""Explicit organizational projections. Unlisted source fields never reach storage.

This is a narrow data contract, not a general personal-data classifier. Identifiers
are syntactically constrained, never inferred from names, and still require the
operator's organizational-scope review. Raw source bytes live only in memory.
"""
from datetime import datetime
import math
import re

from watch_journal import admit

SCHEMA = "sunlight.organisation-projection.v1"
VERSIONS = {"contracts_finder": "contracts-finder-organisations.v1",
            "iati_dportal": "dportal-organisations.v1"}
IDENTIFIER = {"scheme": "scheme", "id": "identifier"}
VALUE = {"amount": "amount", "currency": "currency"}
PERIOD = {"startDate": "date", "endDate": "date"}
PARTY = {"id": "identifier", "identifier": IDENTIFIER,
         "additionalIdentifiers": [IDENTIFIER]}
# roles are a traversal discriminator, not arbitrary retained strings. Only the
# three declared organizational role literals below can enter the projection.
ROLES = frozenset({"buyer", "supplier", "tenderer"})
CF_FIELDS = {
    "ocid": "identifier", "id": "identifier", "date": "timestamp",
    "buyer": PARTY,
    "tender": {"value": VALUE, "procurementMethod": "method",
               "numberOfTenderers": "count", "tenderPeriod": PERIOD,
               "contractPeriod": PERIOD},
    "parties": [PARTY],
    "awards": [{"id": "identifier", "date": "date", "datePublished": "timestamp",
                "value": VALUE, "contractPeriod": PERIOD, "suppliers": [PARTY]}],
}
IATI_FIELDS = {"aid": "identifier", "reporting_ref": "identifier", "updated_at": "timestamp"}


class FieldRefusal(ValueError):
    """Only fixed reason codes and schema-derived field paths, never values."""
    def __init__(self, field, reason):
        self.field, self.reason = field, reason
        super().__init__(reason + ":" + field)


def scalar(value, kind, path):
    try:
        admit(value)
    except ValueError:
        raise FieldRefusal(path, "protection_boundary") from None
    valid = False
    if kind in {"identifier", "scheme", "currency", "method", "date", "timestamp"}:
        if not isinstance(value, str):
            raise FieldRefusal(path, "invalid_field_type")
        if kind == "identifier":
            valid = bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/()%+\-]{0,255}", value))
        elif kind == "scheme":
            valid = bool(re.fullmatch(r"[A-Z0-9][A-Z0-9\-]{0,63}", value))
        elif kind == "currency":
            valid = bool(re.fullmatch(r"[A-Z]{3}", value))
        elif kind == "method":
            valid = value in {"open", "selective", "limited", "direct"}
        else:
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                valid = len(value) <= 40 and (kind != "timestamp" or parsed.tzinfo is not None)
            except ValueError:
                pass
    elif kind == "amount":
        try:
            valid = type(value) in (int, float) and math.isfinite(value)
        except OverflowError:
            valid = False
    elif kind == "count":
        valid = type(value) is int and value >= 0
    if not valid:
        raise FieldRefusal(path, "invalid_" + kind)
    return value


def select_fields(value, schema, path, mapped, gaps):
    """Visit declared keys only. Extra keys and their values are never copied."""
    if isinstance(schema, dict):
        if not isinstance(value, dict):
            raise FieldRefusal(path or "/", "invalid_object")
        result = {}
        for key, child in schema.items():
            field = path + "/" + key
            if key not in value or value[key] is None:
                gaps[field] = "not_supplied_in_record"
            else:
                result[key] = select_fields(value[key], child, field, mapped, gaps)
        return result
    if isinstance(schema, list):
        if not isinstance(value, list):
            raise FieldRefusal(path, "invalid_array")
        if not value:
            mapped.append(path)  # Published empty is different from absent.
        return [select_fields(v, schema[0], path + "/" + str(i), mapped, gaps)
                for i, v in enumerate(value)]
    result = scalar(value, schema, path)
    mapped.append(path)
    return result


def project_record(adapter, row, source_version=None):
    mapped, gaps = [], {}
    if not isinstance(row, dict):
        raise FieldRefusal("/", "invalid_object")
    if adapter == "contracts_finder":
        # Only buyer/supplier identifiers. Non-organizational roles are omitted;
        # keeping an empty slot preserves the original source pointer indexes.
        raw_parties = row.get("parties")
        safe_parties = []
        if isinstance(raw_parties, list):
            buyer = row.get("buyer")
            references = {buyer.get("id")} if isinstance(buyer, dict) and isinstance(buyer.get("id"), str) else set()
            awards = row.get("awards")
            for award in awards if isinstance(awards, list) else []:
                for supplier in award.get("suppliers", []) if isinstance(award, dict) and isinstance(award.get("suppliers", []), list) else []:
                    if isinstance(supplier, dict) and isinstance(supplier.get("id"), str):
                        references.add(supplier["id"])
            for p in raw_parties:
                roles = p.get("roles", []) if isinstance(p, dict) else []
                allowed_roles = [r for r in roles if isinstance(r, str) and r in ROLES] if isinstance(roles, list) else []
                included = bool(allowed_roles) or (isinstance(p, dict) and isinstance(p.get("id"), str) and p["id"] in references)
                safe_parties.append(p if included else {})
            # This temporary dictionary still references source data in memory.
            # select_fields is the sole path into the retained record.
            row_for_selection = {**row, "parties": safe_parties}
        else:
            row_for_selection = row
        result = select_fields(row_for_selection, CF_FIELDS, "", mapped, gaps)
        for key in ("ocid", "id"):
            if not result.get(key):
                raise FieldRefusal("/" + key, "missing_release_identity")
        if isinstance(raw_parties, list):
            for i, p in enumerate(raw_parties):
                roles = p.get("roles", []) if isinstance(p, dict) else []
                roles = sorted({r for r in roles if isinstance(r, str) and r in ROLES}) if isinstance(roles, list) else []
                if roles:
                    result["parties"][i]["roles"] = roles
                    mapped.append(f"/parties/{i}/roles")
        excluded = ["names", "addresses", "contacts", "descriptions", "documents", "review_body_roles"]
        publisher = {"service": "Contracts Finder", "basis": "reviewed_source_policy"}
        contract = "OCDS 1.1 award release JSON"
    elif adapter == "iati_dportal":
        result = select_fields(row, IATI_FIELDS, "", mapped, gaps)
        for key in ("aid", "reporting_ref"):
            if not result.get(key):
                raise FieldRefusal("/" + key, "missing_iati_identity")
        excluded = ["names", "addresses", "contacts", "narratives", "documents"]
        publisher = {"service": "d-portal", "reporting_ref": result["reporting_ref"]}
        contract = "d-portal q act JSON observed 2026-11-10"
    else:
        raise ValueError("unsupported_adapter")
    coverage = {"adapter_version": VERSIONS[adapter], "written_against": contract,
                "publisher": publisher, "publisher_version": source_version,
                "publisher_version_absence_reason": None if source_version else "not_exposed_by_endpoint",
                "mapped_fields": sorted(mapped), "gaps": dict(sorted(gaps.items())),
                "excluded_by_policy": excluded,
                "population_complete": None,
                "population_absence_reason": "single_page_does_not_prove_population_coverage",
                "limits": "Missing fields are not claims that the publisher cannot supply them elsewhere."}
    admit(result)
    admit(coverage)
    return result, coverage
