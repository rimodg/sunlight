"""
Tests for Tenant Jurisdiction Profile System
=============================================
Tests tenant_profile.py and tenant_profile_api.py

Run: pytest test_jurisdiction.py -v
"""

import json
import pytest
from datetime import datetime

# Add parent to path for imports
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from tenant_profile import (
    TenantProfile,
    TenantProfileStore,
    JurisdictionConfig,
    DetectionProfileConfig,
    UILocaleConfig,
    PRESET_DEFAULTS,
    InstitutionPreset,
    EvidentiaryStandard,
    detect_direction,
    list_presets,
    get_preset_description,
)


# =========================================================================
# TenantProfile Model Tests
# =========================================================================

class TestTenantProfile:

    def test_create_from_preset(self):
        profile = TenantProfile.from_preset("global_mdb_default", "T001")
        assert profile.tenant_id == "T001"
        assert profile.detection_profile.prior_fraud_rate == 0.10
        assert profile.detection_profile.evidentiary_standard == "balance_of_probabilities"
        assert profile.detection_profile.red_threshold == 0.65

    def test_create_from_doj_preset(self):
        profile = TenantProfile.from_preset("doj_criminal_strict", "T002")
        assert profile.detection_profile.prior_fraud_rate == 0.03
        assert profile.detection_profile.evidentiary_standard == "beyond_reasonable_doubt"
        assert profile.detection_profile.red_threshold == 0.72

    def test_create_from_afdb_preset(self):
        profile = TenantProfile.from_preset("afdb_integrity", "T003")
        assert profile.detection_profile.prior_fraud_rate == 0.20
        assert profile.ui_locale.language_tag == "fr-FR"
        assert profile.ui_locale.timezone == "Africa/Abidjan"

    def test_create_with_overrides(self):
        profile = TenantProfile.from_preset(
            "global_mdb_default", "T004",
            overrides={
                "jurisdiction": {"country_code": "BF", "preferred_currency": "XOF"},
                "ui_locale": {"language_tag": "fr-FR"},
            }
        )
        assert profile.jurisdiction.country_code == "BF"
        assert profile.jurisdiction.preferred_currency == "XOF"
        assert profile.ui_locale.language_tag == "fr-FR"

    def test_invalid_preset_raises(self):
        with pytest.raises(KeyError):
            TenantProfile.from_preset("nonexistent", "T005")

    def test_to_dict_roundtrip(self):
        original = TenantProfile.from_preset("sai_audit_planning", "T006")
        d = original.to_dict()
        restored = TenantProfile.from_dict(d)
        assert restored.tenant_id == "T006"
        assert restored.detection_profile.prior_fraud_rate == 0.15
        assert restored.detection_profile.evidentiary_standard == "reasonable_suspicion"

    def test_to_json(self):
        profile = TenantProfile.from_preset("eu_procurement", "T007")
        j = profile.to_json()
        data = json.loads(j)
        assert data["tenant_id"] == "T007"
        assert data["detection_profile"]["prior_fraud_rate"] == 0.08

    def test_provenance_string(self):
        profile = TenantProfile.from_preset("afdb_integrity", "T008")
        prov = profile.provenance_string()
        assert "T008" in prov
        assert "afdb_integrity" in prov
        assert "20.0%" in prov or "20%" in prov
        assert "balance_of_probabilities" in prov

    def test_timestamps_set(self):
        profile = TenantProfile.from_preset("global_mdb_default", "T009")
        assert profile.created_at != ""
        assert profile.updated_at != ""


# =========================================================================
# DetectionProfileConfig Validation
# =========================================================================

class TestDetectionProfileValidation:

    def test_valid_config(self):
        config = DetectionProfileConfig(
            prior_fraud_rate=0.10,
            red_threshold=0.65,
            yellow_threshold=0.35,
        )
        assert config.validate() == []

    def test_invalid_prior_too_high(self):
        config = DetectionProfileConfig(prior_fraud_rate=0.80)
        warnings = config.validate()
        assert any("prior_fraud_rate" in w for w in warnings)

    def test_invalid_prior_too_low(self):
        config = DetectionProfileConfig(prior_fraud_rate=0.001)
        warnings = config.validate()
        assert any("prior_fraud_rate" in w for w in warnings)

    def test_inverted_thresholds(self):
        config = DetectionProfileConfig(red_threshold=0.30, yellow_threshold=0.50)
        warnings = config.validate()
        assert any("red_threshold" in w for w in warnings)

    def test_high_fdr(self):
        config = DetectionProfileConfig(fdr_alpha=0.15)
        warnings = config.validate()
        assert any("fdr_alpha" in w for w in warnings)


# =========================================================================
# Preset Tests
# =========================================================================

class TestPresets:

    def test_all_presets_exist(self):
        expected = [
            "global_mdb_default", "doj_criminal_strict", "sai_audit_planning",
            "afdb_integrity", "world_bank_africa", "adb_asia_mdb",
            "eu_procurement", "imf_fiscal",
        ]
        for name in expected:
            assert name in PRESET_DEFAULTS, f"Missing preset: {name}"

    def test_all_presets_have_valid_detection_configs(self):
        for name, preset in PRESET_DEFAULTS.items():
            det = preset["detection"]
            warnings = det.validate()
            assert warnings == [], f"Preset {name} has warnings: {warnings}"

    def test_all_presets_have_descriptions(self):
        for name, preset in PRESET_DEFAULTS.items():
            assert len(preset["description"]) > 20, f"Preset {name} missing description"

    def test_doj_has_lowest_prior(self):
        doj = PRESET_DEFAULTS["doj_criminal_strict"]["detection"]
        for name, preset in PRESET_DEFAULTS.items():
            if name != "doj_criminal_strict":
                assert preset["detection"].prior_fraud_rate >= doj.prior_fraud_rate

    def test_sai_has_lowest_red_threshold(self):
        sai = PRESET_DEFAULTS["sai_audit_planning"]["detection"]
        for name, preset in PRESET_DEFAULTS.items():
            if name != "sai_audit_planning":
                assert sai.red_threshold <= preset["detection"].red_threshold

    def test_list_presets(self):
        presets = list_presets()
        assert len(presets) == len(PRESET_DEFAULTS)
        assert all("preset_id" in p for p in presets)
        assert all("prior_fraud_rate" in p for p in presets)

    def test_get_preset_description(self):
        desc = get_preset_description("afdb_integrity")
        assert "African Development Bank" in desc


# =========================================================================
# Direction Detection
# =========================================================================

class TestDirectionDetection:

    def test_english_ltr(self):
        assert detect_direction("en-US") == "ltr"
        assert detect_direction("en") == "ltr"

    def test_french_ltr(self):
        assert detect_direction("fr-FR") == "ltr"

    def test_arabic_rtl(self):
        assert detect_direction("ar-SA") == "rtl"
        assert detect_direction("ar") == "rtl"

    def test_hebrew_rtl(self):
        assert detect_direction("he") == "rtl"

    def test_farsi_rtl(self):
        assert detect_direction("fa-IR") == "rtl"

    def test_spanish_ltr(self):
        assert detect_direction("es-MX") == "ltr"

    def test_arabic_override_in_profile(self):
        profile = TenantProfile.from_preset(
            "global_mdb_default", "T010",
            overrides={"ui_locale": {"language_tag": "ar-SA"}}
        )
        assert profile.ui_locale.direction == "rtl"


# =========================================================================
# TenantProfileStore Tests
# =========================================================================

class TestProfileStore:

    def test_save_and_load(self):
        store = TenantProfileStore()
        profile = TenantProfile.from_preset("global_mdb_default", "T020")
        store.save(profile)

        loaded = store.load("T020")
        assert loaded is not None
        assert loaded.tenant_id == "T020"
        assert loaded.detection_profile.prior_fraud_rate == 0.10

    def test_load_nonexistent(self):
        store = TenantProfileStore()
        assert store.load("NOEXIST") is None

    def test_delete(self):
        store = TenantProfileStore()
        profile = TenantProfile.from_preset("doj_criminal_strict", "T021")
        store.save(profile)
        assert store.delete("T021") is True
        assert store.load("T021") is None

    def test_delete_nonexistent(self):
        store = TenantProfileStore()
        assert store.delete("NOEXIST") is False

    def test_list_tenants(self):
        store = TenantProfileStore()
        store.save(TenantProfile.from_preset("global_mdb_default", "T030"))
        store.save(TenantProfile.from_preset("afdb_integrity", "T031"))
        tenants = store.list_tenants()
        assert "T030" in tenants
        assert "T031" in tenants

    def test_save_updates_timestamp(self):
        store = TenantProfileStore()
        profile = TenantProfile.from_preset("global_mdb_default", "T032")
        original_updated = profile.updated_at

        import time
        time.sleep(0.01)
        store.save(profile)
        loaded = store.load("T032")
        assert loaded.updated_at >= original_updated


# =========================================================================
# Integration: Profile → CalibrationProfile Bridge
# =========================================================================

class TestCalibrationBridge:
    """Test conversion from TenantProfile to CalibrationProfile for engine injection."""

    def test_to_calibration_profile_imports(self):
        """Verify the bridge works when calibration_config is available."""
        # This test requires calibration_config.py in the path
        try:
            profile = TenantProfile.from_preset("afdb_integrity", "T040")
            cal = profile.to_calibration_profile()
            assert cal.base_rate == 0.20
            assert cal.evidentiary_standard == "balance_of_probabilities"
            assert cal.red_posterior_threshold == 0.60
        except ImportError:
            pytest.skip("calibration_config.py not in path")


# =========================================================================
# Translation File Validation
# =========================================================================

class TestTranslationFiles:
    """Validate translation file structure and critical keys."""

    @pytest.fixture
    def translations(self):
        """Load all translation files."""
        locales_dir = os.path.join(os.path.dirname(__file__), "..", "sunlight-dashboard", "src", "i18n", "locales")
        if not os.path.exists(locales_dir):
            locales_dir = os.path.join(os.path.dirname(__file__), "frontend", "i18n", "locales")

        translations = {}
        for fname in os.listdir(locales_dir):
            if fname.endswith(".json"):
                lang = fname.replace(".json", "")
                with open(os.path.join(locales_dir, fname)) as f:
                    translations[lang] = json.load(f)
        return translations

    def test_all_languages_present(self, translations):
        assert "en" in translations
        assert "fr" in translations
        assert "ar" in translations
        assert "es" in translations

    def test_critical_legal_key_present(self, translations):
        """risk_indicator must exist in every language."""
        for lang, data in translations.items():
            assert "legal" in data, f"{lang}: missing 'legal' namespace"
            assert "risk_indicator" in data["legal"], f"{lang}: missing risk_indicator"
            assert len(data["legal"]["risk_indicator"]) > 10, f"{lang}: risk_indicator too short"

    def test_legal_full_disclaimer_present(self, translations):
        for lang, data in translations.items():
            assert "risk_indicator_full" in data["legal"], f"{lang}: missing risk_indicator_full"

    def test_all_languages_have_same_top_keys(self, translations):
        en_keys = set(translations["en"].keys())
        for lang, data in translations.items():
            lang_keys = set(data.keys())
            missing = en_keys - lang_keys
            assert not missing, f"{lang}: missing top-level keys: {missing}"

    def test_typology_keys_match(self, translations):
        en_typologies = set(translations["en"]["typology"].keys())
        for lang, data in translations.items():
            lang_typologies = set(data["typology"].keys())
            missing = en_typologies - lang_typologies
            assert not missing, f"{lang}: missing typology keys: {missing}"

    def test_tier_keys_match(self, translations):
        en_tiers = set(translations["en"]["tier"].keys())
        for lang, data in translations.items():
            lang_tiers = set(data["tier"].keys())
            missing = en_tiers - lang_tiers
            assert not missing, f"{lang}: missing tier keys: {missing}"

    def test_evidence_standard_keys_match(self, translations):
        en_standards = set(translations["en"]["evidence_standard"].keys())
        for lang, data in translations.items():
            lang_standards = set(data["evidence_standard"].keys())
            missing = en_standards - lang_standards
            assert not missing, f"{lang}: missing evidence_standard keys: {missing}"
