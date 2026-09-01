"""Meta connection, discovery, explicit mapping and resumable sync orchestration."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.integrations.meta.client import MetaAPIError, MetaGraphClient
from app.integrations.meta.config import MetaConfig
from app.integrations.meta.repository import MetaRepository


class MetaMarketingService:
    def __init__(
        self, store: Any, *, config: MetaConfig | None = None, client: MetaGraphClient | None = None
    ) -> None:
        self.store = store
        self.config = config or MetaConfig.from_env()
        self.client = client or MetaGraphClient(self.config)
        self.repository = MetaRepository(store)

    def status(self) -> dict[str, Any]:
        rows = self.repository.list("meta_connections")
        if not rows:
            return {
                "status": "not_configured",
                "configured": self.config.configured,
                "resources": [],
                "mappings": [],
            }
        connection = rows[0]
        resources = []
        for table, kind in (
            ("meta_ad_accounts", "ad_account"),
            ("meta_facebook_pages", "facebook_page"),
            ("meta_instagram_accounts", "instagram_account"),
        ):
            resources.extend({**row, "resource_type": kind} for row in self.repository.list(table))
        return {
            "status": connection.get("status", "connected"),
            "configured": True,
            "last_success_at": connection.get("last_success_at"),
            "last_error": connection.get("last_error"),
            "resources": resources,
            "mappings": self.repository.list("meta_resource_mappings"),
        }

    def connect(self) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        existing = self.repository.list("meta_connections")
        connection_id = str(existing[0]["id"]) if existing else str(uuid4())
        try:
            me = self.client.get("me", fields="id,name")
            account_rows = self.client.ad_accounts()
            page_rows = self.client.pages()
            self.repository.upsert(
                "meta_connections",
                {
                    "id": connection_id,
                    "status": "connected",
                    "meta_user_id": str(me.get("id") or ""),
                    "meta_user_name": str(me.get("name") or ""),
                    "created_at": (existing[0].get("created_at") if existing else now),
                    "updated_at": now,
                    "last_success_at": now,
                },
                ("id",),
            )
            for row in account_rows:
                self.repository.upsert(
                    "meta_ad_accounts",
                    {
                        "id": str(uuid4()),
                        "connection_id": connection_id,
                        "external_id": str(row.get("id")),
                        "name": row.get("name"),
                        "currency": row.get("currency"),
                        "timezone": row.get("timezone_name"),
                        "status": str(row.get("account_status") or "unknown"),
                        "created_at": now,
                        "updated_at": now,
                    },
                    ("connection_id", "external_id"),
                )
            for row in page_rows:
                ig = (
                    row.get("instagram_business_account")
                    if isinstance(row.get("instagram_business_account"), dict)
                    else {}
                )
                self.repository.upsert(
                    "meta_facebook_pages",
                    {
                        "id": str(uuid4()),
                        "connection_id": connection_id,
                        "external_id": str(row.get("id")),
                        "name": row.get("name"),
                        "category": row.get("category"),
                        "instagram_account_id": ig.get("id"),
                        "created_at": now,
                        "updated_at": now,
                    },
                    ("connection_id", "external_id"),
                )
                if ig.get("id"):
                    account = self.client.get(str(ig["id"]), fields="id,username,name")
                    self.repository.upsert(
                        "meta_instagram_accounts",
                        {
                            "id": str(uuid4()),
                            "connection_id": connection_id,
                            "external_id": str(ig["id"]),
                            "username": account.get("username"),
                            "name": account.get("name"),
                            "created_at": now,
                            "updated_at": now,
                        },
                        ("connection_id", "external_id"),
                    )
            return self.status()
        except MetaAPIError as exc:
            return {
                "status": "error",
                "configured": self.config.configured,
                "error": str(exc),
                "error_kind": exc.kind,
                "resources": [],
                "mappings": [],
            }

    def map_resource(
        self,
        *,
        organization_id: str,
        resource_type: str,
        external_id: str,
        display_name: str | None = None,
    ) -> dict[str, Any]:
        if resource_type not in {"ad_account", "facebook_page", "instagram_account"}:
            raise ValueError("Unsupported Meta resource type")
        row = {
            "id": str(uuid4()),
            "organization_id": organization_id,
            "resource_type": resource_type,
            "external_id": external_id,
            "display_name": display_name,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        self.repository.upsert(
            "meta_resource_mappings", row, ("organization_id", "resource_type", "external_id")
        )
        return row

    def sync(self, mode: str = "incremental", backfill_days: int = 7) -> dict[str, Any]:
        if mode not in {"incremental", "backfill"}:
            raise ValueError("Unsupported Meta sync mode")
        result = self.connect()
        if result.get("status") == "connected":
            try:
                self._sync_mapped_resources(min(max(backfill_days, 1), 365))
                result.update(
                    {
                        "sync_mode": mode,
                        "backfill_days": min(max(backfill_days, 1), 365),
                        "sync_status": "completed",
                    }
                )
            except MetaAPIError as exc:
                result.update(
                    {
                        "sync_mode": mode,
                        "sync_status": "partial",
                        "last_error": str(exc),
                        "error_kind": exc.kind,
                    }
                )
        else:
            result.update(
                {
                    "sync_mode": mode,
                    "backfill_days": min(max(backfill_days, 1), 365),
                    "sync_status": "failed",
                }
            )
        return result

    def _sync_mapped_resources(self, backfill_days: int) -> None:
        """Pull only explicitly mapped resources; every upsert is idempotent."""
        mappings = self.repository.list("meta_resource_mappings")
        now = datetime.now(timezone.utc).isoformat()
        from datetime import timedelta

        today = datetime.now(timezone.utc).date()
        since = (today - timedelta(days=backfill_days - 1)).isoformat()
        until = today.isoformat()
        for mapping in mappings:
            org = str(mapping["organization_id"])
            resource = str(mapping["external_id"])
            kind = mapping["resource_type"]
            if kind == "ad_account":
                account = next(
                    (
                        row
                        for row in self.repository.list("meta_ad_accounts")
                        if row.get("external_id") == resource
                    ),
                    None,
                )
                if not account:
                    continue
                account_id = str(account["id"])
                self.repository.upsert(
                    "meta_ad_accounts",
                    {**account, "organization_id": org, "updated_at": now},
                    ("connection_id", "external_id"),
                )
                campaigns = self.client.collection(
                    resource,
                    "campaigns",
                    fields="id,name,status,effective_status,objective,buying_type,start_time,stop_time,created_time,updated_time",
                )
                for campaign in campaigns:
                    campaign_id = str(uuid4())
                    self.repository.upsert(
                        "meta_campaigns",
                        {
                            "id": campaign_id,
                            "organization_id": org,
                            "ad_account_id": account_id,
                            "external_id": str(campaign.get("id")),
                            "name": campaign.get("name"),
                            "status": campaign.get("status"),
                            "effective_status": campaign.get("effective_status"),
                            "objective": campaign.get("objective"),
                            "buying_type": campaign.get("buying_type"),
                            "start_at": campaign.get("start_time"),
                            "stop_at": campaign.get("stop_time"),
                            "created_at": campaign.get("created_time") or now,
                            "updated_at": campaign.get("updated_time") or now,
                        },
                        ("organization_id", "ad_account_id", "external_id"),
                    )
                    campaign_row = next(
                        (
                            row
                            for row in self.repository.list("meta_campaigns", org)
                            if row.get("external_id") == str(campaign.get("id"))
                        ),
                        None,
                    )
                    if not campaign_row:
                        continue
                    for adset in self.client.collection(
                        str(campaign.get("id")),
                        "adsets",
                        fields="id,name,status,optimization_goal,billing_event,bid_strategy,daily_budget,lifetime_budget,start_time,end_time",
                    ):
                        self.repository.upsert(
                            "meta_ad_sets",
                            {
                                "id": str(uuid4()),
                                "organization_id": org,
                                "ad_account_id": account_id,
                                "campaign_id": str(campaign_row["id"]),
                                "external_id": str(adset.get("id")),
                                "name": adset.get("name"),
                                "status": adset.get("status"),
                                "optimization_goal": adset.get("optimization_goal"),
                                "billing_event": adset.get("billing_event"),
                                "bid_strategy": adset.get("bid_strategy"),
                                "daily_budget": adset.get("daily_budget"),
                                "lifetime_budget": adset.get("lifetime_budget"),
                                "start_at": adset.get("start_time"),
                                "end_at": adset.get("end_time"),
                                "created_at": now,
                                "updated_at": now,
                            },
                            ("organization_id", "ad_account_id", "external_id"),
                        )
                        adset_row = next(
                            (
                                row
                                for row in self.repository.list("meta_ad_sets", org)
                                if row.get("external_id") == str(adset.get("id"))
                            ),
                            None,
                        )
                        for ad in self.client.collection(
                            str(adset.get("id")), "ads", fields="id,name,status,creative"
                        ):
                            creative = (
                                ad.get("creative") if isinstance(ad.get("creative"), dict) else {}
                            )
                            self.repository.upsert(
                                "meta_ads",
                                {
                                    "id": str(uuid4()),
                                    "organization_id": org,
                                    "ad_account_id": account_id,
                                    "campaign_id": str(campaign_row["id"]),
                                    "ad_set_id": str(adset_row["id"]) if adset_row else None,
                                    "external_id": str(ad.get("id")),
                                    "name": ad.get("name"),
                                    "status": ad.get("status"),
                                    "creative_id": creative.get("id"),
                                    "created_at": now,
                                    "updated_at": now,
                                },
                                ("organization_id", "ad_account_id", "external_id"),
                            )
                for insight in self.client.insights(
                    resource,
                    since=since,
                    until=until,
                    level="account",
                    breakdowns=("publisher_platform",),
                ):
                    self._save_insight(org, account_id, insight, now)
            elif kind == "facebook_page":
                page_row = next(
                    (
                        row
                        for row in self.repository.list("meta_facebook_pages")
                        if row.get("external_id") == resource
                    ),
                    None,
                )
                page_id = str(page_row["id"]) if page_row else resource
                for post in self.client.collection(
                    resource, "posts", fields="id,message,permalink_url,created_time"
                ):
                    self.repository.upsert(
                        "meta_facebook_posts",
                        {
                            "id": str(uuid4()),
                            "organization_id": org,
                            "page_id": page_id,
                            "external_id": str(post.get("id")),
                            "message": post.get("message"),
                            "permalink": post.get("permalink_url"),
                            "published_at": post.get("created_time"),
                            "created_at": now,
                            "updated_at": now,
                        },
                        ("organization_id", "page_id", "external_id"),
                    )
            elif kind == "instagram_account":
                account = next(
                    (
                        row
                        for row in self.repository.list("meta_instagram_accounts")
                        if row.get("external_id") == resource
                    ),
                    None,
                )
                if not account:
                    continue
                for media in self.client.collection(
                    resource,
                    "media",
                    fields="id,media_type,media_product_type,caption,permalink,timestamp,shortcode",
                ):
                    self.repository.upsert(
                        "meta_instagram_media",
                        {
                            "id": str(uuid4()),
                            "organization_id": org,
                            "account_id": str(account["id"]),
                            "external_id": str(media.get("id")),
                            "media_type": media.get("media_type"),
                            "media_product_type": media.get("media_product_type"),
                            "caption": media.get("caption"),
                            "permalink": media.get("permalink"),
                            "published_at": media.get("timestamp"),
                            "shortcode": media.get("shortcode"),
                            "created_at": now,
                            "updated_at": now,
                        },
                        ("organization_id", "account_id", "external_id"),
                    )

    def _save_insight(
        self, organization_id: str, account_id: str, insight: dict[str, Any], now: str
    ) -> None:
        existing = next(
            (
                item
                for item in self.repository.list("meta_ads_insights_daily", organization_id)
                if item.get("ad_account_id") == account_id
                and item.get("date_start") == insight.get("date_start")
                and item.get("date_stop") == insight.get("date_stop")
                and item.get("breakdown_value") == insight.get("publisher_platform")
            ),
            None,
        )
        row = {
            "id": str(existing["id"]) if existing else str(uuid4()),
            "organization_id": organization_id,
            "ad_account_id": account_id,
            "entity_type": "account",
            "entity_external_id": account_id,
            "date_start": insight.get("date_start"),
            "date_stop": insight.get("date_stop"),
            "breakdown_key": "publisher_platform",
            "breakdown_value": insight.get("publisher_platform"),
            "currency": insight.get("currency"),
            **{
                key: insight.get(key)
                for key in (
                    "spend",
                    "impressions",
                    "reach",
                    "frequency",
                    "clicks",
                    "unique_clicks",
                    "ctr",
                    "cpc",
                    "cpm",
                )
            },
            "created_at": now,
            "updated_at": now,
        }
        self.repository.upsert(
            "meta_ads_insights_daily",
            row,
            (
                "organization_id",
                "ad_account_id",
                "entity_type",
                "entity_external_id",
                "date_start",
                "date_stop",
                "breakdown_key",
                "breakdown_value",
            ),
        )
        for action in insight.get("actions") or []:
            if not isinstance(action, dict) or not action.get("action_type"):
                continue
            action_values = {
                item.get("action_type"): item.get("value")
                for item in insight.get("action_values") or []
                if isinstance(item, dict)
            }
            costs = {
                item.get("action_type"): item.get("value")
                for item in insight.get("cost_per_action_type") or []
                if isinstance(item, dict)
            }
            self.repository.upsert(
                "meta_ads_insight_actions",
                {
                    "id": str(uuid4()),
                    "insight_id": row["id"],
                    "action_type": action.get("action_type"),
                    "value": action.get("value"),
                    "action_value": action_values.get(action.get("action_type")),
                    "cost_per_action": costs.get(action.get("action_type")),
                    "created_at": now,
                    "updated_at": now,
                },
                ("insight_id", "action_type"),
            )
