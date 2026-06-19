import copy
import json
from pathlib import Path

from fraud_detection.model_artifact import verify


def artifact() -> dict:
    return json.loads(Path("models/fraud_logreg_v1.json").read_text(encoding="utf-8"))


def test_accepts_small_float_differences() -> None:
    committed = artifact()
    candidate = copy.deepcopy(committed)
    candidate["coefficients"][0] += 1e-7

    assert verify(committed, candidate) == []


def test_accepts_borderline_prediction_drift() -> None:
    # A sub-tolerance parameter drift across platforms can flip a borderline
    # prediction, nudging metrics and confusion counts. That must NOT fail.
    committed = artifact()
    candidate = copy.deepcopy(committed)
    candidate["training"]["metrics"]["precision_at_0_5"] += 2e-3
    candidate["training"]["metrics"]["confusion_matrix"]["false_positive"] += 1
    candidate["training"]["metrics"]["confusion_matrix"]["true_negative"] -= 1

    assert verify(committed, candidate) == []


def test_rejects_contract_change() -> None:
    committed = artifact()
    candidate = copy.deepcopy(committed)
    candidate["feature_names"] = ["simulation_is_fraud"]

    assert "feature_names differs" in verify(committed, candidate)


def test_rejects_coefficient_regression() -> None:
    committed = artifact()
    candidate = copy.deepcopy(committed)
    candidate["coefficients"][0] += 0.5

    assert any("coefficients" in error for error in verify(committed, candidate))


def test_rejects_metric_regression() -> None:
    committed = artifact()
    candidate = copy.deepcopy(committed)
    candidate["training"]["metrics"]["roc_auc"] -= 0.05

    assert any("roc_auc" in error for error in verify(committed, candidate))
