from fraud_detection.config import Settings


def test_settings_have_safe_local_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.app_env == "development"
    assert settings.kafka_bootstrap_servers == "localhost:9092"
    assert settings.transactions_topic == "transactions.raw"
    assert settings.database_url.startswith("postgresql://")


def test_settings_can_be_overridden(monkeypatch) -> None:
    monkeypatch.setenv("TRANSACTIONS_TOPIC", "test.transactions")

    settings = Settings(_env_file=None)

    assert settings.transactions_topic == "test.transactions"
