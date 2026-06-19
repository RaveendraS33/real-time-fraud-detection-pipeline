"""Replay messages from the dead-letter topic back onto a source topic.

Reads `transactions.dead_letter` from the beginning, republishes each message to the
chosen target topic, and stops once the queue is drained (or after --max). Run with
--dry-run first. Operators use this after fixing the root cause of a poison message or
a downstream outage, so captured events are reprocessed instead of lost.
"""

import argparse

from confluent_kafka import Consumer, Producer

from fraud_detection.config import get_settings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-topic", default="transactions.raw")
    parser.add_argument("--max", type=int, default=0, help="0 replays everything currently queued")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = get_settings()
    consumer = Consumer(
        {
            "bootstrap.servers": settings.kafka_bootstrap_servers,
            "group.id": "dead-letter-replay",
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
        }
    )
    producer = Producer(
        {
            "bootstrap.servers": settings.kafka_bootstrap_servers,
            "client.id": "dead-letter-replay",
            "acks": "all",
            "enable.idempotence": True,
        }
    )
    consumer.subscribe([settings.dead_letter_topic])

    replayed = 0
    idle_polls = 0
    try:
        while True:
            message = consumer.poll(1.0)
            if message is None:
                idle_polls += 1
                if idle_polls >= 3:
                    break  # queue drained
                continue
            if message.error():
                continue
            idle_polls = 0
            print(f"replay {message.topic()}@{message.offset()} -> {args.target_topic}")
            if not args.dry_run:
                producer.produce(args.target_topic, key=message.key(), value=message.value())
                producer.poll(0)
            replayed += 1
            if args.max and replayed >= args.max:
                break
        if not args.dry_run:
            producer.flush(10)
            consumer.commit(asynchronous=False)
    finally:
        consumer.close()

    action = "would replay" if args.dry_run else "replayed"
    print(f"{action} {replayed} message(s) to {args.target_topic}")


if __name__ == "__main__":
    main()
