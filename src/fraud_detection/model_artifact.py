"""Compare two model artifacts while tolerating platform-level float differences.

Model PARAMETERS (scaler, coefficients, intercept) must match within a tight float
tolerance -- they are deterministic up to BLAS-level differences across platforms.
Derived metrics and the confusion matrix are threshold-sensitive: a sub-tolerance
parameter drift can flip a borderline prediction, so they are checked with a small
absolute tolerance rather than for exact equality. Requiring identical metrics or
confusion counts would reintroduce the cross-platform brittleness this verifier
exists to avoid (the metrics are also rounded to 4 decimals at export time).
"""

import math

CONTRACT_FIELDS = ("artifact_version", "model_version", "feature_names", "decision_threshold")
PARAM_VECTOR_FIELDS = ("scaler_mean", "scaler_scale", "coefficients")
TRAINING_CONTRACT_FIELDS = ("samples", "fraud_rate", "seed", "split", "training_data_start")
METRIC_FIELDS = ("roc_auc", "average_precision", "precision_at_0_5", "recall_at_0_5")
CONFUSION_CELLS = ("true_negative", "false_positive", "false_negative", "true_positive")

PARAM_REL_TOL = 1e-5
PARAM_ABS_TOL = 1e-7
METRIC_ABS_TOL = 5e-3
CONFUSION_COUNT_TOL = 10


def _param_close(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=PARAM_REL_TOL, abs_tol=PARAM_ABS_TOL)


def _metric_close(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=0.0, abs_tol=METRIC_ABS_TOL)


def verify(committed: dict, candidate: dict) -> list[str]:
    """Return a list of human-readable differences; empty means the artifacts agree."""
    errors: list[str] = []

    for field in CONTRACT_FIELDS:
        if committed[field] != candidate[field]:
            errors.append(f"{field} differs")

    for field in PARAM_VECTOR_FIELDS:
        left, right = committed[field], candidate[field]
        if len(left) != len(right) or not all(
            _param_close(a, b) for a, b in zip(left, right, strict=True)
        ):
            errors.append(f"{field} differs beyond tolerance")

    if not _param_close(committed["intercept"], candidate["intercept"]):
        errors.append("intercept differs beyond tolerance")

    committed_training = committed["training"]
    candidate_training = candidate["training"]
    for field in TRAINING_CONTRACT_FIELDS:
        if committed_training[field] != candidate_training[field]:
            errors.append(f"training.{field} differs")

    committed_metrics = committed_training["metrics"]
    candidate_metrics = candidate_training["metrics"]
    for field in METRIC_FIELDS:
        if not _metric_close(committed_metrics[field], candidate_metrics[field]):
            errors.append(f"training.metrics.{field} differs beyond tolerance")

    committed_confusion = committed_metrics["confusion_matrix"]
    candidate_confusion = candidate_metrics["confusion_matrix"]
    for cell in CONFUSION_CELLS:
        if abs(committed_confusion[cell] - candidate_confusion[cell]) > CONFUSION_COUNT_TOL:
            errors.append(f"training.metrics.confusion_matrix.{cell} differs beyond tolerance")

    return errors
