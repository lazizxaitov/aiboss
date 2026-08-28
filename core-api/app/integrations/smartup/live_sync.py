"""Background SmartUp synchronization using the existing migration pipeline."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, time, timedelta
from logging import getLogger
from threading import Event, Thread
from time import sleep
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

from app.core.auto_business_analytics import AutoBusinessAnalyticsService
from app.core.config import settings
from app.core.data_layer.contracts import CoreDataStore
from app.integrations.smartup.models import SmartUpMigrationMode
from app.integrations.smartup.operations import (
    SMARTUP_MIGRATION_LOCK,
    SmartUpAccountService,
    SmartUpAuthPayload,
)

logger = getLogger(__name__)

LIVE_SYNC_STATUS_KEY = "smartup:live_sync_status:v1"
SMARTUP_LIVE_SYNC_WAKE = Event()


def wake_smartup_live_sync() -> None:
    """Wake the process-owned sync loop after configuration changes."""

    SMARTUP_LIVE_SYNC_WAKE.set()


class SmartUpOrganizationConnectionState(BaseModel):
    """Persisted connection state for one configured SmartUp organization."""

    organization_id: UUID
    organization_name: str
    status: Literal["not_configured", "checking", "connected", "retry_wait", "error"]
    sync_available: bool = False
    code: str | None = None
    message: str | None = None
    last_checked_at: datetime | None = None
    last_success_at: datetime | None = None


class SmartUpLiveSyncStatus(BaseModel):
    enabled: bool = True
    status: Literal[
        "not_configured",
        "initial_sync_required",
        "initial_sync_running",
        "ready",
        "live_sync_running",
        "retry_wait",
        "error",
        # Compatibility for statuses persisted by older builds.
        "idle",
        "running",
        "success",
        "warning",
    ] = "idle"
    last_started_at: datetime | None = None
    last_completed_at: datetime | None = None
    last_success_at: datetime | None = None
    next_run_at: datetime | None = None
    organizations_processed: int = 0
    raw_records: int = 0
    core_records: int = 0
    canonical_updated: bool = False
    errors_count: int = 0
    skipped_due_to_running: bool = False
    last_mode: SmartUpMigrationMode | None = None
    message: str | None = None
    organization_connections: list[SmartUpOrganizationConnectionState] = Field(default_factory=list)


class SmartUpLiveSyncService:
    """Run short SmartUp reconciliation cycles in one process instance."""

    def __init__(self, store: CoreDataStore) -> None:
        self.store = store
        self._stop = Event()
        self._thread: Thread | None = None
        self._last_reconciliation_at: datetime | None = None

    def status(self) -> SmartUpLiveSyncStatus:
        setting = self.store.get_app_setting(LIVE_SYNC_STATUS_KEY)
        if setting is None:
            return SmartUpLiveSyncStatus(
                enabled=settings.smartup_live_sync_enabled,
                next_run_at=self._next_scheduled_run(datetime.now(UTC)),
            )
        try:
            return SmartUpLiveSyncStatus.model_validate(setting.setting_value)
        except Exception:  # noqa: BLE001
            return SmartUpLiveSyncStatus(enabled=settings.smartup_live_sync_enabled)

    def start(self) -> None:
        if not settings.smartup_live_sync_enabled or self._thread is not None:
            return
        self._thread = Thread(target=self._run_loop, name="smartup-live-sync", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def _run_loop(self) -> None:
        self._run_startup_reconciliation()
        last_trigger: str | None = None
        while not self._stop.is_set():
            woke = False
            for _ in range(60):
                if self._stop.is_set():
                    break
                if SMARTUP_LIVE_SYNC_WAKE.wait(0.5):
                    woke = True
                    break
            SMARTUP_LIVE_SYNC_WAKE.clear()
            if self._stop.is_set():
                break
            now = datetime.now(UTC)
            current = self.status()
            if woke and self._configured_organizations() and current.status not in {
                "initial_sync_running",
                "live_sync_running",
            }:
                self._run_startup_reconciliation()
                continue
            if current.status == "not_configured" and self._configured_organizations():
                self._run_startup_reconciliation()
                continue
            if (
                current.status in {"retry_wait", "initial_sync_required"}
                and current.next_run_at
                and current.next_run_at <= now
            ):
                if not self._verify_startup_connections():
                    continue
                mode = (
                    SmartUpMigrationMode.FULL_BACKFILL
                    if self._initial_sync_required()
                    else SmartUpMigrationMode.WEEKLY_RECONCILIATION
                )
                self.run_once(mode, initial=mode == SmartUpMigrationMode.FULL_BACKFILL)
                continue
            local_now = now.astimezone(ZoneInfo("Asia/Tashkent"))
            for scheduled in self._schedule_times():
                if local_now.hour == scheduled.hour and local_now.minute == scheduled.minute:
                    trigger_key = f"{local_now.date()}-{scheduled.isoformat()}"
                    if trigger_key != last_trigger:
                        last_trigger = trigger_key
                        self.run_once(SmartUpMigrationMode.ONE_DAY_CHECK)
                    break

    def _run_startup_reconciliation(self) -> None:
        if not self._verify_startup_connections():
            return

        initial = self._initial_sync_required()
        self._save(self.status().model_copy(update={
            "status": "initial_sync_required" if initial else "ready",
            "next_run_at": datetime.now(UTC),
            "message": (
                "Требуется первичная синхронизация SmartUp."
                if initial
                else "SmartUp подключён. Данные готовы к обновлению."
            ),
        }))
        self.run_once(
            (
                SmartUpMigrationMode.FULL_BACKFILL
                if initial
                else SmartUpMigrationMode.WEEKLY_RECONCILIATION
            ),
            initial=initial,
        )

    def _configured_organizations(self):
        service = SmartUpAccountService(self.store)
        return [
            organization
            for organization in service.list_organizations()
            if organization.is_active
            and service.resolve_organization_auth(organization).credentials_available
        ]

    def _verify_startup_connections(self) -> bool:
        """Verify saved credentials before allowing the sync pipeline to run."""

        service = SmartUpAccountService(self.store)
        organizations = service.list_organizations()
        now = datetime.now(UTC)
        current = self.status()
        previous = {str(item.organization_id): item for item in current.organization_connections}
        states: list[SmartUpOrganizationConnectionState] = []
        configured_count = 0
        connected_count = 0

        logger.info("SMARTUP_STARTUP_CHECK_START organizations=%s", len(organizations))
        for organization in organizations:
            if not organization.is_active:
                continue
            resolved = service.resolve_organization_auth(organization)
            if not resolved.credentials_available:
                state = SmartUpOrganizationConnectionState(
                    organization_id=organization.id,
                    organization_name=organization.name,
                    status="not_configured",
                    message="Сохраните credentials SmartUp для этой организации.",
                    last_checked_at=now,
                )
                states.append(state)
                logger.info(
                    "SMARTUP_STARTUP_CHECK_FAILED organization_id=%s "
                    "code=SMARTUP_CREDENTIALS_NOT_FOUND",
                    organization.id,
                )
                continue

            configured_count += 1
            logger.info(
                "SMARTUP_STARTUP_CHECK_ORGANIZATION organization_id=%s",
                organization.id,
            )
            previous_state = previous.get(str(organization.id))
            checking = SmartUpOrganizationConnectionState(
                organization_id=organization.id,
                organization_name=organization.name,
                status="checking",
                sync_available=False,
                last_checked_at=now,
                last_success_at=previous_state.last_success_at if previous_state else None,
            )
            states.append(checking)
            self._save(current.model_copy(update={
                "status": "initial_sync_required",
                "organization_connections": states + [
                    item for item in current.organization_connections
                    if item.organization_id not in {state.organization_id for state in states}
                ],
                "message": "Проверяем подключение SmartUp...",
            }))
            try:
                result = service.check_connection(organization.id, SmartUpAuthPayload())
            except Exception as exc:  # noqa: BLE001
                result = None
                error_message = f"Не удалось проверить подключение SmartUp: {exc}"
            else:
                error_message = result.message

            if result is not None and result.connected:
                connected_count += 1
                state = checking.model_copy(update={
                    "status": "connected",
                    "sync_available": True,
                    "code": result.code,
                    "message": result.message,
                    "last_success_at": now,
                })
                logger.info("SMARTUP_STARTUP_CHECK_SUCCESS organization_id=%s", organization.id)
            else:
                code = result.code if result is not None else "SMARTUP_UNAVAILABLE"
                state = checking.model_copy(update={
                    "status": "retry_wait",
                    "code": code,
                    "message": error_message,
                })
                logger.info(
                    "SMARTUP_STARTUP_CHECK_FAILED organization_id=%s code=%s",
                    organization.id,
                    code,
                )
                logger.info(
                    "SMARTUP_CONNECTION_RETRY organization_id=%s next_retry_at=%s",
                    organization.id,
                    now + timedelta(seconds=60),
                )
            states[-1] = state

        if configured_count == 0:
            self._save(current.model_copy(update={
                "status": "not_configured",
                "organization_connections": states,
                "next_run_at": None,
                "message": "SmartUp не настроен.",
            }))
            logger.info("SMARTUP_STARTUP_CHECK_COMPLETE connected=0 configured=0")
            return False

        verified = connected_count > 0
        self._save(current.model_copy(update={
            "status": "initial_sync_required" if verified else "retry_wait",
            "organization_connections": states,
            "next_run_at": now if verified else now + timedelta(seconds=60),
            "message": (
                "Подключение SmartUp подтверждено. Запускаем синхронизацию."
                if verified
                else "Временно нет связи со SmartUp. Повторяем проверку автоматически."
            ),
        }))
        logger.info(
            "SMARTUP_STARTUP_CHECK_COMPLETE connected=%s configured=%s",
            connected_count,
            configured_count,
        )
        return verified

    def _initial_sync_required(self) -> bool:
        organizations = self._configured_organizations()
        return bool(organizations) and any(
            item.last_sync_at is None or self.store.get_canonical_organization(item.id) is None
            for item in organizations
        )

    @staticmethod
    def _schedule_times() -> list[time]:
        result: list[time] = []
        for raw in settings.smartup_auto_sync_schedule.split(","):
            try:
                hour, minute = (int(part.strip()) for part in raw.split(":", 1))
                result.append(time(hour=hour, minute=minute))
            except (ValueError, TypeError):
                continue
        return sorted(result) or [time(8, 0), time(14, 0), time(21, 0)]

    def _next_scheduled_run(self, now: datetime) -> datetime:
        local_now = now.astimezone(ZoneInfo("Asia/Tashkent"))
        for scheduled in self._schedule_times():
            candidate = local_now.replace(
                hour=scheduled.hour,
                minute=scheduled.minute,
                second=0,
                microsecond=0,
            )
            if candidate > local_now:
                return candidate.astimezone(UTC)
        tomorrow = local_now + timedelta(days=1)
        scheduled = self._schedule_times()[0]
        return tomorrow.replace(
            hour=scheduled.hour,
            minute=scheduled.minute,
            second=0,
            microsecond=0,
        ).astimezone(UTC)

    def run_once(
        self,
        mode: SmartUpMigrationMode = SmartUpMigrationMode.ONE_DAY_CHECK,
        *,
        initial: bool = False,
    ) -> bool:
        if SMARTUP_MIGRATION_LOCK.locked():
            current = self.status()
            self._save(current.model_copy(update={
                "status": "initial_sync_required" if initial else "ready",
                "skipped_due_to_running": True,
                "message": (
                    "Синхронизация уже выполняется. Автозапуск продолжится "
                    "после её завершения."
                ),
                "next_run_at": datetime.now(UTC) + timedelta(seconds=30),
            }))
            return False

        now = datetime.now(UTC)
        window_days = 7 if mode == SmartUpMigrationMode.WEEKLY_RECONCILIATION else 2
        current = self.status()
        self._save(SmartUpLiveSyncStatus(
            enabled=True,
            status="initial_sync_running" if initial else "live_sync_running",
            last_started_at=now,
            next_run_at=self._next_scheduled_run(now),
            last_mode=mode,
            message=(
                "Первичная синхронизация SmartUp. Загружаем данные..."
                if initial
                else "Обновляем данные SmartUp..."
            ),
            organization_connections=current.organization_connections,
        ))
        payload = SmartUpAuthPayload(
            migration_mode=mode,
            history_start=(
                None
                if mode == SmartUpMigrationMode.FULL_BACKFILL
                else now - timedelta(days=window_days)
            ),
            history_end=now,
        )
        job = SmartUpAccountService(self.store).start_migration_job(payload)
        while job.status in {"pending", "running"} and not self._stop.is_set():
            sleep(0.5)
            job = SmartUpAccountService(self.store).get_migration_job(job.job_id) or job

        if job.status != "completed" or job.result is None:
            self._save(self.status().model_copy(update={
                "status": "retry_wait",
                "last_completed_at": datetime.now(UTC),
                "errors_count": 1,
                "next_run_at": datetime.now(UTC) + timedelta(seconds=60),
                "message": (
                    "Временно нет связи со SmartUp. Используются последние сохранённые "
                    "данные. Повторное подключение выполняется автоматически."
                ),
            }))
            logger.info(
                "SMARTUP_CONNECTION_RETRY next_retry_at=%s",
                datetime.now(UTC) + timedelta(seconds=60),
            )
            return False

        result = job.result
        errors = len(result.batch_errors) + result.summary.errors
        completed_at = datetime.now(UTC)
        next_status = "retry_wait" if errors else "ready"
        self._save(self.status().model_copy(update={
            "status": next_status,
            "last_completed_at": completed_at,
            "last_success_at": completed_at if not errors else self.status().last_success_at,
            "organizations_processed": result.organizations_count,
            "raw_records": result.counters.get("records", 0),
            "core_records": result.summary.records,
            "canonical_updated": True,
            "errors_count": errors,
            "skipped_due_to_running": False,
            "next_run_at": (
                completed_at + timedelta(seconds=60)
                if errors
                else self._next_scheduled_run(completed_at)
            ),
            "message": (
                "Синхронизация завершена не для всех организаций. Повторяем автоматически."
                if errors
                else "SmartUp подключён. Данные актуальны."
            ),
        }))
        try:
            logger.info(
                "BUSINESS_ANALYSIS_TRIGGERED source=smartup_sync organizations=%s raw_records=%s canonical_updated=%s",
                result.organizations_count,
                result.counters.get("records", 0),
                True,
            )
            asyncio.run(AutoBusinessAnalyticsService(self.store).run_if_due(after_sync=True))
        except Exception as exc:  # noqa: BLE001
            # Data sync remains successful even if optional AI refresh fails.
            logger.exception("BUSINESS_ANALYSIS_ERROR stage=trigger error=%s", str(exc)[:300])
        return not errors

    def _save(self, status: SmartUpLiveSyncStatus) -> None:
        from app.core.data_layer.entities import AppSetting

        self.store.upsert_app_setting(AppSetting(
            setting_key=LIVE_SYNC_STATUS_KEY,
            setting_value=status.model_dump(mode="json"),
            metadata={"scope": "global", "kind": "smartup_live_sync"},
            updated_at=datetime.now(UTC),
        ))
