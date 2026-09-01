"""SQLite storage adapter for the core data layer."""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Protocol
from uuid import UUID

from app.core.ai_readonly_sql import AI_ANALYTICAL_VIEW_SQLITE_DDL
from app.integrations.meta.schema import META_SQLITE_DDL
from app.core.data_layer.schema import CORE_DATA_LAYER_SCHEMA_V2
from app.storage.postgres.adapter import PostgresCoreStore, Row
from app.storage.sqlite.ddl import render_core_data_layer_ddl


class SQLiteCursor(Protocol):
    """DB-API compatible cursor that returns mapping rows."""

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> Any:
        """Execute a SQL statement."""

    def fetchone(self) -> Row | None:
        """Return one row as a mapping."""

    def fetchall(self) -> list[Row]:
        """Return all rows as mappings."""

    def __enter__(self) -> SQLiteCursor:
        """Enter cursor context."""

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        """Exit cursor context."""


class SQLiteConnection(Protocol):
    """DB-API compatible connection."""

    def cursor(self) -> SQLiteCursor:
        """Open a cursor."""

    def commit(self) -> None:
        """Commit the current transaction."""

    def rollback(self) -> None:
        """Rollback the current transaction."""


SQLiteConnectionFactory = Callable[[], SQLiteConnection]


@dataclass(slots=True)
class SQLiteConnectionWrapper:
    """SQLite connection with row-mapping behavior."""

    connection: sqlite3.Connection

    def __post_init__(self) -> None:
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")

    def cursor(self) -> SQLiteCursor:
        return SQLiteCursorWrapper(self.connection.cursor())

    def commit(self) -> None:
        self.connection.commit()

    def rollback(self) -> None:
        self.connection.rollback()


@dataclass(slots=True)
class SQLiteCursorWrapper:
    """Cursor wrapper that adapts SQL and row values for SQLite."""

    cursor: sqlite3.Cursor

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> Any:
        adapted_sql = _adapt_sql(sql)
        adapted_params = tuple(_adapt_param(value) for value in params) if params else None
        if adapted_params is None:
            return self.cursor.execute(adapted_sql)
        return self.cursor.execute(adapted_sql, adapted_params)

    def fetchone(self) -> Row | None:
        row = self.cursor.fetchone()
        if row is None:
            return None
        return _decode_row(dict(row))

    def fetchall(self) -> list[Row]:
        return [_decode_row(dict(row)) for row in self.cursor.fetchall()]

    def __enter__(self) -> SQLiteCursor:
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.cursor.close()


class SQLiteCoreStore(PostgresCoreStore):
    """SQLite-backed core data store for tests and local development."""

    @classmethod
    def from_connection(cls, connection: sqlite3.Connection) -> SQLiteCoreStore:
        """Create a store from an existing SQLite connection."""

        wrapper = SQLiteConnectionWrapper(connection)
        return cls(connection_factory=lambda: wrapper)

    @classmethod
    def from_path(cls, path: str) -> SQLiteCoreStore:
        """Create a store from a SQLite database path."""

        connection = sqlite3.connect(path)
        return cls.from_connection(connection)

    def ensure_schema(self) -> None:
        """Create core tables and indexes if they do not exist."""

        self._execute_many(render_core_data_layer_ddl())
        self._execute_many(list(META_SQLITE_DDL))
        self._execute_many(list(AI_ANALYTICAL_VIEW_SQLITE_DDL))

    def execute_ai_readonly_sql(
        self,
        sql: str,
        params: tuple[Any, ...] = (),
        *,
        statement_timeout_ms: int,
    ) -> list[Row]:
        """Run validated research SQL for local/test SQLite stores."""

        return self._fetch_rows(sql, params)

    def describe_ai_views(self) -> dict[str, Any]:
        """Read the exact published analytical view schema from SQLite."""

        from app.core.ai_readonly_sql import ALLOWED_VIEWS

        schema: dict[str, Any] = {}
        connection = self.connection_factory()
        with connection.cursor() as cursor:
            for view in ALLOWED_VIEWS:
                cursor.execute(f"PRAGMA table_info({view})")
                columns = []
                for row in cursor.fetchall():
                    columns.append(
                        {
                            "name": str(row.get("name") or ""),
                            "type": str(row.get("type") or "unknown"),
                            "nullable": not bool(row.get("notnull")),
                        }
                    )
                if columns:
                    schema[view] = {"columns": columns}
        return schema


def _adapt_sql(sql: str) -> str:
    adapted = sql.replace("%s", "?").replace("NOW()", "CURRENT_TIMESTAMP")
    adapted = re.sub(r"::[a-zA-Z_][a-zA-Z0-9_]*", "", adapted)
    return adapted


def _adapt_param(value: Any) -> Any:
    if value is None:
        return None
    if value.__class__.__name__ == "Jsonb":
        return json.dumps(getattr(value, "obj", None), default=_json_default)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, default=_json_default)
    return value


def _json_default(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _decode_row(row: Row) -> Row:
    decoded = dict(row)
    for key, value in decoded.items():
        if isinstance(value, str) and key in _JSON_COLUMNS:
            try:
                decoded[key] = json.loads(value)
            except json.JSONDecodeError:
                pass
    return decoded


_JSON_COLUMNS = {
    column.name
    for table in CORE_DATA_LAYER_SCHEMA_V2.tables
    for column in table.columns
    if column.data_type == "jsonb"
}
