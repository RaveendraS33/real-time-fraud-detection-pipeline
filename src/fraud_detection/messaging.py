"""Kafka publishing adapter for transaction events."""

import logging
from typing import Protocol

from confluent_kafka import KafkaException, Producer

from fraud_detection.config import Settings
from fraud_detection.schemas import TransactionEvent

logger = logging.getLogger(__name__)


class TransactionPublisher(Protocol):
    def publish(self, transaction: TransactionEvent) -> None: ...

    def close(self) -> None: ...


class KafkaTransactionPublisher:
    """Long-lived Kafka producer shared for the lifetime of the API process."""

    def __init__(self, settings: Settings) -> None:
        self._topic = settings.transactions_topic
        self._producer = Producer(
            {
                "bootstrap.servers": settings.kafka_bootstrap_servers,
                "client.id": "transaction-api",
                "acks": "all",
                "enable.idempotence": True,
                "compression.type": "snappy",
                "delivery.timeout.ms": 10_000,
            }
        )

    def publish(self, transaction: TransactionEvent) -> None:
        try:
            self._producer.produce(
                topic=self._topic,
                key=transaction.kafka_key().encode(),
                value=transaction.model_dump_json().encode(),
                on_delivery=self._on_delivery,
            )
            self._producer.poll(0)
        except (BufferError, KafkaException) as exc:
            raise RuntimeError("Kafka did not accept the transaction") from exc

    def close(self) -> None:
        remaining = self._producer.flush(timeout=10)
        if remaining:
            logger.error("Kafka producer closed with %s undelivered messages", remaining)

    @staticmethod
    def _on_delivery(error, message) -> None:
        if error:
            logger.error("Kafka delivery failed: %s", error)
        else:
            logger.info(
                "transaction_delivered topic=%s partition=%s offset=%s",
                message.topic(),
                message.partition(),
                message.offset(),
            )
