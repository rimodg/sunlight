"""Qualify constructed reference reports without changing any numerical result."""
from copy import deepcopy


def qualify_reference_report(report):
    value = deepcopy(report)
    if "label_set" in value:
        value["label_set"]["positive_definition"] = "Synthesized price examples parameterized by case references; not observed prosecuted contracts"
        value["label_set"]["negative_definition"] = "Presumed negatives sampled from below-median contracts; not independently adjudicated clean outcomes"
    if "dataset_composition" in value:
        value["dataset_composition"]["split_method"] = "Constructed reference regression, not independently labeled field validation"
    value["method_qualification"] = {
        "schema": "sunlight.constructed-reference-qualification.v1",
        "population": "Synthesized positive price examples and presumed-negative comparisons",
        "accuracy": "Metrics describe this constructed population only; real-case precision and recall are unmeasured",
        "legacy_label_fields": "ground_truth and FRAUD/CLEAN are compatibility keys for constructed labels, not independently verified outcomes",
        "legacy_money_fields": "total_fraud_value and detected_fraud_value are supplied settlement-reference weights, not detected losses, harm or recovered money",
        "workload": "Analyst-time figures are configured scenario assumptions, not measured institutional efficiency",
        "computation": "This qualification changes provenance and presentation only, not scoring, thresholds, labels used in the calculation or numeric outputs",
    }
    return value
