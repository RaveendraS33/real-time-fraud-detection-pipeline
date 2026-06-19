"""Versioned event contracts used across pipeline services."""

from datetime import datetime
from enum import StrEnum
from ipaddress import IPv4Address, IPv6Address
from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import AwareDatetime, BaseModel, Field, StringConstraints

Identifier = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
CountryCode = Annotated[str, StringConstraints(pattern=r"^[A-Z]{2}$")]


class Currency(StrEnum):
    USD = "USD"
    EUR = "EUR"
    GBP = "GBP"
    CAD = "CAD"


class PaymentChannel(StrEnum):
    CARD_PRESENT = "card_present"
    ECOMMERCE = "ecommerce"
    MOBILE = "mobile"


class DecisionOutcome(StrEnum):
    APPROVE = "approve"
    REVIEW = "review"
    DECLINE = "decline"


class SimulationMetadata(BaseModel):
    """Ground truth for synthetic evaluation; never used as a model feature."""

    is_fraud: bool
    scenario: str | None = None


class TransactionEvent(BaseModel):
    """Canonical v1 payment transaction accepted by the ingestion API."""

    schema_version: Literal["1.0"] = "1.0"
    transaction_id: UUID = Field(default_factory=uuid4)
    customer_id: Identifier
    card_id: Identifier
    merchant_id: Identifier
    merchant_category: Identifier
    amount: float = Field(gt=0, le=1_000_000)
    currency: Currency
    country_code: CountryCode
    city: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    device_id: Identifier
    ip_address: IPv4Address | IPv6Address
    channel: PaymentChannel
    event_time: AwareDatetime
    simulation: SimulationMetadata | None = None

    def kafka_key(self) -> str:
        """Keep each customer's events ordered within a Kafka partition."""

        return self.customer_id


class AcceptedTransaction(BaseModel):
    transaction_id: UUID
    status: Literal["accepted"] = "accepted"
    accepted_at: datetime


class FeatureSnapshot(BaseModel):
    amount: float
    transaction_count_5m: int = Field(ge=1)
    is_new_device: bool
    is_new_country: bool
    is_risky_merchant: bool


class FraudDecision(BaseModel):
    """Auditable detector output sent to scored and alert topics."""

    schema_version: Literal["1.0"] = "1.0"
    transaction_id: UUID
    customer_id: Identifier
    event_time: AwareDatetime
    amount: float
    currency: Currency
    risk_score: int = Field(ge=0, le=100)
    fraud_probability: float = Field(ge=0, le=1)
    decision: DecisionOutcome
    triggered_rules: list[str]
    features: FeatureSnapshot
    detector_version: str
    processed_at: AwareDatetime
    simulation_is_fraud: bool | None = None

    def kafka_key(self) -> str:
        return self.customer_id

