# Operations Runbook

## Start and Verify

```powershell
docker compose up -d --build
docker compose ps
```

Expected endpoints:

| Service | URL | Healthy signal |
| --- | --- | --- |
| Transaction API | <http://localhost:8000/health> | `{"status":"healthy"}` |
| API documentation | <http://localhost:8000/docs> | OpenAPI page loads |
| Fraud dashboard | <http://localhost:8501> | Metrics and investigation queue render |
| Prometheus | <http://localhost:9090/targets> | Five scrape targets are `UP` |

Generate a short stream:

```powershell
.\.venv\Scripts\python.exe scripts\simulate_transactions.py --count 25 --fraud-rate 0.12
```

Run the live integration test:

```powershell
.\scripts\run_integration_tests.ps1
```

## Service Logs

```powershell
docker compose logs transaction-api --tail=100
docker compose logs detector --tail=100
docker compose logs decision-store --tail=100
docker compose logs alerter --tail=100
docker compose logs postgres --tail=100
```

The detector log includes transaction ID, outcome, risk score, and triggered rules. Prometheus
tracks accepted API requests, decision counts, detector latency, model probability distribution,
storage counts, alert counts, and failure counters.

## Data Checks

Decision summary:

```powershell
docker exec fraud-postgres psql -U fraud_app -d fraud_detection -c "SELECT decision, COUNT(*) FROM fraud_decisions GROUP BY decision;"
```

Dead-letter messages:

```powershell
docker exec fraud-kafka /opt/kafka/bin/kafka-console-consumer.sh --bootstrap-server localhost:9092 --topic transactions.dead_letter --from-beginning --timeout-ms 5000
```

Consumer lag:

```powershell
docker exec fraud-kafka /opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server localhost:9092 --describe --group fraud-detector-v1
docker exec fraud-kafka /opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server localhost:9092 --describe --group decision-store-v1
docker exec fraud-kafka /opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server localhost:9092 --describe --group fraud-alerter-v1
```

## Alerts

Prometheus loads alert rules from `monitoring/alerts.yml`; view them at
<http://localhost:9090/alerts>:

- `ServiceDown` — a scrape target has been down for 1m.
- `DetectorFailures` / `DecisionStoreFailures` — validation or delivery failures within 5m.
- `AlertWebhookFailing` — fraud-alert webhook delivery is failing.
- `PipelineStalled` — the detector scored nothing for 10m while the API kept ingesting.
- `ConsumerLag` — a consumer group's total lag exceeds 1000 for 5m. Per-partition lag is published
  as `fraud_consumer_lag{group,topic,partition}` by the `lag-exporter` service (high watermark minus
  committed offset), the real health signal for the Kafka consumers.

Rules are routed to **Alertmanager** (<http://localhost:9093>), which groups and de-duplicates
them. The demo ships an empty receiver (alerts are visible in the Alertmanager UI); configure a
Slack / PagerDuty / email / webhook receiver in `monitoring/alertmanager.yml` for real paging.

### Replaying dead-letter messages

After fixing the root cause of a poison message or a downstream outage, replay the captured events
back onto a source topic (dry-run first):

```powershell
.\.venv\Scripts\python.exe scripts\replay_dead_letter.py --dry-run
.\.venv\Scripts\python.exe scripts\replay_dead_letter.py --target-topic transactions.raw
```

## Performance

Measure latency and throughput against the running stack:

```powershell
.\.venv\Scripts\python.exe scripts\benchmark.py --count 300 --concurrency 20
```

Observed locally: ~300 transactions/s accepted (API p50 ~50 ms, p99 ~59 ms), detector scoring
~2.4 ms average / ~4.8 ms p95, and ~98 transactions/s end-to-end through Kafka to PostgreSQL.

Context: single-node Docker on one developer machine; the `transactions.raw` topic has 3
partitions; the API produces synchronously with `acks=all`. These numbers demonstrate
order-of-magnitude behavior, not a capacity guarantee, and are environment-dependent. Run
`docker stats` during a benchmark to capture per-container CPU/memory headroom.

## Common Failures

### API returns 503

Check Kafka health and API delivery logs. Confirm `fraud-kafka` is healthy and the
`transactions.raw` topic exists.

### Transactions do not reach PostgreSQL

Check detector and decision-store consumer lag, then inspect both service logs. Invalid payloads
are routed to `transactions.dead_letter`.

### Detector fails during startup

Confirm `models/fraud_logreg_v1.json` exists. Run the documented training command and compare the
artifact using the CI check. A feature-contract mismatch intentionally prevents startup.

### Dashboard shows a database error

Confirm PostgreSQL and `fraud-decision-store` are running. The dashboard retries automatically on
its next five-second refresh.

### Fraud alerts are not delivered

Check `docker compose logs alerter` and the `fraud-alerter-v1` consumer lag. Every alert is written
to the alerter log (`FRAUD_ALERT ...`) regardless of webhook status. Webhook delivery is
best-effort: failures increment `fraud_alert_failures_total{stage="webhook"}` and are logged, but
never block or re-drive the pipeline. Set `ALERT_WEBHOOK_URL` to enable webhook forwarding.

## Stop and Reset

Stop containers while retaining local Kafka, PostgreSQL, and Prometheus data:

```powershell
docker compose down
```

Delete all local project data only when a clean reset is intentional:

```powershell
docker compose down -v
```

Neither command creates or changes AWS resources. The project remains `$0` in cloud spend.
