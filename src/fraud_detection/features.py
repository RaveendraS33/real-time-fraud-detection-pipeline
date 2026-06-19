"""Stateful event-time feature computation for fraud decisions."""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from fraud_detection.schemas import FeatureSnapshot, TransactionEvent


@dataclass
class CustomerState:
    event_times: list[datetime] = field(default_factory=list)
    device_ids: set[str] = field(default_factory=set)
    country_codes: set[str] = field(default_factory=set)


class StreamingFeatureStore:
    """In-memory feature state keyed by customer for the local pipeline."""

    def __init__(self, window_seconds: int = 300) -> None:
        self._window = timedelta(seconds=window_seconds)
        self._customers: dict[str, CustomerState] = defaultdict(CustomerState)

    def observe(self, transaction: TransactionEvent) -> FeatureSnapshot:
        state = self._customers[transaction.customer_id]
        window_start = transaction.event_time - self._window
        state.event_times = [
            timestamp for timestamp in state.event_times if window_start <= timestamp
        ]

        is_new_device = bool(state.device_ids) and transaction.device_id not in state.device_ids
        is_new_country = (
            bool(state.country_codes) and transaction.country_code not in state.country_codes
        )

        state.event_times.append(transaction.event_time)
        state.device_ids.add(transaction.device_id)
        state.country_codes.add(transaction.country_code)

        return FeatureSnapshot(
            amount=transaction.amount,
            transaction_count_5m=len(state.event_times),
            is_new_device=is_new_device,
            is_new_country=is_new_country,
            is_risky_merchant=transaction.merchant_category in {"digital_goods", "electronics"},
        )
