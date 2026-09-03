"""Best-effort in-memory rate limiting for the handful of endpoints that
check a secret (owner password, or the 4-digit unlock PIN) without an
existing, already-verified session backing the request: /auth/login,
/auth/unlock, /device/pair and /telegram/webapp/link. Before this, none of
them had any limit on failed attempts — a 4-digit PIN in particular is only
10,000 combinations, trivially brute-forceable with no lockout at all.

This is intentionally simple: a single-process, in-memory sliding window per
key. It is not meant to withstand a distributed attack, but this app runs as
a single local process for one owner, so that's the right amount of defense
for the actual threat model here.
"""

from __future__ import annotations

import time
from collections import deque
from threading import Lock

from fastapi import HTTPException, Request, status

_WINDOW_SECONDS = 300.0
_MAX_FAILURES = 8
_MAX_TRACKED_KEYS = 500

_lock = Lock()
_failures: dict[str, deque[float]] = {}


def client_key(prefix: str, request: Request) -> str:
    """Build a rate-limit key from a fixed prefix (identifying which
    endpoint) and the caller's IP — the best identity we have for an
    unauthenticated request."""

    host = request.client.host if request.client else "unknown"
    return f"{prefix}:{host}"


def enforce_rate_limit(key: str) -> None:
    """Raise 429 if `key` already hit the failure threshold within the
    current window. Call this before checking the secret."""

    now = time.monotonic()
    with _lock:
        attempts = _failures.get(key)
        if attempts is None:
            return
        while attempts and now - attempts[0] > _WINDOW_SECONDS:
            attempts.popleft()
        if len(attempts) >= _MAX_FAILURES:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Слишком много неудачных попыток. Повторите позже.",
            )


def record_failure(key: str) -> None:
    now = time.monotonic()
    with _lock:
        attempts = _failures.setdefault(key, deque())
        attempts.append(now)
        while attempts and now - attempts[0] > _WINDOW_SECONDS:
            attempts.popleft()
        if len(_failures) > _MAX_TRACKED_KEYS:
            stale = [k for k, v in _failures.items() if not v or now - v[-1] > _WINDOW_SECONDS]
            for stale_key in stale[: len(_failures) - _MAX_TRACKED_KEYS + 50]:
                _failures.pop(stale_key, None)


def record_success(key: str) -> None:
    with _lock:
        _failures.pop(key, None)
