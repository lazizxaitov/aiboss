"""Command-line interface for SmartUp migrations."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import UTC, datetime, time
from pathlib import Path
from uuid import UUID

from app.core.config import get_settings
from app.core.data_layer.migrations import (
    SmartUpExportBundle,
    SmartUpHistoryMigrationReport,
    SmartUpOfflineMigrationService,
)
from app.core.data_layer.service import InMemoryCoreDataLayer
from app.integrations.smartup.client import SmartUpApiClient
from app.integrations.smartup.connector import MAX_SMARTUP_HISTORY_WINDOW_DAYS
from app.integrations.smartup.history import SmartUpHistoricalImportRunner
from app.integrations.smartup.settings import SmartUpSettings
from app.storage.postgres import PostgresCoreStore


@dataclass(frozen=True, slots=True)
class SmartUpHistoryOptions:
    """Normalized CLI options for a SmartUp history migration."""

    business_id: UUID
    business_name: str
    history_start: datetime
    history_end: datetime | None
    chunk_days: int
    base_url: str | None
    username: str | None
    password: str | None
    project_code: str | None
    filial_id: str | None
    timeout_seconds: float | None
    storage_backend: str | None = None
    postgres_dsn: str | None = None
    dry_run: bool = False
    report_path: Path | None = None


@dataclass(frozen=True, slots=True)
class SmartUpBundleOptions:
    """Normalized CLI options for an offline SmartUp bundle migration."""

    input_path: Path
    storage_backend: str | None = None
    postgres_dsn: str | None = None
    dry_run: bool = False
    report_path: Path | None = None


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""

    parser = argparse.ArgumentParser(prog="smartup-migrate")
    subparsers = parser.add_subparsers(dest="command", required=True)

    history = subparsers.add_parser(
        "history",
        help="Run a full-history SmartUp migration into the core data layer.",
    )
    history.add_argument("--business-id", required=True, help="Target business UUID.")
    history.add_argument("--business-name", required=True, help="Target business name.")
    history.add_argument(
        "--history-start",
        required=True,
        help="Start of the historical window in YYYY-MM-DD or ISO-8601 format.",
    )
    history.add_argument(
        "--history-end",
        default=None,
        help="Optional end of the historical window in YYYY-MM-DD or ISO-8601 format.",
    )
    history.add_argument("--chunk-days", type=int, default=7, help="Days per request window.")
    history.add_argument("--base-url", default=None, help="SmartUp API base URL.")
    history.add_argument("--username", default=None, help="SmartUp username.")
    history.add_argument("--password", default=None, help="SmartUp password.")
    history.add_argument("--project-code", default=None, help="SmartUp project_code header.")
    history.add_argument("--filial-id", default=None, help="SmartUp filial_id header.")
    history.add_argument(
        "--timeout-seconds",
        type=float,
        default=None,
        help="HTTP timeout for SmartUp requests.",
    )
    history.add_argument(
        "--storage",
        choices=("memory", "postgres"),
        default=None,
        help="Target storage backend. Defaults to STORAGE_BACKEND from .env.",
    )
    history.add_argument(
        "--postgres-dsn",
        default=None,
        help="PostgreSQL DSN used when --storage postgres is selected.",
    )
    history.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the migration summary without executing requests.",
    )
    history.add_argument(
        "--report",
        default=None,
        help="Optional path to write a JSON report for the migration run.",
    )

    bundle = subparsers.add_parser(
        "bundle",
        help="Import a SmartUp export bundle from JSON without a live account.",
    )
    bundle.add_argument(
        "--input",
        required=True,
        help="Path to a SmartUp export bundle JSON file.",
    )
    bundle.add_argument(
        "--storage",
        choices=("memory", "postgres"),
        default=None,
        help="Target storage backend. Defaults to STORAGE_BACKEND from .env.",
    )
    bundle.add_argument(
        "--postgres-dsn",
        default=None,
        help="PostgreSQL DSN used when --storage postgres is selected.",
    )
    bundle.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate the bundle without importing it.",
    )
    bundle.add_argument(
        "--report",
        default=None,
        help="Optional path to write a JSON report for the migration run.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "history":
        options = _parse_history_options(args)
        if options.dry_run:
            _print_history_dry_run(options)
            return 0

        counters = run_smartup_history_migration(options)
        if options.report_path is not None:
            report = SmartUpHistoryMigrationReport(
                business_id=options.business_id,
                business_name=options.business_name,
                history_start=options.history_start,
                history_end=options.history_end,
                chunk_days=options.chunk_days,
                storage_backend=options.storage_backend or get_settings().storage_backend,
                counters=counters,
                warnings=[],
            )
            _write_json_report(options.report_path, report.model_dump(mode="python"))
        print(
            "SmartUp history migration completed: "
            f"batches={counters['batches']} "
            f"records={counters['records']} "
            f"errors={counters['errors']}",
        )
        return 0 if counters["errors"] == 0 else 1

    if args.command == "bundle":
        options = _parse_bundle_options(args)
        if options.dry_run:
            _print_bundle_dry_run(options)
            return 0

        report = run_smartup_bundle_migration(options)
        if options.report_path is not None:
            _write_json_report(options.report_path, report)
        validation = report["validation"]
        imported = report["import_report"]
        print(
            "SmartUp bundle import completed: "
            f"status={report['status']} "
            f"businesses={imported['businesses_imported']} "
            f"contacts={imported['contacts_imported']} "
            f"sales={imported['sales_imported']} "
            f"marketing={imported['marketing_imported']} "
            f"finance={imported['finance_imported']} "
            f"validation_errors={len(validation['errors'])}",
        )
        return 0 if validation["valid"] else 1

    parser.error(f"Unknown command: {args.command}")
    return 2


def run_smartup_history_migration(options: SmartUpHistoryOptions) -> dict[str, int]:
    """Execute the SmartUp full-history migration."""

    settings = _build_smartup_settings(options)
    client = SmartUpApiClient(settings=settings)
    target = _build_storage_target(options.storage_backend, options.postgres_dsn)
    runner = SmartUpHistoricalImportRunner(
        client=client,
        target=target,
        business_id=options.business_id,
        business_name=options.business_name,
    )
    chunk_days = max(1, min(options.chunk_days, MAX_SMARTUP_HISTORY_WINDOW_DAYS))
    return runner.run(
        history_start=options.history_start,
        history_end=options.history_end,
        chunk_days=chunk_days,
    )


def run_smartup_bundle_migration(options: SmartUpBundleOptions) -> dict[str, object]:
    """Import a SmartUp export bundle into the selected storage backend."""

    bundle = SmartUpExportBundle.model_validate_json(options.input_path.read_text())
    target = _build_storage_target(options.storage_backend, options.postgres_dsn)
    report = SmartUpOfflineMigrationService(target=target).run(bundle)
    return {
        "status": report.status,
        "validation": report.validation.model_dump(mode="python"),
        "import_report": report.import_report.model_dump(mode="python"),
    }


def _parse_history_options(args: argparse.Namespace) -> SmartUpHistoryOptions:
    app_settings = get_settings()
    return SmartUpHistoryOptions(
        business_id=UUID(args.business_id),
        business_name=args.business_name,
        history_start=_parse_datetime_arg(args.history_start, start_of_day=True),
        history_end=_parse_datetime_arg(args.history_end) if args.history_end else None,
        chunk_days=args.chunk_days,
        base_url=args.base_url,
        username=args.username,
        password=args.password,
        project_code=args.project_code,
        filial_id=args.filial_id,
        timeout_seconds=args.timeout_seconds,
        storage_backend=args.storage or app_settings.storage_backend,
        postgres_dsn=args.postgres_dsn,
        dry_run=args.dry_run,
        report_path=Path(args.report) if args.report else None,
    )


def _parse_bundle_options(args: argparse.Namespace) -> SmartUpBundleOptions:
    app_settings = get_settings()
    return SmartUpBundleOptions(
        input_path=Path(args.input),
        storage_backend=args.storage or app_settings.storage_backend,
        postgres_dsn=args.postgres_dsn,
        dry_run=args.dry_run,
        report_path=Path(args.report) if args.report else None,
    )


def _build_smartup_settings(options: SmartUpHistoryOptions) -> SmartUpSettings:
    defaults = SmartUpSettings()
    data = defaults.model_dump()
    overrides = {
        "base_url": options.base_url,
        "username": options.username,
        "password": options.password,
        "project_code": options.project_code,
        "filial_id": options.filial_id,
        "timeout_seconds": options.timeout_seconds,
    }
    data.update({key: value for key, value in overrides.items() if value is not None})
    return SmartUpSettings(**data)


def _build_storage_target(storage_backend: str | None, postgres_dsn: str | None):
    app_settings = get_settings()
    backend = storage_backend or app_settings.storage_backend

    if backend == "memory":
        return InMemoryCoreDataLayer()

    if backend == "postgres":
        dsn = postgres_dsn or app_settings.postgres_dsn
        if not dsn:
            msg = "--postgres-dsn is required when --storage postgres is selected"
            raise ValueError(msg)
        store = PostgresCoreStore.from_dsn(dsn)
        store.ensure_schema()
        return store

    msg = f"Unsupported storage backend: {backend}"
    raise ValueError(msg)


def _parse_datetime_arg(raw_value: str, *, start_of_day: bool = False) -> datetime:
    try:
        parsed = datetime.fromisoformat(raw_value)
    except ValueError:
        parsed = datetime.strptime(raw_value, "%Y-%m-%d")

    if parsed.tzinfo is None:
        if start_of_day:
            parsed = datetime.combine(parsed.date(), time.min, tzinfo=UTC)
        else:
            parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _print_history_dry_run(options: SmartUpHistoryOptions) -> None:
    print(
        "SmartUp history dry-run: "
        f"business_id={options.business_id} business_name={options.business_name} "
        f"history_start={options.history_start.isoformat()} "
        f"history_end={options.history_end.isoformat() if options.history_end else 'now'} "
        f"chunk_days={options.chunk_days}",
    )


def _print_bundle_dry_run(options: SmartUpBundleOptions) -> None:
    bundle = SmartUpExportBundle.model_validate_json(options.input_path.read_text())
    print(
        "SmartUp bundle dry-run: "
        f"input={options.input_path} "
        f"businesses={len(bundle.businesses)} "
        f"contacts={len(bundle.contacts)} "
        f"sales={len(bundle.sales)} "
        f"marketing={len(bundle.marketing)} "
        f"finance={len(bundle.finance)}",
    )


def _write_json_report(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    raise SystemExit(main())
