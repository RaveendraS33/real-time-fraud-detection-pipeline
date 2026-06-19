"""Environment-backed application configuration."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration shared by local services."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    log_level: str = "INFO"
    kafka_bootstrap_servers: str = "localhost:9092"
    transactions_topic: str = "transactions.raw"
    fraud_decisions_topic: str = "transactions.scored"
    fraud_alerts_topic: str = "fraud.alerts"
    dead_letter_topic: str = "transactions.dead_letter"
    high_amount_threshold: float = 2_500
    velocity_window_seconds: int = 300
    velocity_count_threshold: int = 5
    review_score_threshold: int = 40
    decline_score_threshold: int = 70
    model_path: str = "models/fraud_logreg_v1.json"
    metrics_port: int = 9_101
    database_url: str = "postgresql://fraud_app:fraud_dev_password@localhost:5432/fraud_detection"


@lru_cache
def get_settings() -> Settings:
    """Return one immutable-by-convention settings instance per process."""

    return Settings()
