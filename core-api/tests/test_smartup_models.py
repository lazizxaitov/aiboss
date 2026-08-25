"""Tests for SmartUp model compatibility helpers."""

from app.integrations.smartup.models import SmartUpMigrationMode


def test_smartup_migration_mode_accepts_legacy_live_sync_value() -> None:
    """Persisted legacy rows using live_sync must still deserialize safely."""

    assert SmartUpMigrationMode("live_sync") is SmartUpMigrationMode.LIVE_SYNC
