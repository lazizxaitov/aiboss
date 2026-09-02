"""Safe, non-shell system capability implementations."""

from __future__ import annotations

import platform

from app.core.system_control import BACKEND_LABEL, FRONTEND_LABEL


def inspect_system() -> dict[str, object]:
    """Return allowlisted metadata without probing or executing local commands."""

    return {
        "status": "available",
        "platform": platform.system(),
        "known_services": [BACKEND_LABEL, FRONTEND_LABEL],
        "actions": ["lock", "restart", "shutdown"],
        "confirmation_required_for": ["restart", "shutdown"],
    }
