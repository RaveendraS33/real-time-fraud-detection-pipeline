"""Measure ingestion throughput and processing latency against the live stack.

Posts a burst of synthetic transactions to the API concurrently, then waits for the
decisions to land in PostgreSQL, reporting accepted requests/second, API latency
percentiles, end-to-end throughput, and the detector's processing-latency percentiles
(read from Prometheus). Requires a running stack (`docker compose up -d`).
"""

import argparse
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
import psycopg

from fraud_detection.simulator import TransactionSimulator

API_URL = "http://localhost:8000"
DB_URL = "postgresql://fraud_app:fraud_dev_password@localhost:5432/fraud_detection"
PROM_URL = "http://localhost:9090"


def decision_count() -> int:
    with psycopg.connect(DB_URL, connect_timeout=5) as connection:
        return connection.execute("SELECT COUNT(*) FROM fraud_decisions").fetchone()[0]


def detector_quantile(quantile: float, retries: int = 4) -> float:
    expr = (
        f"histogram_quantile({quantile}, "
        "sum(rate(fraud_detector_processing_seconds_bucket[5m])) by (le))"
    )
    for _ in range(retries):
        try:
            response = httpx.get(f"{PROM_URL}/api/v1/query", params={"query": expr}, timeout=5)
            result = response.json()["data"]["result"]
            if result:
                value = float(result[0]["value"][1])
                if value == value:  # reject NaN (rate window not yet populated)
                    return value
        except (httpx.HTTPError, KeyError, ValueError):
            pass
        time.sleep(5)
    return float("nan")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=300)
    parser.add_argument("--concurrency", type=int, default=20)
    parser.add_argument("--fraud-rate", type=float, default=0.1)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    simulator = TransactionSimulator(seed=args.seed)
    payloads = [
        simulator.generate(fraud_rate=args.fraud_rate).model_dump(mode="json")
        for _ in range(args.count)
    ]

    start_count = decision_count()
    latencies: list[float] = []

    def post(payload: dict) -> float:
        started = time.perf_counter()
        response = client.post("/transactions", json=payload)
        response.raise_for_status()
        return time.perf_counter() - started

    started_at = time.perf_counter()
    with (
        httpx.Client(base_url=API_URL, timeout=15) as client,
        ThreadPoolExecutor(max_workers=args.concurrency) as pool,
    ):
        latencies = list(pool.map(post, payloads))
    ingest_elapsed = time.perf_counter() - started_at

    target = start_count + args.count
    deadline = time.perf_counter() + 120
    while time.perf_counter() < deadline and decision_count() < target:
        time.sleep(0.5)
    end_to_end_elapsed = time.perf_counter() - started_at

    latencies.sort()

    def percentile(fraction: float) -> float:
        return latencies[min(len(latencies) - 1, int(len(latencies) * fraction))]

    print(f"posted                {args.count} transactions @ concurrency {args.concurrency}")
    print(f"ingest_throughput     {args.count / ingest_elapsed:.1f} accepted/s")
    print(f"api_latency_p50_ms    {percentile(0.50) * 1000:.1f}")
    print(f"api_latency_p95_ms    {percentile(0.95) * 1000:.1f}")
    print(f"api_latency_p99_ms    {percentile(0.99) * 1000:.1f}")
    print(f"end_to_end_throughput {args.count / end_to_end_elapsed:.1f} processed/s")
    print(f"detector_p50_ms       {detector_quantile(0.50) * 1000:.1f}")
    print(f"detector_p95_ms       {detector_quantile(0.95) * 1000:.1f}")
    print(f"detector_p99_ms       {detector_quantile(0.99) * 1000:.1f}")


if __name__ == "__main__":
    main()
