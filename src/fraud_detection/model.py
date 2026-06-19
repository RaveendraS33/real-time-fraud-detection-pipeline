"""Small, dependency-free runtime for the exported logistic fraud model."""

import json
import math
from dataclasses import dataclass
from pathlib import Path

from fraud_detection.schemas import FeatureSnapshot

FEATURE_NAMES = (
    "log_amount",
    "transaction_count_5m",
    "is_new_device",
    "is_new_country",
    "is_risky_merchant",
)


def feature_vector(features: FeatureSnapshot) -> list[float]:
    """Convert online features to the exact order used during training."""

    return [
        math.log1p(features.amount),
        float(features.transaction_count_5m),
        float(features.is_new_device),
        float(features.is_new_country),
        float(features.is_risky_merchant),
    ]


@dataclass(frozen=True)
class LogisticModelArtifact:
    model_version: str
    feature_names: tuple[str, ...]
    scaler_mean: tuple[float, ...]
    scaler_scale: tuple[float, ...]
    coefficients: tuple[float, ...]
    intercept: float
    decision_threshold: float

    @classmethod
    def load(cls, path: str | Path) -> "LogisticModelArtifact":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        feature_names = tuple(payload["feature_names"])
        if feature_names != FEATURE_NAMES:
            raise ValueError(
                f"Model feature contract mismatch: expected {FEATURE_NAMES}, got {feature_names}"
            )

        artifact = cls(
            model_version=payload["model_version"],
            feature_names=feature_names,
            scaler_mean=tuple(payload["scaler_mean"]),
            scaler_scale=tuple(payload["scaler_scale"]),
            coefficients=tuple(payload["coefficients"]),
            intercept=payload["intercept"],
            decision_threshold=payload["decision_threshold"],
        )
        artifact._validate_dimensions()
        return artifact

    def predict_probability(self, features: FeatureSnapshot) -> float:
        values = feature_vector(features)
        standardized = [
            (value - mean) / scale
            for value, mean, scale in zip(
                values,
                self.scaler_mean,
                self.scaler_scale,
                strict=True,
            )
        ]
        logit = self.intercept + sum(
            coefficient * value
            for coefficient, value in zip(
                self.coefficients,
                standardized,
                strict=True,
            )
        )
        if logit >= 0:
            return 1 / (1 + math.exp(-logit))
        exp_logit = math.exp(logit)
        return exp_logit / (1 + exp_logit)

    def _validate_dimensions(self) -> None:
        expected = len(FEATURE_NAMES)
        dimensions = {
            "scaler_mean": len(self.scaler_mean),
            "scaler_scale": len(self.scaler_scale),
            "coefficients": len(self.coefficients),
        }
        invalid = {name: size for name, size in dimensions.items() if size != expected}
        if invalid:
            raise ValueError(f"Invalid model artifact dimensions: {invalid}")
        if any(scale <= 0 for scale in self.scaler_scale):
            raise ValueError("Model scaler values must be positive")

