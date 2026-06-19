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
| Prometheus | <http://localhost:9090/targets> | Four scrape targets are `UP` |

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
