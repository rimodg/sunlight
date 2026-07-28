#!/usr/bin/env python3
"""Measure the false-positive rate using bulletproof_analyzer."""

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

def get_sample_contracts(limit=10):
    """Get sample high-competition contracts"""
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
    """Test if a single contract gets flagged"""
    contract_id, amount, vendor, agency, desc, start, end = contract
    
    # Find peer group
    peer_amounts = analyzer.find_peer_group(contract, all_contracts)
    
    if not peer_amounts:
        return None, "NO_PEERS"
    
    # Calculate statistics
    stats = analyzer.calculate_statistics(amount, peer_amounts)
    
    # Classify
    tier, reasoning = analyzer.classify(stats)
    
    return tier, stats

def main():
    print("Testing False Positive Rate on High-Competition Contracts")
    print("=" * 80)
    
    # Initialize analyzer
    analyzer = BulletproofAnalyzer(str(DB_PATH))
    
    # Load all contracts for peer matching
    print("\nLoading all contracts for peer matching...")
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
    
    # Get test contracts
    print("\nGetting 10 high-competition test contracts...")
    test_contracts = get_sample_contracts(limit=10)
    print(f"✓ Got {len(test_contracts)} test contracts")
    
    # Test each one
    print("\nTesting each contract:\n")
    
    flagged = 0
    red_count = 0
    yellow_count = 0
    no_peers = 0
    
    for i, contract in enumerate(test_contracts, 1):
        vendor = contract[2]
        amount = contract[1]
        
        tier, result = test_single_contract(analyzer, contract, all_contracts)
        
        if tier == "RED":
            print(f"{i}. 🔴 RED: {vendor} - ${amount:,.2f}")
            print(f"   Z-score: {result['z_score']:.2f}")
            flagged += 1
            red_count += 1
        elif tier == "YELLOW":
            print(f"{i}. 🟡 YELLOW: {vendor} - ${amount:,.2f}")
            print(f"   Z-score: {result['z_score']:.2f}")
            flagged += 1
            yellow_count += 1
        elif result == "NO_PEERS":
            print(f"{i}. ⚪ NO PEERS: {vendor} - ${amount:,.2f}")
            no_peers += 1
        else:
            print(f"{i}. 🟢 GREEN: {vendor} - ${amount:,.2f}")
    
    # Summary
    tested = len(test_contracts) - no_peers
    fpr = (flagged / tested * 100) if tested > 0 else 0
    
    print("\n" + "=" * 80)
    print("RESULTS:")
    print(f"  Tested: {tested}")
    print(f"  Flagged RED: {red_count}")
    print(f"  Flagged YELLOW: {yellow_count}")
    print(f"  Total Flagged: {flagged}")
    print(f"  False Positive Rate: {fpr:.1f}%")
    print("=" * 80)

if __name__ == "__main__":
    main()
