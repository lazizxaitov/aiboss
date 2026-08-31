"""Bounded read-only SQL research interface for internal Business AI."""

from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID
from weakref import WeakKeyDictionary

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
_SCHEMA_CACHE: WeakKeyDictionary[Any, dict[str, object]] = WeakKeyDictionary()
_NON_WEAK_SCHEMA_CACHE: dict[tuple[type[Any], int], dict[str, object]] = {}


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

        try:
            cache_key: Any = self.store
            cached = _SCHEMA_CACHE.get(cache_key)
        except TypeError:
            cache_key = (type(self.store), id(self.store))
            cached = _NON_WEAK_SCHEMA_CACHE.get(cache_key)
        if cached is not None:
            return deepcopy(cached)
        describe = getattr(self.store, "describe_ai_views", None)
        if callable(describe):
            try:
                schema = describe()
                if isinstance(schema, dict) and schema:
                    for view, description in ALLOWED_VIEWS.items():
                        if isinstance(schema.get(view), dict):
                            schema[view].setdefault("description", description)
                    try:
                        _SCHEMA_CACHE[cache_key] = deepcopy(schema)
                    except TypeError:
                        _NON_WEAK_SCHEMA_CACHE[cache_key] = deepcopy(schema)
                    return deepcopy(schema)
            except Exception:  # noqa: BLE001 - schema discovery must not block chat
                pass
        schema = {
            view: {
                "columns": [
                    {"name": column, "type": "published"}
                    for column in _AI_PUBLISHED_COLUMNS[view]
                ],
                "description": ALLOWED_VIEWS[view],
            }
            for view, definition in _AI_VIEW_DEFINITIONS.items()
        }
        return schema

    def semantic_environment(self, schema: dict[str, object] | None = None) -> dict[str, object]:
        """Describe the published business data environment without inventing fields."""

        schema = schema or self.database_schema()
        datasets: list[dict[str, object]] = []
        for view, meaning in ALLOWED_VIEWS.items():
            published = schema.get(view)
            columns = published.get("columns", []) if isinstance(published, dict) else []
            names = {
                item.get("name")
                for item in columns
                if isinstance(item, dict) and isinstance(item.get("name"), str)
            }
            fields = {
                name: _AI_COLUMN_SEMANTICS.get(view, {}).get(name, _generic_column_semantics(name))
                for name in names
                if isinstance(name, str)
            }
            datasets.append({
                "name": view,
                "meaning": meaning,
                "grain": _AI_VIEW_GRAINS.get(view),
                "columns": fields,
                "date_semantics": _AI_DATE_SEMANTICS.get(view, {}),
            })
        relationships = [
            relationship for relationship in _AI_RELATIONSHIPS
            if _relationship_is_published(relationship, schema)
        ]
        return {
            "datasets": datasets,
            "relationships": relationships,
            "rules": [
                "Use only the exact dataset and column names published above.",
                "Keep organization_id in every relationship and filter within the same organization.",
                "A sale is a realized sale fact; sale items are line-level facts.",
            ],
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
    "ai_sales": "SELECT s.organization_id, s.id, s.sale_id, s.sale_at, s.closed_at, s.sales_rep_id, s.sales_rep_external_id, COALESCE((SELECT r.sales_manager_name FROM canonical_sales_reps r WHERE r.organization_id = s.organization_id AND (r.id = s.sales_rep_id OR r.sales_manager_id = s.sales_rep_external_id OR r.sales_manager_code = s.sales_rep_external_id) ORDER BY CASE WHEN r.sales_manager_id = s.sales_rep_external_id THEN 0 ELSE 1 END LIMIT 1), NULL) AS sales_rep_name, s.customer_id, s.customer_external_id, s.customer_name, s.total_amount, s.sold_quantity, s.returned_quantity, s.order_id, s.deal_id, s.normalized_status, s.currency_code FROM canonical_sales s",
    "ai_sale_items": "SELECT organization_id, sale_id, sale_external_id, order_id, order_external_id, product_id, product_external_id, product_code, product_name, warehouse_id, warehouse_external_id, warehouse_code, sold_quantity, returned_quantity, unit_price, amount, margin_amount, currency_code FROM canonical_sale_items",
    "ai_orders": "SELECT organization_id, id, order_id, deal_id, order_at, delivery_date, sales_rep_id, sales_rep_external_id, customer_id, customer_external_id, customer_name, total_amount, ordered_quantity, sold_quantity, item_count, normalized_status, currency_code FROM canonical_orders",
    "ai_products": "SELECT organization_id, id, product_id, code, name, short_name, article_code, producer_code, state, source_kind, measure_code, gtin, ikpu FROM canonical_products",
    "ai_customers": "SELECT organization_id, id, person_id, code, name, short_name, main_phone, email, state, customer_kind, tin FROM canonical_customers",
    "ai_returns": "SELECT organization_id, return_id, return_at, booked_at, sales_rep_id, sales_rep_external_id, customer_id, customer_external_id, customer_name, total_amount, returned_quantity, normalized_status, linked_order_id, linked_order_external_id, deal_id, currency_code FROM canonical_customer_returns",
    "ai_visits": "SELECT organization_id, id, visit_id, visit_date, visited_at, sales_rep_id, sales_rep_external_id, sales_rep_name, customer_id, customer_external_id, customer_name, working_zone_id, working_zone_external_id, normalized_status, display_status FROM canonical_visits",
    "ai_inventory": "SELECT organization_id, id, snapshot_date, warehouse_id, warehouse_external_id, warehouse_code, product_id, product_external_id, product_code, product_name, quantity, available_quantity, reserved_quantity, valuation_amount, currency_code, inventory_kind, measure_code FROM canonical_inventory_balances",
    "ai_finance": "SELECT organization_id, id, operation_id, operation_at, operation_date, normalized_operation_type, direction, amount, currency_code, counterparty_external_id, counterparty_name, posted FROM canonical_financial_operations",
    "ai_organizations": "SELECT organization_id, name, company_id, filial_id, filial_code, project_code, is_active, sort_order FROM canonical_organizations",
}

_AI_PUBLISHED_COLUMNS = {
    "ai_sales": ("organization_id", "id", "sale_id", "sale_at", "closed_at", "sales_rep_id", "sales_rep_external_id", "sales_rep_name", "customer_id", "customer_external_id", "customer_name", "total_amount", "sold_quantity", "returned_quantity", "order_id", "deal_id", "normalized_status", "currency_code"),
    "ai_sale_items": ("organization_id", "sale_id", "sale_external_id", "order_id", "order_external_id", "product_id", "product_external_id", "product_code", "product_name", "warehouse_id", "warehouse_external_id", "warehouse_code", "sold_quantity", "returned_quantity", "unit_price", "amount", "margin_amount", "currency_code"),
    "ai_orders": ("organization_id", "id", "order_id", "deal_id", "order_at", "delivery_date", "sales_rep_id", "sales_rep_external_id", "customer_id", "customer_external_id", "customer_name", "total_amount", "ordered_quantity", "sold_quantity", "item_count", "normalized_status", "currency_code"),
    "ai_products": ("organization_id", "id", "product_id", "code", "name", "short_name", "article_code", "producer_code", "state", "source_kind", "measure_code", "gtin", "ikpu"),
    "ai_customers": ("organization_id", "id", "person_id", "code", "name", "short_name", "main_phone", "email", "state", "customer_kind", "tin"),
    "ai_returns": ("organization_id", "return_id", "return_at", "booked_at", "sales_rep_id", "sales_rep_external_id", "customer_id", "customer_external_id", "customer_name", "total_amount", "returned_quantity", "normalized_status", "linked_order_id", "linked_order_external_id", "deal_id", "currency_code"),
    "ai_visits": ("organization_id", "id", "visit_id", "visit_date", "visited_at", "sales_rep_id", "sales_rep_external_id", "sales_rep_name", "customer_id", "customer_external_id", "customer_name", "working_zone_id", "working_zone_external_id", "normalized_status", "display_status"),
    "ai_inventory": ("organization_id", "id", "snapshot_date", "warehouse_id", "warehouse_external_id", "warehouse_code", "product_id", "product_external_id", "product_code", "product_name", "quantity", "available_quantity", "reserved_quantity", "valuation_amount", "currency_code", "inventory_kind", "measure_code"),
    "ai_finance": ("organization_id", "id", "operation_id", "operation_at", "operation_date", "normalized_operation_type", "direction", "amount", "currency_code", "counterparty_external_id", "counterparty_name", "posted"),
    "ai_organizations": ("organization_id", "name", "company_id", "filial_id", "filial_code", "project_code", "is_active", "sort_order"),
}

_AI_VIEW_GRAINS = {
    "ai_sales": "one realized sale fact",
    "ai_sale_items": "one sale line item",
    "ai_orders": "one order document",
    "ai_products": "one canonical product",
    "ai_customers": "one canonical customer",
    "ai_returns": "one customer return document",
    "ai_visits": "one field visit",
    "ai_inventory": "one inventory balance snapshot per organization, warehouse and product",
    "ai_finance": "one financial operation",
    "ai_organizations": "one organization/filial",
}

_AI_DATE_SEMANTICS = {
    "ai_sales": {"event_date_column": "sale_at", "meaning": "Realization event time; filter by the supplied business period."},
    "ai_orders": {"event_date_column": "order_at", "meaning": "Order creation/business event time."},
    "ai_returns": {"event_date_column": "return_at", "meaning": "Return event time."},
    "ai_visits": {"event_date_column": "visit_date", "meaning": "Authoritative business visit date; timestamptz interpreted in the system/business timezone."},
    "ai_inventory": {"event_date_column": "snapshot_date", "meaning": "Inventory snapshot timestamp, not a movement event."},
    "ai_finance": {"event_date_column": "operation_at", "meaning": "Financial operation event time."},
}

_AI_COLUMN_SEMANTICS = {
    "ai_sales": {
        "organization_id": {"kind": "identifier", "meaning": "Canonical organization scope."},
        "id": {"kind": "identifier", "meaning": "Canonical sale row identifier; joins to ai_sale_items.sale_id."},
        "sale_id": {"kind": "identifier", "meaning": "Canonical realized sale identifier."},
        "sale_at": {"kind": "date", "meaning": "Sale realization timestamp."},
        "closed_at": {"kind": "date", "meaning": "Sale closing timestamp when available."},
        "sales_rep_id": {"kind": "identifier", "meaning": "Canonical sales representative identifier."},
        "sales_rep_external_id": {"kind": "identifier", "meaning": "Source sales representative identifier."},
        "sales_rep_name": {"kind": "label", "meaning": "Sales representative name resolved from canonical sales reps."},
        "customer_external_id": {"kind": "identifier", "meaning": "Source customer identifier."},
        "customer_name": {"kind": "label", "meaning": "Customer name captured on the sale."},
        "total_amount": {"kind": "measure", "meaning": "Realized sale amount."},
        "sold_quantity": {"kind": "measure", "meaning": "Realized quantity."},
        "returned_quantity": {"kind": "measure", "meaning": "Quantity returned against the sale."},
        "order_id": {"kind": "identifier", "meaning": "Canonical order identifier when linked."},
        "deal_id": {"kind": "identifier", "meaning": "Source deal identifier."},
        "normalized_status": {"kind": "dimension", "meaning": "Canonical sale status."},
        "currency_code": {"kind": "dimension", "meaning": "Currency of the amount."},
    },
    "ai_sale_items": {
        "organization_id": {"kind": "identifier", "meaning": "Canonical organization scope."},
        "sale_id": {"kind": "identifier", "meaning": "Canonical sale identifier."},
        "product_id": {"kind": "identifier", "meaning": "Canonical product identifier."},
        "product_external_id": {"kind": "identifier", "meaning": "Source product identifier."},
        "product_code": {"kind": "dimension", "meaning": "Product code."},
        "product_name": {"kind": "label", "meaning": "Product name captured on the line."},
        "warehouse_id": {"kind": "identifier", "meaning": "Canonical warehouse identifier."},
        "warehouse_external_id": {"kind": "identifier", "meaning": "Source warehouse identifier."},
        "sold_quantity": {"kind": "measure", "meaning": "Realized line quantity."},
        "returned_quantity": {"kind": "measure", "meaning": "Returned line quantity."},
        "unit_price": {"kind": "measure", "meaning": "Line unit price."},
        "amount": {"kind": "measure", "meaning": "Line amount."},
        "margin_amount": {"kind": "measure", "meaning": "Margin when populated by source data."},
        "currency_code": {"kind": "dimension", "meaning": "Currency of line amounts."},
    },
    "ai_visits": {
        "organization_id": {"kind": "identifier", "meaning": "Canonical organization scope."},
        "visit_date": {"kind": "date", "meaning": "Authoritative business date for visit period filtering; stored as timestamptz."},
        "visited_at": {"kind": "date", "meaning": "Visit event timestamp when available."},
        "sales_rep_external_id": {"kind": "identifier", "meaning": "Source representative identifier."},
        "sales_rep_name": {"kind": "label", "meaning": "Human-readable representative name."},
        "normalized_status": {"kind": "dimension", "meaning": "Canonical visit completion/status."},
    },
    "ai_products": {
        "id": {"kind": "identifier", "meaning": "Canonical product identifier; target of ai_sale_items.product_id."},
        "product_id": {"kind": "identifier", "meaning": "Source product identifier."},
        "name": {"kind": "label", "meaning": "Canonical product name."},
    },
}


def _generic_column_semantics(name: str) -> dict[str, str]:
    if name.endswith("_id") or name in {"id", "code", "filial_code", "project_code"}:
        kind = "identifier"
    elif name.endswith("_at") or name.endswith("_date"):
        kind = "date"
    elif any(token in name for token in ("amount", "quantity", "price", "margin", "count")):
        kind = "measure"
    elif name.endswith("_name") or name in {"name", "short_name"}:
        kind = "label"
    else:
        kind = "dimension"
    return {"kind": kind, "meaning": name.replace("_", " ") + " from the canonical source."}

_AI_RELATIONSHIPS = (
    {"from": "ai_sales.organization_id", "to": "ai_organizations.organization_id", "scope": "same organization"},
    {"from": "ai_sales.(organization_id,id)", "to": "ai_sale_items.(organization_id,sale_id)", "scope": "same organization; sale line items"},
    {"from": "ai_sales.(organization_id,sales_rep_external_id)", "to": "canonical_sales_reps.(organization_id,sales_manager_id|sales_manager_code)", "scope": "same organization; name is resolved in ai_sales"},
    {"from": "ai_sale_items.(organization_id,product_id)", "to": "ai_products.(organization_id,id)", "scope": "same organization when product_id is populated"},
)


def _relationship_is_published(relationship: dict[str, object], schema: dict[str, object]) -> bool:
    endpoints = [relationship.get("from"), relationship.get("to")]
    for endpoint in endpoints:
        if not isinstance(endpoint, str) or "." not in endpoint:
            return False
        view, fields = endpoint.split(".", 1)
        if view == "canonical_sales_reps":
            continue
        published = schema.get(view)
        names = {
            item.get("name") for item in (published.get("columns", []) if isinstance(published, dict) else [])
            if isinstance(item, dict)
        }
        for field in fields.strip("()").split(","):
            if "|" in field:
                if not any(option in names for option in field.split("|")):
                    return False
            elif field not in names:
                return False
    return True

_AI_VIEW_SELECTS = tuple(
    f"{view} AS {definition}" for view, definition in _AI_VIEW_DEFINITIONS.items()
)

# PostgreSQL view columns can change only after the old view is removed. This
# drops views only, then recreates the published read-only projections.
AI_ANALYTICAL_VIEW_DDL = (
    "DROP VIEW IF EXISTS " + ", ".join(_AI_VIEW_DEFINITIONS),
    *tuple(f"CREATE VIEW {definition}" for definition in _AI_VIEW_SELECTS),
)
AI_ANALYTICAL_VIEW_SQLITE_DDL = (
    *tuple(f"DROP VIEW IF EXISTS {view}" for view in _AI_VIEW_DEFINITIONS),
    *tuple(f"CREATE VIEW {definition}" for definition in _AI_VIEW_SELECTS),
)
