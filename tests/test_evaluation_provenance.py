"""Report correction tests, not evaluation runs. No database or scores computed."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code"))
from evaluation_provenance import qualify_reference_report


def numeric_leaves(value, path=()):
    result = {}
    if isinstance(value, dict):
        for key, child in value.items():
            result.update(numeric_leaves(child, path + (key,)))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            result.update(numeric_leaves(child, path + (index,)))
    elif isinstance(value, (bool, int, float)):
        result[path] = value
    return result


class EvaluationProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.report = json.loads((ROOT / "docs/evaluation_report.json").read_text())

    def test_correction_preserves_every_numeric_leaf_and_does_not_mutate_input(self):
        before = deepcopy(self.report)
        qualified = qualify_reference_report(self.report)
        self.assertEqual(self.report, before)
        self.assertEqual(numeric_leaves(qualified), numeric_leaves(before))
        self.assertEqual(qualified["case_details"], before["case_details"])
        self.assertIn("Synthesized", qualified["label_set"]["positive_definition"])
        self.assertIn("Presumed", qualified["label_set"]["negative_definition"])

    def test_qualification_is_idempotent(self):
        once = qualify_reference_report(self.report)
        self.assertEqual(qualify_reference_report(once), once)

    def test_both_json_exporters_preserve_numbers_and_include_the_qualification(self):
        from evaluation import write_evaluation_report_json
        from doj_validation import write_json_report
        secondary = json.loads((ROOT / "reports/validation_report.json").read_text())
        with tempfile.TemporaryDirectory() as folder:
            for index, (writer, report) in enumerate([(write_evaluation_report_json, self.report), (write_json_report, secondary)]):
                with self.subTest(writer=writer.__name__):
                    path = Path(folder) / (str(index) + ".json")
                    writer(report, str(path))
                    actual = json.loads(path.read_text())
                    self.assertEqual(numeric_leaves(actual), numeric_leaves(report))
                    self.assertIn("not independently verified", actual["method_qualification"]["legacy_label_fields"])

    def test_old_stored_reports_render_without_claiming_actual_fraud_or_clean_outcomes(self):
        from evaluation import write_evaluation_report_md
        from doj_validation import write_markdown_report
        secondary = json.loads((ROOT / "reports/validation_report.json").read_text())
        with tempfile.TemporaryDirectory() as folder:
            for index, (writer, report) in enumerate([(write_evaluation_report_md, self.report), (write_markdown_report, secondary)]):
                with self.subTest(writer=writer.__name__):
                    path = Path(folder) / (str(index) + ".md")
                    writer(report, str(path))
                    text = path.read_text()
                    self.assertIn("Constructed reference regression", text)
                    self.assertNotIn("Actual Fraud", text)
                    self.assertNotIn("Actual Clean", text)
                    self.assertNotIn("known-clean", text)
                    self.assertNotIn("confirmed DOJ-grade fraud", text)
                    self.assertIn("not detected losses", text)
