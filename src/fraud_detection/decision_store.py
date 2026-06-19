"""Consume scored decisions and persist them idempotently in PostgreSQL."""

import logging
import signal
from threading import Event

from confluent_kafka import Consumer, KafkaError, KafkaException, Producer
from prometheus_client import start_http_server
from pydantic import ValidationError

from fraud_detection.config import Settings, get_settings
from fraud_detection.metrics import STORE_DECISIONS, STORE_FAILURES
from fraud_detection.schemas import FraudDecision
from fraud_detection.storage import DecisionRepository

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


class DecisionStoreWorker:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._repository = DecisionRepository(settings.database_url)
        self._consumer = Consumer(
            {
                "bootstrap.servers": settings.kafka_bootstrap_servers,
                "group.id": "decision-store-v1",
                "auto.offset.reset": "earliest",
                "enable.auto.commit": False,
            }
        )
        self._producer = Producer(
            {
                "bootstrap.servers": settings.kafka_bootstrap_servers,
                "client.id": "decision-store",
                "acks": "all",
                "enable.idempotence": True,
            }
        )
        self._stop = Event()

    def run(self) -> None:
        self._repository.ensure_schema()
        start_http_server(self._settings.metrics_port)
        self._consumer.subscribe([self._settings.fraud_decisions_topic])
        logger.info("Decision store consuming %s", self._settings.fraud_decisions_topic)

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
        try:
            decision = FraudDecision.model_validate_json(message.value())
            self._repository.upsert(decision)
            STORE_DECISIONS.labels(decision=decision.decision.value).inc()
            logger.info(
                "decision_stored transaction_id=%s decision=%s",
                decision.transaction_id,
                decision.decision,
            )
        except ValidationError as exc:
            STORE_FAILURES.labels(stage="validation").inc()
            logger.warning("Invalid decision sent to dead letter topic: %s", exc)
            self._producer.produce(
                self._settings.dead_letter_topic,
                key=message.key(),
                value=message.value(),
                headers={"error": str(exc)[:500], "source": "decision-store"},
            )
            if self._producer.flush(10):
                raise RuntimeError(
                    "Failed to publish invalid decision to dead letter topic"
                ) from exc

        self._consumer.commit(message=message, asynchronous=False)


def main() -> None:
    worker = DecisionStoreWorker(get_settings())
    signal.signal(signal.SIGTERM, worker.stop)
    signal.signal(signal.SIGINT, worker.stop)
    worker.run()


if __name__ == "__main__":
    main()
