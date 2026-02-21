#!/usr/bin/env python3
"""
SUNLIGHT Demo Reliability Test
================================

Runs 10 consecutive demo walkthroughs against the API and measures
latency (p95/p99) and error rate.

Acceptance criteria:
    - 10/10 walkthroughs pass
    - p95 latency < 2s
    - 0% errors

Each walkthrough exercises the full demo path:
    1. GET /health
    2. GET /contracts (list)
    3. GET /contracts/{id} (single)
    4. GET /scores (list)
    5. GET /reports/triage (triage queue)
    6. GET /reports/detection/{id}?format=json
    7. GET /reports/detection/{id}?format=markdown
    8. GET /runs (runs list)
    9. GET /methodology
   10. GET /api/v2/risk-inbox
   11. GET /api/v2/portfolio
   12. GET /api/v2/onboarding/status
   13. GET /api/v2/metrics

Usage:
    # Start the API first:
    SUNLIGHT_AUTH_ENABLED=false SUNLIGHT_DB_PATH=data/demo.db uvicorn code.api:app --port 8000

    # Then run this test:
    python scripts/demo_reliability_test.py
    python scripts/demo_reliability_test.py --host http://localhost:8000 --runs 10
"""

import argparse
import json
import os
import sys
import time
import statistics
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError


def http_get(url, timeout=30):
    """Make a GET request, return (status_code, latency_ms, body_or_error)."""
    t0 = time.monotonic()
    try:
        req = Request(url)
        resp = urlopen(req, timeout=timeout)
        body = resp.read().decode('utf-8')
        latency_ms = (time.monotonic() - t0) * 1000
        return resp.status, latency_ms, body
    except HTTPError as e:
        latency_ms = (time.monotonic() - t0) * 1000
        return e.code, latency_ms, str(e)
    except (URLError, OSError) as e:
        latency_ms = (time.monotonic() - t0) * 1000
        return 0, latency_ms, str(e)


def discover_contract_id(host):
    """Find a scored contract ID to use in subsequent requests."""
    status, _, body = http_get(f"{host}/contracts?limit=5")
    if status != 200:
        return None
    data = json.loads(body)
    items = data.get('items', [])
    if not items:
        return None

    # Try to find one that has scores
    for item in items:
        cid = item['contract_id']
        s, _, b = http_get(f"{host}/scores/{cid}")
        if s == 200:
            return cid
    return items[0]['contract_id']


def run_walkthrough(host, contract_id, walkthrough_num):
    """Execute one full demo walkthrough. Returns (passed, results)."""
    results = []

    endpoints = [
        ("GET /health", f"{host}/health"),
        ("GET /contracts", f"{host}/contracts?limit=10"),
        ("GET /contracts/{{id}}", f"{host}/contracts/{contract_id}"),
        ("GET /scores", f"{host}/scores?limit=10"),
        ("GET /reports/triage", f"{host}/reports/triage?limit=10"),
        ("GET /reports/detection (json)", f"{host}/reports/detection/{contract_id}?format=json"),
        ("GET /reports/detection (md)", f"{host}/reports/detection/{contract_id}?format=markdown"),
        ("GET /runs", f"{host}/runs"),
        ("GET /methodology", f"{host}/methodology"),
        ("GET /api/v2/risk-inbox", f"{host}/api/v2/risk-inbox?limit=10"),
        ("GET /api/v2/portfolio", f"{host}/api/v2/portfolio"),
        ("GET /api/v2/onboarding/status", f"{host}/api/v2/onboarding/status"),
        ("GET /api/v2/metrics", f"{host}/api/v2/metrics"),
    ]

    all_pass = True
    for name, url in endpoints:
        status, latency_ms, body = http_get(url)
        ok = 200 <= status < 400
        if not ok:
            all_pass = False
        results.append({
            'endpoint': name,
            'status': status,
            'latency_ms': round(latency_ms, 1),
            'ok': ok,
            'error': body[:200] if not ok else None,
        })

    return all_pass, results


def compute_percentile(values, pct):
    """Compute percentile from a sorted list of values."""
    if not values:
        return 0
    sorted_vals = sorted(values)
    k = (len(sorted_vals) - 1) * (pct / 100)
    f = int(k)
    c = f + 1
    if c >= len(sorted_vals):
        return sorted_vals[f]
    d = k - f
    return sorted_vals[f] * (1 - d) + sorted_vals[c] * d


def main():
    parser = argparse.ArgumentParser(description='SUNLIGHT Demo Reliability Test')
    parser.add_argument('--host', default='http://localhost:8000',
                        help='API base URL (default: http://localhost:8000)')
    parser.add_argument('--runs', type=int, default=10,
                        help='Number of consecutive walkthroughs (default: 10)')
    args = parser.parse_args()

    host = args.host.rstrip('/')
    n_runs = args.runs

    print()
    print('=' * 70)
    print('  SUNLIGHT Demo Reliability Test')
    print('=' * 70)
    print(f'  Target:         {host}')
    print(f'  Walkthroughs:   {n_runs}')
    print()

    # Check connectivity
    print('[0] Checking API connectivity...')
    status, latency, body = http_get(f"{host}/health")
    if status == 0:
        print(f'    FAIL: Cannot connect to {host}')
        print(f'    Error: {body}')
        print()
        print('    Start the API first:')
        print('    SUNLIGHT_AUTH_ENABLED=false SUNLIGHT_DB_PATH=data/demo.db \\')
        print('        uvicorn code.api:app --port 8000')
        sys.exit(1)
    print(f'    Connected ({latency:.0f}ms, status={status})')

    # Discover a contract ID for detail endpoints
    print('[0] Discovering test contract ID...')
    contract_id = discover_contract_id(host)
    if not contract_id:
        print('    WARN: No scored contracts found. Using placeholder.')
        contract_id = 'DEMO-DEF-001'
    print(f'    Using: {contract_id}')
    print()

    # Run walkthroughs
    all_latencies = []
    walkthrough_results = []
    total_requests = 0
    total_errors = 0

    for i in range(1, n_runs + 1):
        t0 = time.monotonic()
        passed, results = run_walkthrough(host, contract_id, i)
        elapsed = time.monotonic() - t0

        n_ok = sum(1 for r in results if r['ok'])
        n_err = sum(1 for r in results if not r['ok'])
        latencies = [r['latency_ms'] for r in results]
        max_lat = max(latencies)
        avg_lat = statistics.mean(latencies)

        total_requests += len(results)
        total_errors += n_err
        all_latencies.extend(latencies)

        status_str = 'PASS' if passed else 'FAIL'
        print(f'  [{i:2d}/{n_runs}] {status_str}  '
              f'{n_ok}/{len(results)} endpoints  '
              f'avg={avg_lat:.0f}ms  max={max_lat:.0f}ms  '
              f'total={elapsed:.1f}s')

        if not passed:
            for r in results:
                if not r['ok']:
                    print(f'         FAIL: {r["endpoint"]} -> {r["status"]} {r["error"]}')

        walkthrough_results.append({
            'run': i,
            'passed': passed,
            'endpoints_ok': n_ok,
            'endpoints_total': len(results),
            'errors': n_err,
            'avg_latency_ms': round(avg_lat, 1),
            'max_latency_ms': round(max_lat, 1),
            'total_time_s': round(elapsed, 2),
        })

    # Compute aggregate metrics
    p50 = compute_percentile(all_latencies, 50)
    p95 = compute_percentile(all_latencies, 95)
    p99 = compute_percentile(all_latencies, 99)
    avg = statistics.mean(all_latencies)
    error_rate = (total_errors / total_requests * 100) if total_requests > 0 else 0
    walkthroughs_passed = sum(1 for w in walkthrough_results if w['passed'])

    # Check acceptance criteria
    accept_walkthroughs = walkthroughs_passed == n_runs
    accept_p95 = p95 < 2000  # < 2s
    accept_errors = total_errors == 0
    all_accept = accept_walkthroughs and accept_p95 and accept_errors

    print()
    print('-' * 70)
    print('  Results')
    print('-' * 70)
    print(f'  Walkthroughs:   {walkthroughs_passed}/{n_runs}  '
          f'{"PASS" if accept_walkthroughs else "FAIL"}')
    print(f'  Total Requests: {total_requests}')
    print(f'  Errors:         {total_errors} ({error_rate:.1f}%)  '
          f'{"PASS" if accept_errors else "FAIL"}')
    print()
    print(f'  Latency:')
    print(f'    avg:  {avg:7.1f} ms')
    print(f'    p50:  {p50:7.1f} ms')
    print(f'    p95:  {p95:7.1f} ms  {"PASS" if accept_p95 else "FAIL"} (SLO: < 2000ms)')
    print(f'    p99:  {p99:7.1f} ms')
    print()
    print('=' * 70)
    if all_accept:
        print('  OVERALL: PASS')
    else:
        print('  OVERALL: FAIL')
        if not accept_walkthroughs:
            print(f'    - {n_runs - walkthroughs_passed} walkthrough(s) failed')
        if not accept_p95:
            print(f'    - p95 latency {p95:.0f}ms exceeds 2000ms SLO')
        if not accept_errors:
            print(f'    - {total_errors} error(s) detected')
    print('=' * 70)
    print()

    # Write JSON report
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    reports_dir = os.path.join(repo_root, 'reports')
    os.makedirs(reports_dir, exist_ok=True)
    report_path = os.path.join(reports_dir, 'demo_reliability_results.json')

    report = {
        'test': 'demo_reliability',
        'host': host,
        'n_runs': n_runs,
        'total_requests': total_requests,
        'total_errors': total_errors,
        'error_rate_pct': round(error_rate, 2),
        'walkthroughs_passed': walkthroughs_passed,
        'latency': {
            'avg_ms': round(avg, 1),
            'p50_ms': round(p50, 1),
            'p95_ms': round(p95, 1),
            'p99_ms': round(p99, 1),
        },
        'acceptance': {
            'walkthroughs': accept_walkthroughs,
            'p95_under_2s': accept_p95,
            'zero_errors': accept_errors,
            'overall': all_accept,
        },
        'walkthroughs': walkthrough_results,
    }

    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2)
    print(f'  Report written to: {report_path}')
    print()

    sys.exit(0 if all_accept else 1)


if __name__ == '__main__':
    main()
