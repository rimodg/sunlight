"""
Integration tests — end-to-end SUNLIGHT pipeline with realistic data.

Simulates scanning procurement data from multiple countries,
verifies the pipeline correctly identifies known corruption patterns.
"""

import pytest
import json
import os
from datetime import datetime, timezone, timedelta

from batch_pipeline import BatchPipeline, JurisdictionConfig, JURISDICTION_CONFIGS
from evidence_report import (
    generate_text_report,
    generate_json_report,
    generate_markdown_report,
    generate_reports_for_tier,
)
from ocds_fetcher import load_releases_from_file


# ---------------------------------------------------------------------------
# Realistic synthetic data generators
# ---------------------------------------------------------------------------

def _uk_healthcare_release(i, corrupt=False):
    """Generate a realistic UK healthcare procurement release."""
    base = datetime(2024, 3, 1, tzinfo=timezone.utc)

    if corrupt:
        return {
            "ocid": f"ocds-b5fd17-{100000 + i}",
            "id": f"release-{i}",
            "date": (base + timedelta(days=i)).isoformat(),
            "buyer": {"id": "GB-GOR-NHS-TRUST-999", "name": "Riverside NHS Trust"},
            "tender": {
                "procurementMethod": "limited",
                "procurementMethodDetails": "Framework call-off",
                "numberOfTenderers": 1,
                "tenderPeriod": {
                    "startDate": (base + timedelta(days=i)).isoformat(),
                    "endDate": (base + timedelta(days=i + 3)).isoformat(),
                },
                "items": [
                    {"classification": {"scheme": "CPV", "id": "33100000", "description": "Medical equipment"}}
                ],
            },
            "awards": [{
                "status": "active",
                "date": (base + timedelta(days=i + 3, hours=6)).isoformat(),
                "value": {"amount": 45000 + (i * 100), "currency": "GBP"},
                "suppliers": [{"id": "GB-COH-MEDTECH-LTD", "name": "MedTech Solutions Ltd"}],
            }],
            "contracts": [{
                "value": {"amount": 65000 + (i * 100), "currency": "GBP"},
                "amendments": [
                    {"date": (base + timedelta(days=i + 30)).isoformat(), "description": "Scope extension"},
                ],
            }],
        }
    else:
        suppliers = ["HealthCorp", "MediSupply", "CareEquip", "PharmaTech", "BioInstruments"]
        return {
            "ocid": f"ocds-b5fd17-{200000 + i}",
            "id": f"release-{i}",
            "date": (base + timedelta(days=i)).isoformat(),
            "buyer": {"id": "GB-GOR-NHS-TRUST-001", "name": "Greater London NHS Foundation Trust"},
            "tender": {
                "procurementMethod": "open",
                "numberOfTenderers": 4 + (i % 5),
                "tenderPeriod": {
                    "startDate": (base + timedelta(days=i)).isoformat(),
                    "endDate": (base + timedelta(days=i + 35)).isoformat(),
                },
                "items": [
                    {"classification": {"scheme": "CPV", "id": "33100000", "description": "Medical equipment"}}
                ],
            },
            "awards": [{
                "status": "active",
                "date": (base + timedelta(days=i + 50)).isoformat(),
                "value": {"amount": 80000 + (i * 500), "currency": "GBP"},
                "suppliers": [{"id": f"GB-COH-{suppliers[i % 5].upper()}", "name": suppliers[i % 5]}],
            }],
            "contracts": [{
                "value": {"amount": 80000 + (i * 500), "currency": "GBP"},
                "amendments": [],
            }],
        }


def _colombia_infrastructure_release(i, corrupt=False):
    """Generate a realistic Colombian infrastructure procurement release."""
    base = datetime(2024, 6, 1, tzinfo=timezone.utc)

    if corrupt:
        return {
            "ocid": f"ocds-k50g02-{300000 + i}",
            "id": f"release-{i}",
            "date": (base + timedelta(days=i * 2)).isoformat(),
            "buyer": {"id": "CO-RNT-890000001", "name": "Gobernación del Departamento"},
            "tender": {
                "procurementMethod": "direct",
                "procurementMethodDetails": "Contratación directa",
                "tenderPeriod": {
                    "startDate": (base + timedelta(days=i * 2)).isoformat(),
                    "endDate": (base + timedelta(days=i * 2 + 1)).isoformat(),
                },
                "items": [
                    {"classification": {"scheme": "UNSPSC", "id": "72141000", "description": "Building construction"}}
                ],
            },
            "awards": [{
                "status": "active",
                "date": (base + timedelta(days=i * 2 + 1)).isoformat(),
                "value": {"amount": 500000000 + (i * 10000000), "currency": "COP"},
                "suppliers": [{"id": "CO-RNT-900111222", "name": "Constructora Hermanos S.A.S."}],
            }],
            "contracts": [{
                "value": {"amount": 750000000 + (i * 10000000), "currency": "COP"},
                "amendments": [
                    {"date": (base + timedelta(days=i * 2 + 60)).isoformat(), "description": "Adición presupuestal"},
                    {"date": (base + timedelta(days=i * 2 + 90)).isoformat(), "description": "Prórroga"},
                    {"date": (base + timedelta(days=i * 2 + 120)).isoformat(), "description": "Modificación alcance"},
                ],
            }],
        }
    else:
        return {
            "ocid": f"ocds-k50g02-{400000 + i}",
            "id": f"release-{i}",
            "date": (base + timedelta(days=i * 3)).isoformat(),
            "buyer": {"id": "CO-RNT-800000001", "name": "Ministerio de Transporte"},
            "tender": {
                "procurementMethod": "open",
                "procurementMethodDetails": "Licitación pública",
                "numberOfTenderers": 6 + (i % 4),
                "tenderPeriod": {
                    "startDate": (base + timedelta(days=i * 3)).isoformat(),
                    "endDate": (base + timedelta(days=i * 3 + 30)).isoformat(),
                },
            },
            "awards": [{
                "status": "active",
                "date": (base + timedelta(days=i * 3 + 45)).isoformat(),
                "value": {"amount": 2000000000 + (i * 50000000), "currency": "COP"},
                "suppliers": [{"id": f"CO-RNT-{900000000 + i}", "name": f"Ingeniería Nacional {i}"}],
            }],
            "contracts": [{
                "value": {"amount": 2000000000 + (i * 50000000), "currency": "COP"},
                "amendments": [],
            }],
        }


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------

class TestUKScan:
    """Simulate a UK Contracts Finder scan with mixed clean/corrupt data."""

    def setup_method(self):
        releases = []
        # 20 clean contracts
        for i in range(20):
            releases.append(_uk_healthcare_release(i, corrupt=False))
        # 10 corrupt contracts
        for i in range(10):
            releases.append(_uk_healthcare_release(i, corrupt=True))

        self.pipeline = BatchPipeline(JURISDICTION_CONFIGS["GB"])
        self.pipeline.analyze(releases)

    def test_correct_count(self):
        assert len(self.pipeline.scores) == 30

    def test_corrupt_contracts_flagged(self):
        red = [s for s in self.pipeline.scores if s.cri_tier == "RED"]
        # Corrupt contracts should mostly be RED
        assert len(red) >= 5  # At least half of the 10 corrupt ones

    def test_clean_contracts_not_red(self):
        clean_ocids = {f"ocds-b5fd17-{200000 + i}" for i in range(20)}
        clean_scores = [s for s in self.pipeline.scores if s.ocid in clean_ocids]
        red_clean = [s for s in clean_scores if s.cri_tier == "RED"]
        # Very few clean contracts should be RED (false positive rate)
        assert len(red_clean) <= 3

    def test_corrupt_buyer_concentrated(self):
        corrupt_ocids = {f"ocds-b5fd17-{100000 + i}" for i in range(10)}
        corrupt_scores = [s for s in self.pipeline.scores if s.ocid in corrupt_ocids]
        # Same buyer + same supplier for all 10 → should flag concentration
        concentrated = [s for s in corrupt_scores if s.buyer_concentration_flag == 1]
        assert len(concentrated) >= 8

    def test_profile_shows_risk_buyer(self):
        top_buyers = self.pipeline.profile.top_risk_buyers
        buyer_ids = [b["buyer_id"] for b in top_buyers]
        assert "GB-GOR-NHS-TRUST-999" in buyer_ids[:3]

    def test_non_competitive_rate_reasonable(self):
        # Corrupt contracts use "limited" method — procedure_type catches this
        rate = self.pipeline.profile.non_competitive_rate
        assert rate is not None
        # 10 limited out of 30 total = ~33%
        assert 0.2 < rate < 0.5


class TestColombiaScan:
    """Simulate a Colombia SECOP II scan."""

    def setup_method(self):
        releases = []
        for i in range(15):
            releases.append(_colombia_infrastructure_release(i, corrupt=False))
        for i in range(8):
            releases.append(_colombia_infrastructure_release(i, corrupt=True))

        self.pipeline = BatchPipeline(JURISDICTION_CONFIGS.get("CO", JurisdictionConfig(
            country_code="CO", country_name="Colombia", currency="COP",
            tender_period_minimum=10.0,
        )))
        self.pipeline.analyze(releases)

    def test_correct_count(self):
        assert len(self.pipeline.scores) == 23

    def test_corrupt_flagged_higher(self):
        corrupt_ocids = {f"ocds-k50g02-{300000 + i}" for i in range(8)}
        corrupt_scores = [s for s in self.pipeline.scores if s.ocid in corrupt_ocids]
        clean_scores = [s for s in self.pipeline.scores if s.ocid not in corrupt_ocids]

        avg_corrupt = sum(s.cri_score for s in corrupt_scores if s.cri_score) / max(len([s for s in corrupt_scores if s.cri_score]), 1)
        avg_clean = sum(s.cri_score for s in clean_scores if s.cri_score) / max(len([s for s in clean_scores if s.cri_score]), 1)

        assert avg_corrupt > avg_clean

    def test_amendments_caught(self):
        corrupt_ocids = {f"ocds-k50g02-{300000 + i}" for i in range(8)}
        corrupt_scores = [s for s in self.pipeline.scores if s.ocid in corrupt_ocids]
        amendment_flagged = [s for s in corrupt_scores if s.amendment_flag == 1]
        assert len(amendment_flagged) >= 6


class TestEvidenceReports:
    """Test evidence report generation."""

    def setup_method(self):
        releases = [_uk_healthcare_release(0, corrupt=True)]
        self.pipeline = BatchPipeline(JURISDICTION_CONFIGS["GB"])
        self.pipeline.analyze(releases)
        self.score = self.pipeline.scores[0]

    def test_text_report_generated(self):
        report = generate_text_report(self.score)
        assert "SUNLIGHT EVIDENCE REPORT" in report
        assert self.score.ocid in report
        assert "METHODOLOGY REFERENCES" in report

    def test_text_report_contains_evidence(self):
        report = generate_text_report(self.score)
        assert "FLAGGED" in report or "CLEAR" in report

    def test_json_report_structure(self):
        report = generate_json_report(self.score)
        assert report["report_type"] == "SUNLIGHT_EVIDENCE_REPORT"
        assert "contract" in report
        assert "risk_assessment" in report
        assert "indicators" in report
        assert len(report["indicators"]) == 6

    def test_json_report_has_methodology(self):
        report = generate_json_report(self.score)
        for ind_name, ind_data in report["indicators"].items():
            assert "methodology" in ind_data
            assert len(ind_data["methodology"]) > 20

    def test_markdown_report_generated(self):
        report = generate_markdown_report(self.score)
        assert "# SUNLIGHT Evidence Report" in report
        assert self.score.ocid in report

    def test_batch_report_generation(self):
        # Build a bigger pipeline
        releases = [_uk_healthcare_release(i, corrupt=True) for i in range(5)]
        pipe = BatchPipeline(JURISDICTION_CONFIGS["GB"])
        pipe.analyze(releases)

        reports = generate_reports_for_tier(pipe, tier="RED", format="text", max_reports=10)
        # Should generate at least some reports
        assert len(reports) >= 1
        for r in reports:
            assert "SUNLIGHT EVIDENCE REPORT" in r

    def test_recommendations_for_red(self):
        if self.score.cri_tier == "RED":
            report = generate_text_report(self.score)
            assert "RECOMMENDED ACTIONS" in report


class TestMultiCountryComparison:
    """Test comparing CRI distributions across countries."""

    def test_cross_country_profiles(self):
        """Each country should produce a valid profile."""
        countries = {}

        # UK
        uk_releases = [_uk_healthcare_release(i, corrupt=(i < 3)) for i in range(15)]
        uk_pipe = BatchPipeline(JURISDICTION_CONFIGS["GB"])
        uk_pipe.analyze(uk_releases)
        countries["GB"] = uk_pipe.profile

        # Colombia
        co_releases = [_colombia_infrastructure_release(i, corrupt=(i < 5)) for i in range(15)]
        co_pipe = BatchPipeline(JURISDICTION_CONFIGS.get("CO", JurisdictionConfig(
            country_code="CO", country_name="Colombia", currency="COP")))
        co_pipe.analyze(co_releases)
        countries["CO"] = co_pipe.profile

        # Both should have profiles
        for code, profile in countries.items():
            assert profile is not None
            assert profile.total_contracts > 0
            assert profile.country_code == code

        # Colombia (more corrupt data) should have higher mean CRI
        if countries["GB"].mean_cri and countries["CO"].mean_cri:
            assert countries["CO"].mean_cri > countries["GB"].mean_cri


class TestExportRoundtrip:
    """Test that exported data can be read back correctly."""

    def test_json_roundtrip(self, tmp_path):
        releases = [_uk_healthcare_release(i, corrupt=(i < 3)) for i in range(10)]
        pipe = BatchPipeline(JURISDICTION_CONFIGS["GB"])
        pipe.analyze(releases)

        path = str(tmp_path / "roundtrip.json")
        pipe.export_json(path)

        with open(path) as f:
            data = json.load(f)

        assert data["metadata"]["country"] == "United Kingdom"
        assert len(data["contracts"]) == 10
        assert all("cri_tier" in c for c in data["contracts"])

        # Verify tier distribution matches
        tiers = data["profile"]["tier_distribution"]
        assert tiers["RED"] + tiers["YELLOW"] + tiers["GREEN"] + tiers["GRAY"] == 10

    def test_csv_roundtrip(self, tmp_path):
        import csv as csvmod
        releases = [_uk_healthcare_release(i, corrupt=(i < 3)) for i in range(10)]
        pipe = BatchPipeline(JURISDICTION_CONFIGS["GB"])
        pipe.analyze(releases)

        path = str(tmp_path / "roundtrip.csv")
        pipe.export_csv(path)

        with open(path) as f:
            rows = list(csvmod.DictReader(f))

        assert len(rows) == 10
        # Should be sorted by CRI (descending)
        cri_values = [float(r["cri_score"]) for r in rows if r["cri_score"]]
        if len(cri_values) >= 2:
            assert cri_values[0] >= cri_values[-1]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
