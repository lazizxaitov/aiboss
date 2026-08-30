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
    assert len(AI_ANALYTICAL_VIEW_DDL) == 10
    assert all(statement.startswith("CREATE OR REPLACE VIEW ai_") for statement in AI_ANALYTICAL_VIEW_DDL)
    assert all(statement.startswith("CREATE VIEW IF NOT EXISTS ai_") for statement in AI_ANALYTICAL_VIEW_SQLITE_DDL)


def test_sql_research_uses_the_published_sqlite_view_schema():
    store = SQLiteCoreStore.from_connection(sqlite3.connect(":memory:"))
    store.ensure_schema()

    schema = AIReadOnlySQLService(store).database_schema()

    assert schema["ai_sales"]["columns"]
    assert {column["name"] for column in schema["ai_sales"]["columns"]} == {
        "organization_id", "sale_at", "sales_rep_id", "sales_rep_external_id",
        "customer_id", "customer_external_id", "customer_name", "total_amount",
        "sold_quantity", "returned_quantity", "order_id", "deal_id", "currency_code",
    }
    assert "seller_name" not in {column["name"] for column in schema["ai_sales"]["columns"]}


@pytest.mark.parametrize("query", [
    "UPDATE ai_sales SET total_amount = 1",
    "SELECT * FROM canonical_sales",
    "SELECT * FROM ai_sales; SELECT * FROM ai_orders",
    "SELECT * FROM ai_sales JOIN ai_orders ON true",
])
def test_sql_research_rejects_unsafe_or_non_analytical_queries(query):
    with pytest.raises(AIReadOnlyQueryError):
        AIReadOnlySQLService(SimpleNamespace()).validate(query)
