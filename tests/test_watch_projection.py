"""Synthetic privacy, coverage and replay proofs for organizational projection."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile

import pytest

from watch_capture import adapt, frozen_records, project_page, records_from_projection
from watch_engine import WatchEngine
from watch_identity import canonical, digest
from watch_journal import Journal
from watch_packet import packet, replay
from watch_examination import procurement
from tests.test_watch_loop import CF, IATI, release, response, reader


def test_projection_discards_unlisted_fields_before_gate_and_storage():
    row = release()
    secret = "synthetic-person@example.invalid"
    row.update(title=secret, description=secret, documents=[{"url": secret}])
    row["parties"][0].update(name=secret, contactPoint={"email": secret}, address={"streetAddress": secret})
    row["parties"][0]["identifier"]["legalName"] = secret
    body = json.dumps({"releases": [row], "publisher": {"name": secret}}).encode()
    with tempfile.TemporaryDirectory() as directory:
        j = Journal(Path(directory) / "journal.sqlite3")
        try:
            engine = WatchEngine(j, {"schema": "sunlight.watch-source-policy.v1", "sources": [CF]},
                                 transport=lambda u: {"body": body, "status": 200},
                                 clock=lambda: "2026-01-02T00:00:00Z", reader=reader)
            result = engine.tick()
            assert len(result["observations"]) == 1
            capture = j.capture(j.events(kind="capture")[0]["id"])
            assert "body" not in capture
            assert capture["sha256"] == hashlib.sha256(body).hexdigest()
            assert capture["projection_sha256"] == digest(capture["projection"])
            value = packet(j, j.events(kind="examination")[0]["id"])
            assert canonical(replay(value, reader=reader)) == canonical(result)
            assert secret not in canonical(value)
            assert secret not in canonical(j.events())
            j.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            for path in Path(directory).iterdir():
                assert secret.encode() not in path.read_bytes()
        finally:
            j.close()


@pytest.mark.parametrize("field,change", [
    ("/ocid", lambda r: r.update(ocid="person@example.invalid")),
    ("/id", lambda r: r.update(id="Jane Smith")),
    ("/parties/0/identifier/id", lambda r: r["parties"][0]["identifier"].update(id="person@example.invalid")),
    ("/parties/0/identifier/scheme", lambda r: r["parties"][0]["identifier"].update(scheme="Jane Smith")),
    ("/awards/0/value/currency", lambda r: r["awards"][0]["value"].update(currency="person@example.invalid")),
    ("/awards/0/value/amount", lambda r: r["awards"][0]["value"].update(amount="person@example.invalid")),
    ("/date", lambda r: r.update(date="person@example.invalid")),
])
def test_allowed_fields_still_refuse_personal_shaped_values_without_echo(field, change):
    row = release()
    change(row)
    page = project_page(CF, json.dumps({"releases": [row, release()]}).encode())
    assert len(page["records"]) == 1
    assert page["records"][0]["index"] == 1
    assert len(page["refusals"]) == 1
    assert page["refusals"][0]["field"] == field
    assert "person@example.invalid" not in canonical(page)
    assert "Jane Smith" not in canonical(page)
    records, _ = records_from_projection(CF, page)
    assert records[0]["locator"] == "/releases/1"


def test_coverage_preserves_zero_and_reports_missing_without_blame():
    row = release(0)
    row["tender"] = {"numberOfTenderers": 0}
    records, _ = adapt(CF, json.dumps({"version": "1.1", "releases": [row]}).encode())
    item = records[0]
    assert item["record"]["awards"][0]["value"]["amount"] == 0
    assert item["record"]["tender"]["numberOfTenderers"] == 0
    coverage = item["coverage"]
    assert "/tender/numberOfTenderers" in coverage["mapped_fields"]
    assert coverage["gaps"]["/tender/value"] == "not_supplied_in_record"
    assert coverage["publisher_version"] == "1.1"
    assert coverage["population_complete"] is None
    assert "addresses" in coverage["excluded_by_policy"]


def test_excluded_review_parties_never_become_negative_evidence():
    row = release()
    row["parties"].append({"roles": ["reviewBody"], "name": "Excluded person"})
    record = adapt(CF, json.dumps({"releases": [row]}).encode())[0][0]
    results = {r["rule"]: r for r in procurement(record["record"])}
    assert results["PROC-003"]["status"] == "UNASSESSABLE"
    assert results["PROC-004"]["status"] == "UNASSESSABLE"
    assert "Excluded person" not in canonical(record)


def test_internal_party_scheme_is_not_registry_identity():
    row = release()
    row["parties"][0] = {"roles": ["supplier"], "id": "GB-CFS-200872"}
    record = adapt(CF, json.dumps({"releases": [row]}).encode())[0][0]
    identifier = record["parties"][0]["identifiers"][0]
    assert identifier["scheme"] == "GB-CFS"
    assert identifier["normalised_value"] is None
    assert identifier["locator"] == "/releases/0/parties/0/id"


def test_excluded_fields_do_not_change_observation_identity():
    first = release()
    second = copy.deepcopy(first)
    first["parties"][0]["name"] = "First excluded name"
    second["parties"][0]["name"] = "Second excluded name"
    a = adapt(CF, json.dumps({"releases": [first]}).encode())[0][0]
    b = adapt(CF, json.dumps({"releases": [second]}).encode())[0][0]
    assert a["id"] == b["id"]


def test_iati_identifier_query_and_offset_next_page():
    source = {**IATI, "url": "https://example.invalid/q?from=act&select=aid,reporting_ref&reporting_ref_like=GB-COH-%25&limit=1&offset=0&orderby=aid&form=json"}
    body = json.dumps({"rows": [{"aid": "activity-1", "reporting_ref": "GB-COH-00123456",
                                "title": "person@example.invalid"}], "dquery": "ignored"}).encode()
    page = project_page(source, body)
    assert "offset=1" in page["next"]
    assert page["refusals"] == []
    record = records_from_projection(source, page)[0][0]
    assert record["key"] == "activity-1"
    assert record["coverage"]["gaps"]["/updated_at"] == "not_supplied_in_record"
    assert "person@example.invalid" not in canonical(page)


def test_iati_missing_id_refused_with_field_reason():
    page = project_page(IATI, b'{"rows":[{"reporting_ref":"GB-COH-00123456"}]}')
    assert page["records"] == []
    assert page["refusals"] == [{"index": 0, "field": "/aid", "reason": "missing_iati_identity"}]


def test_projection_tampering_and_wrong_adapter_version_refused():
    page = project_page(CF, json.dumps({"releases": [release()]}).encode())
    page["adapter_version"] = "unreviewed"
    with pytest.raises(ValueError, match="matching_adapter"):
        records_from_projection(CF, page)


def test_bad_allowed_nested_shape_refuses_row_not_other_rows():
    row = release()
    row["awards"][0]["value"] = ["person@example.invalid"]
    page = project_page(CF, json.dumps({"releases": [row, release()]}).encode())
    assert page["refusals"] == [{"index": 0, "field": "/awards/0/value", "reason": "invalid_object"}]
    assert len(page["records"]) == 1


def test_legacy_capture_is_refused_without_rewriting_old_journal():
    with tempfile.TemporaryDirectory() as directory:
        j = Journal(Path(directory) / "journal.sqlite3")
        try:
            cid = j.append("capture", "2026-01-01T00:00:00Z", {"body": "{}", "sha256": hashlib.sha256(b'{}').hexdigest()})
            before = canonical(j.events())
            with pytest.raises(ValueError, match="explicit_migration"):
                j.capture(cid)
            assert canonical(j.events()) == before
        finally:
            j.close()
