"""Reviewed source policy, organization adapters, bounded HTTP and resumable paging."""
from __future__ import annotations

import hashlib
import json
import os
from urllib.parse import urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError

from watch_identity import POLICY, digest, normalise
from watch_journal import admit, utc

MAX_BYTES = 8 * 1024 * 1024


def checked_url(url, base=None):
    if not isinstance(url, str):
        raise ValueError("source_url_refused")
    p = urlparse(url)
    if p.scheme != "https" or not p.hostname or p.username or p.password or p.fragment:
        raise ValueError("source_url_refused")
    if base:
        b = urlparse(base)
        if (p.scheme, p.netloc, p.path) != (b.scheme, b.netloc, b.path):
            raise ValueError("pagination_scope_refused")
    return url


def policy(value):
    if not isinstance(value, dict) or value.get("schema") != "sunlight.watch-source-policy.v1" or not isinstance(value.get("sources"), list):
        raise ValueError("source_policy_schema")
    seen = set()
    for s in value["sources"]:
        if not isinstance(s, dict):
            raise ValueError("source_policy_schema")
        if not isinstance(s.get("id"), str) or not s["id"] or s["id"] in seen:
            raise ValueError("duplicate_or_missing_source_id")
        seen.add(s["id"])
        if s.get("adapter") not in {"contracts_finder", "iati_dportal"}:
            raise ValueError("unsupported_adapter")
        if s.get("organisation_only_reviewed") is not True:
            raise ValueError("organisation_scope_review_required")
        if not isinstance(s.get("interval_seconds"), int) or not 60 <= s["interval_seconds"] <= 31536000:
            raise ValueError("invalid_source_interval")
        checked_url(s["url"])
        if s["adapter"] == "contracts_finder":
            from urllib.parse import parse_qs
            if parse_qs(urlparse(s["url"]).query).get("limit") != ["100"]:
                raise ValueError("contracts_finder_limit_must_be_100")
        if s["adapter"] == "iati_dportal":
            from urllib.parse import parse_qs
            refs = parse_qs(urlparse(s["url"]).query).get("reporting_ref_like", [])
            if not refs or not any("%" in r for r in refs):
                raise ValueError("iati_reporting_ref_like_wildcard_required")
    admit(value)
    return value


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("redirect_refused")


def fetch(url):
    """No retries here. Each attempted reach is recorded by the scheduler."""
    if os.environ.get("SUNLIGHT_OFFLINE") == "1":
        raise OSError("offline")
    checked_url(url)
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "SUNLIGHT-watch/1"})
    try:
        with build_opener(NoRedirect).open(request, timeout=30) as response:
            try:
                body = response.read(MAX_BYTES + 1)
            except OSError:
                # Headers were reached even when downloading the body failed.
                return {"status": response.status, "body": b"", "read_failed": True}
            return {"status": response.status, "body": body, "retry_after": None}
    except HTTPError as error:
        # Do not admit or log error bodies. Receiving an HTTP failure is a reach.
        return {"status": error.code, "body": b"", "retry_after": error.headers.get("Retry-After")}


def party(identifiers, locator):
    out = []
    for item in identifiers:
        if not isinstance(item, dict):
            continue
        scheme, value = item.get("scheme"), item.get("id")
        if not isinstance(value, str):
            continue
        out.append({"scheme": scheme, "value": value, "published_value": value,
                    "normalised_value": normalise(scheme, value), "policy": POLICY,
                    "locator": item.get("_locator", locator)})
    return {"identifiers": out}


def adapt(source, body):
    """Records retain their document pointers and published identifiers.

    Bodies are admitted before freezing. Unknown parties remain unresolved.
    D-portal JSON rows must supply an activity ID and reporting_ref; titles,
    personnel and beneficiary data are neither required nor invented.
    """
    doc = json.loads(body)
    admit(doc)
    if not isinstance(doc, dict):
        raise ValueError("source_document_must_be_object")
    records = []
    if source["adapter"] == "contracts_finder":
        rows = doc.get("releases")
        if not isinstance(rows, list) or len(rows) > 100:
            raise ValueError("invalid_ocds_page")
        next_url = (doc.get("links") or {}).get("next")
        for i, row in enumerate(rows):
            if not isinstance(row.get("ocid"), str) or not row.get("id"):
                raise ValueError("missing_release_identity")
            parties = []
            for j, p in enumerate(row.get("parties", [])):
                loc = f"/releases/{i}/parties/{j}"
                ids = ([{**p["identifier"], "_locator": loc + "/identifier"}] if isinstance(p.get("identifier"), dict) else [])
                ids += [{**item, "_locator": f"{loc}/additionalIdentifiers/{k}"}
                        for k, item in enumerate(p.get("additionalIdentifiers", [])) if isinstance(item, dict)]
                parties.append(party(ids, loc))
            known = {p.get("id") for p in row.get("parties", [])}
            # Publisher-local party references are not company identifiers. Keep
            # unmatched suppliers as explicit unresolved parties, never discard.
            for a, award in enumerate(row.get("awards", [])):
                for s, supplier in enumerate(award.get("suppliers", [])):
                    if supplier.get("id") not in known:
                        ids = [supplier["identifier"]] if isinstance(supplier.get("identifier"), dict) else []
                        parties.append(party(ids, f"/releases/{i}/awards/{a}/suppliers/{s}/identifier"))
            records.append({"key": row["ocid"], "release_id": row["id"], "category": "procurement",
                            "published_at": utc(row["date"]) if row.get("date") else None,
                            "parties": parties, "locator": f"/releases/{i}", "record": row})
    else:
        rows = doc.get("rows")
        if not isinstance(rows, list):
            raise ValueError("invalid_iati_page")
        next_url = (doc.get("links") or {}).get("next")
        # A naked full limit page is not evidence that the population ended.
        if len(rows) >= source.get("page_limit", 100) and not next_url and doc.get("complete") is not True:
            raise ValueError("iati_pagination_not_proven")
        for i, row in enumerate(rows):
            if not isinstance(row.get("aid"), str) or not isinstance(row.get("reporting_ref"), str):
                raise ValueError("missing_iati_identity")
            ref = row["reporting_ref"]
            ids = [{"scheme": "GB-COH", "id": ref[len("GB-COH-"):]}] if ref.startswith("GB-COH-") else []
            records.append({"key": row["aid"], "category": "aid",
                            "published_at": utc(row["updated_at"]) if row.get("updated_at") else None,
                            "parties": [party(ids, f"/rows/{i}/reporting_ref")],
                            "locator": f"/rows/{i}", "record": row})
    if next_url:
        checked_url(next_url, source["url"])
    for record in records:
        # An observation's identity does not depend on unrelated rows on its page.
        record["source"] = source["id"]
        def without_locators(value):
            if isinstance(value, dict):
                return {k: without_locators(v) for k, v in value.items() if k != "locator"}
            if isinstance(value, list):
                return [without_locators(v) for v in value]
            return value
        record["id"] = digest(without_locators(record))
    return records, next_url


def frozen_records(journal, source, url, at, body, policy_hash, seen=()):
    if len(body) > MAX_BYTES:
        raise ValueError("source_body_too_large")
    records, next_url = adapt(source, body)
    if next_url and (next_url == url or next_url in seen):
        raise ValueError("pagination_cycle")
    capture_id = journal.freeze(source["id"], url, at, body, policy_hash,
                                {"records": records, "adapter": source["adapter"],
                                 "source_policy": source, "next": next_url})
    return capture_id, records, next_url
