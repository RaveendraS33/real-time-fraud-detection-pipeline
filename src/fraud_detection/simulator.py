"""Deterministic synthetic transaction generator with explainable fraud scenarios."""

import random
from datetime import UTC, datetime
from uuid import uuid4

from fraud_detection.schemas import SimulationMetadata, TransactionEvent

LOCATIONS = [
    ("US", "Boston", 42.3601, -71.0589, "USD"),
    ("US", "New York", 40.7128, -74.0060, "USD"),
    ("CA", "Toronto", 43.6532, -79.3832, "CAD"),
    ("GB", "London", 51.5072, -0.1276, "GBP"),
]
MERCHANTS = [
    ("merchant-grocery", "grocery"),
    ("merchant-electronics", "electronics"),
    ("merchant-travel", "travel"),
    ("merchant-digital", "digital_goods"),
]


class TransactionSimulator:
    def __init__(self, seed: int | None = None) -> None:
        self._random = random.Random(seed)

    def generate(self, fraud_rate: float = 0.08) -> TransactionEvent:
        if not 0 <= fraud_rate <= 1:
            raise ValueError("fraud_rate must be between 0 and 1")

        is_fraud = self._random.random() < fraud_rate
        customer_number = self._random.randint(1, 250)
        country, city, latitude, longitude, currency = self._random.choice(LOCATIONS)
        merchant_id, category = self._random.choice(MERCHANTS)
        scenario = None

        if is_fraud:
            scenario = self._random.choice(("high_amount", "foreign_device", "card_testing"))
            if scenario == "high_amount":
                amount = round(self._random.uniform(1_000, 8_000), 2)
                category = "electronics"
            elif scenario == "foreign_device":
                amount = round(self._random.uniform(80, 1_500), 2)
                country, city, latitude, longitude, currency = self._random.choice(LOCATIONS[2:])
            else:
                amount = round(self._random.uniform(2, 100), 2)
                merchant_id, category = "merchant-digital", "digital_goods"
            device_id = f"new-device-{uuid4().hex[:10]}"
        else:
            amount = round(max(1, self._random.lognormvariate(4.2, 1.05)), 2)
            if self._random.random() < 0.03:
                amount = round(self._random.uniform(500, 1_800), 2)
            if self._random.random() < 0.05:
                device_id = f"replacement-device-{uuid4().hex[:10]}"
            else:
                device_id = f"device-{customer_number}"

        return TransactionEvent(
            customer_id=f"customer-{customer_number}",
            card_id=f"card-{customer_number}",
            merchant_id=merchant_id,
            merchant_category=category,
            amount=amount,
            currency=currency,
            country_code=country,
            city=city,
            latitude=latitude,
            longitude=longitude,
            device_id=device_id,
            ip_address=f"198.51.100.{self._random.randint(1, 254)}",
            channel=self._random.choice(("card_present", "ecommerce", "mobile")),
            event_time=datetime.now(UTC),
            simulation=SimulationMetadata(is_fraud=is_fraud, scenario=scenario),
        )
