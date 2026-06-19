"""Offline evaluation of the committed model artifact: ranking and calibration.

Rebuilds the deterministic holdout, scores it with the COMMITTED artifact (not a
retrain), and reports ROC AUC, average precision, precision/recall at the decision
threshold, the Brier score, and a reliability (calibration) table. The numbers feed
the Calibration section of docs/MODEL_CARD.md.
"""

import argparse
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
from sklearn.calibration import calibration_curve
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    precision_score,
    recall_score,
    roc_auc_score,
)

from fraud_detection.features import StreamingFeatureStore
from fraud_detection.model import FEATURE_NAMES, feature_vector
from fraud_detection.simulator import TransactionSimulator


def build_dataset(samples: int, fraud_rate: float, seed: int) -> tuple[np.ndarray, np.ndarray]:
    simulator = TransactionSimulator(seed=seed)
    store = StreamingFeatureStore(window_seconds=300)
    start = datetime(2026, 1, 1, tzinfo=UTC)
    rows: list[list[float]] = []
    labels: list[int] = []
    for index in range(samples):
        transaction = simulator.generate(fraud_rate=fraud_rate).model_copy(
            update={"event_time": start + timedelta(seconds=index * 2)}
        )
        rows.append(feature_vector(store.observe(transaction)))
        labels.append(int(transaction.simulation.is_fraud))
    return np.asarray(rows, dtype=float), np.asarray(labels, dtype=int)


def predict_probability(artifact: dict, features: np.ndarray) -> np.ndarray:
    mean = np.asarray(artifact["scaler_mean"])
    scale = np.asarray(artifact["scaler_scale"])
    coefficients = np.asarray(artifact["coefficients"])
    standardized = (features - mean) / scale
    logits = artifact["intercept"] + standardized @ coefficients
    calibration = artifact.get("calibration")
    if calibration and calibration.get("method") == "platt":
        logits = calibration["a"] * logits + calibration["b"]
    return 1.0 / (1.0 + np.exp(-logits))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", type=Path, default=Path("models/fraud_logreg_v1.json"))
    parser.add_argument("--samples", type=int, default=20_000)
    parser.add_argument("--fraud-rate", type=float, default=0.08)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--bins", type=int, default=5)
    args = parser.parse_args()

    artifact = json.loads(args.artifact.read_text(encoding="utf-8"))
    if artifact["feature_names"] != list(FEATURE_NAMES):
        raise SystemExit("Artifact feature contract does not match the code")

    features, labels = build_dataset(args.samples, args.fraud_rate, args.seed)
    split = int(args.samples * 0.8)
    test_x, test_y = features[split:], labels[split:]
    proba = predict_probability(artifact, test_x)
    predictions = proba >= artifact["decision_threshold"]

    print(f"holdout_samples     {len(test_y)}")
    print(f"positives           {int(test_y.sum())}")
    print(f"roc_auc             {roc_auc_score(test_y, proba):.4f}")
    print(f"average_precision   {average_precision_score(test_y, proba):.4f}")
    print(f"precision_at_0_5    {precision_score(test_y, predictions):.4f}")
    print(f"recall_at_0_5       {recall_score(test_y, predictions):.4f}")
    print(f"brier_score         {brier_score_loss(test_y, proba):.4f}")

    fraction_positive, mean_predicted = calibration_curve(
        test_y, proba, n_bins=args.bins, strategy="quantile"
    )
    print("reliability (quantile bins): mean_predicted -> observed_fraud_rate")
    for predicted, observed in zip(mean_predicted, fraction_positive, strict=False):
        print(f"  {predicted:.3f} -> {observed:.3f}")


if __name__ == "__main__":
    main()
