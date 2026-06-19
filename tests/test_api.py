from datetime import datetime

from fastapi.testclient import TestClient

from fraud_detection.api import create_app
from fraud_detection.config import Settings
from fraud_detection.schemas import TransactionEvent


class FakePublisher:
    def __init__(self) -> None:
        self.published: list[TransactionEvent] = []
        self.closed = False

    def publish(self, transaction: TransactionEvent) -> None:
        self.published.append(transaction)

    def close(self) -> None:
        self.closed = True


def test_submit_transaction_publishes_valid_event(valid_transaction_data: dict) -> None:
    publisher = FakePublisher()
    app = create_app(
        Settings(_env_file=None),
        publisher_factory=lambda settings: publisher,
    )
    payload = valid_transaction_data
    payload["event_time"] = payload["event_time"].isoformat()

    with TestClient(app) as client:
        response = client.post("/transactions", json=payload)

    assert response.status_code == 202
    assert response.json()["status"] == "accepted"
    assert len(publisher.published) == 1
    assert publisher.closed is True


def test_sample_transaction_matches_contract() -> None:
    publisher = FakePublisher()
    app = create_app(
        Settings(_env_file=None),
        publisher_factory=lambda settings: publisher,
    )

    with TestClient(app) as client:
        response = client.get("/transactions/sample")

    assert response.status_code == 200
    assert response.json()["schema_version"] == "1.0"
    assert datetime.fromisoformat(response.json()["event_time"]).tzinfo is not None
