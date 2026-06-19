"""FastAPI service that validates and publishes transaction events."""

import logging
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from fraud_detection.config import Settings, get_settings
from fraud_detection.messaging import KafkaTransactionPublisher, TransactionPublisher
from fraud_detection.metrics import API_TRANSACTIONS
from fraud_detection.schemas import AcceptedTransaction, TransactionEvent

PublisherFactory = Callable[[Settings], TransactionPublisher]
logger = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    publisher_factory: PublisherFactory = KafkaTransactionPublisher,
) -> FastAPI:
    app_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.publisher = publisher_factory(app_settings)
        logger.info("Transaction API started in %s", app_settings.app_env)
        yield
        app.state.publisher.close()

    application = FastAPI(
        title="Real-Time Fraud Detection Transaction API",
        version="0.1.0",
        lifespan=lifespan,
    )

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "healthy"}

    @application.get("/metrics", include_in_schema=False)
    def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @application.get("/transactions/sample", response_model=TransactionEvent)
    def sample_transaction() -> TransactionEvent:
        return TransactionEvent(
            customer_id="customer-1001",
            card_id="card-501",
            merchant_id="merchant-42",
            merchant_category="grocery",
            amount=48.75,
            currency="USD",
            country_code="US",
            city="Boston",
            latitude=42.3601,
            longitude=-71.0589,
            device_id="device-901",
            ip_address="198.51.100.10",
            channel="ecommerce",
            event_time=datetime.now(UTC),
        )

    @application.post(
        "/transactions",
        response_model=AcceptedTransaction,
        status_code=status.HTTP_202_ACCEPTED,
    )
    def submit_transaction(
        transaction: TransactionEvent,
        request: Request,
    ) -> AcceptedTransaction:
        try:
            request.app.state.publisher.publish(transaction)
        except RuntimeError as exc:
            API_TRANSACTIONS.labels(outcome="rejected").inc()
            logger.exception("Transaction publish failed")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Transaction stream is temporarily unavailable",
            ) from exc

        API_TRANSACTIONS.labels(outcome="accepted").inc()
        return AcceptedTransaction(
            transaction_id=transaction.transaction_id,
            accepted_at=datetime.now(UTC),
        )

    return application


app = create_app()
