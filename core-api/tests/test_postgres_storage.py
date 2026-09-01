"""Tests for the PostgreSQL core storage adapter."""

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from psycopg.types.json import Jsonb

from app.core.data_layer.entities import (
    AppSetting,
    BusinessProfile,
    IngestionBatch,
    IngestionBatchStatus,
)
from app.core.data_layer.models import CoreRecord, CoreRecordKind, DataSourceType, KPIValue
from app.storage.postgres.adapter import PostgresCoreStore


@dataclass
class _FakeCursor:
    statements: list[tuple[str, tuple[object, ...] | None]]
    rows: list[tuple[object, ...]] | None = None
    description: tuple[tuple[str, object, object, object, object, object, object], ...] = ()

    def execute(self, sql: str, params=None):  # noqa: ANN001
        self.statements.append((sql, params))

    def fetchone(self):  # noqa: ANN001
        if not self.rows:
            return None
        return self.rows[0]

    def fetchall(self):  # noqa: ANN001
        return self.rows or []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        return None


@dataclass
class _FakeConnection:
    statements: list[tuple[str, tuple[object, ...] | None]]
    rows: list[tuple[object, ...]] | None = None
    description: tuple[tuple[str, object, object, object, object, object, object], ...] = ()
    committed: bool = False
    rolled_back: bool = False
    closed: bool = False

    def cursor(self):
        return _FakeCursor(self.statements, self.rows, self.description)

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:
        self.closed = True


def test_ai_readonly_sql_uses_postgres_timeout_literal() -> None:
    statements: list[tuple[str, tuple[object, ...] | None]] = []
    connection = _FakeConnection(
        statements,
        rows=[("seller-1", 125)],
        description=(("seller", object, None, None, None, None, None), ("revenue", object, None, None, None, None, None)),
    )
    store = PostgresCoreStore(connection_factory=lambda: connection)

    result = store.execute_ai_readonly_sql(
        "SELECT seller, revenue FROM ai_sales LIMIT 1",
        (),
        statement_timeout_ms=20_000,
    )

    assert result == [{"seller": "seller-1", "revenue": 125}]
    timeout_statement = statements[1]
    assert timeout_statement == ("SET LOCAL statement_timeout = '20000ms'", None)
    assert "$1" not in timeout_statement[0]
    assert connection.closed is True


def test_postgres_store_wraps_json_values_in_jsonb() -> None:
    statements: list[tuple[str, tuple[object, ...] | None]] = []
    connection = _FakeConnection(statements)
    store = PostgresCoreStore(connection_factory=lambda: connection)

    store.register_business(
        BusinessProfile(
            business_id=UUID("11111111-1111-1111-1111-111111111111"),
            name="Acme LLC",
            metadata={"tier": "gold"},
        ),
    )
    store.upsert_ingestion_batch(
        IngestionBatch(
            batch_id=UUID("22222222-2222-2222-2222-222222222222"),
            business_id=UUID("11111111-1111-1111-1111-111111111111"),
            batch_name="SmartUp import",
            status=IngestionBatchStatus.COMPLETED,
            started_at="2026-07-30T00:00:00+00:00",
            stats={"records": 10},
            metadata={"project_code": "trade"},
        ),
    )
    store.ingest_record(
        CoreRecord(
            record_id=UUID("33333333-3333-3333-3333-333333333333"),
            business_id=UUID("11111111-1111-1111-1111-111111111111"),
            source="SmartUp",
            source_type=DataSourceType.IMPORT,
            kind=CoreRecordKind.EVENT,
            payload={"hello": "world"},
            occurred_at="2026-07-30T00:00:00+00:00",
            metadata={"nested": {"value": 1}},
        ),
    )
    store.upsert_kpi(
        KPIValue(
            business_id=UUID("11111111-1111-1111-1111-111111111111"),
            metric_key="revenue",
            value=Decimal("123.45"),
            unit="USD",
            metadata={"source": "SmartUp"},
        ),
    )

    assert any(isinstance(param, Jsonb) for _, params in statements for param in (params or ()))
    assert connection.committed is True
    assert connection.rolled_back is False


def test_postgres_store_reads_tuple_rows_into_models() -> None:
    statements: list[tuple[str, tuple[object, ...] | None]] = []
    connection = _FakeConnection(
        statements,
        rows=[
            (
                UUID("11111111-1111-1111-1111-111111111111"),
                UUID("22222222-2222-2222-2222-222222222222"),
                "SmartUp",
                "erp",
                "smartup",
                {},
            ),
        ],
        description=(
            ("source_system_id", None, None, None, None, None, None),
            ("business_id", None, None, None, None, None, None),
            ("name", None, None, None, None, None, None),
            ("source_type", None, None, None, None, None, None),
            ("external_ref", None, None, None, None, None, None),
            ("metadata", None, None, None, None, None, None),
        ),
    )
    store = PostgresCoreStore(connection_factory=lambda: connection)

    source_system = store.get_source_system(UUID("11111111-1111-1111-1111-111111111111"))

    assert source_system is not None
    assert source_system.name == "SmartUp"
    assert source_system.business_id == UUID("22222222-2222-2222-2222-222222222222")
    assert connection.closed is True


def test_postgres_store_upsert_app_setting_targets_setting_key_conflict() -> None:
    statements: list[tuple[str, tuple[object, ...] | None]] = []
    connection = _FakeConnection(statements)
    store = PostgresCoreStore(connection_factory=lambda: connection)

    store.upsert_app_setting(
        AppSetting(
            setting_key="smartup:organization_credentials:org-1",
            setting_value={"username": "demo", "password": "secret-1"},
            metadata={"scope": "smartup_organization_credentials"},
        ),
    )
    store.upsert_app_setting(
        AppSetting(
            setting_key="smartup:organization_credentials:org-1",
            setting_value={"username": "demo", "password": "secret-2"},
            metadata={"scope": "smartup_organization_credentials"},
        ),
    )

    joined_sql = "\n".join(sql for sql, _ in statements)
    assert joined_sql.count("ON CONFLICT (setting_key) DO UPDATE SET") == 2
    assert "setting_value = EXCLUDED.setting_value" in joined_sql
    assert "metadata = EXCLUDED.metadata" in joined_sql
    assert "updated_at = NOW()" in joined_sql


def test_postgres_store_ensure_schema_backfills_migration_batch_columns() -> None:
    statements: list[tuple[str, tuple[object, ...] | None]] = []
    connection = _FakeConnection(statements)
    store = PostgresCoreStore(connection_factory=lambda: connection)

    store.ensure_schema()

    joined_sql = "\n".join(sql for sql, _ in statements)
    assert "ALTER TABLE IF EXISTS migration_batches" in joined_sql
    assert "ADD COLUMN IF NOT EXISTS filial_id text" in joined_sql
    assert "ADD COLUMN IF NOT EXISTS endpoint text" in joined_sql
    assert "ADD COLUMN IF NOT EXISTS request_payload jsonb" in joined_sql
