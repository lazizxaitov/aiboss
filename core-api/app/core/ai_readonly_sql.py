"""Bounded read-only SQL research interface for internal Business AI."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

ALLOWED_VIEWS = {
    "ai_sales": "realized sales facts; one row per sale",
    "ai_sale_items": "realized sale line items",
    "ai_orders": "order facts",
    "ai_products": "canonical product catalog",
    "ai_customers": "canonical customer catalog",
    "ai_returns": "customer return facts",
    "ai_visits": "field visit facts",
    "ai_inventory": "latest canonical inventory balances",
    "ai_finance": "canonical financial operations",
    "ai_organizations": "available organizations",
}
MAX_ROWS = 100
STATEMENT_TIMEOUT_MS = 20_000
_SELECT = re.compile(r"^\s*select\b", re.IGNORECASE)
_FROM = re.compile(r"\bfrom\s+([a-z_][a-z0-9_]*)\b", re.IGNORECASE)
_LIMIT = re.compile(r"\blimit\s+(\d+)\b", re.IGNORECASE)
_FORBIDDEN = re.compile(
    r"\b(?:insert|update|delete|drop|alter|create|truncate|copy|call|execute|grant|revoke|merge|vacuum|analyze|pg_sleep|pg_read_file|current_setting|set_config|dblink|nextval|information_schema|pg_catalog)\b",
    re.IGNORECASE,
)


class AIReadOnlyQueryError(ValueError):
    """Raised when a model-generated SQL query is outside the safe contract."""


@dataclass(frozen=True, slots=True)
class AIQueryResult:
    rows: list[dict[str, Any]]
    view: str
    sql: str
    limited: bool


class AIReadOnlySQLService:
    """Validate and execute model SQL without exposing database credentials."""

    def __init__(self, store: Any) -> None:
        self.store = store

    @staticmethod
    def catalog() -> dict[str, str]:
        return dict(ALLOWED_VIEWS)

    def database_schema(self) -> dict[str, object]:
        """Return the live published view schema for model grounding.

        The storage adapter reads this from the database after schema setup. A
        DDL-derived fallback keeps the prompt useful for lightweight adapters,
        while production PostgreSQL always publishes its actual column types.
        """

        describe = getattr(self.store, "describe_ai_views", None)
        if callable(describe):
            try:
                schema = describe()
                if isinstance(schema, dict) and schema:
                    for view, description in ALLOWED_VIEWS.items():
                        if isinstance(schema.get(view), dict):
                            schema[view].setdefault("description", description)
                    return schema
            except Exception:  # noqa: BLE001 - schema discovery must not block chat
                pass
        return {
            view: {
                "columns": [
                    {"name": column, "type": "published"}
                    for column in definition.split("SELECT ", 1)[1].split(" FROM ", 1)[0].split(", ")
                ],
                "description": ALLOWED_VIEWS[view],
            }
            for view, definition in _AI_VIEW_DEFINITIONS.items()
        }

    def validate(self, sql: str) -> tuple[str, str, tuple[Any, ...]]:
        if not isinstance(sql, str) or not sql.strip():
            raise AIReadOnlyQueryError("AI не передал SQL-запрос.")
        query = sql.strip()
        if len(query) > 12_000 or ";" in query or "\x00" in query:
            raise AIReadOnlyQueryError("Разрешён только один короткий SELECT-запрос.")
        if "--" in query or "/*" in query or "*/" in query:
            raise AIReadOnlyQueryError("SQL-комментарии запрещены.")
        if not _SELECT.match(query) or _FORBIDDEN.search(query):
            raise AIReadOnlyQueryError("Разрешены только SELECT-запросы.")
        if len(re.findall(r"\bselect\b", query, re.IGNORECASE)) != 1:
            raise AIReadOnlyQueryError("Вложенные SELECT-запросы запрещены.")
        matches = _FROM.findall(query)
        if len(matches) != 1 or matches[0].lower() not in ALLOWED_VIEWS:
            raise AIReadOnlyQueryError("Запрос должен читать ровно одно разрешённое ai_* представление.")
        view = matches[0].lower()
        if re.search(r"\b(?:join|union|intersect|except|into)\b", query, re.IGNORECASE):
            raise AIReadOnlyQueryError("JOIN и составные запросы не разрешены в AI research interface.")
        limit_match = _LIMIT.search(query)
        if limit_match and int(limit_match.group(1)) > MAX_ROWS:
            query = query[: limit_match.start()] + f"LIMIT {MAX_ROWS}"
        elif not limit_match:
            query = f"{query} LIMIT {MAX_ROWS}"
        # Organization scope is injected as a parameter by execute().
        return query, view, ()

    def execute(
        self,
        sql: str,
        *,
        organization_id: UUID | str | None = None,
        organization_ids: list[UUID | str] | None = None,
    ) -> dict[str, Any]:
        query, view, _ = self.validate(sql)
        scope = [str(item) for item in (organization_ids or []) if item]
        if organization_id:
            scope = [str(organization_id)]
        if not scope and view != "ai_organizations":
            # Global dashboard context means all configured canonical
            # organizations, not an unscoped database request.
            list_organizations = getattr(self.store, "list_canonical_organizations", None)
            if callable(list_organizations):
                scope = [
                    str(getattr(item, "organization_id", getattr(item, "id", "")))
                    for item in list_organizations()
                    if getattr(item, "organization_id", getattr(item, "id", None))
                ]
        # Every business view except the organization directory is scoped. The
        # predicate must be applied to the source view before the model query is
        # aggregated: an aggregate SELECT is not required to return
        # organization_id itself.
        params: tuple[Any, ...] = ()
        if view != "ai_organizations":
            if not scope:
                raise AIReadOnlyQueryError("Для бизнес-данных требуется organization scope.")
            placeholders = ", ".join(["%s"] * len(scope))
            scoped_source = (
                f"(SELECT * FROM {view} "
                f"WHERE organization_id IN ({placeholders})) AS ai_scoped_{view}"
            )
            query, replacements = re.subn(
                rf"\bFROM\s+{re.escape(view)}\b",
                f"FROM {scoped_source}",
                query,
                count=1,
                flags=re.IGNORECASE,
            )
            if replacements != 1:
                raise AIReadOnlyQueryError("Не удалось применить organization scope к запросу.")
            params = tuple(scope)
        rows = self.store.execute_ai_readonly_sql(
            query,
            params,
            statement_timeout_ms=STATEMENT_TIMEOUT_MS,
        )
        return {
            "available": True,
            "source": "AI Business OS Canonical/Core analytical views",
            "view": view,
            "rows": rows[:MAX_ROWS],
            "row_count": min(len(rows), MAX_ROWS),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "limited": len(rows) > MAX_ROWS,
        }


_AI_VIEW_DEFINITIONS = {
    "ai_sales": "SELECT organization_id, sale_at, sales_rep_id, sales_rep_external_id, customer_id, customer_external_id, customer_name, total_amount, sold_quantity, returned_quantity, order_id, deal_id, currency_code FROM canonical_sales",
    "ai_sale_items": "SELECT organization_id, sale_id, sale_external_id, product_id, product_external_id, product_code, product_name, warehouse_id, warehouse_external_id, sold_quantity, returned_quantity, unit_price, amount, margin_amount, currency_code FROM canonical_sale_items",
    "ai_orders": "SELECT organization_id, order_at, sales_rep_id, sales_rep_external_id, customer_id, customer_external_id, customer_name, total_amount, ordered_quantity, sold_quantity, normalized_status, order_id, deal_id, currency_code FROM canonical_orders",
    "ai_products": "SELECT organization_id, id, product_id, code, name, short_name, state, source_kind, measure_code FROM canonical_products",
    "ai_customers": "SELECT organization_id, id, person_id, code, name, short_name, state, customer_kind FROM canonical_customers",
    "ai_returns": "SELECT organization_id, return_at, sales_rep_id, sales_rep_external_id, customer_id, customer_external_id, customer_name, total_amount, returned_quantity, normalized_status, linked_sale_id, deal_id, currency_code FROM canonical_customer_returns",
    "ai_visits": "SELECT organization_id, visit_date, visited_at, sales_rep_id, sales_rep_external_id, sales_rep_name, customer_id, customer_external_id, customer_name, working_zone_id, working_zone_external_id FROM canonical_visits",
    "ai_inventory": "SELECT organization_id, snapshot_date, warehouse_id, warehouse_external_id, product_id, product_external_id, product_code, product_name, quantity, available_quantity, reserved_quantity, valuation_amount, currency_code, inventory_kind FROM canonical_inventory_balances",
    "ai_finance": "SELECT organization_id, operation_at, normalized_operation_type, direction, amount, currency_code, counterparty_external_id, posted FROM canonical_financial_operations",
    "ai_organizations": "SELECT organization_id, name, company_id, filial_id, filial_code, project_code, is_active FROM canonical_organizations",
}

_AI_VIEW_SELECTS = tuple(
    f"{view} AS {definition}" for view, definition in _AI_VIEW_DEFINITIONS.items()
)

# PostgreSQL has no CREATE VIEW IF NOT EXISTS; OR REPLACE is idempotent.
AI_ANALYTICAL_VIEW_DDL = tuple(f"CREATE OR REPLACE VIEW {definition}" for definition in _AI_VIEW_SELECTS)
AI_ANALYTICAL_VIEW_SQLITE_DDL = tuple(f"CREATE VIEW IF NOT EXISTS {definition}" for definition in _AI_VIEW_SELECTS)
