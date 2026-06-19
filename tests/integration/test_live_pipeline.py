import json
import os
import time
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import psycopg
import pytest
from confluent_kafka import Consumer

RUN_INTEGRATION_TESTS = os.getenv("RUN_INTEGRATION_TESTS") == "1"
API_URL = os.getenv("API_URL", "http://localhost:8000")
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://fraud_app:fraud_dev_password@localhost:5432/fraud_detection",
)
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
ALERTS_TOPIC = os.getenv("FRAUD_ALERTS_TOPIC", "fraud.alerts")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not RUN_INTEGRATION_TESTS,
        reason="set RUN_INTEGRATION_TESTS=1 to test the live stack",
    ),
]


def wait_for_api(timeout_seconds: int = 60) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            response = httpx.get(f"{API_URL}/health", timeout=2)
            if response.status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(1)
    pytest.fail("transaction API did not become healthy")


def wait_for_decision(transaction_id: str, timeout_seconds: int = 60) -> tuple:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with psycopg.connect(DATABASE_URL, connect_timeout=2) as connection:
                row = connection.execute(
                    """
                    SELECT decision, risk_score, rule_risk_score, fraud_probability,
                           detector_version
                    FROM fraud_decisions
                    WHERE transaction_id = %s
                    """,
                    (transaction_id,),
                ).fetchone()
                if row:
                    return row
        except psycopg.Error:
            pass
        time.sleep(1)
    pytest.fail(f"decision {transaction_id} did not reach PostgreSQL")


def wait_for_alert(transaction_id: str, timeout_seconds: int = 60) -> dict:
    consumer = Consumer(
        {
            "bootstrap.servers": KAFKA_BOOTSTRAP,
            "group.id": f"integration-alert-check-{uuid4()}",
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
        }
    )
    consumer.subscribe([ALERTS_TOPIC])
    deadline = time.monotonic() + timeout_seconds
    try:
        while time.monotonic() < deadline:
            message = consumer.poll(1.0)
            if message is None or message.error():
                continue
            payload = json.loads(message.value())
            if payload.get("transaction_id") == transaction_id:
                return payload
    finally:
        consumer.close()
    pytest.fail(f"alert {transaction_id} did not reach {ALERTS_TOPIC}")


def test_high_risk_transaction_reaches_hybrid_decision_store() -> None:
    wait_for_api()
    transaction_id = str(uuid4())
    payload = {
        "schema_version": "1.0",
        "transaction_id": transaction_id,
        "customer_id": f"integration-{transaction_id[:8]}",
        "card_id": "integration-card",
        "merchant_id": "integration-electronics",
        "merchant_category": "electronics",
        "amount": 5_000,
        "currency": "USD",
        "country_code": "US",
        "city": "Boston",
        "latitude": 42.3601,
        "longitude": -71.0589,
        "device_id": "integration-device",
        "ip_address": "198.51.100.20",
        "channel": "ecommerce",
        "event_time": datetime.now(UTC).isoformat(),
        "simulation": {"is_fraud": True, "scenario": "high_amount"},
    }

    response = httpx.post(f"{API_URL}/transactions", json=payload, timeout=10)

    assert response.status_code == 202
    decision, risk_score, rule_score, probability, detector_version = wait_for_decision(
        transaction_id
    )
    assert decision == "decline"
    assert risk_score >= 80
    assert rule_score == 80
    assert 0 <= probability <= 1
    assert detector_version == "hybrid-rules-v1+logreg-v1"

    alert = wait_for_alert(transaction_id)
    assert alert["decision"] == "decline"
    assert alert["transaction_id"] == transaction_id
