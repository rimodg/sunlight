#!/usr/bin/env python3
"""Measure the false-positive rate on 100 high-competition contracts."""

import os
import sqlite3
import sys
from pathlib import Path

# Relocated from code/ during the institution-readiness pass: pytest collected
# these as test modules (test_*.py) and errored, because their test_* functions
# take positional arguments no fixture supplies. They are analysis scripts, not
# tests. Living in code/ was also what made the bare import below work; from
# scripts/ it needs the same bootstrap every other script here uses.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'code'))

from bulletproof_analyzer import BulletproofAnalyzer

DB_PATH = Path.home() / "brain" / "SUNLIGHT" / "data" / "sunlight.db"

def get_sample_contracts(limit=100):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    query = """
    SELECT contract_id, award_amount, vendor_name, agency_name, 
           description, start_date, end_date
    FROM contracts_clean
    WHERE num_offers >= 5
      AND extent_competed = 'FULL AND OPEN COMPETITION'
      AND award_amount > 0
    ORDER BY RANDOM()
    LIMIT ?
    """
    
    cursor.execute(query, (limit,))
    contracts = cursor.fetchall()
    conn.close()
    return contracts

def test_single_contract(analyzer, contract, all_contracts):
    contract_id, amount, vendor, agency, desc, start, end = contract
    peer_amounts = analyzer.find_peer_group(contract, all_contracts)
    
    if not peer_amounts:
        return None, "NO_PEERS"
    
    stats = analyzer.calculate_statistics(amount, peer_amounts)
    tier, reasoning = analyzer.classify(stats)
    
    return tier, stats

def main():
    print("Testing False Positive Rate on 100 High-Competition Contracts")
    print("=" * 80)
    
    analyzer = BulletproofAnalyzer(str(DB_PATH))
    
    print("\nLoading all contracts...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT contract_id, award_amount, vendor_name, agency_name, 
               description, start_date, end_date
        FROM contracts_clean
    """)
    all_contracts = cursor.fetchall()
    conn.close()
    print(f"✓ Loaded {len(all_contracts):,} contracts")
    
    print("\nGetting 100 test contracts...")
    test_contracts = get_sample_contracts(limit=100)
    print(f"✓ Got {len(test_contracts)} test contracts")
    
    print("\nTesting contracts (this may take 2-3 minutes)...\n")
    
    flagged = 0
    red_count = 0
    yellow_count = 0
    no_peers = 0
    flagged_details = []
    
    for i, contract in enumerate(test_contracts, 1):
        if i % 10 == 0:
            print(f"  Progress: {i}/100...")
        
        vendor = contract[2]
        amount = contract[1]
        
        tier, result = test_single_contract(analyzer, contract, all_contracts)
        
        if tier == "RED":
            flagged += 1
            red_count += 1
            flagged_details.append((vendor, amount, result['z_score'], 'RED'))
        elif tier == "YELLOW":
            flagged += 1
            yellow_count += 1
            flagged_details.append((vendor, amount, result['z_score'], 'YELLOW'))
        elif result == "NO_PEERS":
            no_peers += 1
    
    tested = len(test_contracts) - no_peers
    fpr = (flagged / tested * 100) if tested > 0 else 0
    
    print("\n" + "=" * 80)
    print("RESULTS:")
    print(f"  Total contracts: 100")
    print(f"  Tested (with peers): {tested}")
    print(f"  No peers found: {no_peers}")
    print(f"  Flagged RED: {red_count}")
    print(f"  Flagged YELLOW: {yellow_count}")
    print(f"  Total Flagged: {flagged}")
    print(f"  False Positive Rate: {fpr:.1f}%")
    print("=" * 80)
    
    if flagged_details:
        print("\nFLAGGED CONTRACTS (High-competition, potentially false positives):")
        for vendor, amount, z_score, tier in flagged_details:
            print(f"  {tier}: {vendor} - ${amount:,.2f} (Z-score: {z_score:.2f})")
    
    print("\n" + "=" * 80)
    print("INTERPRETATION:")
    if fpr < 5:
        print("✓ EXCELLENT: FPR < 5% - Very conservative, ready for deployment")
    elif fpr < 10:
        print("✓ GOOD: FPR 5-10% - Acceptable for fraud detection")
    elif fpr < 20:
        print("⚠ MODERATE: FPR 10-20% - Consider threshold adjustment")
    else:
        print("⚠ HIGH: FPR > 20% - Threshold adjustment recommended")
    print("=" * 80)

if __name__ == "__main__":
    main()
