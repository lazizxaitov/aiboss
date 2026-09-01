"""Evidence-first attribution foundation; correlation is never promoted to attribution."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

EVIDENCE_TYPES = {
    "explicit_tracking_id", "click_id", "campaign_tracking_parameter",
    "platform_conversion_reference", "first_party_session", "first_party_lead",
    "first_party_order_link", "imported_conversion_link",
}
SOURCE_TABLES = {
    "meta": {"account": "meta_ad_accounts", "campaign": "meta_campaigns", "adset": "meta_ad_sets", "ad": "meta_ads"},
    "instagram": {"account": "meta_instagram_accounts", "media": "meta_instagram_media"},
    "facebook": {"page": "meta_facebook_pages", "post": "meta_facebook_posts"},
    "youtube": {"channel": "youtube_channels", "video": "youtube_videos"},
}
TARGET_TABLES = {"sale": "canonical_sales", "order": "canonical_orders", "customer": "canonical_customers"}


class AttributionError(ValueError):
    pass


class MarketingAttributionService:
    def __init__(self, store: Any) -> None:
        self.store = store

    def ingest(self, payload: dict[str, Any]) -> dict[str, Any]:
        required = ("organization_id", "source_platform", "source_entity_type", "source_entity_id", "target_entity_type", "target_entity_id", "evidence_type")
        if any(not payload.get(field) for field in required):
            raise AttributionError("Все поля доказательства attribution обязательны")
        evidence_type = str(payload["evidence_type"])
        if evidence_type not in EVIDENCE_TYPES:
            raise AttributionError("Неподдерживаемый тип attribution evidence")
        organization_id = str(payload["organization_id"])
        source_table = SOURCE_TABLES.get(str(payload["source_platform"]), {}).get(str(payload["source_entity_type"]))
        if not source_table or not self._source_exists(source_table, str(payload["source_entity_id"]), organization_id):
            raise AttributionError("Source entity не существует в mapped marketing data")
        target_table = TARGET_TABLES.get(str(payload["target_entity_type"]))
        if not target_table or not self._target_exists(target_table, str(payload["target_entity_id"]), organization_id):
            raise AttributionError("Target entity не существует в Canonical/Core scope")
        now = datetime.now(timezone.utc).isoformat()
        existing = next((item for item in self.store.list_source_records("marketing_attribution_evidence", organization_id) if all(str(item.get(field)) == str(payload[field]) for field in ("source_platform", "source_entity_type", "source_entity_id", "target_entity_type", "target_entity_id", "evidence_type"))), None)
        row = {
            "id": str(existing["id"]) if existing else str(uuid4()), "organization_id": organization_id,
            "source_platform": payload["source_platform"], "source_entity_type": payload["source_entity_type"], "source_entity_id": payload["source_entity_id"],
            "target_entity_type": payload["target_entity_type"], "target_entity_id": payload["target_entity_id"],
            "evidence_type": evidence_type, "confidence": payload.get("confidence") or "confirmed",
            "occurred_at": payload.get("occurred_at"), "attribution_window": payload.get("attribution_window"),
            "utm_source": payload.get("utm_source"), "utm_medium": payload.get("utm_medium"), "utm_campaign": payload.get("utm_campaign"), "utm_content": payload.get("utm_content"), "utm_term": payload.get("utm_term"), "click_id_hash": payload.get("click_id_hash"),
            "provenance": payload.get("provenance") or "first_party", "created_at": now, "updated_at": now,
        }
        self.store.upsert_source_record("marketing_attribution_evidence", row, ("organization_id", "source_platform", "source_entity_type", "source_entity_id", "target_entity_type", "target_entity_id", "evidence_type"))
        self._save_outcome(row, target_table, organization_id, now)
        return {"status": "confirmed", "evidence_id": row["id"], "organization_id": organization_id, "source_platform": row["source_platform"], "target_entity_type": row["target_entity_type"], "target_entity_id": row["target_entity_id"]}

    def _source_exists(self, table: str, external_id: str, organization_id: str) -> bool:
        return any(str(row.get("external_id")) == external_id and str(row.get("organization_id")) == organization_id for row in self.store.list_source_records(table, organization_id))

    def _target_exists(self, table: str, identity: str, organization_id: str) -> bool:
        method = getattr(self.store, "list_canonical_sales" if table == "canonical_sales" else "list_canonical_orders" if table == "canonical_orders" else "list_canonical_customers", None)
        if not callable(method):
            return False
        return any(str(getattr(row, "id", "")) == identity and str(getattr(row, "organization_id", "")) == organization_id for row in method())

    def _save_outcome(self, evidence: dict[str, Any], target_table: str, organization_id: str, now: str) -> None:
        if evidence["target_entity_type"] != "sale":
            return
        sale = next((row for row in self.store.list_canonical_sales() if str(getattr(row, "id", "")) == str(evidence["target_entity_id"])), None)
        if sale is None:
            return
        existing = next((item for item in self.store.list_source_records("marketing_attributed_outcomes", organization_id) if str(item.get("evidence_id")) == str(evidence["id"])), None)
        self.store.upsert_source_record("marketing_attributed_outcomes", {"id": str(existing["id"]) if existing else str(uuid4()), "organization_id": organization_id, "evidence_id": evidence["id"], "source_platform": evidence["source_platform"], "source_entity_type": evidence["source_entity_type"], "source_entity_id": evidence["source_entity_id"], "sale_id": evidence["target_entity_id"], "revenue": getattr(sale, "total_amount", None), "currency": getattr(sale, "currency_code", None), "occurred_at": evidence.get("occurred_at"), "created_at": now, "updated_at": now}, ("organization_id", "evidence_id", "sale_id"))
