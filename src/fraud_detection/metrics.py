"""Prometheus metrics shared by pipeline services."""

from prometheus_client import Counter, Histogram

API_TRANSACTIONS = Counter(
    "fraud_api_transactions_total",
    "Transactions accepted or rejected by the ingestion API",
    ("outcome",),
)

DETECTOR_TRANSACTIONS = Counter(
    "fraud_detector_transactions_total",
    "Transactions processed by fraud decision",
    ("decision",),
)
DETECTOR_FAILURES = Counter(
    "fraud_detector_failures_total",
    "Detector failures by stage",
    ("stage",),
)
DETECTOR_DURATION = Histogram(
    "fraud_detector_processing_seconds",
    "Detector processing latency per transaction",
)
MODEL_PROBABILITY = Histogram(
    "fraud_model_probability",
    "Distribution of fraud model probabilities",
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 0.7, 0.9, 0.99),
)

STORE_DECISIONS = Counter(
    "fraud_store_decisions_total",
    "Decisions persisted by outcome",
    ("decision",),
)
STORE_FAILURES = Counter(
    "fraud_store_failures_total",
    "Decision-store failures by stage",
    ("stage",),
)
