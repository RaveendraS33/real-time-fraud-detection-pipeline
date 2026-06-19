# Security and Privacy

This is a **local-first portfolio system**. It is built to demonstrate production-minded design,
not to process real payments. This document states the posture honestly and lists what a real
deployment would add.

## Data and privacy

- **Synthetic data only.** All transactions come from `TransactionSimulator`. There is no real
  cardholder data, and no real names, cards, devices, or IP addresses.
- **No PII by construction.** Identifiers (`customer_id`, `card_id`, `device_id`) are opaque
  synthetic strings. If this system ingested real data, those fields would require tokenization,
  encryption at rest, and masking in logs and the dashboard.
- **No label leakage.** `simulation.is_fraud` is ground-truth metadata used only as the training
  target and for dashboard evaluation. It is excluded from the feature contract, so the model
  cannot "cheat" by reading the label. See [MODEL_CARD.md](MODEL_CARD.md).
- **Input validation at the boundary.** The ingestion API validates every event against a Pydantic
  schema; malformed events are rejected (HTTP 422) or routed to the dead-letter topic rather than
  crashing a worker.

## Credentials and access

- The PostgreSQL credentials in `docker-compose.yml` / `.env.example` are **development-only
  defaults** and must never be reused in a real environment.
- `.env` is git-ignored; only `.env.example` (placeholders) is committed. No secrets are committed.
- Services run as a non-root user inside their containers.

## Network exposure

Containers communicate on an internal Docker network. Only these ports are published to the host
for local use: API `8000`, dashboard `8501`, Prometheus `9090`, PostgreSQL `5432`, Kafka `9092`.
Nothing is exposed publicly.

## Intentionally out of scope (what production would require)

- Secrets management (e.g., a vault) instead of environment defaults.
- TLS and authentication/authorization on the API, dashboard, Kafka, and PostgreSQL.
- Role-based access control and audit logging for dashboard and database access.
- PII encryption, tokenization, masking, and a data-retention/deletion policy.
- Network policies, image scanning, and dependency/supply-chain controls in CI.

Calling these out explicitly is the point: the project is honest about being a demonstration, and
about exactly what would have to harden before it touched real money or real customers.
