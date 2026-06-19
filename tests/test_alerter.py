from datetime import UTC, datetime
from uuid import UUID

import httpx

from fraud_detection.alerter import deliver_webhook, format_alert
from fraud_detection.schemas import FeatureSnapshot, FraudDecision


def _decision() -> FraudDecision:
    return FraudDecision(
        transaction_id=UUID("0a93d3eb-5fbd-4c4e-9736-27c7be35aaf1"),
        customer_id="customer-7",
        event_time=datetime.now(UTC),
        amount=3_500,
        currency="USD",
        risk_score=85,
        rule_risk_score=80,
        fraud_probability=0.91,
        decision="decline",
        triggered_rules=["high_amount", "risky_merchant_amount"],
        features=FeatureSnapshot(
            amount=3_500,
            transaction_count_5m=1,
            is_new_device=False,
            is_new_country=False,
            is_risky_merchant=True,
        ),
        detector_version="hybrid-rules-v1+logreg-v1",
        processed_at=datetime.now(UTC),
        simulation_is_fraud=True,
    )


def test_format_alert_includes_key_fields() -> None:
    line = format_alert(_decision())

    assert "FRAUD_ALERT" in line
    assert "transaction_id=0a93d3eb-5fbd-4c4e-9736-27c7be35aaf1" in line
    assert "customer_id=customer-7" in line
    assert "decision=decline" in line
    assert "risk_score=85" in line
    assert "high_amount,risky_merchant_amount" in line


def test_format_alert_is_single_line() -> None:
    assert "\n" not in format_alert(_decision())


class _StubResponse:
    def raise_for_status(self) -> None:
        return None


class _FlakyClient:
    def __init__(self, fail_times: int) -> None:
        self.fail_times = fail_times
        self.calls = 0

    def post(self, *args, **kwargs) -> _StubResponse:
        self.calls += 1
        if self.calls <= self.fail_times:
            raise httpx.HTTPError("boom")
        return _StubResponse()


def test_deliver_webhook_retries_then_succeeds() -> None:
    client = _FlakyClient(fail_times=2)

    delivered = deliver_webhook(
        client, "http://sink", "{}", max_retries=3, backoff_seconds=0, sleep=lambda _: None
    )

    assert delivered is True
    assert client.calls == 3


def test_deliver_webhook_returns_false_when_exhausted() -> None:
    client = _FlakyClient(fail_times=10)

    delivered = deliver_webhook(
        client, "http://sink", "{}", max_retries=3, backoff_seconds=0, sleep=lambda _: None
    )

    assert delivered is False
    assert client.calls == 3
