"""Bounded read-only SQL research interface for internal Business AI."""

from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from time import monotonic
from typing import Any
from uuid import UUID
from weakref import WeakKeyDictionary

from app.integrations.meta.schema import META_VIEW_COLUMNS, META_VIEW_DEFINITIONS
from app.integrations.youtube.schema import YOUTUBE_VIEW_COLUMNS, YOUTUBE_VIEW_DEFINITIONS

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
ALLOWED_VIEWS.update(
    {
        "ai_meta_ad_accounts": "Meta advertising accounts and account-level currency/timezone",
        "ai_meta_campaigns": "Meta advertising campaigns",
        "ai_meta_adsets": "Meta advertising ad sets",
        "ai_meta_ads": "Meta advertisements",
        "ai_meta_ads_daily": "Daily Meta advertising insights and controlled breakdowns",
        "ai_instagram_accounts": "Instagram professional accounts",
        "ai_instagram_media": "Instagram organic media",
        "ai_instagram_media_daily": "Daily Instagram media insights",
        "ai_facebook_pages": "Facebook Pages",
        "ai_facebook_posts": "Facebook Page posts",
        "ai_facebook_posts_daily": "Daily Facebook post insights",
    }
)
ALLOWED_VIEWS.update(
    {
        "ai_youtube_channels": "YouTube channels",
        "ai_youtube_videos": "YouTube video metadata",
        "ai_youtube_channel_daily": "Daily YouTube channel analytics",
        "ai_youtube_video_daily": "Daily YouTube video analytics",
    }
)
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
        self.last_timing: dict[str, float] = {}

    @staticmethod
    def catalog() -> dict[str, str]:
        return dict(ALLOWED_VIEWS)

    @staticmethod
    def compact_schema(schema: dict[str, object]) -> dict[str, object]:
        """Keep exact published names while removing repetitive DB metadata."""

        compact: dict[str, object] = {}
        for view, definition in schema.items():
            if not isinstance(definition, dict):
                continue
            columns = definition.get("columns")
            names = (
                [
                    item.get("name")
                    for item in columns
                    if isinstance(item, dict) and isinstance(item.get("name"), str)
                ]
                if isinstance(columns, list)
                else []
            )
            compact[view] = {
                "columns": names,
                "description": definition.get("description", ALLOWED_VIEWS.get(view, "")),
            }
        return compact

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
                    {"name": column, "type": "published"} for column in _AI_PUBLISHED_COLUMNS[view]
                ],
                "description": ALLOWED_VIEWS[view],
            }
            for view, definition in _AI_VIEW_DEFINITIONS.items()
        }
        return schema

    def semantic_environment(
        self,
        schema: dict[str, object] | None = None,
        *,
        include_columns: bool = True,
    ) -> dict[str, object]:
        """Describe the published business data environment without inventing fields."""

        schema = schema or self.database_schema()
        datasets: list[dict[str, object]] = []
        published_views = list(ALLOWED_VIEWS)
        published_views.extend(
            view
            for view in ai_semantic_graph_registry.names()
            if view in schema and view not in ALLOWED_VIEWS
        )
        for view in published_views:
            meaning = ALLOWED_VIEWS.get(
                view, str((ai_semantic_graph_registry.get(view) or {}).get("meaning", ""))
            )
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
            contract = ai_semantic_graph_registry.get(view) or {}
            dataset: dict[str, object] = {
                "name": view,
                "meaning": meaning,
                "domain": contract.get("domain", "commerce"),
                "source": contract.get("source", "canonical"),
                "grain": contract.get("grain", _AI_VIEW_GRAINS.get(view)),
                "identity": _published_metadata(contract.get("identity"), names),
                "organization_behavior": contract.get(
                    "organization_behavior",
                    "organization_id scopes every published business fact",
                ),
                "dimensions": _published_metadata(contract.get("dimensions"), names),
                "measures": _published_metadata(contract.get("measures"), names),
                "labels": _published_metadata(contract.get("labels"), names),
                "date_semantics": contract.get("date_semantics", _AI_DATE_SEMANTICS.get(view, {})),
            }
            if include_columns:
                dataset["columns"] = fields
            datasets.append(dataset)
        relationships = [
            relationship
            for relationship in _AI_RELATIONSHIPS
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
            "extensibility": {
                "registration": "Register a dataset contract first; publish its approved view and capability separately before it becomes queryable.",
                "supported_future_domains": [
                    "marketing",
                    "advertising",
                    "content",
                    "social",
                    "attribution",
                ],
                "attribution": "Only explicit tracking, conversion, campaign or source identifiers establish attribution; date coincidence is not causality.",
                "unresolved_relationships": "Potential relationships may be documented, but are not joinable until a real key or attribution mechanism is confirmed.",
            },
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
            raise AIReadOnlyQueryError(
                "Запрос должен читать ровно одно разрешённое ai_* представление."
            )
        view = matches[0].lower()
        if re.search(r"\b(?:join|union|intersect|except|into)\b", query, re.IGNORECASE):
            raise AIReadOnlyQueryError(
                "JOIN и составные запросы не разрешены в AI research interface."
            )
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
        statement_timeout_ms: int | None = None,
    ) -> dict[str, Any]:
        started_at = monotonic()
        validation_started = monotonic()
        query, view, _ = self.validate(sql)
        validation_ms = (monotonic() - validation_started) * 1000
        requested_scope = [str(item) for item in (organization_ids or []) if item]
        if organization_id:
            requested_scope = [str(organization_id)]
        from app.core.organization_context import OrganizationContextService

        accessible_scope = [
            str(item)
            for item in OrganizationContextService(self.store).resolve_accessible_organization_ids()
        ]
        if requested_scope and accessible_scope:
            unauthorized = sorted(set(requested_scope) - set(accessible_scope))
            if unauthorized:
                raise AIReadOnlyQueryError(
                    "Запрошенная организация недоступна текущему пользователю."
                )
        scope = requested_scope or accessible_scope
        # Every business view is scoped. The
        # predicate must be applied to the source view before the model query is
        # aggregated: an aggregate SELECT is not required to return
        # organization_id itself.
        params: tuple[Any, ...] = ()
        if scope:
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
        elif view != "ai_organizations":
            raise AIReadOnlyQueryError("Для бизнес-данных требуется organization scope.")
        query_started = monotonic()
        effective_timeout_ms = (
            STATEMENT_TIMEOUT_MS
            if statement_timeout_ms is None
            else min(
                STATEMENT_TIMEOUT_MS,
                max(1, int(statement_timeout_ms)),
            )
        )
        rows = self.store.execute_ai_readonly_sql(
            query,
            params,
            statement_timeout_ms=effective_timeout_ms,
        )
        query_ms = (monotonic() - query_started) * 1000
        self.last_timing = {
            "sql_validation_ms": validation_ms,
            "postgres_query_ms": query_ms,
            "capability_result_ms": (monotonic() - query_started) * 1000,
            "total_ms": (monotonic() - started_at) * 1000,
            "statement_timeout_ms": effective_timeout_ms,
        }
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
    "ai_returns": "SELECT organization_id, return_id, return_at, booked_at, sales_rep_id, sales_rep_external_id, customer_id, customer_external_id, customer_name, total_amount, returned_quantity, normalized_status, linked_order_id, linked_order_external_id, deal_id, currency_code FROM (SELECT r.*, ROW_NUMBER() OVER (PARTITION BY return_id, external_document_id, order_deal_id, customer_external_id, sales_rep_external_id, return_at, booked_at, total_amount, returned_quantity, item_count, currency_code ORDER BY organization_id, id) AS identity_rank FROM canonical_customer_returns r) returns WHERE identity_rank = 1",
    "ai_visits": "SELECT organization_id, id, visit_id, visit_date, visited_at, sales_rep_id, sales_rep_external_id, sales_rep_name, customer_id, customer_external_id, customer_name, working_zone_id, working_zone_external_id, normalized_status, display_status FROM (SELECT v.*, ROW_NUMBER() OVER (PARTITION BY visit_id, customer_external_id, sales_rep_external_id, visit_date, visited_at, visit_start_time, visit_end_time, working_zone_external_id, duration_seconds ORDER BY organization_id, id) AS identity_rank FROM canonical_visits v) visits WHERE identity_rank = 1",
    "ai_inventory": "SELECT organization_id, id, snapshot_date, warehouse_id, warehouse_external_id, warehouse_code, product_id, product_external_id, product_code, product_name, quantity, available_quantity, reserved_quantity, valuation_amount, currency_code, inventory_kind, measure_code FROM canonical_inventory_balances",
    "ai_finance": "SELECT organization_id, id, operation_id, operation_at, operation_date, normalized_operation_type, direction, amount, currency_code, counterparty_external_id, counterparty_name, posted FROM canonical_financial_operations",
    "ai_organizations": "SELECT organization_id, name, company_id, filial_id, filial_code, project_code, is_active, sort_order FROM canonical_organizations",
}
_AI_VIEW_DEFINITIONS.update(META_VIEW_DEFINITIONS)
_AI_VIEW_DEFINITIONS.update(YOUTUBE_VIEW_DEFINITIONS)

_AI_PUBLISHED_COLUMNS = {
    "ai_sales": (
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
    ),
    "ai_sale_items": (
        "organization_id",
        "sale_id",
        "sale_external_id",
        "order_id",
        "order_external_id",
        "product_id",
        "product_external_id",
        "product_code",
        "product_name",
        "warehouse_id",
        "warehouse_external_id",
        "warehouse_code",
        "sold_quantity",
        "returned_quantity",
        "unit_price",
        "amount",
        "margin_amount",
        "currency_code",
    ),
    "ai_orders": (
        "organization_id",
        "id",
        "order_id",
        "deal_id",
        "order_at",
        "delivery_date",
        "sales_rep_id",
        "sales_rep_external_id",
        "customer_id",
        "customer_external_id",
        "customer_name",
        "total_amount",
        "ordered_quantity",
        "sold_quantity",
        "item_count",
        "normalized_status",
        "currency_code",
    ),
    "ai_products": (
        "organization_id",
        "id",
        "product_id",
        "code",
        "name",
        "short_name",
        "article_code",
        "producer_code",
        "state",
        "source_kind",
        "measure_code",
        "gtin",
        "ikpu",
    ),
    "ai_customers": (
        "organization_id",
        "id",
        "person_id",
        "code",
        "name",
        "short_name",
        "main_phone",
        "email",
        "state",
        "customer_kind",
        "tin",
    ),
    "ai_returns": (
        "organization_id",
        "return_id",
        "return_at",
        "booked_at",
        "sales_rep_id",
        "sales_rep_external_id",
        "customer_id",
        "customer_external_id",
        "customer_name",
        "total_amount",
        "returned_quantity",
        "normalized_status",
        "linked_order_id",
        "linked_order_external_id",
        "deal_id",
        "currency_code",
    ),
    "ai_visits": (
        "organization_id",
        "id",
        "visit_id",
        "visit_date",
        "visited_at",
        "sales_rep_id",
        "sales_rep_external_id",
        "sales_rep_name",
        "customer_id",
        "customer_external_id",
        "customer_name",
        "working_zone_id",
        "working_zone_external_id",
        "normalized_status",
        "display_status",
    ),
    "ai_inventory": (
        "organization_id",
        "id",
        "snapshot_date",
        "warehouse_id",
        "warehouse_external_id",
        "warehouse_code",
        "product_id",
        "product_external_id",
        "product_code",
        "product_name",
        "quantity",
        "available_quantity",
        "reserved_quantity",
        "valuation_amount",
        "currency_code",
        "inventory_kind",
        "measure_code",
    ),
    "ai_finance": (
        "organization_id",
        "id",
        "operation_id",
        "operation_at",
        "operation_date",
        "normalized_operation_type",
        "direction",
        "amount",
        "currency_code",
        "counterparty_external_id",
        "counterparty_name",
        "posted",
    ),
    "ai_organizations": (
        "organization_id",
        "name",
        "company_id",
        "filial_id",
        "filial_code",
        "project_code",
        "is_active",
        "sort_order",
    ),
}
_AI_PUBLISHED_COLUMNS.update(META_VIEW_COLUMNS)
_AI_PUBLISHED_COLUMNS.update(YOUTUBE_VIEW_COLUMNS)

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
_AI_VIEW_GRAINS.update(
    {
        "ai_meta_ad_accounts": "one Meta ad account",
        "ai_meta_campaigns": "one Meta campaign",
        "ai_meta_adsets": "one Meta ad set",
        "ai_meta_ads": "one Meta ad",
        "ai_meta_ads_daily": "one daily Meta insight grain and breakdown",
        "ai_instagram_accounts": "one Instagram professional account",
        "ai_instagram_media": "one Instagram media item",
        "ai_instagram_media_daily": "one daily Instagram media insight",
        "ai_facebook_pages": "one Facebook Page",
        "ai_facebook_posts": "one Facebook Page post",
        "ai_facebook_posts_daily": "one daily Facebook post insight",
    }
)
_AI_VIEW_GRAINS.update(
    {
        "ai_youtube_channels": "one YouTube channel",
        "ai_youtube_videos": "one YouTube video",
        "ai_youtube_channel_daily": "one channel reporting day",
        "ai_youtube_video_daily": "one video reporting day",
    }
)

_AI_DATE_SEMANTICS = {
    "ai_sales": {
        "event_date_column": "sale_at",
        "meaning": "Realization event time; filter by the supplied business period.",
    },
    "ai_orders": {
        "event_date_column": "order_at",
        "meaning": "Order creation/business event time.",
    },
    "ai_returns": {"event_date_column": "return_at", "meaning": "Return event time."},
    "ai_visits": {
        "event_date_column": "visit_date",
        "meaning": "Authoritative business visit date; timestamptz interpreted in the system/business timezone.",
    },
    "ai_inventory": {
        "event_date_column": "snapshot_date",
        "meaning": "Inventory snapshot timestamp, not a movement event.",
    },
    "ai_finance": {
        "event_date_column": "operation_at",
        "meaning": "Financial operation event time.",
    },
}
_AI_DATE_SEMANTICS.update(
    {
        "ai_meta_ads_daily": {
            "event_date_column": "date_start",
            "meaning": "Meta account reporting date in the ad account timezone.",
        },
        "ai_instagram_media_daily": {
            "event_date_column": "date_start",
            "meaning": "Organic Instagram reporting date.",
        },
        "ai_facebook_posts_daily": {
            "event_date_column": "date_start",
            "meaning": "Organic Facebook reporting date.",
        },
    }
)
_AI_DATE_SEMANTICS.update(
    {
        "ai_youtube_channel_daily": {"event_date_column": "date", "meaning": "YouTube Analytics reporting day."},
        "ai_youtube_video_daily": {"event_date_column": "date", "meaning": "YouTube Analytics reporting day."},
    }
)

_AI_ENTITY_CONTRACTS: dict[str, dict[str, object]] = {
    "ai_organizations": {
        "identity": ["organization_id"],
        "dimensions": [
            "name",
            "company_id",
            "filial_id",
            "filial_code",
            "project_code",
            "is_active",
        ],
        "measures": [],
        "labels": ["name", "filial_code", "project_code"],
        "organization_behavior": "One row is the organization/filial scope itself; organization_id is globally scoped.",
    },
    "ai_sales": {
        "identity": ["organization_id", "id"],
        "dimensions": [
            "organization_id",
            "sale_id",
            "sales_rep_id",
            "sales_rep_external_id",
            "customer_id",
            "customer_external_id",
            "order_id",
            "deal_id",
            "normalized_status",
            "currency_code",
        ],
        "measures": ["total_amount", "sold_quantity", "returned_quantity"],
        "labels": ["sales_rep_name", "customer_name"],
        "organization_behavior": "Sale identity is organization_id + canonical sale id. Never join sale identifiers across organizations.",
    },
    "ai_sale_items": {
        "identity": ["organization_id", "sale_id", "product_id", "line_number"],
        "dimensions": [
            "organization_id",
            "sale_id",
            "order_id",
            "product_id",
            "product_external_id",
            "product_code",
            "warehouse_id",
            "warehouse_external_id",
            "warehouse_code",
            "currency_code",
        ],
        "measures": [
            "ordered_quantity",
            "sold_quantity",
            "returned_quantity",
            "unit_price",
            "amount",
            "margin_amount",
        ],
        "labels": ["product_name"],
        "organization_behavior": "Line identity and every product/warehouse link are scoped by organization_id.",
    },
    "ai_orders": {
        "identity": ["organization_id", "id"],
        "dimensions": [
            "organization_id",
            "order_id",
            "deal_id",
            "sales_rep_id",
            "sales_rep_external_id",
            "customer_id",
            "customer_external_id",
            "normalized_status",
            "currency_code",
        ],
        "measures": ["total_amount", "ordered_quantity", "sold_quantity", "item_count"],
        "labels": ["customer_name"],
        "organization_behavior": "Order identity is organization_id + canonical order id.",
    },
    "ai_products": {
        "identity": ["organization_id", "id"],
        "dimensions": [
            "organization_id",
            "product_id",
            "code",
            "article_code",
            "producer_code",
            "state",
            "source_kind",
            "measure_code",
            "gtin",
            "ikpu",
        ],
        "measures": [],
        "labels": ["name", "short_name"],
        "organization_behavior": "Product identity is organization_id + canonical product id; source codes are not global keys.",
    },
    "ai_customers": {
        "identity": ["organization_id", "id"],
        "dimensions": ["organization_id", "person_id", "code", "state", "customer_kind", "tin"],
        "measures": [],
        "labels": ["name", "short_name", "main_phone", "email"],
        "organization_behavior": "Customer identity is organization_id + canonical customer id.",
    },
    "ai_returns": {
        "identity": ["organization_id", "return_id"],
        "dimensions": [
            "organization_id",
            "return_id",
            "deal_id",
            "sales_rep_id",
            "sales_rep_external_id",
            "customer_id",
            "customer_external_id",
            "normalized_status",
            "linked_order_id",
            "linked_order_external_id",
            "currency_code",
        ],
        "measures": ["total_amount", "returned_quantity", "item_count"],
        "labels": ["customer_name"],
        "organization_behavior": "Return identity is deduplicated at the published view while organization_id remains part of every cross-entity link.",
    },
    "ai_visits": {
        "identity": ["organization_id", "id"],
        "dimensions": [
            "organization_id",
            "visit_id",
            "sales_rep_id",
            "sales_rep_external_id",
            "customer_id",
            "customer_external_id",
            "working_zone_id",
            "working_zone_external_id",
            "normalized_status",
            "display_status",
        ],
        "measures": [],
        "labels": ["sales_rep_name", "customer_name"],
        "organization_behavior": "Visit identity is deduplicated at the published view; organization_id is retained for scope and joins.",
    },
    "ai_inventory": {
        "identity": ["organization_id", "warehouse_id", "product_id", "snapshot_date", "grain_key"],
        "dimensions": [
            "organization_id",
            "warehouse_id",
            "warehouse_external_id",
            "warehouse_code",
            "product_id",
            "product_external_id",
            "product_code",
            "inventory_kind",
            "measure_code",
            "currency_code",
        ],
        "measures": ["quantity", "available_quantity", "reserved_quantity", "valuation_amount"],
        "labels": ["product_name"],
        "organization_behavior": "Balance identity is organization_id + warehouse/product grain; snapshot_date is temporal state, not a movement event.",
    },
    "ai_finance": {
        "identity": ["organization_id", "id"],
        "dimensions": [
            "organization_id",
            "operation_id",
            "normalized_operation_type",
            "direction",
            "currency_code",
            "counterparty_external_id",
            "posted",
        ],
        "measures": ["amount"],
        "labels": ["counterparty_name"],
        "organization_behavior": "Financial operation identity is organization_id + canonical operation id.",
    },
}
for _meta_view, _meta_columns in META_VIEW_COLUMNS.items():
    _AI_ENTITY_CONTRACTS.setdefault(
        _meta_view,
        {
            "identity": ["organization_id", "external_id"],
            "dimensions": [
                column
                for column in _meta_columns
                if column.endswith("_id")
                or column.endswith("_type")
                or column in {"currency", "timezone", "status", "breakdown_key", "breakdown_value"}
            ],
            "measures": [
                column
                for column in _meta_columns
                if column
                in {
                    "spend",
                    "impressions",
                    "reach",
                    "frequency",
                    "clicks",
                    "unique_clicks",
                    "ctr",
                    "cpc",
                    "cpm",
                    "views",
                    "likes",
                    "comments",
                    "shares",
                    "saves",
                    "interactions",
                    "engaged_users",
                    "reactions",
                }
            ],
            "labels": [
                column
                for column in _meta_columns
                if column in {"name", "username", "caption", "message", "permalink"}
            ],
            "domain": "marketing" if "meta_" in _meta_view else "social",
            "source": "meta"
            if "meta_" in _meta_view
            else ("instagram" if "instagram" in _meta_view else "facebook"),
            "organization_behavior": "Explicit AI Business OS organization mapping; never infer scope from resource names.",
            "date_semantics": {
                "event_date_column": "date_start",
                "meaning": "Source reporting date; preserve source timezone semantics.",
            },
        },
    )

for _youtube_view, _youtube_columns in YOUTUBE_VIEW_COLUMNS.items():
    _AI_ENTITY_CONTRACTS.setdefault(
        _youtube_view,
        {
            "identity": ["organization_id", "id"],
            "dimensions": [column for column in _youtube_columns if column.endswith("_id") or column in {"country", "privacy_status", "content_type"}],
            "measures": [column for column in _youtube_columns if column in {"subscriber_count", "video_count", "view_count", "views", "estimated_minutes_watched", "average_view_duration", "average_view_percentage", "likes", "comments", "shares", "subscribers_gained", "subscribers_lost"}],
            "labels": [column for column in _youtube_columns if column in {"title", "description", "custom_url"}],
            "domain": "video",
            "source": "youtube",
            "organization_behavior": "Explicit AI Business OS channel mapping; never infer organization from channel name.",
            "date_semantics": {"event_date_column": "date", "meaning": "YouTube reporting date."},
        },
    )


class SemanticBusinessGraphRegistry:
    """Extensible metadata registry kept separate from SQL authorization."""

    def __init__(self, definitions: dict[str, dict[str, object]] | None = None) -> None:
        self._definitions = dict(definitions or {})

    def get(self, dataset: str) -> dict[str, object] | None:
        definition = self._definitions.get(dataset)
        return dict(definition) if definition is not None else None

    def names(self) -> tuple[str, ...]:
        return tuple(self._definitions)

    def register(
        self,
        dataset: str,
        *,
        meaning: str,
        grain: str,
        domain: str,
        source: str,
        identity: list[str] | tuple[str, ...] = (),
        dimensions: list[str] | tuple[str, ...] = (),
        measures: list[str] | tuple[str, ...] = (),
        labels: list[str] | tuple[str, ...] = (),
        organization_behavior: str = "organization scope is defined by the published dataset contract",
        date_semantics: dict[str, str] | None = None,
    ) -> None:
        """Register semantic metadata; this does not authorize SQL access."""

        if not re.fullmatch(r"ai_[a-z][a-z0-9_]*", dataset):
            raise ValueError("Semantic datasets must use an ai_* identifier.")
        self._definitions[dataset] = {
            "meaning": meaning,
            "grain": grain,
            "domain": domain,
            "source": source,
            "identity": list(identity),
            "dimensions": list(dimensions),
            "measures": list(measures),
            "labels": list(labels),
            "organization_behavior": organization_behavior,
            "date_semantics": dict(date_semantics or {}),
        }


ai_semantic_graph_registry = SemanticBusinessGraphRegistry(_AI_ENTITY_CONTRACTS)

_AI_COLUMN_SEMANTICS = {
    "ai_sales": {
        "organization_id": {"kind": "identifier", "meaning": "Canonical organization scope."},
        "id": {
            "kind": "identifier",
            "meaning": "Canonical sale row identifier; joins to ai_sale_items.sale_id.",
        },
        "sale_id": {"kind": "identifier", "meaning": "Canonical realized sale identifier."},
        "sale_at": {"kind": "date", "meaning": "Sale realization timestamp."},
        "closed_at": {"kind": "date", "meaning": "Sale closing timestamp when available."},
        "sales_rep_id": {
            "kind": "identifier",
            "meaning": "Canonical sales representative identifier.",
        },
        "sales_rep_external_id": {
            "kind": "identifier",
            "meaning": "Source sales representative identifier.",
        },
        "sales_rep_name": {
            "kind": "label",
            "meaning": "Sales representative name resolved from canonical sales reps.",
        },
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
        "visit_date": {
            "kind": "date",
            "meaning": "Authoritative business date for visit period filtering; stored as timestamptz.",
        },
        "visited_at": {"kind": "date", "meaning": "Visit event timestamp when available."},
        "sales_rep_external_id": {
            "kind": "identifier",
            "meaning": "Source representative identifier.",
        },
        "sales_rep_name": {"kind": "label", "meaning": "Human-readable representative name."},
        "normalized_status": {"kind": "dimension", "meaning": "Canonical visit completion/status."},
    },
    "ai_products": {
        "id": {
            "kind": "identifier",
            "meaning": "Canonical product identifier; target of ai_sale_items.product_id.",
        },
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
    {
        "from": "ai_sales.organization_id",
        "to": "ai_organizations.organization_id",
        "from_key": ["organization_id"],
        "to_key": ["organization_id"],
        "cardinality": "many-to-one",
        "organization_scope": "global organization identity",
        "meaning": "Every sale belongs to one published organization.",
    },
    {
        "from": "ai_sales.(organization_id,id)",
        "to": "ai_sale_items.(organization_id,sale_id)",
        "from_key": ["organization_id", "id"],
        "to_key": ["organization_id", "sale_id"],
        "cardinality": "one-to-many",
        "organization_scope": "compound organization_id plus sale identifier",
        "meaning": "A realized sale contains its line items.",
    },
    {
        "from": "ai_sales.(organization_id,order_id)",
        "to": "ai_orders.(organization_id,id)",
        "from_key": ["organization_id", "order_id"],
        "to_key": ["organization_id", "id"],
        "cardinality": "many-to-one",
        "organization_scope": "compound organization_id plus order identifier",
        "meaning": "A realized sale may reference its source order.",
    },
    {
        "from": "ai_sales.(organization_id,customer_id)",
        "to": "ai_customers.(organization_id,id)",
        "from_key": ["organization_id", "customer_id"],
        "to_key": ["organization_id", "id"],
        "cardinality": "many-to-one",
        "organization_scope": "compound organization_id plus customer identifier",
        "meaning": "A sale may reference its customer.",
    },
    {
        "from": "ai_sale_items.(organization_id,product_id)",
        "to": "ai_products.(organization_id,id)",
        "from_key": ["organization_id", "product_id"],
        "to_key": ["organization_id", "id"],
        "cardinality": "many-to-one",
        "organization_scope": "compound organization_id plus product identifier",
        "meaning": "A sale line references its product.",
    },
    {
        "from": "ai_sale_items.(organization_id,warehouse_id,product_id)",
        "to": "ai_inventory.(organization_id,warehouse_id,product_id)",
        "from_key": ["organization_id", "warehouse_id", "product_id"],
        "to_key": ["organization_id", "warehouse_id", "product_id"],
        "cardinality": "many-to-many-over-time",
        "organization_scope": "compound organization_id plus warehouse/product grain",
        "meaning": "A sale line can be compared with inventory balance snapshots.",
    },
    {
        "from": "ai_returns.(organization_id,linked_order_id)",
        "to": "ai_orders.(organization_id,id)",
        "from_key": ["organization_id", "linked_order_id"],
        "to_key": ["organization_id", "id"],
        "cardinality": "many-to-one",
        "organization_scope": "compound organization_id plus order identifier",
        "meaning": "A return may reference its source order.",
    },
    {
        "from": "ai_returns.(organization_id,customer_id)",
        "to": "ai_customers.(organization_id,id)",
        "from_key": ["organization_id", "customer_id"],
        "to_key": ["organization_id", "id"],
        "cardinality": "many-to-one",
        "organization_scope": "compound organization_id plus customer identifier",
        "meaning": "A return may reference its customer.",
    },
    {
        "from": "ai_visits.(organization_id,customer_id)",
        "to": "ai_customers.(organization_id,id)",
        "from_key": ["organization_id", "customer_id"],
        "to_key": ["organization_id", "id"],
        "cardinality": "many-to-one",
        "organization_scope": "compound organization_id plus customer identifier",
        "meaning": "A field visit may reference its customer.",
    },
    {
        "from": "ai_products.(organization_id,id)",
        "to": "ai_inventory.(organization_id,product_id)",
        "from_key": ["organization_id", "id"],
        "to_key": ["organization_id", "product_id"],
        "cardinality": "one-to-many-over-time",
        "organization_scope": "compound organization_id plus product identifier",
        "meaning": "A product can have inventory balances.",
    },
    {
        "from": "ai_finance.organization_id",
        "to": "ai_organizations.organization_id",
        "from_key": ["organization_id"],
        "to_key": ["organization_id"],
        "cardinality": "many-to-one",
        "organization_scope": "global organization identity",
        "meaning": "A financial operation belongs to one published organization.",
    },
    {
        "from": "ai_meta_ad_accounts.organization_id",
        "to": "ai_organizations.organization_id",
        "from_key": ["organization_id"],
        "to_key": ["organization_id"],
        "cardinality": "many-to-one",
        "organization_scope": "explicit organization mapping",
        "meaning": "A Meta ad account is mapped explicitly to an AI Business OS organization.",
    },
    {
        "from": "ai_meta_campaigns.(organization_id,ad_account_id)",
        "to": "ai_meta_ad_accounts.(organization_id,external_id)",
        "from_key": ["organization_id", "ad_account_id"],
        "to_key": ["organization_id", "external_id"],
        "cardinality": "many-to-one",
        "organization_scope": "same organization and account",
        "meaning": "Campaigns belong to a mapped Meta ad account.",
    },
    {
        "from": "ai_meta_adsets.(organization_id,campaign_id)",
        "to": "ai_meta_campaigns.(organization_id,external_id)",
        "from_key": ["organization_id", "campaign_id"],
        "to_key": ["organization_id", "external_id"],
        "cardinality": "many-to-one",
        "organization_scope": "same organization and campaign",
        "meaning": "Ad sets belong to a campaign.",
    },
    {
        "from": "ai_meta_ads.(organization_id,ad_set_id)",
        "to": "ai_meta_adsets.(organization_id,id)",
        "from_key": ["organization_id", "ad_set_id"],
        "to_key": ["organization_id", "id"],
        "cardinality": "many-to-one",
        "organization_scope": "same organization and ad set",
        "meaning": "Ads belong to an ad set.",
    },
    {
        "from": "ai_instagram_media.(organization_id,account_id)",
        "to": "ai_instagram_accounts.(organization_id,id)",
        "from_key": ["organization_id", "account_id"],
        "to_key": ["organization_id", "id"],
        "cardinality": "many-to-one",
        "organization_scope": "same organization and account",
        "meaning": "Instagram media belongs to a professional account.",
    },
    {
        "from": "ai_facebook_posts.(organization_id,page_id)",
        "to": "ai_facebook_pages.(organization_id,id)",
        "from_key": ["organization_id", "page_id"],
        "to_key": ["organization_id", "id"],
        "cardinality": "many-to-one",
        "organization_scope": "same organization and page",
        "meaning": "Facebook posts belong to a Page.",
    },
)


def _published_metadata(metadata: object, published_names: set[str]) -> list[str]:
    """Return only contract fields that are present in the live published view."""

    if not isinstance(metadata, list):
        return []
    return [name for name in metadata if isinstance(name, str) and name in published_names]


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
            item.get("name")
            for item in (published.get("columns", []) if isinstance(published, dict) else [])
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
