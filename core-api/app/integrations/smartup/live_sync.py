"""Background SmartUp synchronization using the existing migration pipeline."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, time, timedelta
from threading import Event, Thread
from time import sleep
from typing import Literal
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

LIVE_SYNC_STATUS_KEY = "smartup:live_sync_status:v1"


class SmartUpLiveSyncStatus(BaseModel):
    enabled: bool = True
    status: Literal["idle", "running", "success", "warning", "error"] = "idle"
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
        current = self.status()
        if current.status == "running":
            self._save(current.model_copy(update={
                "status": "idle",
                "next_run_at": self._next_scheduled_run(datetime.now(UTC)),
                "message": "Автосинхронизация ожидает ближайшего запуска по расписанию.",
            }))
        self._thread = Thread(target=self._run_loop, name="smartup-live-sync", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def _run_loop(self) -> None:
        last_trigger: str | None = None
        while not self._stop.wait(30):
            now = datetime.now(UTC)
            local_now = now.astimezone(ZoneInfo("Asia/Tashkent"))
            for scheduled in self._schedule_times():
                if local_now.hour == scheduled.hour and local_now.minute == scheduled.minute:
                    trigger_key = f"{local_now.date()}-{scheduled.isoformat()}"
                    if trigger_key != last_trigger:
                        last_trigger = trigger_key
                        self.run_once(SmartUpMigrationMode.ONE_DAY_CHECK)
                    break

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

    def run_once(self, mode: SmartUpMigrationMode = SmartUpMigrationMode.ONE_DAY_CHECK) -> None:
        if SMARTUP_MIGRATION_LOCK.locked():
            current = self.status()
            self._save(current.model_copy(update={
                "skipped_due_to_running": True,
                "message": "Синхронизация пропущена: предыдущий запуск ещё выполняется.",
                "next_run_at": self._next_scheduled_run(datetime.now(UTC)),
            }))
            return

        now = datetime.now(UTC)
        window_days = 7 if mode == SmartUpMigrationMode.WEEKLY_RECONCILIATION else 2
        self._save(SmartUpLiveSyncStatus(
            enabled=True,
            status="running",
            last_started_at=now,
            next_run_at=self._next_scheduled_run(now),
            last_mode=mode,
            message="Синхронизация SmartUp выполняется.",
        ))
        payload = SmartUpAuthPayload(
            migration_mode=mode,
            history_start=now - timedelta(days=window_days),
            history_end=now,
        )
        job = SmartUpAccountService(self.store).start_migration_job(payload)
        while job.status in {"pending", "running"} and not self._stop.is_set():
            sleep(0.5)
            job = SmartUpAccountService(self.store).get_migration_job(job.job_id) or job

        if job.status != "completed" or job.result is None:
            self._save(self.status().model_copy(update={
                "status": "error",
                "last_completed_at": datetime.now(UTC),
                "errors_count": 1,
                "message": job.error or "Синхронизация SmartUp завершилась с ошибкой.",
            }))
            return

        result = job.result
        errors = len(result.batch_errors) + result.summary.errors
        completed_at = datetime.now(UTC)
        self._save(self.status().model_copy(update={
            "status": "warning" if errors else "success",
            "last_completed_at": completed_at,
            "last_success_at": completed_at if not errors else self.status().last_success_at,
            "organizations_processed": result.organizations_count,
            "raw_records": result.counters.get("records", 0),
            "core_records": result.summary.records,
            "canonical_updated": True,
            "errors_count": errors,
            "skipped_due_to_running": False,
            "message": result.message,
        }))
        if result.counters.get("records", 0) > 0:
            try:
                asyncio.run(AutoBusinessAnalyticsService(self.store).run_if_due(after_sync=True))
            except Exception:  # noqa: BLE001
                # Data sync remains successful even if optional AI refresh fails.
                pass

    def _save(self, status: SmartUpLiveSyncStatus) -> None:
        from app.core.data_layer.entities import AppSetting

        self.store.upsert_app_setting(AppSetting(
            setting_key=LIVE_SYNC_STATUS_KEY,
            setting_value=status.model_dump(mode="json"),
            metadata={"scope": "global", "kind": "smartup_live_sync"},
            updated_at=datetime.now(UTC),
        ))
