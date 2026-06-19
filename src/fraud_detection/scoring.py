"""Combine streaming features with the active detector version."""

from datetime import UTC, datetime

from fraud_detection.config import Settings
from fraud_detection.features import StreamingFeatureStore
from fraud_detection.model import LogisticModelArtifact
from fraud_detection.rules import FraudRuleEngine
from fraud_detection.schemas import FraudDecision, TransactionEvent


class FraudScorer:
    def __init__(
        self,
        settings: Settings,
        model: LogisticModelArtifact | None = None,
    ) -> None:
        self._features = StreamingFeatureStore(settings.velocity_window_seconds)
        self._rules = FraudRuleEngine(settings)
        self._model = model or LogisticModelArtifact.load(settings.model_path)
        self.detector_version = f"hybrid-rules-v1+{self._model.model_version}"

    def score(self, transaction: TransactionEvent) -> FraudDecision:
        features = self._features.observe(transaction)
        result = self._rules.evaluate(features)
        model_probability = self._model.predict_probability(features)
        combined_score = max(result.risk_score, round(model_probability * 100))
        simulation_label = (
            transaction.simulation.is_fraud if transaction.simulation is not None else None
        )

        return FraudDecision(
            transaction_id=transaction.transaction_id,
            customer_id=transaction.customer_id,
            event_time=transaction.event_time,
            amount=transaction.amount,
            currency=transaction.currency,
            risk_score=combined_score,
            rule_risk_score=result.risk_score,
            fraud_probability=model_probability,
            decision=self._rules.decision_for_score(combined_score),
            triggered_rules=result.triggered_rules,
            features=features,
            detector_version=self.detector_version,
            processed_at=datetime.now(UTC),
            simulation_is_fraud=simulation_label,
        )
