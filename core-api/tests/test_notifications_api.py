"""Tests for the notifications API."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from app.api.routes.dashboard import get_core_store
from app.api.routes.notifications import clear_notification_read_state
from app.core.data_layer.entities import (
    BusinessProfile,
    FinanceEntry,
    FinanceEntryType,
    IngestionBatch,
    IngestionBatchStatus,
    IngestionError,
    SaleRecord,
    SaleStage,
)
from app.core.data_layer.service import InMemoryCoreDataLayer
from app.main import app


def test_notifications_feed_returns_live_items_from_store() -> None:
    clear_notification_read_state()
    store = InMemoryCoreDataLayer()
    business = store.register_business(
        BusinessProfile(
            name="Acme LLC",
            legal_name="Acme LLC",
            external_ref="su-biz-001",
        ),
    )
    store.upsert_sale(
        SaleRecord(
            business_id=business.business_id,
            contact_id=None,
            external_ref="su-sale-001",
            amount=Decimal("125.50"),
            currency="USD",
            stage=SaleStage.WON,
            occurred_at=datetime.now(UTC) - timedelta(minutes=5),
        ),
    )
    store.upsert_finance_entry(
        FinanceEntry(
            business_id=business.business_id,
            external_ref="su-fin-001",
            entry_type=FinanceEntryType.EXPENSE,
            category="ads",
            amount=Decimal("30.25"),
            currency="USD",
            occurred_at=datetime.now(UTC) - timedelta(minutes=30),
        ),
    )
    batch = store.upsert_ingestion_batch(
        IngestionBatch(
            business_id=business.business_id,
            source_system_id=None,
            batch_name="Legal entities import",
            status=IngestionBatchStatus.FAILED,
            started_at=datetime.now(UTC) - timedelta(hours=2),
            finished_at=datetime.now(UTC) - timedelta(hours=1, minutes=45),
        ),
    )
    store.record_ingestion_error(
        IngestionError(
            batch_id=batch.batch_id,
            business_id=business.business_id,
            entity_type="legal_person",
            error_code="HTTPStatusError",
            error_message="Запрашиваемая страница или ресурс не найдены.",
            metadata={"endpoint": "/b/trade/mxsx/mr/legal_person$export"},
        ),
    )

    app.dependency_overrides[get_core_store] = lambda: store
    client = TestClient(app)

    try:
        response = client.get("/api/v1/notifications")
        assert response.status_code == 200

        payload = response.json()
        notification_id = payload["items"][0]["id"]
        read_response = client.post(f"/api/v1/notifications/{notification_id}/read")
        detail_response = client.get(f"/api/v1/notifications/{notification_id}")
    finally:
        app.dependency_overrides.clear()
        clear_notification_read_state()

    assert read_response.status_code == 200
    assert detail_response.status_code == 200

    payload = response.json()
    assert payload["total_count"] == len(payload["items"])
    assert payload["unread_count"] == sum(1 for item in payload["items"] if item["unread"])
    assert any(item["tag"] == "AI Alerts" for item in payload["items"])
    assert any(item["id"].startswith("batch-error-") for item in payload["items"])
    assert any(item["details_href"].startswith("/alerts/") for item in payload["items"])
    assert any(item["read"] is True for item in payload["items"])

    detail_payload = detail_response.json()
    assert detail_payload["id"] == notification_id
    assert detail_payload["read"] is True
    assert detail_payload["unread"] is False
