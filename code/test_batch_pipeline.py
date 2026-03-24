"""
Tests for batch pipeline — end-to-end scoring, country profiles, export.
"""

import pytest
import json
import csv
import os
from datetime import datetime, timezone, timedelta
from batch_pipeline import BatchPipeline, JurisdictionConfig, JURISDICTION_CONFIGS


def _make_release(
    ocid="ocds-test-001",
    method="open",
    n_tenderers=3,
    tender_start="2024-01-01T00:00:00Z",
    tender_end="2024-01-30T00:00:00Z",
    award_date="2024-02-15T00:00:00Z",
    award_value=50000,
    currency="GBP",
    buyer_id="GOV-001",
    buyer_name="Ministry of Health",
    supplier_id="SUP-001",
    supplier_name="MedCorp",
    amendments=None,
    contract_value=None,
):
    release = {
        "ocid": ocid,
        "id": f"{ocid}-release",
        "date": "2024-01-15T10:00:00Z",
        "buyer": {"id": buyer_id, "name": buyer_name},
        "tender": {
            "procurementMethod": method,
            "numberOfTenderers": n_tenderers,
            "tenderPeriod": {
                "startDate": tender_start,
                "endDate": tender_end,
            } if tender_start and tender_end else {},
        },
        "awards": [{
            "status": "active",
            "date": award_date,
            "value": {"amount": award_value, "currency": currency},
            "suppliers": [{"id": supplier_id, "name": supplier_name}],
        }] if award_date else [],
        "contracts": [{
            "value": {"amount": contract_value or award_value, "currency": currency},
            "amendments": amendments or [],
        }],
    }
    return release


class TestBatchPipelineBasic:
    def test_single_clean_contract(self):
        releases = [_make_release()]
        pipe = BatchPipeline(JurisdictionConfig(country_code="GB", country_name="UK", currency="GBP"))
        pipe.analyze(releases)
        assert len(pipe.scores) == 1
        assert pipe.scores[0].cri_tier in ("GREEN", "YELLOW", "GRAY")

    def test_single_suspicious_contract(self):
        releases = [_make_release(
            method="direct",
            n_tenderers=1,
            tender_start="2024-01-01T00:00:00Z",
            tender_end="2024-01-04T00:00:00Z",
            award_date="2024-01-04T12:00:00Z",
            amendments=[{"date": "2024-02-01", "description": "increase"}],
            award_value=100000,
            contract_value=200000,
        )]
        pipe = BatchPipeline()
        pipe.analyze(releases)
        s = pipe.scores[0]
        assert s.cri_tier == "RED"
        assert s.n_indicators_flagged >= 3

    def test_multiple_contracts_scored(self):
        releases = [
            _make_release(ocid=f"ocds-test-{i:03d}", n_tenderers=i + 1)
            for i in range(10)
        ]
        pipe = BatchPipeline()
        pipe.analyze(releases)
        assert len(pipe.scores) == 10

    def test_gray_handling(self):
        """Contracts with missing data should be GRAY, not GREEN."""
        releases = [{
            "ocid": "ocds-sparse-001",
            "id": "r1",
            "tender": {},
            "awards": [],
            "contracts": [],
        }]
        pipe = BatchPipeline()
        pipe.analyze(releases)
        assert pipe.scores[0].cri_tier == "GRAY"


class TestBuyerConcentration:
    def test_concentrated_buyer_flagged(self):
        # Same buyer, same supplier, 5 contracts
        releases = [
            _make_release(
                ocid=f"ocds-conc-{i:03d}",
                buyer_id="GOV-CORRUPT",
                supplier_id="CRONY-INC",
                award_value=100000,
            ) for i in range(5)
        ]
        pipe = BatchPipeline()
        pipe.analyze(releases)
        # All should have buyer_concentration flagged
        for s in pipe.scores:
            assert s.buyer_concentration_flag == 1

    def test_diversified_buyer_clean(self):
        releases = [
            _make_release(
                ocid=f"ocds-div-{i:03d}",
                buyer_id="GOV-CLEAN",
                supplier_id=f"SUPPLIER-{i}",
                award_value=100000,
            ) for i in range(5)
        ]
        pipe = BatchPipeline()
        pipe.analyze(releases)
        for s in pipe.scores:
            assert s.buyer_concentration_flag == 0


class TestCountryProfile:
    def test_profile_computed(self):
        releases = [
            _make_release(ocid=f"ocds-p-{i:03d}", n_tenderers=i % 4 + 1)
            for i in range(20)
        ]
        pipe = BatchPipeline(JurisdictionConfig(country_code="GB", country_name="UK", currency="GBP"))
        pipe.analyze(releases)
        assert pipe.profile is not None
        assert pipe.profile.total_contracts == 20
        assert pipe.profile.red_count + pipe.profile.yellow_count + pipe.profile.green_count + pipe.profile.gray_count == 20

    def test_profile_summary_string(self):
        releases = [_make_release(ocid=f"ocds-s-{i:03d}") for i in range(5)]
        pipe = BatchPipeline(JurisdictionConfig(country_code="GB", country_name="UK"))
        pipe.analyze(releases)
        summary = pipe.profile.summary()
        assert "UK" in summary
        assert "Total contracts" in summary

    def test_top_risk_buyers(self):
        # Mix of clean and dirty buyers
        releases = []
        for i in range(5):
            releases.append(_make_release(
                ocid=f"ocds-dirty-{i}", buyer_id="DIRTY-BUYER",
                supplier_id="CRONY", method="direct", n_tenderers=1,
                tender_start="2024-01-01T00:00:00Z", tender_end="2024-01-03T00:00:00Z",
            ))
        for i in range(5):
            releases.append(_make_release(
                ocid=f"ocds-clean-{i}", buyer_id="CLEAN-BUYER",
                supplier_id=f"SUPPLIER-{i}", method="open", n_tenderers=5,
            ))
        pipe = BatchPipeline()
        pipe.analyze(releases)
        top = pipe.profile.top_risk_buyers
        assert len(top) >= 2
        # Dirty buyer should have higher avg CRI
        dirty_entry = next((b for b in top if b["buyer_id"] == "DIRTY-BUYER"), None)
        clean_entry = next((b for b in top if b["buyer_id"] == "CLEAN-BUYER"), None)
        if dirty_entry and clean_entry:
            assert dirty_entry["avg_cri"] > clean_entry["avg_cri"]


class TestExport:
    def test_csv_export(self, tmp_path):
        releases = [_make_release(ocid=f"ocds-csv-{i}") for i in range(5)]
        pipe = BatchPipeline()
        pipe.analyze(releases)
        path = str(tmp_path / "output.csv")
        pipe.export_csv(path)
        assert os.path.exists(path)
        with open(path) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) == 5
        assert "cri_tier" in rows[0]
        assert "cri_score" in rows[0]

    def test_json_export(self, tmp_path):
        releases = [_make_release(ocid=f"ocds-json-{i}") for i in range(3)]
        pipe = BatchPipeline(JurisdictionConfig(country_code="GB", country_name="UK"))
        pipe.analyze(releases)
        path = str(tmp_path / "output.json")
        pipe.export_json(path)
        with open(path) as f:
            data = json.load(f)
        assert data["metadata"]["country"] == "UK"
        assert len(data["contracts"]) == 3
        assert "profile" in data

    def test_csv_sorted_by_risk(self, tmp_path):
        releases = [
            _make_release(ocid="clean", n_tenderers=5, method="open"),
            _make_release(ocid="dirty", n_tenderers=1, method="direct",
                          tender_start="2024-01-01T00:00:00Z", tender_end="2024-01-03T00:00:00Z"),
        ]
        pipe = BatchPipeline()
        pipe.analyze(releases)
        path = str(tmp_path / "sorted.csv")
        pipe.export_csv(path)
        with open(path) as f:
            rows = list(csv.DictReader(f))
        # First row should be dirtier
        if rows[0]["cri_score"] and rows[1]["cri_score"]:
            assert float(rows[0]["cri_score"]) >= float(rows[1]["cri_score"])


class TestJurisdictionConfigs:
    def test_gb_config_exists(self):
        assert "GB" in JURISDICTION_CONFIGS
        assert JURISDICTION_CONFIGS["GB"].currency == "GBP"

    def test_config_affects_scoring(self):
        # 12-day tender period: fine with default 15-day minimum would flag,
        # but let's test with 10-day minimum (GB config)
        releases = [_make_release(
            tender_start="2024-01-01T00:00:00Z",
            tender_end="2024-01-12T00:00:00Z",
        )]
        # With strict config (15 day min) — should flag
        strict = BatchPipeline(JurisdictionConfig(tender_period_minimum=15.0))
        strict.analyze(releases)
        assert strict.scores[0].tender_period_flag == 1

        # With lenient config (10 day min) — should be clean
        lenient = BatchPipeline(JurisdictionConfig(tender_period_minimum=10.0))
        lenient.analyze(releases)
        assert lenient.scores[0].tender_period_flag == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
