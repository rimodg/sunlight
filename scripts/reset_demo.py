#!/usr/bin/env python3
"""
SUNLIGHT Demo Reset Script
=============================

Resets the demo environment to a clean state:
    1. Deletes existing demo database
    2. Runs seed_demo.py to generate fresh data
    3. Verifies scoring results (RED/YELLOW flags exist)
    4. Optionally starts the API server

Usage:
    python scripts/reset_demo.py                   # Reset and verify
    python scripts/reset_demo.py --serve            # Reset, verify, start API
    python scripts/reset_demo.py --out /tmp/demo    # Custom output directory
"""

import argparse
import os
import sys
import time
import subprocess


def main():
    parser = argparse.ArgumentParser(description='Reset SUNLIGHT demo environment')
    parser.add_argument('--out', default=None, help='Output directory (default: data/)')
    parser.add_argument('--seed', type=int, default=2026, help='Random seed')
    parser.add_argument('--serve', action='store_true', help='Start API server after reset')
    parser.add_argument('--port', type=int, default=8000, help='API server port (with --serve)')
    args = parser.parse_args()

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_dir = args.out or os.path.join(repo_root, 'data')
    db_path = os.path.join(out_dir, 'demo.db')
    seed_script = os.path.join(repo_root, 'scripts', 'seed_demo.py')

    print()
    print('=' * 60)
    print('  SUNLIGHT Demo Reset')
    print('=' * 60)
    print()

    # Step 1: Remove existing demo data
    print('[1/4] Cleaning existing demo data...')
    removed = []
    for f in [db_path]:
        if os.path.exists(f):
            os.remove(f)
            removed.append(f)
    # Remove sample reports
    reports_dir = os.path.join(out_dir, 'sample_reports')
    if os.path.isdir(reports_dir):
        import shutil
        shutil.rmtree(reports_dir)
        removed.append(reports_dir)
    if removed:
        for r in removed:
            print(f'      Removed: {r}')
    else:
        print('      No existing demo data found')

    # Step 2: Run seed script
    print(f'[2/4] Seeding fresh demo data (seed={args.seed})...')
    cmd = [sys.executable, seed_script, '--seed', str(args.seed)]
    if args.out:
        cmd.extend(['--out', args.out])

    result = subprocess.run(cmd, capture_output=True, text=True, cwd=repo_root)
    if result.returncode != 0:
        print('      SEED FAILED:')
        print(result.stderr[-500:] if result.stderr else result.stdout[-500:])
        sys.exit(1)
    # Print last few lines of seed output
    lines = result.stdout.strip().split('\n')
    for line in lines[-8:]:
        print(f'      {line}')

    # Step 3: Verify
    print('[3/4] Verifying demo database...')
    import sqlite3
    if not os.path.exists(db_path):
        print(f'      FAIL: Database not found at {db_path}')
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    c.execute('SELECT COUNT(*) FROM contracts')
    n_contracts = c.fetchone()[0]

    c.execute('SELECT COUNT(*) FROM contract_scores')
    n_scores = c.fetchone()[0]

    c.execute("SELECT fraud_tier, COUNT(*) FROM contract_scores GROUP BY fraud_tier")
    tiers = dict(c.fetchall())

    c.execute('SELECT COUNT(*) FROM analysis_runs')
    n_runs = c.fetchone()[0]

    conn.close()

    checks_passed = 0
    checks_failed = 0

    # Check contract count
    if n_contracts == 100:
        print(f'      Contracts: {n_contracts} OK')
        checks_passed += 1
    else:
        print(f'      Contracts: {n_contracts} (expected 100)')
        checks_failed += 1

    # Check scores exist
    if n_scores > 0:
        print(f'      Scores: {n_scores} OK')
        checks_passed += 1
    else:
        print(f'      Scores: {n_scores} FAIL (expected > 0)')
        checks_failed += 1

    # Check RED/YELLOW flags exist
    n_red = tiers.get('RED', 0)
    n_yellow = tiers.get('YELLOW', 0)
    if n_red > 0 or n_yellow > 0:
        print(f'      Flags: RED={n_red}, YELLOW={n_yellow} OK')
        checks_passed += 1
    else:
        print(f'      Flags: RED={n_red}, YELLOW={n_yellow} FAIL (expected some flags)')
        checks_failed += 1

    # Check run exists
    if n_runs > 0:
        print(f'      Runs: {n_runs} OK')
        checks_passed += 1
    else:
        print(f'      Runs: {n_runs} FAIL')
        checks_failed += 1

    print(f'      Verification: {checks_passed} passed, {checks_failed} failed')

    if checks_failed > 0:
        print()
        print('  RESET FAILED — verification errors above')
        sys.exit(1)

    # Step 4: Summary
    print('[4/4] Demo environment ready')
    print()
    print(f'  Database: {db_path}')
    print(f'  Contracts: {n_contracts} (95 clean + 5 fraud)')
    print(f'  Tier distribution: {tiers}')
    print()

    if args.serve:
        print(f'  Starting API server on port {args.port}...')
        print(f'  Dashboard: http://localhost:{args.port}/dashboard')
        print(f'  API Docs:  http://localhost:{args.port}/docs')
        print()
        env = os.environ.copy()
        env['SUNLIGHT_DB_PATH'] = db_path
        env['SUNLIGHT_AUTH_ENABLED'] = 'false'
        subprocess.run(
            [sys.executable, '-m', 'uvicorn', 'code.api:app',
             '--host', '0.0.0.0', '--port', str(args.port), '--reload'],
            cwd=repo_root, env=env,
        )
    else:
        print('  Quick start:')
        print(f'    SUNLIGHT_DB_PATH={db_path} SUNLIGHT_AUTH_ENABLED=false \\')
        print(f'        uvicorn code.api:app --port {args.port} --reload')

    print()
    print('=' * 60)


if __name__ == '__main__':
    main()
