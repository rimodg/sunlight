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
        from urllib.parse import parse_qs
        query, original = parse_qs(p.query), parse_qs(b.query)
        stable = lambda q: {k: v for k, v in q.items() if k not in {"cursor", "offset"}}
        if stable(query) != stable(original):
            raise ValueError("pagination_filter_drift")
        # Check decoded values too, rather than letting percent encoding hide
        # personal-shaped query text from the journal boundary.
        admit(query)
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
        # Let urllib produce an HTTP failure receipt without following it.
        return None


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
            except Exception:
                # Headers were reached even when downloading the body failed.
                return {"status": response.status, "body": b"", "read_failed": True}
            return {"status": response.status, "body": body, "retry_after": None}
    except HTTPError as error:
        # Do not admit or log error bodies. Receiving an HTTP failure is a reach.
        result = {"status": error.code, "body": b"", "retry_after": (error.headers or {}).get("Retry-After")}
        error.close()
        return result


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


def project_page(source, body, *, url=None):
    """Project before admission. Refused rows keep only a fixed reason and path."""
    from watch_projection import SCHEMA, VERSIONS, FieldRefusal, project_record
    from urllib.parse import parse_qs, urlencode, urlunparse
    if len(body) > MAX_BYTES:
        raise ValueError("source_body_too_large")
    doc = json.loads(body)
    if not isinstance(doc, dict):
        raise ValueError("source_document_must_be_object")
    adapter = source["adapter"]
    key = "releases" if adapter == "contracts_finder" else "rows"
    rows = doc.get(key)
    if not isinstance(rows, list):
        raise ValueError("invalid_source_page")
    if adapter == "contracts_finder" and len(rows) > 100:
        raise ValueError("invalid_ocds_page")
    version = doc.get("version") if adapter == "contracts_finder" else None
    if version not in (None, "1.1"):
        raise ValueError("unsupported_source_version")
    records, refusals = [], []
    for index, row in enumerate(rows):
        try:
            record, coverage = project_record(adapter, row, version)
            records.append({"index": index, "record": record, "coverage": coverage})
        except FieldRefusal as error:
            refusals.append({"index": index, "field": error.field, "reason": error.reason})
    links = doc.get("links")
    next_url = links.get("next") if isinstance(links, dict) else None
    if adapter == "iati_dportal" and not next_url:
        current = url or source["url"]
        parsed = urlparse(current)
        query = parse_qs(parsed.query)
        # Live q responses expose LIMIT/OFFSET in their generated dquery SQL.
        # Only synthesize paging for this explicit reviewed query contract.
        if "limit" in query and query.get("orderby") == ["aid"]:
            limit = int(query["limit"][0])
            offset = int(query.get("offset", ["0"])[0])
            if not 1 <= limit <= 100 or offset < 0:
                raise ValueError("invalid_iati_paging")
            if len(rows) >= limit:
                query["offset"] = [str(offset + limit)]
                next_url = urlunparse(parsed._replace(query=urlencode(query, doseq=True)))
        elif len(rows) >= source.get("page_limit", 100):
            raise ValueError("iati_pagination_not_proven")
    if next_url:
        checked_url(next_url, source["url"])
        admit(next_url)
    projected = {"schema": SCHEMA, "adapter": adapter, "adapter_version": VERSIONS[adapter],
                 "records": records, "refusals": refusals, "received_count": len(rows), "next": next_url}
    admit(projected)
    return projected


def records_from_projection(source, projection):
    """Replay retained organizational data, never re-fetch the original body."""
    from watch_projection import SCHEMA, VERSIONS
    if projection.get("schema") != SCHEMA or projection.get("adapter") != source["adapter"]:
        raise ValueError("projection_schema")
    if projection.get("adapter_version") != VERSIONS[source["adapter"]]:
        raise ValueError("replay_requires_matching_adapter")
    admit(projection)
    records = []
    for item in projection["records"]:
        i, row = item["index"], item["record"]
        parties = []
        if source["adapter"] == "contracts_finder":
            def projected_party(p, loc):
                ids = ([{**p["identifier"], "_locator": loc + "/identifier"}]
                       if isinstance(p.get("identifier"), dict) else [])
                ids += [{**v, "_locator": loc + "/additionalIdentifiers/" + str(j)}
                        for j, v in enumerate(p.get("additionalIdentifiers", []))]
                # This is an explicitly published internal ID, never GB-COH.
                local = p.get("id", "")
                if local.startswith("GB-CFS-"):
                    ids.append({"scheme": "GB-CFS", "id": local[len("GB-CFS-"):],
                                "_locator": loc + "/id"})
                return party(ids, loc)
            for j, p in enumerate(row.get("parties", [])):
                if p:
                    parties.append(projected_party(p, f"/releases/{i}/parties/{j}"))
            known = {p.get("id") for p in row.get("parties", []) if p.get("id")}
            buyer = row.get("buyer")
            if buyer and buyer.get("id") not in known:
                parties.append(projected_party(buyer, f"/releases/{i}/buyer"))
            for a, award in enumerate(row.get("awards", [])):
                for j, supplier in enumerate(award.get("suppliers", [])):
                    if supplier.get("id") is None or supplier["id"] not in known:
                        parties.append(projected_party(supplier, f"/releases/{i}/awards/{a}/suppliers/{j}"))
            record = {"key": row["ocid"], "release_id": row["id"], "category": "procurement",
                      "published_at": utc(row["date"]) if row.get("date") else None,
                      "parties": parties, "locator": f"/releases/{i}",
                      "record": {**row, "_watch_projection": projection["adapter_version"]}}
        else:
            ref = row["reporting_ref"]
            ids = [{"scheme": "GB-COH", "id": ref[len("GB-COH-"):]}] if ref.startswith("GB-COH-") else []
            record = {"key": row["aid"], "category": "aid",
                      "published_at": utc(row["updated_at"]) if row.get("updated_at") else None,
                      "parties": [party(ids, f"/rows/{i}/reporting_ref")],
                      "locator": f"/rows/{i}", "record": row}
        record["coverage"] = item["coverage"]
        record["source"] = source["id"]
        def without_locators(value):
            if isinstance(value, dict):
                return {k: without_locators(v) for k, v in value.items() if k != "locator"}
            if isinstance(value, list):
                return [without_locators(v) for v in value]
            return value
        record["id"] = digest(without_locators(record))
        records.append(record)
    return records, projection["next"]


def adapt(source, body):
    return records_from_projection(source, project_page(source, body))


def frozen_records(journal, source, url, at, body, policy_hash, seen=()):
    projection = project_page(source, body, url=url)
    records, next_url = records_from_projection(source, projection)
    if next_url and (next_url == url or next_url in seen):
        raise ValueError("pagination_cycle")
    capture_id = journal.freeze(source["id"], url, at, projection, policy_hash,
                                {"records": records, "adapter": source["adapter"],
                                 "source_policy": source, "next": next_url},
                                source_sha256=hashlib.sha256(body).hexdigest())
    return capture_id, records, next_url
