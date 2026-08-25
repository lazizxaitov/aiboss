"""Tests for the SmartUp migration CLI."""

import json
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

import app.cli as cli
from app.core.data_layer.migrations.smartup import (
    SmartUpBusinessRow,
    SmartUpContactRow,
    SmartUpExportBundle,
)


def test_cli_dry_run_returns_zero(capsys) -> None:
    exit_code = cli.main(
        [
            "history",
            "--business-id",
            "11111111-1111-1111-1111-111111111111",
            "--business-name",
            "Example Business",
            "--history-start",
            "2020-01-01",
            "--dry-run",
        ],
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "SmartUp history dry-run" in captured.out


def test_run_smartup_history_migration_can_be_monkeypatched(monkeypatch) -> None:
    called = {}

    class FakeRunner:
        def __init__(self, *, client, target, business_id, business_name):  # noqa: ANN001
            called["business_id"] = business_id
            called["business_name"] = business_name
            called["target_type"] = type(target).__name__
            called["client_type"] = type(client).__name__

        def run(self, *, history_start, history_end, chunk_days):  # noqa: ANN001
            called["history_start"] = history_start
            called["history_end"] = history_end
            called["chunk_days"] = chunk_days
            return {"batches": 2, "records": 10, "errors": 0}

    monkeypatch.setattr(cli, "SmartUpHistoricalImportRunner", FakeRunner)

    result = cli.run_smartup_history_migration(
        cli.SmartUpHistoryOptions(
            business_id=UUID("11111111-1111-1111-1111-111111111111"),
            business_name="Example Business",
            history_start=datetime(2020, 1, 1, tzinfo=UTC),
            history_end=datetime(2020, 12, 31, tzinfo=UTC),
            chunk_days=30,
            base_url="https://api.greenwhite.uz",
            username="user",
            password="pass",
            project_code="trade",
            filial_id="86401",
            timeout_seconds=15.0,
            storage_backend="memory",
            postgres_dsn=None,
            dry_run=False,
        ),
    )

    assert result == {"batches": 2, "records": 10, "errors": 0}
    assert called["business_id"] == UUID("11111111-1111-1111-1111-111111111111")
    assert called["business_name"] == "Example Business"
    assert called["target_type"] == "InMemoryCoreDataLayer"
    assert called["client_type"] == "SmartUpApiClient"
    assert called["chunk_days"] == 7


def test_cli_postgres_backend_uses_postgres_store(monkeypatch) -> None:
    called = {}

    class FakePostgresStore:
        def ensure_schema(self) -> None:
            called["ensure_schema"] = True

    def fake_from_dsn(dsn: str):  # noqa: ANN001
        called["dsn"] = dsn
        return FakePostgresStore()

    monkeypatch.setattr(cli.PostgresCoreStore, "from_dsn", staticmethod(fake_from_dsn))
    monkeypatch.setattr(
        cli,
        "SmartUpHistoricalImportRunner",
        lambda **kwargs: type(
            "Runner",
            (),
            {"run": lambda self, **run_kwargs: {"batches": 1, "records": 1, "errors": 0}},
        )(),
    )

    result = cli.run_smartup_history_migration(
        cli.SmartUpHistoryOptions(
            business_id=UUID("11111111-1111-1111-1111-111111111111"),
            business_name="Example Business",
            history_start=datetime(2020, 1, 1, tzinfo=UTC),
            history_end=None,
            chunk_days=7,
            base_url="https://api.greenwhite.uz",
            username=None,
            password=None,
            project_code=None,
            filial_id=None,
            timeout_seconds=None,
            storage_backend="postgres",
            postgres_dsn="postgresql://user:pass@localhost:5432/core",
            dry_run=False,
        ),
    )

    assert result == {"batches": 1, "records": 1, "errors": 0}
    assert called["dsn"] == "postgresql://user:pass@localhost:5432/core"
    assert called["ensure_schema"] is True


def test_cli_uses_memory_backend_from_settings(monkeypatch) -> None:
    called = {}

    class FakeMemoryStore:
        def __init__(self) -> None:
            called["constructed"] = True

    monkeypatch.setattr(
        cli,
        "get_settings",
        lambda: SimpleNamespace(
            storage_backend="memory",
            postgres_dsn=None,
        ),
    )
    monkeypatch.setattr(cli, "InMemoryCoreDataLayer", lambda: FakeMemoryStore())
    monkeypatch.setattr(
        cli,
        "SmartUpHistoricalImportRunner",
        lambda **kwargs: type(
            "Runner",
            (),
            {"run": lambda self, **run_kwargs: {"batches": 1, "records": 1, "errors": 0}},
        )(),
    )

    result = cli.run_smartup_history_migration(
        cli.SmartUpHistoryOptions(
            business_id=UUID("11111111-1111-1111-1111-111111111111"),
            business_name="Example Business",
            history_start=datetime(2020, 1, 1, tzinfo=UTC),
            history_end=None,
            chunk_days=7,
            base_url="https://api.greenwhite.uz",
            username=None,
            password=None,
            project_code=None,
            filial_id=None,
            timeout_seconds=None,
            storage_backend=None,
            postgres_dsn=None,
            dry_run=False,
        ),
    )

    assert result == {"batches": 1, "records": 1, "errors": 0}
    assert called["constructed"] is True


def test_cli_bundle_import_uses_offline_pipeline(tmp_path, capsys) -> None:
    bundle = SmartUpExportBundle(
        businesses=[
            SmartUpBusinessRow(
                external_business_id="su-biz-001",
                name="Acme LLC",
                legal_name="Acme LLC",
            ),
        ],
        contacts=[
            SmartUpContactRow(
                external_customer_id="su-cust-001",
                external_business_id="su-biz-001",
                full_name="John Doe",
                email="john@example.com",
            ),
        ],
    )
    bundle_path = tmp_path / "bundle.json"
    bundle_path.write_text(bundle.model_dump_json())

    exit_code = cli.main(
        [
            "bundle",
            "--input",
            str(bundle_path),
            "--storage",
            "memory",
        ],
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "SmartUp bundle import completed" in captured.out


def test_cli_history_writes_json_report(tmp_path, monkeypatch) -> None:
    report_path = tmp_path / "history-report.json"

    class FakeRunner:
        def __init__(self, *, client, target, business_id, business_name):  # noqa: ANN001
            pass

        def run(self, *, history_start, history_end, chunk_days):  # noqa: ANN001
            return {"batches": 3, "records": 9, "errors": 0}

    monkeypatch.setattr(cli, "SmartUpHistoricalImportRunner", FakeRunner)

    exit_code = cli.main(
        [
            "history",
            "--business-id",
            "11111111-1111-1111-1111-111111111111",
            "--business-name",
            "Example Business",
            "--history-start",
            "2020-01-01",
            "--storage",
            "memory",
            "--report",
            str(report_path),
        ],
    )

    report = json.loads(report_path.read_text())

    assert exit_code == 0
    assert report["run_type"] == "history"
    assert report["status"] == "completed"
    assert report["counters"] == {"batches": 3, "records": 9, "errors": 0}


def test_cli_bundle_writes_json_report(tmp_path, capsys) -> None:
    bundle = SmartUpExportBundle(
        businesses=[
            SmartUpBusinessRow(
                external_business_id="su-biz-001",
                name="Acme LLC",
                legal_name="Acme LLC",
            ),
        ],
        contacts=[
            SmartUpContactRow(
                external_customer_id="su-cust-001",
                external_business_id="su-biz-001",
                full_name="John Doe",
                email="john@example.com",
            ),
        ],
    )
    bundle_path = tmp_path / "bundle.json"
    report_path = tmp_path / "bundle-report.json"
    bundle_path.write_text(bundle.model_dump_json())

    exit_code = cli.main(
        [
            "bundle",
            "--input",
            str(bundle_path),
            "--storage",
            "memory",
            "--report",
            str(report_path),
        ],
    )

    captured = capsys.readouterr()
    report = json.loads(report_path.read_text())

    assert exit_code == 0
    assert "SmartUp bundle import completed" in captured.out
    assert report["status"] == "completed"
    assert report["validation"]["valid"] is True
    assert report["import_report"]["businesses_imported"] == 1
