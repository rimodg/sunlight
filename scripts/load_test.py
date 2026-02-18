"""
SUNLIGHT Load Test Suite
=========================

Tests every API endpoint under concurrent load using Locust.

Usage (headless, for CI/automated runs):
    locust -f scripts/load_test.py --headless \
        -u 100 -r 10 --run-time 60s \
        --host http://localhost:8000 \
        --csv reports/load_test

Usage (web UI):
    locust -f scripts/load_test.py --host http://localhost:8000

The runner script (scripts/run_load_test.py) automates 100/500/1000 user tests.
"""

import json
import random
import string
from locust import HttpUser, task, between, events


# Sample contract IDs (populated during test)
SAMPLE_CONTRACT_IDS = []
SAMPLE_RUN_IDS = []


class SunlightUser(HttpUser):
    """Simulates a typical API client with mixed read/write workload."""
    wait_time = between(0.1, 0.5)

    def on_start(self):
        """Fetch sample data on user start."""
        global SAMPLE_CONTRACT_IDS, SAMPLE_RUN_IDS

        if not SAMPLE_CONTRACT_IDS:
            resp = self.client.get("/contracts?limit=50")
            if resp.status_code == 200:
                items = resp.json().get('items', [])
                SAMPLE_CONTRACT_IDS.extend(
                    [i['contract_id'] for i in items]
                )

        if not SAMPLE_RUN_IDS:
            resp = self.client.get("/runs")
            if resp.status_code == 200:
                runs = resp.json()
                SAMPLE_RUN_IDS.extend([r['run_id'] for r in runs])

    # --- High frequency endpoints (70% of traffic) ---

    @task(20)
    def health_check(self):
        self.client.get("/health")

    @task(15)
    def list_contracts(self):
        offset = random.randint(0, 1000)
        self.client.get(f"/contracts?limit=50&offset={offset}")

    @task(10)
    def list_contracts_filtered(self):
        agencies = ["DEFENSE", "ENERGY", "STATE", "INTERIOR", "HOMELAND"]
        agency = random.choice(agencies)
        self.client.get(f"/contracts?agency={agency}&limit=20")

    @task(10)
    def get_single_contract(self):
        if SAMPLE_CONTRACT_IDS:
            cid = random.choice(SAMPLE_CONTRACT_IDS)
            self.client.get(f"/contracts/{cid}")

    @task(15)
    def list_scores(self):
        self.client.get("/scores?limit=50")

    # --- Medium frequency (20% of traffic) ---

    @task(5)
    def get_contract_scores(self):
        if SAMPLE_CONTRACT_IDS:
            cid = random.choice(SAMPLE_CONTRACT_IDS)
            self.client.get(f"/scores/{cid}")

    @task(3)
    def triage_queue(self):
        self.client.get("/reports/triage?limit=20")

    @task(3)
    def methodology(self):
        self.client.get("/methodology")

    @task(3)
    def audit_trail(self):
        self.client.get("/audit?limit=50")

    @task(2)
    def list_runs(self):
        self.client.get("/runs")

    @task(2)
    def get_run_detail(self):
        if SAMPLE_RUN_IDS:
            rid = random.choice(SAMPLE_RUN_IDS)
            self.client.get(f"/runs/{rid}")

    @task(2)
    def detection_report(self):
        if SAMPLE_CONTRACT_IDS:
            cid = random.choice(SAMPLE_CONTRACT_IDS)
            fmt = random.choice(["json", "markdown"])
            self.client.get(f"/reports/detection/{cid}?format={fmt}")

    # --- Low frequency (10% of traffic) ---

    @task(2)
    def evidence_package(self):
        if SAMPLE_CONTRACT_IDS:
            cid = random.choice(SAMPLE_CONTRACT_IDS)
            self.client.get(f"/reports/evidence/{cid}")

    @task(1)
    def analyze_single(self):
        """Score a single contract — CPU-intensive endpoint."""
        if SAMPLE_CONTRACT_IDS:
            cid = random.choice(SAMPLE_CONTRACT_IDS)
            self.client.post("/analyze", json={
                "contract_id": cid,
                "award_amount": random.uniform(100000, 50000000),
                "vendor_name": "Load Test Vendor",
                "agency_name": "DEPARTMENT OF DEFENSE",
                "description": "Load test contract",
            })

    @task(1)
    def submit_contract(self):
        """Submit a new contract — write endpoint."""
        uid = ''.join(random.choices(string.ascii_uppercase + string.digits, k=12))
        self.client.post("/contracts", json={
            "contract_id": f"LOAD_TEST_{uid}",
            "award_amount": random.uniform(10000, 1000000),
            "vendor_name": f"Load Test Vendor {uid[:4]}",
            "agency_name": "DEPARTMENT OF DEFENSE",
            "description": "Load test submission",
        })

    @task(1)
    def ingest_json(self):
        """Ingest a small JSON document."""
        uid = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        contract = json.dumps({
            "contract_id": f"INGEST_LT_{uid}",
            "award_amount": random.uniform(50000, 500000),
            "vendor_name": f"Ingest Test {uid[:4]}",
            "agency_name": "DEPARTMENT OF DEFENSE",
        }).encode()
        self.client.post(
            "/ingest",
            files={"file": ("test.json", contract, "application/json")},
        )
