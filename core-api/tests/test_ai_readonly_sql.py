import sqlite3
from types import SimpleNamespace

import pytest

from app.core.ai_readonly_sql import (
    AI_ANALYTICAL_VIEW_DDL,
    AI_ANALYTICAL_VIEW_SQLITE_DDL,
    AIReadOnlyQueryError,
    AIReadOnlySQLService,
    ALLOWED_VIEWS,
    _escape_percent_literals,
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


def test_sql_research_escapes_percent_wildcards_before_psycopg_bind_formatting():
    store = FakeStore()

    AIReadOnlySQLService(store).execute(
        "SELECT sales_rep_name FROM ai_visits WHERE sales_rep_name ILIKE '%Акрамова Нигора%'",
        organization_id="org-1",
    )

    sql, params, _ = store.calls[0]
    assert "ILIKE '%%Акрамова Нигора%%'" in sql
    assert params == ("org-1",)


def test_percent_literal_escaping_does_not_change_non_literal_sql():
    sql = "SELECT total_amount % 2 AS remainder FROM ai_sales"
    assert _escape_percent_literals(sql) == sql


def test_sql_research_defaults_to_all_accessible_organizations():
    class OrganizationStore(FakeStore):
        def list_canonical_organizations(self):
            return [
                SimpleNamespace(organization_id="org-a"),
                SimpleNamespace(organization_id="org-b"),
            ]

    store = OrganizationStore()
    AIReadOnlySQLService(store).execute("SELECT organization_id FROM ai_sales")

    sql, params, _ = store.calls[0]
    assert "IN (%s, %s)" in sql
    assert params == ("org-a", "org-b")


def test_sql_research_clamps_per_execution_timeout_to_safe_default():
    store = FakeStore()

    AIReadOnlySQLService(store).execute(
        "SELECT organization_id FROM ai_sales",
        organization_id="org-1",
        statement_timeout_ms=2_500,
    )

    assert store.calls[0][2] == 2_500


def test_sql_research_never_allows_timeout_above_safe_default():
    store = FakeStore()

    AIReadOnlySQLService(store).execute(
        "SELECT organization_id FROM ai_sales",
        organization_id="org-1",
        statement_timeout_ms=60_000,
    )

    assert store.calls[0][2] == 20_000


def test_sql_research_rejects_organization_outside_accessible_scope():
    class OrganizationStore(FakeStore):
        def list_canonical_organizations(self):
            return [
                SimpleNamespace(organization_id="org-a"),
                SimpleNamespace(organization_id="org-b"),
            ]

    with pytest.raises(AIReadOnlyQueryError, match="недоступна"):
        AIReadOnlySQLService(OrganizationStore()).execute(
            "SELECT organization_id FROM ai_sales",
            organization_id="org-c",
        )


def test_database_specific_view_ddl_is_idempotent():
    assert len(AI_ANALYTICAL_VIEW_DDL) == len(ALLOWED_VIEWS) + 1
    assert AI_ANALYTICAL_VIEW_DDL[0].startswith("DROP VIEW IF EXISTS ai_")
    assert all(statement.startswith("CREATE VIEW ai_") for statement in AI_ANALYTICAL_VIEW_DDL[1:])
    assert len(AI_ANALYTICAL_VIEW_SQLITE_DDL) == len(ALLOWED_VIEWS) * 2
    assert all(
        statement.startswith("DROP VIEW IF EXISTS ai_")
        for statement in AI_ANALYTICAL_VIEW_SQLITE_DDL[: len(ALLOWED_VIEWS)]
    )
    assert all(
        statement.startswith("CREATE VIEW ai_")
        for statement in AI_ANALYTICAL_VIEW_SQLITE_DDL[len(ALLOWED_VIEWS) :]
    )


def test_sql_research_uses_the_published_sqlite_view_schema():
    store = SQLiteCoreStore.from_connection(sqlite3.connect(":memory:"))
    store.ensure_schema()

    schema = AIReadOnlySQLService(store).database_schema()

    assert schema["ai_sales"]["columns"]
    assert {column["name"] for column in schema["ai_sales"]["columns"]} == {
        "organization_id",
        "id",
        "sale_id",
        "sale_at",
        "closed_at",
        "sales_rep_id",
        "sales_rep_external_id",
        "sales_rep_name",
        "customer_id",
        "customer_external_id",
        "customer_name",
        "total_amount",
        "sold_quantity",
        "returned_quantity",
        "order_id",
        "deal_id",
        "normalized_status",
        "currency_code",
    }


def test_semantic_environment_is_grounded_in_published_columns():
    class SchemaStore:
        def describe_ai_views(self):
            return {
                "ai_sales": {"columns": [{"name": "organization_id"}, {"name": "total_amount"}]}
            }

    environment = AIReadOnlySQLService(SchemaStore()).semantic_environment()
    sales = next(item for item in environment["datasets"] if item["name"] == "ai_sales")

    assert sales["grain"] == "one realized sale fact"
    assert set(sales["columns"]) == {"organization_id", "total_amount"}
    assert sales["columns"]["total_amount"]["kind"] == "measure"
    assert environment["relationships"] == []


def test_semantic_environment_can_omit_duplicate_column_catalog_for_agent_prompt():
    class SchemaStore:
        def describe_ai_views(self):
            return {"ai_sales": {"columns": [{"name": "organization_id"}]}}

    environment = AIReadOnlySQLService(SchemaStore()).semantic_environment(include_columns=False)
    sales = next(item for item in environment["datasets"] if item["name"] == "ai_sales")

    assert "columns" not in sales
    assert sales["grain"] == "one realized sale fact"


def test_compact_domain_index_is_derived_from_published_contract():
    class SchemaStore:
        def describe_ai_views(self):
            return {"ai_sales": {"columns": [
                {"name": "organization_id"},
                {"name": "sale_at"},
                {"name": "sales_rep_name"},
                {"name": "total_amount"},
            ]}}

    index = AIReadOnlySQLService(SchemaStore()).semantic_domain_index()
    sales = next(item for item in index["datasets"] if item["view"] == "ai_sales")

    assert sales["primary_time"] == "sale_at"
    assert "sales_rep_name" in sales["dimensions"]
    assert "total_amount" in sales["measures"]
    assert "columns" not in sales


def test_semantic_discovery_returns_only_requested_dataset_details():
    service = AIReadOnlySQLService(SimpleNamespace())
    result = service.describe_semantic(domain="sales")

    assert result["available"] is True
    assert result["dataset"]["name"] == "ai_sales"
    assert "columns" in result["dataset"]


def test_semantic_graph_covers_published_domains_and_compound_identity():
    environment = AIReadOnlySQLService(SimpleNamespace()).semantic_environment(
        include_columns=False,
    )
    datasets = {item["name"]: item for item in environment["datasets"]}

    assert set(datasets) == {
        "ai_organizations",
        "ai_sales",
        "ai_sale_items",
        "ai_orders",
        "ai_products",
        "ai_customers",
        "ai_returns",
        "ai_visits",
        "ai_inventory",
        "ai_finance",
    } | set(ALLOWED_VIEWS) - {
        "ai_organizations",
        "ai_sales",
        "ai_sale_items",
        "ai_orders",
        "ai_products",
        "ai_customers",
        "ai_returns",
        "ai_visits",
        "ai_inventory",
        "ai_finance",
    }
    assert datasets["ai_sales"]["identity"] == ["organization_id", "id"]
    assert "total_amount" in datasets["ai_sales"]["measures"]
    assert datasets["ai_sales"]["labels"] == ["sales_rep_name", "customer_name"]
    assert datasets["ai_visits"]["date_semantics"]["event_date_column"] == "visit_date"
    assert datasets["ai_inventory"]["date_semantics"]["event_date_column"] == "snapshot_date"
    assert any(
        relationship["from"] == "ai_sale_items.(organization_id,product_id)"
        and relationship["to"] == "ai_products.(organization_id,id)"
        and relationship["organization_scope"].startswith("compound organization_id")
        for relationship in environment["relationships"]
    )
    assert all(
        "canonical_" not in str(relationship) for relationship in environment["relationships"]
    )


def test_schema_introspection_is_reused_for_one_store():
    class SchemaStore:
        def __init__(self):
            self.calls = 0

        def describe_ai_views(self):
            self.calls += 1
            return {"ai_sales": {"columns": [{"name": "organization_id"}]}}

    store = SchemaStore()
    service = AIReadOnlySQLService(store)
    service.database_schema()
    service.database_schema()
    service.semantic_environment()

    assert store.calls == 1


def test_semantic_environment_publishes_confirmed_cross_domain_links_and_visit_date():
    class SchemaStore:
        def describe_ai_views(self):
            return {
                "ai_sales": {"columns": [{"name": "organization_id"}, {"name": "id"}]},
                "ai_sale_items": {"columns": [{"name": "organization_id"}, {"name": "sale_id"}]},
                "ai_products": {"columns": [{"name": "organization_id"}, {"name": "id"}]},
                "ai_organizations": {"columns": [{"name": "organization_id"}]},
                "ai_visits": {"columns": [{"name": "organization_id"}, {"name": "visit_date"}]},
            }

    environment = AIReadOnlySQLService(SchemaStore()).semantic_environment()
    assert {(item["from"], item["to"]) for item in environment["relationships"]} == {
        ("ai_sales.organization_id", "ai_organizations.organization_id"),
        ("ai_sales.(organization_id,id)", "ai_sale_items.(organization_id,sale_id)"),
    }
    visits = next(item for item in environment["datasets"] if item["name"] == "ai_visits")
    assert visits["date_semantics"]["event_date_column"] == "visit_date"


def test_sales_view_resolves_rep_name_within_organization_scope():
    connection = sqlite3.connect(":memory:")
    connection.executescript(
        """
        CREATE TABLE canonical_sales (
            organization_id TEXT, id TEXT, sale_id TEXT, sale_at TEXT, closed_at TEXT,
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
            ('org-a', 'sale-row-a', 'sale-a', '2026-08-30', NULL, NULL, 'seller-1', NULL, NULL, NULL, 100, 1, 0, NULL, NULL, 'realized', 'UZS'),
            ('org-b', 'sale-row-b', 'sale-b', '2026-08-30', NULL, NULL, 'seller-1', NULL, NULL, NULL, 200, 1, 0, NULL, NULL, 'realized', 'UZS');
        """
    )
    sales_view = next(
        statement
        for statement in AI_ANALYTICAL_VIEW_SQLITE_DDL
        if "CREATE VIEW ai_sales AS" in statement
    )
    connection.execute(sales_view)

    rows = connection.execute(
        "SELECT organization_id, sales_rep_name FROM ai_sales WHERE organization_id = 'org-a'"
    ).fetchall()

    assert rows == [("org-a", "Seller A")]


@pytest.mark.parametrize(
    "query",
    [
        "UPDATE ai_sales SET total_amount = 1",
        "SELECT * FROM canonical_sales",
        "SELECT * FROM ai_sales; SELECT * FROM ai_orders",
        "SELECT * FROM ai_sales JOIN ai_orders ON true",
    ],
)
def test_sql_research_rejects_unsafe_or_non_analytical_queries(query):
    with pytest.raises(AIReadOnlyQueryError):
        AIReadOnlySQLService(SimpleNamespace()).validate(query)
