import sqlite3
from types import SimpleNamespace

import pytest

from app.core.ai_readonly_sql import (
    AI_ANALYTICAL_VIEW_DDL,
    AI_ANALYTICAL_VIEW_SQLITE_DDL,
    AIReadOnlyQueryError,
    AIReadOnlySQLService,
)
from app.storage.sqlite.adapter import SQLiteCoreStore


class FakeStore:
    def __init__(self):
        self.calls = []

    def execute_ai_readonly_sql(self, sql, params, *, statement_timeout_ms):
        self.calls.append((sql, params, statement_timeout_ms))
        return [{"sales_rep_external_id": "seller-1", "revenue": 125}]


def test_sql_research_is_scoped_limited_and_read_only():
    store = FakeStore()
    result = AIReadOnlySQLService(store).execute(
        "SELECT sales_rep_external_id, SUM(total_amount) AS revenue FROM ai_sales GROUP BY sales_rep_external_id ORDER BY revenue DESC",
        organization_id="org-1",
    )
    assert result["rows"] == [{"sales_rep_external_id": "seller-1", "revenue": 125}]
    sql, params, timeout = store.calls[0]
    assert "ai_sales" in sql
    assert "FROM (SELECT * FROM ai_sales WHERE organization_id IN (%s))" in sql
    assert "WHERE organization_id IN (%s)" in sql
    assert params == ("org-1",)
    assert timeout == 20_000
    assert "LIMIT 100" in sql


def test_database_specific_view_ddl_is_idempotent():
    assert len(AI_ANALYTICAL_VIEW_DDL) == 11
    assert AI_ANALYTICAL_VIEW_DDL[0].startswith("DROP VIEW IF EXISTS ai_")
    assert all(statement.startswith("CREATE VIEW ai_") for statement in AI_ANALYTICAL_VIEW_DDL[1:])
    assert len(AI_ANALYTICAL_VIEW_SQLITE_DDL) == 20
    assert all(statement.startswith("DROP VIEW IF EXISTS ai_") for statement in AI_ANALYTICAL_VIEW_SQLITE_DDL[:10])
    assert all(statement.startswith("CREATE VIEW ai_") for statement in AI_ANALYTICAL_VIEW_SQLITE_DDL[10:])


def test_sql_research_uses_the_published_sqlite_view_schema():
    store = SQLiteCoreStore.from_connection(sqlite3.connect(":memory:"))
    store.ensure_schema()

    schema = AIReadOnlySQLService(store).database_schema()

    assert schema["ai_sales"]["columns"]
    assert {column["name"] for column in schema["ai_sales"]["columns"]} == {
        "organization_id", "sale_id", "sale_at", "closed_at", "sales_rep_id",
        "sales_rep_external_id", "sales_rep_name", "customer_id", "customer_external_id",
        "customer_name", "total_amount", "sold_quantity", "returned_quantity", "order_id",
        "deal_id", "normalized_status", "currency_code",
    }


def test_semantic_environment_is_grounded_in_published_columns():
    class SchemaStore:
        def describe_ai_views(self):
            return {"ai_sales": {"columns": [{"name": "organization_id"}, {"name": "total_amount"}]}}

    environment = AIReadOnlySQLService(SchemaStore()).semantic_environment()
    sales = next(item for item in environment["datasets"] if item["name"] == "ai_sales")

    assert sales["grain"] == "one realized sale fact"
    assert set(sales["columns"]) == {"organization_id", "total_amount"}
    assert sales["columns"]["total_amount"]["kind"] == "measure"
    assert environment["relationships"] == []


def test_sales_view_resolves_rep_name_within_organization_scope():
    connection = sqlite3.connect(":memory:")
    connection.executescript(
        """
        CREATE TABLE canonical_sales (
            organization_id TEXT, sale_id TEXT, sale_at TEXT, closed_at TEXT,
            sales_rep_id TEXT, sales_rep_external_id TEXT, customer_id TEXT,
            customer_external_id TEXT, customer_name TEXT, total_amount REAL,
            sold_quantity REAL, returned_quantity REAL, order_id TEXT, deal_id TEXT,
            normalized_status TEXT, currency_code TEXT
        );
        CREATE TABLE canonical_sales_reps (
            id TEXT, organization_id TEXT, sales_manager_id TEXT,
            sales_manager_code TEXT, sales_manager_name TEXT
        );
        INSERT INTO canonical_sales_reps VALUES
            ('rep-a', 'org-a', 'seller-1', NULL, 'Seller A'),
            ('rep-b', 'org-b', 'seller-1', NULL, 'Seller B');
        INSERT INTO canonical_sales VALUES
            ('org-a', 'sale-a', '2026-08-30', NULL, NULL, 'seller-1', NULL, NULL, NULL, 100, 1, 0, NULL, NULL, 'realized', 'UZS'),
            ('org-b', 'sale-b', '2026-08-30', NULL, NULL, 'seller-1', NULL, NULL, NULL, 200, 1, 0, NULL, NULL, 'realized', 'UZS');
        """
    )
    sales_view = next(statement for statement in AI_ANALYTICAL_VIEW_SQLITE_DDL if "CREATE VIEW ai_sales AS" in statement)
    connection.execute(sales_view)

    rows = connection.execute(
        "SELECT organization_id, sales_rep_name FROM ai_sales WHERE organization_id = 'org-a'"
    ).fetchall()

    assert rows == [("org-a", "Seller A")]


@pytest.mark.parametrize("query", [
    "UPDATE ai_sales SET total_amount = 1",
    "SELECT * FROM canonical_sales",
    "SELECT * FROM ai_sales; SELECT * FROM ai_orders",
    "SELECT * FROM ai_sales JOIN ai_orders ON true",
])
def test_sql_research_rejects_unsafe_or_non_analytical_queries(query):
    with pytest.raises(AIReadOnlyQueryError):
        AIReadOnlySQLService(SimpleNamespace()).validate(query)
