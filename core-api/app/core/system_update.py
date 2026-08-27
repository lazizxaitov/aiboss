"""Owner-controlled GitHub update workflow for the local Mac mini deployment."""

from __future__ import annotations

import os
import subprocess
from datetime import UTC, datetime
from threading import Lock, Thread
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from app.core.data_layer.contracts import CoreDataStore
from app.core.data_layer.entities import AppSetting

REPOSITORY_ROOT = os.path.expanduser("~/Projects/aiboss")
BACKEND_DIRECTORY = os.path.join(REPOSITORY_ROOT, "core-api")
FRONTEND_DIRECTORY = os.path.join(REPOSITORY_ROOT, "ai-business-os-front")
UPDATE_INDEX_KEY = "system_update:state:v1"
UPDATE_JOB_KEY_PREFIX = "system_update:job:v1:"
UPDATE_TIMEOUT_SECONDS = 30 * 60

UpdateStatus = Literal["running", "success", "failed", "rollback"]
UpdateStage = Literal[
    "checking", "downloading", "backend_dependencies", "frontend_dependencies",
    "frontend_build", "restarting", "completed", "failed", "rollback",
]


class SystemUpdateJob(BaseModel):
    job_id: str = Field(default_factory=lambda: str(uuid4()))
    status: UpdateStatus = "running"
    stage: UpdateStage = "checking"
    message: str = "Проверка обновления"
    current_version: str | None = None
    target_version: str | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SystemUpdateService:
    _lock = Lock()

    def __init__(self, store: CoreDataStore) -> None:
        self.store = store

    def status(self) -> dict[str, Any]:
        self._run_git(["fetch", "origin", "main"], REPOSITORY_ROOT)
        current = self._git_version("HEAD")
        latest = self._git_version("origin/main")
        state = self._state()
        return {
            "current_version": current,
            "latest_version": latest,
            "update_available": bool(current and latest and current != latest),
            "status": "ready",
            "last_successful_update_at": state.get("last_successful_update_at"),
        }

    def start_install(self) -> SystemUpdateJob:
        with self._lock:
            active = self._active_job()
            if active is not None:
                return active
            job = SystemUpdateJob()
            self._save_job(job)
            Thread(target=self._run_install, args=(job.job_id,), name="aiboss-system-update", daemon=True).start()
            return job

    def get_job(self, job_id: str) -> SystemUpdateJob | None:
        setting = self.store.get_app_setting(f"{UPDATE_JOB_KEY_PREFIX}{job_id}")
        if setting is None or not isinstance(setting.setting_value, dict):
            return None
        try:
            return SystemUpdateJob.model_validate(setting.setting_value)
        except Exception:  # noqa: BLE001
            return None

    def _run_install(self, job_id: str) -> None:
        job = self.get_job(job_id)
        if job is None:
            return
        rollback_commit: str | None = None
        try:
            rollback_commit = self._git_version("HEAD", short=False)
            job.current_version = self._short(rollback_commit)
            self._update(job, stage="downloading", message="Загрузка последней версии из GitHub")
            self._run_git(["fetch", "origin", "main"], REPOSITORY_ROOT)
            target_commit = self._git_version("origin/main", short=False)
            job.target_version = self._short(target_commit)
            self._run_git(["reset", "--hard", "origin/main"], REPOSITORY_ROOT)
            self._update(job, stage="backend_dependencies", message="Обновление зависимостей backend")
            self._run_command(["uv", "sync"], BACKEND_DIRECTORY)
            self._update(job, stage="frontend_dependencies", message="Обновление зависимостей frontend")
            self._run_command(["npm", "ci"], FRONTEND_DIRECTORY)
            self._update(job, stage="frontend_build", message="Сборка frontend")
            self._run_command(["npm", "run", "build"], FRONTEND_DIRECTORY)
            self._update(job, stage="restarting", message="Перезапуск рабочих сервисов")
            job.status = "success"
            job.stage = "completed"
            job.message = "Обновление установлено"
            self._update(job)
            self._save_state({"last_successful_update_at": datetime.now(UTC).isoformat(), "version": job.target_version})
            self._restart_services()
        except Exception as exc:  # noqa: BLE001
            job.error = str(exc)
            self._update(job, stage="rollback", message="Ошибка обновления. Выполняется откат")
            if rollback_commit is None:
                job.status = "failed"
                job.stage = "failed"
                job.message = "Обновление не установлено"
                self._update(job)
                return
            try:
                self._run_git(["reset", "--hard", rollback_commit], REPOSITORY_ROOT)
                self._run_command(["uv", "sync"], BACKEND_DIRECTORY)
                self._run_command(["npm", "ci"], FRONTEND_DIRECTORY)
                self._run_command(["npm", "run", "build"], FRONTEND_DIRECTORY)
                job.status = "rollback"
                job.stage = "rollback"
                job.message = "Обновление отменено, восстановлена предыдущая версия"
                self._update(job)
                self._restart_services()
            except Exception as rollback_error:  # noqa: BLE001
                job.status = "failed"
                job.stage = "failed"
                job.message = "Не удалось восстановить предыдущую версию"
                job.error = f"{job.error}; rollback: {rollback_error}"
                self._update(job)

    def _active_job(self) -> SystemUpdateJob | None:
        job_id = self._state().get("active_job_id")
        if not isinstance(job_id, str):
            return None
        job = self.get_job(job_id)
        return job if job is not None and job.status == "running" else None

    def _update(self, job: SystemUpdateJob, *, stage: UpdateStage | None = None, message: str | None = None) -> None:
        if stage is not None:
            job.stage = stage
        if message is not None:
            job.message = message
        job.updated_at = datetime.now(UTC)
        self._save_job(job)
        if job.status != "running":
            state = self._state()
            if state.get("active_job_id") == job.job_id:
                self._save_state({"active_job_id": None, "last_successful_update_at": state.get("last_successful_update_at")})

    def _save_job(self, job: SystemUpdateJob) -> None:
        self.store.upsert_app_setting(AppSetting(
            setting_key=f"{UPDATE_JOB_KEY_PREFIX}{job.job_id}",
            setting_value=job.model_dump(mode="json"),
            metadata={"scope": "system", "kind": "system_update_job", "job_id": job.job_id},
            created_at=job.created_at,
            updated_at=job.updated_at,
        ))
        state = self._state()
        if job.status == "running":
            self._save_state({"active_job_id": job.job_id, "last_successful_update_at": state.get("last_successful_update_at")})

    def _state(self) -> dict[str, Any]:
        setting = self.store.get_app_setting(UPDATE_INDEX_KEY)
        return setting.setting_value if setting and isinstance(setting.setting_value, dict) else {}

    def _save_state(self, value: dict[str, Any]) -> None:
        now = datetime.now(UTC)
        self.store.upsert_app_setting(AppSetting(
            setting_key=UPDATE_INDEX_KEY,
            setting_value=value,
            metadata={"scope": "system", "kind": "system_update_state"},
            created_at=now,
            updated_at=now,
        ))

    @staticmethod
    def _run_git(args: list[str], cwd: str) -> str:
        return SystemUpdateService._run_command(["git", *args], cwd)

    @staticmethod
    def _run_command(args: list[str], cwd: str) -> str:
        result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=UPDATE_TIMEOUT_SECONDS, check=False)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "команда завершилась с ошибкой").strip()
            raise RuntimeError(f"{' '.join(args)}: {detail[-1200:]}")
        return result.stdout.strip()

    @classmethod
    def _git_version(cls, ref: str, *, short: bool = True) -> str:
        return cls._run_git(["rev-parse", "--short" if short else "--verify", ref], REPOSITORY_ROOT)

    @staticmethod
    def _short(commit: str) -> str:
        return commit[:7]

    @staticmethod
    def _restart_services() -> None:
        uid = str(os.getuid())
        for label in ("com.aiboss.frontend", "com.aiboss.backend"):
            subprocess.run(["launchctl", "kickstart", "-k", f"gui/{uid}/{label}"], capture_output=True, text=True, timeout=30, check=True)
