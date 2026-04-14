#!/usr/bin/env python3
"""
SUNLIGHT Data Quality Monitor
Runs automated checks on USASpending.gov data integrity.
Alerts before analysis if data quality has degraded.

Usage:
    python data_quality_monitor.py --db sunlight.db --baseline baseline_metrics.json
    python data_quality_monitor.py --db sunlight.db --create-baseline  # First run only
"""

import sqlite3
import json
import argparse
from datetime import datetime
from pathlib import Path
import sys

# === CONFIGURATION ===
THRESHOLDS = {
    "row_count_drop_pct": 5.0,
    "null_rate_increase_pct": 2.0,
    "mean_shift_pct": 10.0,
    "new_agency_count": 5,
    "missing_agency_count": 3,
}

CRITICAL_FIELDS = [
    "contract_id",
    "award_amount", 
    "vendor_name",
    "agency_name",
    "start_date",
    "award_type",
]


def connect_db(db_path):
    if not Path(db_path).exists():
        print(f"ERROR: Database not found: {db_path}")
        sys.exit(1)
    return sqlite3.connect(db_path)


def compute_metrics(conn, table="contracts_clean"):
    from sql_allowlist import validate_table, validate_column
    tbl = validate_table(table)
    cursor = conn.cursor()
    metrics = {
        "timestamp": datetime.now().isoformat(),
        "table": tbl,
    }
    cursor.execute(f"SELECT COUNT(*) FROM {tbl}")
    metrics["row_count"] = cursor.fetchone()[0]
    metrics["null_rates"] = {}
    for field in CRITICAL_FIELDS:
        col = validate_column(field)
        try:
            cursor.execute(f"""
                SELECT COUNT(*) as total,
                    SUM(CASE WHEN {col} IS NULL OR {col} = '' THEN 1 ELSE 0 END) as nulls
                FROM {tbl}
            """)
            total, nulls = cursor.fetchone()
            metrics["null_rates"][field] = round((nulls / total) * 100, 2) if total > 0 else 0
        except sqlite3.OperationalError:
            metrics["null_rates"][field] = "FIELD_MISSING"
    cursor.execute(f"""
        SELECT AVG(award_amount) as mean, MIN(award_amount) as min, MAX(award_amount) as max
        FROM {tbl} WHERE award_amount IS NOT NULL
    """)
    row = cursor.fetchone()
    metrics["award_amount"] = {"mean": round(row[0], 2) if row[0] else 0, "min": row[1], "max": row[2]}
    cursor.execute(f"SELECT DISTINCT agency_name FROM {tbl} WHERE agency_name IS NOT NULL")
    metrics["agencies"] = sorted([r[0] for r in cursor.fetchall()])
    metrics["agency_count"] = len(metrics["agencies"])
    cursor.execute(f"SELECT MIN(start_date), MAX(start_date) FROM {tbl} WHERE start_date IS NOT NULL")
    row = cursor.fetchone()
    metrics["date_range"] = {"min": row[0], "max": row[1]}
    cursor.execute(f"SELECT COUNT(DISTINCT vendor_name) FROM {tbl}")
    metrics["vendor_count"] = cursor.fetchone()[0]
    return metrics


def compare_metrics(current, baseline):
    alerts = []
    if baseline["row_count"] > 0:
        drop_pct = ((baseline["row_count"] - current["row_count"]) / baseline["row_count"]) * 100
        if drop_pct > THRESHOLDS["row_count_drop_pct"]:
            alerts.append({"severity": "CRITICAL", "check": "row_count", "message": f"Row count dropped {drop_pct:.1f}%"})
    for field in CRITICAL_FIELDS:
        baseline_rate = baseline["null_rates"].get(field, 0)
        current_rate = current["null_rates"].get(field, 0)
        if current_rate == "FIELD_MISSING":
            alerts.append({"severity": "CRITICAL", "check": f"null_rate_{field}", "message": f"Field '{field}' is missing"})
        elif isinstance(baseline_rate, (int, float)) and isinstance(current_rate, (int, float)):
            if current_rate - baseline_rate > THRESHOLDS["null_rate_increase_pct"]:
                alerts.append({"severity": "WARNING", "check": f"null_rate_{field}", "message": f"Null rate increased"})
    return alerts


def print_report(current, baseline, alerts):
    print("\n" + "=" * 60)
    print("SUNLIGHT DATA QUALITY REPORT")
    print(f"Generated: {current['timestamp']}")
    print("=" * 60)
    print(f"\nDatabase: {current['table']}")
    print(f"Row count: {current['row_count']:,}")
    print(f"Agencies: {current['agency_count']}")
    print(f"Vendors: {current['vendor_count']:,}")
    print(f"Date range: {current['date_range']['min']} to {current['date_range']['max']}")
    print(f"Award amount: ${current['award_amount']['min']:,} to ${current['award_amount']['max']:,} (mean: ${current['award_amount']['mean']:,.0f})")
    print("\nNull rates:")
    for field, rate in current["null_rates"].items():
        print(f"  {field}: {rate}%") if rate != "FIELD_MISSING" else print(f"  {field}: MISSING")
    if alerts:
        print("\n" + "-" * 60)
        print(f"ALERTS ({len(alerts)})")
        for alert in alerts:
            print(f"  [{alert['severity']}] {alert['message']}")
    else:
        print("\n✅ All quality checks passed")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="SUNLIGHT Data Quality Monitor")
    parser.add_argument("--db", required=True, help="Path to SQLite database")
    parser.add_argument("--baseline", default="baseline_metrics.json", help="Path to baseline metrics file")
    parser.add_argument("--create-baseline", action="store_true", help="Create new baseline from current data")
    parser.add_argument("--table", default="contracts_clean", help="Table to analyze")
    args = parser.parse_args()
    conn = connect_db(args.db)
    current = compute_metrics(conn, args.table)
    conn.close()
    if args.create_baseline:
        with open(args.baseline, "w") as f:
            json.dump(current, f, indent=2)
        print(f"Baseline created: {args.baseline}")
        return
    baseline_path = Path(args.baseline)
    if not baseline_path.exists():
        print(f"ERROR: Baseline not found. Run with --create-baseline first")
        sys.exit(1)
    with open(baseline_path) as f:
        baseline = json.load(f)
    alerts = compare_metrics(current, baseline)
    print_report(current, baseline, alerts)


if __name__ == "__main__":
    main()
