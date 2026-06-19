"""Consume fraud alerts and dispatch them to notification sinks.

This worker closes the detection->action loop: the detector publishes every
non-approve decision to the fraud.alerts topic, and this service turns those into
operator-facing alerts. The durable sink is a structured log line (always on, $0);
an optional webhook (ALERT_WEBHOOK_URL) forwards alerts to an external system such
as Slack or PagerDuty. Webhook delivery uses bounded exponential-backoff retries; if all
retries are exhausted the alert is captured in the dead-letter topic (replayable via
scripts/replay_dead_letter.py) rather than dropped, so a flaky external sink never silently
loses an alert and never blocks or re-drives the pipeline.
"""

import logging
import signal
import time
from threading import Event

import httpx
from confluent_kafka import Consumer, KafkaError, KafkaException, Producer
from prometheus_client import start_http_server
from pydantic import ValidationError

from fraud_detection.config import Settings, get_settings
from fraud_detection.metrics import ALERT_FAILURES, ALERTS_DISPATCHED, ALERTS_RECEIVED
from fraud_detection.schemas import FraudDecision

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


def format_alert(decision: FraudDecision) -> str:
    """Render a single-line, queryable alert record from a decision."""
    rules = ",".join(decision.triggered_rules)
    return (
        f"FRAUD_ALERT transaction_id={decision.transaction_id} "
        f"customer_id={decision.customer_id} decision={decision.decision.value} "
        f"risk_score={decision.risk_score} amount={decision.amount} "
        f"{decision.currency.value} rules={rules}"
    )


def deliver_webhook(
    http: httpx.Client,
    url: str,
    payload: str,
    max_retries: int,
    backoff_seconds: float,
    sleep=time.sleep,
) -> bool:
    """POST the alert with bounded exponential-backoff retries; return delivery success."""
    for attempt in range(max_retries):
        try:
            response = http.post(url, content=payload, headers={"content-type": "application/json"})
            response.raise_for_status()
            return True
        except httpx.HTTPError as exc:
            logger.warning("Alert webhook attempt %s/%s failed: %s", attempt + 1, max_retries, exc)
            if attempt + 1 < max_retries:
                sleep(backoff_seconds * (2**attempt))
    return False


class AlertWorker:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._consumer = Consumer(
            {
                "bootstrap.servers": settings.kafka_bootstrap_servers,
                "group.id": "fraud-alerter-v1",
                "auto.offset.reset": "earliest",
                "enable.auto.commit": False,
            }
        )
        self._producer = Producer(
            {
                "bootstrap.servers": settings.kafka_bootstrap_servers,
                "client.id": "fraud-alerter",
                "acks": "all",
                "enable.idempotence": True,
            }
        )
        self._webhook_url = settings.alert_webhook_url
        self._webhook_max_retries = settings.alert_webhook_max_retries
        self._webhook_backoff = settings.alert_webhook_backoff_seconds
        self._http = (
            httpx.Client(timeout=settings.alert_webhook_timeout_seconds)
            if self._webhook_url
            else None
        )
        self._stop = Event()

    def run(self) -> None:
        start_http_server(self._settings.metrics_port)
        self._consumer.subscribe([self._settings.fraud_alerts_topic])
        logger.info("Alerter consuming %s", self._settings.fraud_alerts_topic)

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
        if self._http is not None:
            self._http.close()

    def _process(self, message) -> None:
        try:
            decision = FraudDecision.model_validate_json(message.value())
        except ValidationError as exc:
            ALERT_FAILURES.labels(stage="validation").inc()
            logger.warning("Invalid alert sent to dead letter topic: %s", exc)
            self._producer.produce(
                self._settings.dead_letter_topic,
                key=message.key(),
                value=message.value(),
                headers={"error": str(exc)[:500], "source": "alerter"},
            )
            if self._producer.flush(10):
                raise RuntimeError("Failed to publish invalid alert to dead letter topic") from exc
            self._consumer.commit(message=message, asynchronous=False)
            return

        self._dispatch(decision)
        self._consumer.commit(message=message, asynchronous=False)

    def _dispatch(self, decision: FraudDecision) -> None:
        ALERTS_RECEIVED.labels(decision=decision.decision.value).inc()
        logger.warning(format_alert(decision))
        ALERTS_DISPATCHED.labels(sink="log").inc()

        if self._http is None:
            return

        payload = decision.model_dump_json()
        if deliver_webhook(
            self._http,
            self._webhook_url,
            payload,
            self._webhook_max_retries,
            self._webhook_backoff,
        ):
            ALERTS_DISPATCHED.labels(sink="webhook").inc()
            return

        # Retries exhausted: capture the undelivered alert in the dead-letter topic
        # instead of dropping it, so it can be replayed (scripts/replay_dead_letter.py).
        ALERT_FAILURES.labels(stage="webhook").inc()
        logger.error("Alert webhook delivery exhausted; capturing alert in dead-letter topic")
        self._producer.produce(
            self._settings.dead_letter_topic,
            key=decision.kafka_key().encode(),
            value=payload.encode(),
            headers={"error": "alert webhook delivery exhausted", "source": "alerter-webhook"},
        )
        self._producer.flush(10)
        ALERTS_DISPATCHED.labels(sink="dead_letter").inc()


def main() -> None:
    worker = AlertWorker(get_settings())
    signal.signal(signal.SIGTERM, worker.stop)
    signal.signal(signal.SIGINT, worker.stop)
    worker.run()


if __name__ == "__main__":
    main()
