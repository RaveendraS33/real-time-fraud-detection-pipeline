"""Explainable fraud rules and deterministic risk aggregation."""

from dataclasses import dataclass

from fraud_detection.config import Settings
from fraud_detection.schemas import DecisionOutcome, FeatureSnapshot


@dataclass(frozen=True)
class RuleResult:
    risk_score: int
    triggered_rules: list[str]
    decision: DecisionOutcome


class FraudRuleEngine:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def evaluate(self, features: FeatureSnapshot) -> RuleResult:
        triggered: list[str] = []
        score = 0

        if features.amount >= self._settings.high_amount_threshold:
            triggered.append("high_amount")
            score += 60

        if features.transaction_count_5m >= self._settings.velocity_count_threshold:
            triggered.append("high_velocity")
            score += 35

        if features.is_new_device:
            triggered.append("new_device")
            score += 20

        if features.is_new_country:
            triggered.append("new_country")
            score += 25

        if features.is_risky_merchant and features.amount >= 500:
            triggered.append("risky_merchant_amount")
            score += 20

        score = min(score, 100)
        return RuleResult(score, triggered, self.decision_for_score(score))

    def decision_for_score(self, score: int) -> DecisionOutcome:
        if score >= self._settings.decline_score_threshold:
            return DecisionOutcome.DECLINE
        if score >= self._settings.review_score_threshold:
            return DecisionOutcome.REVIEW
        return DecisionOutcome.APPROVE
