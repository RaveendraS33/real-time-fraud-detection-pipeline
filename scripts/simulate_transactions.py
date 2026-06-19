"""Send synthetic transactions to the local ingestion API."""

import argparse
import time

import httpx

from fraud_detection.simulator import TransactionSimulator


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-url", default="http://localhost:8000")
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--fraud-rate", type=float, default=0.08)
    parser.add_argument("--delay", type=float, default=0.1)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    simulator = TransactionSimulator(seed=args.seed)

    with httpx.Client(base_url=args.api_url, timeout=10) as client:
        for number in range(1, args.count + 1):
            transaction = simulator.generate(fraud_rate=args.fraud_rate)
            response = client.post("/transactions", json=transaction.model_dump(mode="json"))
            response.raise_for_status()
            label = (
                "fraud"
                if transaction.simulation and transaction.simulation.is_fraud
                else "normal"
            )
            print(f"{number}/{args.count}: {transaction.transaction_id} ({label})")
            time.sleep(args.delay)


if __name__ == "__main__":
    main()
