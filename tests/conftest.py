from datetime import UTC, datetime

import pytest


@pytest.fixture
def valid_transaction_data() -> dict:
    return {
        "customer_id": "customer-1",
        "card_id": "card-1",
        "merchant_id": "merchant-1",
        "merchant_category": "grocery",
        "amount": 25.5,
        "currency": "USD",
        "country_code": "US",
        "city": "Boston",
        "latitude": 42.36,
        "longitude": -71.05,
        "device_id": "device-1",
        "ip_address": "198.51.100.1",
        "channel": "ecommerce",
        "event_time": datetime.now(UTC),
    }

