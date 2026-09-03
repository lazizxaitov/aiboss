"""Owner-controlled GitHub update workflow for the local Mac mini deployment."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import time
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
INSTALLED_APP = "/Applications/AI Business OS.app"
APP_BACKUP = "/Applications/.AI Business OS.backup.app"
BUILT_APP = os.path.join(FRONTEND_DIRECTORY, "src-tauri", "target", "release", "bundle", "macos", "AI Business OS.app")
UPDATE_INDEX_KEY = "system_update:state:v1"
UPDATE_JOB_KEY_PREFIX = "system_update:job:v1:"
UPDATE_TIMEOUT_SECONDS = 30 * 60

UpdateStatus = Literal["running", "success", "failed", "rollback"]
UpdateStage = Literal[
    "checking", "downloading", "backend_dependencies", "frontend_dependencies",
    "app_build", "install", "restarting", "completed", "failed", "rollback",
]


class SystemUpdateJob(BaseModel):
    job_id: str = Field(default_factory=lambda: str(uuid4()))
    status: UpdateStatus = "running"
    stage: UpdateStage = "checking"
    message: str = "Проверка обновления"
    current_version: str | None = None
    target_version: str | None = None
    previous_commit: str | None = None
    target_commit: str | None = None
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

    def get_latest_job(self) -> SystemUpdateJob | None:
        """The most recent update attempt, whatever it finished as (success,
        failed, or rolled back) — so the Settings page can tell the owner
        what happened even after the backend restart an update itself
        triggers wipes any in-memory/React state the page was showing."""

        job_id = self._state().get("last_job_id")
        if not isinstance(job_id, str):
            return None
        return self.get_job(job_id)

    def _run_install(self, job_id: str) -> None:
        job = self.get_job(job_id)
        if job is None:
            return
        rollback_commit: str | None = None
        app_backup: str | None = None
        try:
            self._assert_clean_worktree()
            rollback_commit = self._git_version("HEAD", short=False)
            job.previous_commit = rollback_commit
            job.current_version = self._short(rollback_commit)
            self._update(job, stage="downloading", message="Получение последней версии из GitHub")
            self._run_git(["fetch", "origin", "main"], REPOSITORY_ROOT)
            target_commit = self._git_version("origin/main", short=False)
            job.target_commit = target_commit
            job.target_version = self._short(target_commit)
            self._run_git(["reset", "--hard", "origin/main"], REPOSITORY_ROOT)
            current_commit = self._git_version("HEAD", short=False)
            origin_commit = self._git_version("origin/main", short=False)
            if current_commit != target_commit or current_commit != origin_commit:
                raise RuntimeError(
                    "После обновления локальный HEAD не совпадает с origin/main: "
                    f"HEAD={self._short(current_commit)}, "
                    f"origin/main={self._short(origin_commit)}, "
                    f"target={self._short(target_commit)}"
                )
            job.current_version = self._short(current_commit)
            self._update(job, stage="downloading", message="Локальная ветка синхронизирована с origin/main")
            self._update(job, stage="backend_dependencies", message="Обновление зависимостей backend")
            self._run_command(["uv", "sync"], BACKEND_DIRECTORY)
            self._update(job, stage="frontend_dependencies", message="Обновление зависимостей frontend")
            self._run_command(["npm", "ci"], FRONTEND_DIRECTORY)
            self._update(job, stage="app_build", message="Сборка приложения")
            self._run_command(["npm", "run", "build"], FRONTEND_DIRECTORY)
            self._run_command(["cargo", "--version"], FRONTEND_DIRECTORY)
            self._run_command(["npm", "run", "tauri:build"], FRONTEND_DIRECTORY)
            if not os.path.isdir(BUILT_APP):
                raise RuntimeError(f"Собранное приложение не найдено: {BUILT_APP}")
            self._update(job, stage="install", message="Установка новой версии приложения")
            app_backup = self._install_app()
            self._update(job, stage="restarting", message="Перезапуск рабочих сервисов")
            job.status = "success"
            job.stage = "completed"
            job.message = "Обновление установлено"
            self._update(job)
            self._save_state({"last_successful_update_at": datetime.now(UTC).isoformat(), "version": job.target_version})
            if app_backup:
                self._remove_app_backup(app_backup)
            self._restart_services(open_app=True)
        except Exception as exc:  # noqa: BLE001
            job.error = str(exc)
            if app_backup:
                try:
                    self._restore_app_backup(app_backup)
                except Exception as restore_error:  # noqa: BLE001
                    job.error = f"{job.error}; восстановление приложения: {restore_error}"
            self._update(job, stage="rollback", message="Ошибка обновления. Выполняется откат")
            if rollback_commit is None:
                job.status = "failed"
                job.stage = "failed"
                job.message = "Обновление не установлено"
                self._update(job)
                return
            try:
                self._run_git(["reset", "--hard", rollback_commit], REPOSITORY_ROOT)
                restored_commit = self._git_version("HEAD", short=False)
                if restored_commit != rollback_commit:
                    raise RuntimeError(
                        "После rollback HEAD не совпадает с предыдущим commit: "
                        f"{self._short(restored_commit)} != {self._short(rollback_commit)}"
                    )
                job.current_version = self._short(restored_commit)
                self._run_command(["uv", "sync"], BACKEND_DIRECTORY)
                self._run_command(["npm", "ci"], FRONTEND_DIRECTORY)
                self._run_command(["npm", "run", "build"], FRONTEND_DIRECTORY)
                self._run_command(["npm", "run", "tauri:build"], FRONTEND_DIRECTORY)
                job.status = "rollback"
                job.stage = "rollback"
                job.message = "Обновление отменено, восстановлена предыдущая версия"
                self._update(job)
                self._restart_services(open_app=False)
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
            # Record this as the latest finished job (success, failed, or
            # rollback alike) so the Settings page can show what happened
            # even after reopening — an update restarts the backend itself,
            # which wipes whatever the page had in memory.
            update: dict[str, Any] = {"last_job_id": job.job_id}
            if self._state().get("active_job_id") == job.job_id:
                update["active_job_id"] = None
            self._save_state(update)

    def _save_job(self, job: SystemUpdateJob) -> None:
        self.store.upsert_app_setting(AppSetting(
            setting_key=f"{UPDATE_JOB_KEY_PREFIX}{job.job_id}",
            setting_value=job.model_dump(mode="json"),
            metadata={"scope": "system", "kind": "system_update_job", "job_id": job.job_id},
            created_at=job.created_at,
            updated_at=job.updated_at,
        ))
        if job.status == "running":
            self._save_state({"active_job_id": job.job_id})

    def _state(self) -> dict[str, Any]:
        setting = self.store.get_app_setting(UPDATE_INDEX_KEY)
        return setting.setting_value if setting and isinstance(setting.setting_value, dict) else {}

    def _save_state(self, value: dict[str, Any]) -> None:
        # Merges rather than replaces — this setting accumulates several
        # independent fields (active_job_id, last_job_id,
        # last_successful_update_at, version) written from different call
        # sites, and a plain replace would silently drop whichever fields
        # the current caller didn't happen to mention.
        now = datetime.now(UTC)
        merged = {**self._state(), **value}
        self.store.upsert_app_setting(AppSetting(
            setting_key=UPDATE_INDEX_KEY,
            setting_value=merged,
            metadata={"scope": "system", "kind": "system_update_state"},
            created_at=now,
            updated_at=now,
        ))

    def _assert_clean_worktree(self) -> None:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
        tracked_changes = [line for line in result.stdout.splitlines() if line and not line.startswith("??")]
        if tracked_changes:
            raise RuntimeError("Обновление остановлено: обнаружены локальные изменения.")

    @staticmethod
    def _run_git(args: list[str], cwd: str) -> str:
        return SystemUpdateService._run_command(["git", *args], cwd)

    @staticmethod
    def _run_command(args: list[str], cwd: str) -> str:
        environment = os.environ.copy()
        cargo_bin = os.path.expanduser("~/.cargo/bin")
        environment["PATH"] = f"{cargo_bin}{os.pathsep}{environment.get('PATH', '')}"
        result = subprocess.run(args, cwd=cwd, env=environment, capture_output=True, text=True, timeout=UPDATE_TIMEOUT_SECONDS, check=False)
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

    def _install_app(self) -> str | None:
        self._stop_running_app()
        if not os.path.isdir(BUILT_APP):
            raise RuntimeError(f"Собранное приложение не найдено: {BUILT_APP}")

        installed_exists = os.path.isdir(INSTALLED_APP)
        if os.path.exists(APP_BACKUP):
            shutil.rmtree(APP_BACKUP)
        if installed_exists:
            shutil.move(INSTALLED_APP, APP_BACKUP)
        try:
            shutil.copytree(BUILT_APP, INSTALLED_APP)
        except Exception:
            if os.path.exists(INSTALLED_APP):
                shutil.rmtree(INSTALLED_APP)
            if installed_exists and os.path.isdir(APP_BACKUP):
                shutil.move(APP_BACKUP, INSTALLED_APP)
            raise RuntimeError("Не удалось установить новую версию приложения") from None
        return APP_BACKUP if installed_exists else None

    @staticmethod
    def _stop_running_app() -> None:
        subprocess.run(
            ["osascript", "-e", 'tell application "AI Business OS" to quit'],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            process = subprocess.run(
                ["pgrep", "-x", "AI Business OS"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if process.returncode != 0:
                return
            time.sleep(0.5)
        raise RuntimeError("Не удалось завершить запущенное AI Business OS.app")

    @staticmethod
    def _remove_app_backup(backup: str) -> None:
        if os.path.isdir(backup):
            shutil.rmtree(backup)

    @staticmethod
    def _restore_app_backup(backup: str) -> None:
        SystemUpdateService._stop_running_app()
        if os.path.isdir(INSTALLED_APP):
            shutil.rmtree(INSTALLED_APP)
        if os.path.isdir(backup):
            shutil.move(backup, INSTALLED_APP)

    @staticmethod
    def _restart_services(*, open_app: bool) -> None:
        uid = str(os.getuid())
        frontend_label = f"gui/{uid}/com.aiboss.frontend"
        backend_label = f"gui/{uid}/com.aiboss.backend"
        commands = [f"launchctl kickstart -k {frontend_label}", "sleep 2"]
        if open_app:
            # Open the shell as soon as Next is started; its bundled splash waits for backend health.
            commands.extend([f"open {shlex.quote(INSTALLED_APP)}", "sleep 1"])
        commands.append(f"launchctl kickstart -k {backend_label}")
        subprocess.Popen(
            ["/bin/sh", "-c", "; ".join(commands)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
