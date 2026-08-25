"""Notifications endpoint built from core data signals."""

from __future__ import annotations

from datetime import UTC, datetime
from threading import Lock
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.core.data_layer.contracts import CoreDataStore
from app.core.data_layer.dashboard import build_dashboard_overview
from app.core.data_layer.entities import FinanceEntry, IngestionBatch, IngestionError, SaleRecord
from app.core.data_layer.factory import get_core_store

router = APIRouter()
_READ_NOTIFICATION_IDS: set[str] = set()
_READ_STATE_LOCK = Lock()


NotificationTab = Literal["Transactions", "Payouts", "Invoices", "System", "AI Alerts"]
NotificationTone = Literal["ai", "success", "danger", "info"]


class NotificationItem(BaseModel):
    """Presentation-friendly notification row."""

    id: str
    title: str
    message: str
    time: str
    tag: NotificationTab
    tone: NotificationTone
    unread: bool = False
    read: bool = True
    action_label: str = "View Details"
    details_href: str


class NotificationFeedResponse(BaseModel):
    """Notification feed for the topbar and alerts screen."""

    generated_at: datetime
    unread_count: int
    total_count: int
    items: list[NotificationItem] = Field(default_factory=list)


class NotificationReadResponse(BaseModel):
    """Read-state mutation response."""

    item: NotificationItem
    unread_count: int
    total_count: int


class NotificationMarkAllReadResponse(BaseModel):
    """Bulk read-state mutation response."""

    unread_count: int
    total_count: int
    items: list[NotificationItem] = Field(default_factory=list)


def clear_notification_read_state() -> None:
    """Reset the transient read-state cache used by the notifications feed."""

    with _READ_STATE_LOCK:
        _READ_NOTIFICATION_IDS.clear()


@router.get("/notifications", response_model=NotificationFeedResponse)
def get_notifications(
    store: Annotated[CoreDataStore, Depends(get_core_store)],
) -> NotificationFeedResponse:
    """Return a live notification feed built from core data."""

    items = _build_notification_items(store)
    unread_count = sum(1 for item in items if item.unread)

    return NotificationFeedResponse(
        generated_at=datetime.now(UTC),
        unread_count=unread_count,
        total_count=len(items),
        items=items,
    )


@router.get("/notifications/{notification_id}", response_model=NotificationItem)
def get_notification(
    notification_id: str,
    store: Annotated[CoreDataStore, Depends(get_core_store)],
) -> NotificationItem:
    """Return one notification item from the live feed."""

    item = _find_notification_item(notification_id, store)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    return item


@router.post("/notifications/{notification_id}/read", response_model=NotificationReadResponse)
def mark_notification_read(
    notification_id: str,
    store: Annotated[CoreDataStore, Depends(get_core_store)],
) -> NotificationReadResponse:
    """Mark one notification as read in the transient backend cache."""

    item = _find_notification_item(notification_id, store)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")

    with _READ_STATE_LOCK:
        _READ_NOTIFICATION_IDS.add(notification_id)

    refreshed_item = _apply_read_state(item)
    feed = _build_notification_items(store)
    return NotificationReadResponse(
        item=refreshed_item,
        unread_count=sum(1 for notification in feed if notification.unread),
        total_count=len(feed),
    )


@router.post("/notifications/read-all", response_model=NotificationMarkAllReadResponse)
def mark_all_notifications_read(
    store: Annotated[CoreDataStore, Depends(get_core_store)],
) -> NotificationMarkAllReadResponse:
    """Mark all live notifications as read in the transient backend cache."""

    items = _build_notification_items(store)
    with _READ_STATE_LOCK:
        _READ_NOTIFICATION_IDS.update(item.id for item in items)

    refreshed_items = [_apply_read_state(item) for item in items]
    return NotificationMarkAllReadResponse(
        unread_count=sum(1 for item in refreshed_items if item.unread),
        total_count=len(refreshed_items),
        items=refreshed_items,
    )


def _build_notification_items(store: CoreDataStore) -> list[NotificationItem]:
    overview = build_dashboard_overview(store)
    items: list[NotificationItem] = []

    if overview.ai_insights:
        items.append(
            _apply_read_state(
                NotificationItem(
                    id="ai-insight-0",
                    title="AI Insight",
                    message=overview.ai_insights[0],
                    time="Now",
                    tag="AI Alerts",
                    tone="ai",
                    unread=True,
                    action_label="View Details",
                    details_href="/alerts/ai-insight-0",
                ),
            ),
        )

    items.extend(_build_signal_notifications(overview.signals))
    items.extend(
        _build_error_notifications(store.list_ingestion_batches(), store.list_ingestion_errors())
    )
    items.extend(_build_transaction_notifications(store.list_sales()))
    items.extend(_build_finance_notifications(store.list_finance_entries()))

    unique_items: list[NotificationItem] = []
    seen_ids: set[str] = set()
    for item in items:
        if item.id in seen_ids:
            continue
        seen_ids.add(item.id)
        unique_items.append(_apply_read_state(item))

    return unique_items[:8]


def _find_notification_item(notification_id: str, store: CoreDataStore) -> NotificationItem | None:
    items = _build_notification_items(store)
    for item in items:
        if item.id == notification_id:
            return item
    return None


def _apply_read_state(item: NotificationItem) -> NotificationItem:
    with _READ_STATE_LOCK:
        is_read = item.id in _READ_NOTIFICATION_IDS or not item.unread

    return item.model_copy(update={"unread": not is_read, "read": is_read})


def _build_signal_notifications(signals: list) -> list[NotificationItem]:
    notifications: list[NotificationItem] = []
    for index, signal in enumerate(signals):
        tag = _tag_from_badge(signal.badge)
        notifications.append(
            NotificationItem(
                id=f"signal-{index}",
                title=signal.title,
                message=signal.note,
                time="Recent",
                tag=tag,
                tone=_tone_from_tag(tag),
                unread=index < 3,
                read=index >= 3,
                action_label="View Details",
                details_href=f"/alerts/signal-{index}",
            ),
        )
    return notifications


def _build_error_notifications(
    batches: list[IngestionBatch],
    errors: list[IngestionError],
) -> list[NotificationItem]:
    batch_map = {batch.batch_id: batch for batch in batches}
    notifications: list[NotificationItem] = []
    sorted_errors = sorted(
        errors,
        key=lambda error: (
            batch_map.get(error.batch_id).finished_at
            if batch_map.get(error.batch_id) and batch_map.get(error.batch_id).finished_at
            else batch_map.get(error.batch_id).started_at
            if batch_map.get(error.batch_id)
            else datetime.min.replace(tzinfo=UTC)
        ),
        reverse=True,
    )

    for error in sorted_errors[:3]:
        batch = batch_map.get(error.batch_id)
        tag = _tag_from_error(error)
        notifications.append(
            NotificationItem(
                id=f"batch-error-{error.error_id}",
                title=f"Import error: {batch.batch_name if batch else error.entity_type}",
                message=error.error_message,
                time=_relative_batch_time(batch),
                tag=tag,
                tone="danger",
                unread=True,
                read=False,
                action_label="Inspect Batch",
                details_href=f"/alerts/batch-error-{error.error_id}",
            ),
        )
    return notifications


def _build_transaction_notifications(sales: list[SaleRecord]) -> list[NotificationItem]:
    if not sales:
        return []

    latest_sale = max(sales, key=lambda sale: sale.occurred_at)
    amount = f"{latest_sale.amount:.2f}".rstrip("0").rstrip(".")
    return [
        NotificationItem(
            id=f"sale-{latest_sale.sale_id}",
            title="Payment Received",
            message=f"{amount} {latest_sale.currency} received from latest sales activity.",
            time=_relative_time(latest_sale.occurred_at),
            tag="Transactions",
            tone="success",
            unread=False,
            read=True,
            action_label="View Transaction",
            details_href=f"/alerts/sale-{latest_sale.sale_id}",
        ),
    ]


def _build_finance_notifications(entries: list[FinanceEntry]) -> list[NotificationItem]:
    if not entries:
        return []

    latest_entry = max(entries, key=lambda entry: entry.occurred_at)
    tag = "Payouts" if latest_entry.entry_type.value == "expense" else "Invoices"
    amount = f"{latest_entry.amount:.2f}".rstrip("0").rstrip(".")
    tone: NotificationTone = "danger" if latest_entry.entry_type.value == "expense" else "info"
    return [
        NotificationItem(
            id=f"finance-{latest_entry.entry_id}",
            title="Finance Update",
            message=f"{amount} {latest_entry.currency} logged for {latest_entry.category}.",
            time=_relative_time(latest_entry.occurred_at),
            tag=tag,
            tone=tone,
            unread=False,
            read=True,
            action_label="View",
            details_href=f"/alerts/finance-{latest_entry.entry_id}",
        ),
    ]


def _tag_from_badge(badge: str) -> NotificationTab:
    normalized = badge.casefold()
    if "финанс" in normalized:
        return "Payouts"
    if "продаж" in normalized:
        return "Transactions"
    if "рост" in normalized:
        return "AI Alerts"
    return "System"


def _tag_from_error(error: IngestionError) -> NotificationTab:
    entity_type = error.entity_type.casefold()
    if "sale" in entity_type or "order" in entity_type:
        return "Transactions"
    if "finance" in entity_type or "cash" in entity_type:
        return "Payouts"
    if "invoice" in entity_type:
        return "Invoices"
    return "System"


def _tone_from_tag(tag: NotificationTab) -> NotificationTone:
    if tag == "Transactions":
        return "success"
    if tag == "Payouts":
        return "danger"
    if tag == "Invoices":
        return "info"
    if tag == "AI Alerts":
        return "ai"
    return "info"


def _relative_time(timestamp: datetime) -> str:
    delta = datetime.now(UTC) - timestamp.astimezone(UTC)
    minutes = max(int(delta.total_seconds() // 60), 0)
    if minutes < 1:
        return "Now"
    if minutes < 60:
        return f"{minutes} mins ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    days = hours // 24
    return f"{days} day{'s' if days != 1 else ''} ago"


def _relative_batch_time(batch: IngestionBatch | None) -> str:
    if batch is None:
        return "Recent"
    reference = batch.finished_at or batch.started_at
    return _relative_time(reference)
