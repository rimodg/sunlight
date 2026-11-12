from scripts.report_watch_population import summarize


def test_buyer_registry_id_is_not_supplier_coverage_and_internal_ids_do_not_join():
    buyer = {"id": "buyer", "identifier": {"scheme": "GB-COH", "id": "00123456"}}
    supplier = {"id": "GB-CFS-123", "identifier": {"scheme": "GB-CFS", "id": "123"}}
    record = {"id": "version-1", "key": "contract-1", "parties": [],
              "record": {"parties": [buyer, supplier], "awards": [{"id": "a", "suppliers": [{"id": "GB-CFS-123"}]}]}}
    result = summarize([{"kind": "observations", "payload": {"records": [record]}}])
    assert result["admitted_award_rows"] == 1
    assert result["awards_with_supplier_registry_identifier"] == 0
    supplier["additionalIdentifiers"] = [{"scheme": "GB-COH", "id": "87654321"}]
    result = summarize([{"kind": "observations", "payload": {"records": [record]}}])
    assert result["registry_identifiers"] == [("GB-COH", "87654321")]
    assert result["registry_share_of_admitted_awards"] == 1


def test_missing_denominator_is_not_zero():
    result = summarize([])
    assert result["registry_share_of_admitted_awards"] is None
    assert result["cycle_complete"] is False
