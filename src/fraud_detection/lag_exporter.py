"""Export Kafka consumer-group lag as Prometheus gauges.

Consumer lag -- a partition's high-watermark offset minus the group's committed
offset -- is the real health signal for a streaming consumer: a healthy worker keeps
it near zero, while a stalled or slow worker shows it climbing. This service polls the
broker on an interval and publishes fraud_consumer_lag{group,topic,partition}, which
Prometheus scrapes and the ConsumerLag alert rule fires on.
"""

import logging
import signal
from threading import Event

from confluent_kafka import Consumer, ConsumerGroupTopicPartitions, TopicPartition
from confluent_kafka.admin import AdminClient
from prometheus_client import Gauge, start_http_server

from fraud_detection.config import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)

CONSUMER_GROUPS = ("fraud-detector-v1", "decision-store-v1", "fraud-alerter-v1")
POLL_INTERVAL_SECONDS = 15

CONSUMER_LAG = Gauge(
    "fraud_consumer_lag",
    "Kafka consumer-group lag (high watermark minus committed offset) per partition",
    ("group", "topic", "partition"),
)


def compute_lag(high_watermark: int, committed_offset: int) -> int:
    """Lag for one partition; 0 when the group has no committed offset yet."""
    if committed_offset < 0:
        return 0
    return max(high_watermark - committed_offset, 0)


def collect(admin: AdminClient, consumer: Consumer, groups: tuple[str, ...]) -> None:
    for group in groups:
        # list_consumer_group_offsets accepts only one consumer group per request.
        try:
            futures = admin.list_consumer_group_offsets([ConsumerGroupTopicPartitions(group)])
            partitions = futures[group].result().topic_partitions
        except Exception as exc:
            logger.warning("Could not read offsets for %s: %s", group, exc)
            continue
        for tp in partitions:
            try:
                _, high = consumer.get_watermark_offsets(
                    TopicPartition(tp.topic, tp.partition), timeout=5
                )
            except Exception as exc:
                logger.warning("Watermark failed for %s[%s]: %s", tp.topic, tp.partition, exc)
                continue
            lag = compute_lag(high, tp.offset)
            CONSUMER_LAG.labels(group=group, topic=tp.topic, partition=str(tp.partition)).set(lag)


def main() -> None:
    settings = get_settings()
    admin = AdminClient({"bootstrap.servers": settings.kafka_bootstrap_servers})
    consumer = Consumer(
        {
            "bootstrap.servers": settings.kafka_bootstrap_servers,
            "group.id": "lag-exporter-probe",
            "enable.auto.commit": False,
        }
    )
    start_http_server(settings.metrics_port)
    stop = Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    logger.info("Lag exporter polling %s every %ss", CONSUMER_GROUPS, POLL_INTERVAL_SECONDS)
    while not stop.is_set():
        collect(admin, consumer, CONSUMER_GROUPS)
        stop.wait(POLL_INTERVAL_SECONDS)
    consumer.close()


if __name__ == "__main__":
    main()
