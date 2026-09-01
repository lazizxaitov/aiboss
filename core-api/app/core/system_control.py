"""Fixed local service controls used by the owner system menu."""

from __future__ import annotations

import os
import subprocess
from threading import Thread

BACKEND_LABEL = "com.aiboss.backend"
FRONTEND_LABEL = "com.aiboss.frontend"


class SystemControlService:
    """Restart or stop only the two known AI Business OS launch agents."""

    @staticmethod
    def restart() -> None:
        Thread(target=SystemControlService._restart_worker, name="aiboss-system-restart", daemon=True).start()

    @staticmethod
    def shutdown() -> None:
        Thread(target=SystemControlService._shutdown_worker, name="aiboss-system-shutdown", daemon=True).start()

    @staticmethod
    def _restart_worker() -> None:
        uid = str(os.getuid())
        for label in (FRONTEND_LABEL, BACKEND_LABEL):
            subprocess.run(
                ["/bin/launchctl", "kickstart", "-k", f"gui/{uid}/{label}"],
                capture_output=True,
                check=False,
                timeout=30,
            )
        subprocess.run(["/usr/bin/open", "/Applications/AI Business OS.app"], capture_output=True, check=False, timeout=30)

    @staticmethod
    def _shutdown_worker() -> None:
        uid = str(os.getuid())
        # Bootout prevents KeepAlive from immediately spawning the services.
        # Tauri bootstraps the same fixed plists on the next application launch.
        for label in (FRONTEND_LABEL, BACKEND_LABEL):
            subprocess.run(
                ["/bin/launchctl", "bootout", f"gui/{uid}/{label}"],
                capture_output=True,
                check=False,
                timeout=30,
            )
