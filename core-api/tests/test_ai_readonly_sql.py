from types import SimpleNamespace

import pytest

from app.core.ai_readonly_sql import (
    AIReadOnlyQueryError,
    AIReadOnlySQLService,
    AI_ANALYTICAL_VIEW_DDL,
    AI_ANALYTICAL_VIEW_SQLITE_DDL,
)


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
    assert "organization_id IN (%s)" in sql
    assert params == ("org-1",)
    assert timeout == 20_000
    assert "LIMIT 100" in sql


def test_database_specific_view_ddl_is_idempotent():
    assert len(AI_ANALYTICAL_VIEW_DDL) == 10
    assert all(statement.startswith("CREATE OR REPLACE VIEW ai_") for statement in AI_ANALYTICAL_VIEW_DDL)
    assert all(statement.startswith("CREATE VIEW IF NOT EXISTS ai_") for statement in AI_ANALYTICAL_VIEW_SQLITE_DDL)


@pytest.mark.parametrize("query", [
    "UPDATE ai_sales SET total_amount = 1",
    "SELECT * FROM canonical_sales",
    "SELECT * FROM ai_sales; SELECT * FROM ai_orders",
    "SELECT * FROM ai_sales JOIN ai_orders ON true",
])
def test_sql_research_rejects_unsafe_or_non_analytical_queries(query):
    with pytest.raises(AIReadOnlyQueryError):
        AIReadOnlySQLService(SimpleNamespace()).validate(query)
