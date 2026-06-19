from fraud_detection.model import FEATURE_NAMES, LogisticModelArtifact
from fraud_detection.schemas import FeatureSnapshot


def test_model_contract_does_not_include_simulation_labels() -> None:
    assert "simulation" not in FEATURE_NAMES
    assert "is_fraud" not in FEATURE_NAMES
    assert "scenario" not in FEATURE_NAMES


def test_exported_model_scores_suspicious_features_higher() -> None:
    model = LogisticModelArtifact.load("models/fraud_logreg_v1.json")
    ordinary = FeatureSnapshot(
        amount=45,
        transaction_count_5m=1,
        is_new_device=False,
        is_new_country=False,
        is_risky_merchant=False,
    )
    suspicious = FeatureSnapshot(
        amount=3_500,
        transaction_count_5m=6,
        is_new_device=True,
        is_new_country=True,
        is_risky_merchant=True,
    )

    ordinary_probability = model.predict_probability(ordinary)
    suspicious_probability = model.predict_probability(suspicious)

    assert 0 <= ordinary_probability <= 1
    assert 0 <= suspicious_probability <= 1
    assert suspicious_probability > ordinary_probability
    assert model.model_version == "logreg-v1"

