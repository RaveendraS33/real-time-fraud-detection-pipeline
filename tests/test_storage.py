from datetime import UTC, datetime
from uuid import UUID

from psycopg.types.json import Jsonb

from fraud_detection.schemas import FeatureSnapshot, FraudDecision
from fraud_detection.storage import decision_to_params


def test_decision_is_converted_to_database_parameters() -> None:
    decision = FraudDecision(
        transaction_id=UUID("0a93d3eb-5fbd-4c4e-9736-27c7be35aaf1"),
        customer_id="customer-7",
        event_time=datetime.now(UTC),
        amount=3_500,
        currency="USD",
        risk_score=80,
        rule_risk_score=80,
        fraud_probability=0.8,
        decision="decline",
        triggered_rules=["high_amount", "risky_merchant_amount"],
        features=FeatureSnapshot(
            amount=3_500,
            transaction_count_5m=1,
            is_new_device=False,
            is_new_country=False,
            is_risky_merchant=True,
        ),
        detector_version="rules-v1",
        processed_at=datetime.now(UTC),
        simulation_is_fraud=True,
    )

    params = decision_to_params(decision)

    assert params["transaction_id"] == decision.transaction_id
    assert params["decision"] == "decline"
    assert params["rule_risk_score"] == 80
    assert params["currency"] == "USD"
    assert isinstance(params["triggered_rules"], Jsonb)
    assert isinstance(params["features"], Jsonb)
