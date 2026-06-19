from datetime import datetime

import pytest
from pydantic import ValidationError

from fraud_detection.schemas import TransactionEvent


def test_valid_transaction_has_version_and_partition_key(valid_transaction_data: dict) -> None:
    transaction = TransactionEvent(**valid_transaction_data)

    assert transaction.schema_version == "1.0"
    assert transaction.kafka_key() == "customer-1"


@pytest.mark.parametrize(
    ("field", "value"),
    [("amount", -1), ("country_code", "USA"), ("latitude", 91)],
)
def test_invalid_transaction_is_rejected(
    valid_transaction_data: dict,
    field: str,
    value,
) -> None:
    data = valid_transaction_data
    data[field] = value

    with pytest.raises(ValidationError):
        TransactionEvent(**data)


def test_naive_event_time_is_rejected(valid_transaction_data: dict) -> None:
    data = valid_transaction_data
    data["event_time"] = datetime(2026, 1, 1)

    with pytest.raises(ValidationError):
        TransactionEvent(**data)


def test_unknown_future_fields_are_ignored(valid_transaction_data: dict) -> None:
    # Forward-compatible schema evolution: a newer producer may add fields the
    # current contract does not know about; those must be ignored, not rejected.
    data = valid_transaction_data
    data["new_signal_v2"] = "future"

    transaction = TransactionEvent(**data)

    assert transaction.schema_version == "1.0"
    assert not hasattr(transaction, "new_signal_v2")
