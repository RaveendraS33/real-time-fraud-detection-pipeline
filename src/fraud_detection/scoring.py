"""Combine streaming features with the active detector version."""

from datetime import UTC, datetime

from fraud_detection.config import Settings
from fraud_detection.features import StreamingFeatureStore
from fraud_detection.rules import FraudRuleEngine
from fraud_detection.schemas import FraudDecision, TransactionEvent


class FraudScorer:
    detector_version = "rules-v1"

    def __init__(self, settings: Settings) -> None:
        self._features = StreamingFeatureStore(settings.velocity_window_seconds)
        self._rules = FraudRuleEngine(settings)

    def score(self, transaction: TransactionEvent) -> FraudDecision:
        features = self._features.observe(transaction)
        result = self._rules.evaluate(features)
        simulation_label = (
            transaction.simulation.is_fraud if transaction.simulation is not None else None
        )

        return FraudDecision(
            transaction_id=transaction.transaction_id,
            customer_id=transaction.customer_id,
            event_time=transaction.event_time,
            amount=transaction.amount,
            currency=transaction.currency,
            risk_score=result.risk_score,
            fraud_probability=result.risk_score / 100,
            decision=result.decision,
            triggered_rules=result.triggered_rules,
            features=features,
            detector_version=self.detector_version,
            processed_at=datetime.now(UTC),
            simulation_is_fraud=simulation_label,
        )

