"""
SUNLIGHT Load Test Runner
==========================

Runs load tests at 100, 500, and 1000 concurrent users against a local
SUNLIGHT API server. Generates reports/load_test_results.md with
performance data and bottleneck analysis.

Usage:
    # Start the API server first:
    cd code && uvicorn api:app --host 0.0.0.0 --port 8000

    # Then run this script:
    python scripts/run_load_test.py

    # Or specify host:
    python scripts/run_load_test.py --host http://localhost:8000
"""

import argparse
import csv
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone


def run_locust(users, spawn_rate, duration, host, csv_prefix):
    """Run a single locust test and return the CSV results path."""
    cmd = [
        sys.executable, "-m", "locust",
        "-f", "scripts/load_test.py",
        "--headless",
        f"-u", str(users),
        f"-r", str(spawn_rate),
        f"--run-time", f"{duration}s",
        f"--host", host,
        f"--csv", csv_prefix,
        "--only-summary",
    ]

    env = os.environ.copy()
    env['SUNLIGHT_AUTH_ENABLED'] = 'false'

    print(f"\n{'='*60}")
    print(f"  Load Test: {users} concurrent users")
    print(f"  Spawn rate: {spawn_rate}/s, Duration: {duration}s")
    print(f"{'='*60}")

    result = subprocess.run(
        cmd, capture_output=True, text=True, env=env, timeout=duration + 60
    )

    if result.returncode != 0:
        print(f"  WARNING: locust exited with code {result.returncode}")
        if result.stderr:
            # Print last few lines of stderr for diagnostics
            lines = result.stderr.strip().split('\n')
            for line in lines[-10:]:
                print(f"  {line}")

    return csv_prefix


def parse_stats_csv(csv_path):
    """Parse locust stats CSV into structured data."""
    stats_file = f"{csv_path}_stats.csv"
    if not os.path.exists(stats_file):
        return None

    results = []
    with open(stats_file) as f:
        reader = csv.DictReader(f)
        for row in reader:
            results.append(row)
    return results


def parse_stats_history(csv_path):
    """Parse stats history for throughput over time."""
    history_file = f"{csv_path}_stats_history.csv"
    if not os.path.exists(history_file):
        return None

    with open(history_file) as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    return rows


def generate_report(test_results, host):
    """Generate the markdown report."""
    lines = [
        "# SUNLIGHT Load Test Results",
        "",
        f"**Date:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"**Target:** {host}",
        f"**Test Duration:** 60 seconds per tier",
        "",
        "---",
        "",
    ]

    bottlenecks = []
    overall_stats = {}

    for tier_name, users, stats in test_results:
        if not stats:
            lines.append(f"## {tier_name} ({users} Users)")
            lines.append("")
            lines.append("*Test failed to produce results.*")
            lines.append("")
            continue

        # Find the aggregated row
        agg = None
        endpoint_rows = []
        for row in stats:
            if row.get('Name') == 'Aggregated':
                agg = row
            elif row.get('Name', '').strip():
                endpoint_rows.append(row)

        if not agg:
            continue

        total_reqs = int(agg.get('Request Count', 0) or 0)
        total_fails = int(agg.get('Failure Count', 0) or 0)
        avg_rt = float(agg.get('Average Response Time', 0) or 0)
        median_rt = float(agg.get('Median Response Time', 0) or 0)
        p95_rt = float(agg.get('95%', 0) or 0)
        p99_rt = float(agg.get('99%', 0) or 0)
        rps = float(agg.get('Requests/s', 0) or 0)
        fail_pct = (total_fails / total_reqs * 100) if total_reqs > 0 else 0

        overall_stats[users] = {
            'rps': rps, 'avg_rt': avg_rt, 'p95_rt': p95_rt,
            'p99_rt': p99_rt, 'fail_pct': fail_pct, 'total_reqs': total_reqs,
        }

        lines.extend([
            f"## {tier_name} ({users} Users)",
            "",
            "### Summary",
            "",
            "| Metric | Value |",
            "|---|---|",
            f"| Total Requests | {total_reqs:,} |",
            f"| Failed Requests | {total_fails:,} ({fail_pct:.1f}%) |",
            f"| Requests/sec | {rps:.1f} |",
            f"| Avg Response Time | {avg_rt:.0f} ms |",
            f"| Median Response Time | {median_rt:.0f} ms |",
            f"| 95th Percentile | {p95_rt:.0f} ms |",
            f"| 99th Percentile | {p99_rt:.0f} ms |",
            "",
            "### Per-Endpoint Breakdown",
            "",
            "| Endpoint | Requests | Failures | Avg (ms) | P95 (ms) | RPS |",
            "|---|---|---|---|---|---|",
        ])

        # Sort endpoints by average response time (slowest first)
        endpoint_rows.sort(
            key=lambda r: float(r.get('Average Response Time', 0) or 0),
            reverse=True,
        )

        for row in endpoint_rows:
            name = row.get('Name', '').strip()
            reqs = int(row.get('Request Count', 0) or 0)
            fails = int(row.get('Failure Count', 0) or 0)
            avg = float(row.get('Average Response Time', 0) or 0)
            p95 = float(row.get('95%', 0) or 0)
            erps = float(row.get('Requests/s', 0) or 0)
            method = row.get('Type', 'GET')

            lines.append(
                f"| {method} {name} | {reqs:,} | {fails} | {avg:.0f} | {p95:.0f} | {erps:.1f} |"
            )

            # Identify bottlenecks (>1s avg or >5% failure rate)
            if avg > 1000:
                bottlenecks.append(
                    f"**{method} {name}** — {avg:.0f}ms avg at {users} users (CPU-intensive scoring)"
                )
            if reqs > 0 and fails / reqs > 0.05:
                bottlenecks.append(
                    f"**{method} {name}** — {fails/reqs*100:.1f}% failure rate at {users} users"
                )

        lines.extend(["", "---", ""])

    # Scalability summary
    lines.extend([
        "## Scalability Summary",
        "",
        "| Users | RPS | Avg (ms) | P95 (ms) | P99 (ms) | Fail % |",
        "|---|---|---|---|---|---|",
    ])
    for users in sorted(overall_stats.keys()):
        s = overall_stats[users]
        lines.append(
            f"| {users} | {s['rps']:.1f} | {s['avg_rt']:.0f} | "
            f"{s['p95_rt']:.0f} | {s['p99_rt']:.0f} | {s['fail_pct']:.1f}% |"
        )

    # Bottleneck analysis
    lines.extend([
        "",
        "---",
        "",
        "## Bottleneck Analysis",
        "",
    ])

    if bottlenecks:
        for b in bottlenecks:
            lines.append(f"- {b}")
    else:
        lines.append("No significant bottlenecks identified at tested load levels.")

    lines.extend([
        "",
        "### Recommendations",
        "",
        "1. **Evidence/Analyze endpoints** are CPU-bound (bootstrap iterations). "
        "Consider async worker pools or pre-computed scores for production.",
        "2. **Database connections** should use connection pooling (pgBouncer) under high load.",
        "3. **Read endpoints** (contracts, scores, triage) can be cached with Redis/memcached.",
        "4. **Rate limiting** should be enforced per-client to prevent abuse at scale.",
        "",
    ])

    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description="SUNLIGHT Load Test Runner")
    parser.add_argument('--host', default='http://localhost:8000')
    parser.add_argument('--duration', type=int, default=60, help='Seconds per tier')
    args = parser.parse_args()

    os.makedirs('reports', exist_ok=True)

    tiers = [
        ("Tier 1", 100, 10),
        ("Tier 2", 500, 50),
        ("Tier 3", 1000, 100),
    ]

    test_results = []

    for tier_name, users, spawn_rate in tiers:
        csv_prefix = f"reports/load_{users}u"
        run_locust(users, spawn_rate, args.duration, args.host, csv_prefix)
        stats = parse_stats_csv(csv_prefix)
        test_results.append((tier_name, users, stats))

        # Brief pause between tiers
        if users < 1000:
            print("  Cooling down for 5 seconds...")
            time.sleep(5)

    # Generate report
    report = generate_report(test_results, args.host)
    report_path = 'reports/load_test_results.md'
    with open(report_path, 'w') as f:
        f.write(report)

    print(f"\n{'='*60}")
    print(f"  Load test complete. Report: {report_path}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
