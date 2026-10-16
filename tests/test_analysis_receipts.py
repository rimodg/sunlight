"""Institutional output contracts: traceability without altering verdicts."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys

from fastapi.testclient import TestClient
from api import app
from analysis_receipt import content_digest, substantive_result

client = TestClient(app)


def record(ocid="receipt-test"):
    return {"ocid": ocid,
            "tender": {"procurementMethod": "direct", "value": {"amount": 1000000, "currency": "USD"}},
            "awards": [{"value": {"amount": 1500000, "currency": "USD"},
                        "suppliers": [{"name": "Example supplier", "id": "example"}]}]}


def assert_receipt(result):
    receipt = result["analysis_receipt"]
    assert content_digest(receipt["normalized_request"]) == receipt["input_sha256"]
    substantive = substantive_result(result)
    assert content_digest(substantive) == receipt["result_sha256"]
    assert content_digest(receipt["source_manifest"]) == receipt["source_manifest_sha256"]
    assert "api.py" in receipt["source_manifest"]
    assert "probability" in receipt["interpretation"]


def test_receipt_reproduces_and_detects_changed_output():
    request = {"contract": record()}
    a = client.post('/analyze', json=request).json()
    b = client.post('/analyze', json=request).json()
    assert_receipt(a)
    assert 'tender_value' not in a['ingestion_quality']['missing_fields']
    assert 'award_value' not in a['ingestion_quality']['missing_fields']
    assert not a['ingestion_quality']['mapping_gaps']
    assert 'suppliers' not in a['ingestion_quality']['missing_fields']
    assert a['analysis_receipt'] == b['analysis_receipt']
    changed = deepcopy(a)
    changed['recommended_for_investigation'] = not a['recommended_for_investigation']
    substantive = substantive_result(changed)
    assert content_digest(substantive) != a['analysis_receipt']['result_sha256']


def test_sparse_input_reports_missing_fields_without_inventing_completeness():
    result = client.post('/analyze', json={'contract': {'ocid': 'sparse'}}).json()
    quality = result['ingestion_quality']
    assert quality['fields_present'] < quality['fields_total']
    assert 'supplier_name' in quality['missing_fields']
    assert 'number_of_tenderers' in quality['missing_fields']
    assert_receipt(result)


def test_ties_are_disclosed_and_capacity_is_stable_under_reordering():
    contracts = [record(f'case-{i}') for i in range(6)]
    a = client.post('/batch', json={'contracts': contracts, 'capacity_budget': 2}).json()
    b = client.post('/batch', json={'contracts': list(reversed(contracts)), 'capacity_budget': 2}).json()
    selected = lambda body: sorted(r['ocid'] for r in body['results'] if r['recommended_for_investigation'])
    assert selected(a) == selected(b) == ['case-0', 'case-1']
    meta = a['threshold_metadata']
    assert meta['recommended_count'] == 2
    assert meta['deferred_count'] == 4
    assert len(meta['boundary_tie']) == 6
    assert sum(t['selected'] for t in meta['boundary_tie']) == 2
    for result in a['results']:
        assert_receipt(result)


def test_capacity_zero_and_empty_batch_have_finite_json_metadata():
    for contracts in ([], [record()]):
        response = client.post('/batch', json={'contracts': contracts, 'capacity_budget': 0})
        assert response.status_code == 200
        body = response.json()
        assert body['threshold_metadata']['recommended_count'] == 0
        assert body['threshold_metadata']['binding_threshold'] is not None
        assert all(not r['recommended_for_investigation'] for r in body['results'])


def test_capacity_does_not_change_analytical_findings():
    contracts = [record(f'case-{i}') for i in range(3)]
    a = client.post('/batch', json={'contracts': contracts}).json()
    b = client.post('/batch', json={'contracts': contracts, 'capacity_budget': 1}).json()
    for left, right in zip(a['results'], b['results']):
        for field in ('structure', 'gate_outcome', 'structural_scoring', 'ingestion_quality'):
            if field == 'structural_scoring':
                left[field]['corpus_stamp'].pop('computed_at')
                right[field]['corpus_stamp'].pop('computed_at')
            assert left[field] == right[field]


def test_assurance_separates_available_capabilities_from_design():
    body = client.get('/assurance').json()
    by_name = {c['name']: c for c in body['capabilities']}
    assert by_name['Procurement analysis']['state'] == 'API available'
    assert by_name['Cross-category Registry and Need Ledger']['state'] == 'Design'
    assert by_name['Payment control and enforcement']['endpoint'] is None
    assert body['reference_evaluation']['state'] == 'Not executed by this endpoint'


def test_offline_verifier_checks_exported_request_and_rejects_tampering(tmp_path):
    request = {'contract': record()}
    packet = {'request': request, 'response': client.post('/analyze', json=request).json()}
    target = tmp_path / 'packet.json'
    root = Path(__file__).resolve().parents[1]
    command = [sys.executable, str(root / 'scripts/verify_evidence_packet.py'), str(target),
               '--code-root', str(root / 'code')]
    target.write_text(json.dumps(packet))
    passed = subprocess.run(command, capture_output=True, text=True)
    assert passed.returncode == 0, passed.stdout + passed.stderr
    packet['request']['contract']['ocid'] = 'changed-after-analysis'
    target.write_text(json.dumps(packet))
    failed = subprocess.run(command, capture_output=True, text=True)
    assert failed.returncode == 1
    assert json.loads(failed.stdout)['checks'][0]['submitted_request_matches'] is False
