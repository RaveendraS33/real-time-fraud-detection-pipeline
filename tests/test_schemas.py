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
