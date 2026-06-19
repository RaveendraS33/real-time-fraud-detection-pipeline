"""PostgreSQL schema and idempotent fraud-decision persistence."""

from collections.abc import Callable
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from fraud_detection.schemas import FraudDecision

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS fraud_decisions (
    transaction_id UUID PRIMARY KEY,
    customer_id VARCHAR(64) NOT NULL,
    event_time TIMESTAMPTZ NOT NULL,
    amount NUMERIC(14, 2) NOT NULL,
    currency VARCHAR(3) NOT NULL,
    risk_score SMALLINT NOT NULL CHECK (risk_score BETWEEN 0 AND 100),
    rule_risk_score SMALLINT NOT NULL CHECK (rule_risk_score BETWEEN 0 AND 100),
    fraud_probability DOUBLE PRECISION NOT NULL CHECK (fraud_probability BETWEEN 0 AND 1),
    decision VARCHAR(10) NOT NULL CHECK (decision IN ('approve', 'review', 'decline')),
    triggered_rules JSONB NOT NULL,
    features JSONB NOT NULL,
    detector_version VARCHAR(50) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL,
    simulation_is_fraud BOOLEAN,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""

INDEX_STATEMENTS = (
    "CREATE INDEX IF NOT EXISTS idx_fraud_decisions_event_time "
    "ON fraud_decisions (event_time DESC)",
    "CREATE INDEX IF NOT EXISTS idx_fraud_decisions_outcome "
    "ON fraud_decisions (decision, event_time DESC)",
    "CREATE INDEX IF NOT EXISTS idx_fraud_decisions_risk ON fraud_decisions (risk_score DESC)",
)

MIGRATION_STATEMENTS = (
    "ALTER TABLE fraud_decisions ADD COLUMN IF NOT EXISTS "
    "rule_risk_score SMALLINT NOT NULL DEFAULT 0",
)

UPSERT_SQL = """
INSERT INTO fraud_decisions (
    transaction_id, customer_id, event_time, amount, currency, risk_score, rule_risk_score,
    fraud_probability, decision, triggered_rules, features, detector_version,
    processed_at, simulation_is_fraud
) VALUES (
    %(transaction_id)s, %(customer_id)s, %(event_time)s, %(amount)s, %(currency)s,
    %(risk_score)s, %(rule_risk_score)s, %(fraud_probability)s, %(decision)s,
    %(triggered_rules)s,
    %(features)s, %(detector_version)s, %(processed_at)s, %(simulation_is_fraud)s
)
ON CONFLICT (transaction_id) DO UPDATE SET
    customer_id = EXCLUDED.customer_id,
    event_time = EXCLUDED.event_time,
    amount = EXCLUDED.amount,
    currency = EXCLUDED.currency,
    risk_score = EXCLUDED.risk_score,
    rule_risk_score = EXCLUDED.rule_risk_score,
    fraud_probability = EXCLUDED.fraud_probability,
    decision = EXCLUDED.decision,
    triggered_rules = EXCLUDED.triggered_rules,
    features = EXCLUDED.features,
    detector_version = EXCLUDED.detector_version,
    processed_at = EXCLUDED.processed_at,
    simulation_is_fraud = EXCLUDED.simulation_is_fraud,
    ingested_at = NOW()
WHERE EXCLUDED.processed_at >= fraud_decisions.processed_at
"""


def decision_to_params(decision: FraudDecision) -> dict[str, Any]:
    return {
        "transaction_id": decision.transaction_id,
        "customer_id": decision.customer_id,
        "event_time": decision.event_time,
        "amount": decision.amount,
        "currency": decision.currency.value,
        "risk_score": decision.risk_score,
        "rule_risk_score": decision.rule_risk_score,
        "fraud_probability": decision.fraud_probability,
        "decision": decision.decision.value,
        "triggered_rules": Jsonb(decision.triggered_rules),
        "features": Jsonb(decision.features.model_dump(mode="json")),
        "detector_version": decision.detector_version,
        "processed_at": decision.processed_at,
        "simulation_is_fraud": decision.simulation_is_fraud,
    }


class DecisionRepository:
    """Own the database schema and transaction-idempotent upsert operation."""

    def __init__(
        self,
        database_url: str,
        connect: Callable[..., Any] = psycopg.connect,
    ) -> None:
        self._database_url = database_url
        self._connect = connect

    def ensure_schema(self) -> None:
        with self._connect(self._database_url) as connection:
            connection.execute(CREATE_TABLE_SQL)
            for statement in MIGRATION_STATEMENTS:
                connection.execute(statement)
            for statement in INDEX_STATEMENTS:
                connection.execute(statement)

    def upsert(self, decision: FraudDecision) -> None:
        with self._connect(self._database_url) as connection:
            connection.execute(UPSERT_SQL, decision_to_params(decision))
