"""Train and export the reproducible logistic fraud model."""

import argparse
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.preprocessing import StandardScaler

from fraud_detection.features import StreamingFeatureStore
from fraud_detection.model import FEATURE_NAMES, feature_vector
from fraud_detection.simulator import TransactionSimulator


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=int, default=20_000)
    parser.add_argument("--fraud-rate", type=float, default=0.08)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=Path, default=Path("models/fraud_logreg_v1.json"))
    return parser.parse_args()


def build_dataset(samples: int, fraud_rate: float, seed: int) -> tuple[np.ndarray, np.ndarray]:
    if samples < 1_000:
        raise ValueError("At least 1,000 samples are required for training")

    simulator = TransactionSimulator(seed=seed)
    feature_store = StreamingFeatureStore(window_seconds=300)
    start_time = datetime(2026, 1, 1, tzinfo=UTC)
    rows: list[list[float]] = []
    labels: list[int] = []

    for index in range(samples):
        transaction = simulator.generate(fraud_rate=fraud_rate).model_copy(
            update={"event_time": start_time + timedelta(seconds=index * 2)}
        )
        features = feature_store.observe(transaction)
        rows.append(feature_vector(features))
        labels.append(int(transaction.simulation.is_fraud))

    return np.asarray(rows, dtype=float), np.asarray(labels, dtype=int)


def _sigmoid(values: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-values))


def train_and_export(
    samples: int,
    fraud_rate: float,
    seed: int,
    output: Path,
) -> dict:
    features, labels = build_dataset(samples, fraud_rate, seed)
    train_end = int(samples * 0.7)
    calibration_end = int(samples * 0.8)
    train_x, calibration_x, test_x = (
        features[:train_end],
        features[train_end:calibration_end],
        features[calibration_end:],
    )
    train_y, calibration_y, test_y = (
        labels[:train_end],
        labels[train_end:calibration_end],
        labels[calibration_end:],
    )

    scaler = StandardScaler()
    classifier = LogisticRegression(class_weight="balanced", max_iter=1_000, random_state=seed)
    classifier.fit(scaler.fit_transform(train_x), train_y)

    # Platt scaling fit on the held-out calibration split: map the raw decision logit
    # through a calibration sigmoid so served probabilities are calibrated, not raw.
    calibration_logits = classifier.decision_function(scaler.transform(calibration_x))
    platt = LogisticRegression()
    platt.fit(calibration_logits.reshape(-1, 1), calibration_y)
    platt_a = float(platt.coef_[0][0])
    platt_b = float(platt.intercept_[0])

    test_logits = classifier.decision_function(scaler.transform(test_x))
    probabilities = _sigmoid(platt_a * test_logits + platt_b)
    predictions = probabilities >= 0.5
    true_negative, false_positive, false_negative, true_positive = confusion_matrix(
        test_y, predictions, labels=[0, 1]
    ).ravel()

    metrics = {
        "roc_auc": round(float(roc_auc_score(test_y, probabilities)), 4),
        "average_precision": round(float(average_precision_score(test_y, probabilities)), 4),
        "precision_at_0_5": round(float(precision_score(test_y, predictions)), 4),
        "recall_at_0_5": round(float(recall_score(test_y, predictions)), 4),
        "confusion_matrix": {
            "true_negative": int(true_negative),
            "false_positive": int(false_positive),
            "false_negative": int(false_negative),
            "true_positive": int(true_positive),
        },
    }
    artifact = {
        "artifact_version": 2,
        "model_version": "logreg-v1",
        "feature_names": list(FEATURE_NAMES),
        "scaler_mean": scaler.mean_.tolist(),
        "scaler_scale": scaler.scale_.tolist(),
        "coefficients": classifier.coef_[0].tolist(),
        "intercept": float(classifier.intercept_[0]),
        "decision_threshold": 0.5,
        "calibration": {"method": "platt", "a": platt_a, "b": platt_b},
        "training": {
            "samples": samples,
            "fraud_rate": fraud_rate,
            "seed": seed,
            "split": "first 70% train, next 10% calibration, final 20% test",
            "training_data_start": start_time_iso(),
            "metrics": metrics,
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes((json.dumps(artifact, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    return artifact


def start_time_iso() -> str:
    return datetime(2026, 1, 1, tzinfo=UTC).isoformat()


def main() -> None:
    args = parse_args()
    artifact = train_and_export(args.samples, args.fraud_rate, args.seed, args.output)
    print(json.dumps(artifact["training"]["metrics"], indent=2))
    print(f"Model written to {args.output}")


if __name__ == "__main__":
    main()
