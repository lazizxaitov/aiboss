"""Canonical V2 seed helpers for AI analytics API tests."""

from __future__ import annotations

from tests.test_analytics_engine import _seed_analytics_store


def seed_ai_analytics_store():
    """Return a canonical analytics-ready store plus two organizations."""

    return _seed_analytics_store()
