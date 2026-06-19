"""Kafka consumer that scores transactions and publishes decisions and alerts."""

import logging
import signal
from threading import Event
from time import perf_counter

from confluent_kafka import Consumer, KafkaError, KafkaException, Producer
from prometheus_client import start_http_server
from pydantic import ValidationError

from fraud_detection.config import Settings, get_settings
from fraud_detection.metrics import (
    DETECTOR_DURATION,
    DETECTOR_FAILURES,
    DETECTOR_TRANSACTIONS,
    MODEL_PROBABILITY,
)
from fraud_detection.schemas import DecisionOutcome, FraudDecision, TransactionEvent
from fraud_detection.scoring import FraudScorer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


class DetectionWorker:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._scorer = FraudScorer(settings)
        self._consumer = Consumer(
            {
                "bootstrap.servers": settings.kafka_bootstrap_servers,
                "group.id": "fraud-detector-v1",
                "auto.offset.reset": "earliest",
                "enable.auto.commit": False,
            }
        )
        self._producer = Producer(
            {
                "bootstrap.servers": settings.kafka_bootstrap_servers,
                "client.id": "fraud-detector",
                "acks": "all",
                "enable.idempotence": True,
            }
        )
        self._stop = Event()

    def run(self) -> None:
        start_http_server(self._settings.metrics_port)
        self._consumer.subscribe([self._settings.transactions_topic])
        logger.info("Detector consuming %s", self._settings.transactions_topic)

        while not self._stop.is_set():
            message = self._consumer.poll(1.0)
            if message is None:
                continue
            if message.error():
                if message.error().code() == KafkaError._PARTITION_EOF:
                    continue
                raise KafkaException(message.error())

            self._process(message)

        self.close()

    def stop(self, *_args) -> None:
        self._stop.set()

    def close(self) -> None:
        self._producer.flush(10)
        self._consumer.close()

    def _process(self, message) -> None:
        started_at = perf_counter()
        try:
            transaction = TransactionEvent.model_validate_json(message.value())
            decision = self._scorer.score(transaction)
            self._publish_decision(decision)
            DETECTOR_TRANSACTIONS.labels(decision=decision.decision.value).inc()
            MODEL_PROBABILITY.observe(decision.fraud_probability)
        except (ValidationError, ValueError) as exc:
            DETECTOR_FAILURES.labels(stage="validation").inc()
            logger.warning("Invalid transaction sent to dead letter topic: %s", exc)
            self._producer.produce(
                self._settings.dead_letter_topic,
                key=message.key(),
                value=message.value(),
                headers={"error": str(exc)[:500]},
            )

        remaining = self._producer.flush(10)
        if remaining:
            DETECTOR_FAILURES.labels(stage="delivery").inc()
            raise RuntimeError(f"Kafka did not deliver {remaining} detector outputs")
        self._consumer.commit(message=message, asynchronous=False)
        DETECTOR_DURATION.observe(perf_counter() - started_at)

    def _publish_decision(self, decision: FraudDecision) -> None:
        payload = decision.model_dump_json().encode()
        key = decision.kafka_key().encode()
        self._producer.produce(self._settings.fraud_decisions_topic, key=key, value=payload)

        if decision.decision is not DecisionOutcome.APPROVE:
            self._producer.produce(self._settings.fraud_alerts_topic, key=key, value=payload)

        logger.info(
            "transaction_scored transaction_id=%s decision=%s risk_score=%s rules=%s",
            decision.transaction_id,
            decision.decision,
            decision.risk_score,
            decision.triggered_rules,
        )


def main() -> None:
    worker = DetectionWorker(get_settings())
    signal.signal(signal.SIGTERM, worker.stop)
    signal.signal(signal.SIGINT, worker.stop)
    worker.run()


if __name__ == "__main__":
    main()
