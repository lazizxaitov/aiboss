"""SQLite DDL for Core Data Layer V2-compatible core data layer."""

from collections.abc import Iterable

from app.core.data_layer.schema import (
    CORE_DATA_LAYER_SCHEMA_V2,
    CoreDataLayerSchema,
    SchemaColumn,
    SchemaRelation,
    SchemaTable,
)


def render_core_data_layer_ddl(
    schema: CoreDataLayerSchema = CORE_DATA_LAYER_SCHEMA_V2,
) -> list[str]:
    """Render SQLite DDL statements for the core data layer."""

    statements: list[str] = []
    for table in schema.tables:
        statements.append(_render_table(table, schema.relations))
        statements.extend(_render_indexes(table))
    return statements


def _render_table(table: SchemaTable, relations: Iterable[SchemaRelation]) -> str:
    columns = [_render_column(column, table.primary_key) for column in table.columns]
    columns.append(f"PRIMARY KEY ({table.primary_key})")
    columns.extend(
        _render_foreign_key(relation)
        for relation in relations
        if relation.source_table == table.name
    )
    body = ",\n    ".join(columns)
    return f"CREATE TABLE IF NOT EXISTS {table.name} (\n    {body}\n);"


def _render_column(column: SchemaColumn, primary_key: str) -> str:
    parts = [column.name, _sqlite_type(column)]
    if column.name != primary_key and not column.nullable:
        parts.append("NOT NULL")
    if column.unique and column.name != primary_key:
        parts.append("UNIQUE")
    if column.default is not None:
        parts.append(f"DEFAULT {_render_default(column)}")
    elif column.name in {"created_at", "updated_at"}:
        parts.append("DEFAULT CURRENT_TIMESTAMP")
    return " ".join(parts)


def _sqlite_type(column: SchemaColumn) -> str:
    if column.data_type.startswith("numeric"):
        return "TEXT"
    if column.data_type in {"uuid", "text", "timestamptz", "jsonb"}:
        return "TEXT"
    return column.data_type.upper()


def _render_default(column: SchemaColumn) -> str:
    if column.data_type == "jsonb" and column.default == "{}":
        return "'{}'"
    if column.data_type == "jsonb" and column.default == "[]":
        return "'[]'"
    return column.default or "NULL"


def _render_foreign_key(relation: SchemaRelation) -> str:
    return (
        f"FOREIGN KEY ({relation.source_column}) REFERENCES "
        f"{relation.target_table} ({relation.target_column})"
    )


def _render_indexes(table: SchemaTable) -> list[str]:
    statements: list[str] = []
    for index in table.indexes:
        index_name = f"idx_{table.name}_{'_'.join(index)}"
        columns = ", ".join(index)
        statements.append(
            f"CREATE INDEX IF NOT EXISTS {index_name} ON {table.name} ({columns});",
        )
    return statements
