from datetime import timedelta

from fraud_detection.config import Settings
from fraud_detection.schemas import DecisionOutcome, TransactionEvent
from fraud_detection.scoring import FraudScorer


def transaction(valid_transaction_data: dict, **overrides) -> TransactionEvent:
    return TransactionEvent(**(valid_transaction_data | overrides))


def test_normal_transaction_is_approved(valid_transaction_data: dict) -> None:
    decision = FraudScorer(Settings(_env_file=None)).score(
        transaction(valid_transaction_data)
    )

    assert decision.decision is DecisionOutcome.APPROVE
    assert decision.risk_score == 0
    assert decision.triggered_rules == []
    assert decision.detector_version == "hybrid-rules-v1+logreg-v1"
    assert 0 <= decision.fraud_probability <= 1


def test_high_amount_risky_merchant_is_declined(valid_transaction_data: dict) -> None:
    decision = FraudScorer(Settings(_env_file=None)).score(
        transaction(
            valid_transaction_data,
            amount=5_000,
            merchant_category="electronics",
        )
    )

    assert decision.decision is DecisionOutcome.DECLINE
    assert decision.risk_score >= 80
    assert decision.rule_risk_score == 80
    assert decision.triggered_rules == ["high_amount", "risky_merchant_amount"]


def test_velocity_rule_uses_event_time_window(valid_transaction_data: dict) -> None:
    scorer = FraudScorer(Settings(_env_file=None, velocity_count_threshold=3))
    event_time = valid_transaction_data["event_time"]

    scorer.score(transaction(valid_transaction_data, event_time=event_time))
    scorer.score(
        transaction(
            valid_transaction_data,
            transaction_id="5e37066c-48ea-4227-b497-4773f6d97ab3",
            event_time=event_time + timedelta(seconds=30),
        )
    )
    decision = scorer.score(
        transaction(
            valid_transaction_data,
            transaction_id="5ed2e362-3990-4cb7-bcb2-717c1401a8aa",
            event_time=event_time + timedelta(seconds=60),
        )
    )

    assert decision.features.transaction_count_5m == 3
    assert "high_velocity" in decision.triggered_rules


def test_new_device_and_country_are_detected_after_baseline(
    valid_transaction_data: dict,
) -> None:
    scorer = FraudScorer(Settings(_env_file=None))
    scorer.score(transaction(valid_transaction_data))

    decision = scorer.score(
        transaction(
            valid_transaction_data,
            transaction_id="dd0e36e0-68a4-4860-a8e9-f1ac93acb4d9",
            device_id="new-device",
            country_code="GB",
            currency="GBP",
            city="London",
        )
    )

    assert decision.features.is_new_device is True
    assert decision.features.is_new_country is True
    assert decision.decision is DecisionOutcome.REVIEW
