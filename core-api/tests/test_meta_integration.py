from typing import Any

from app.core.ai_readonly_sql import AIReadOnlySQLService, ALLOWED_VIEWS, ai_semantic_graph_registry
from app.core.data_layer.service import InMemoryCoreDataLayer
from app.integrations.meta.service import MetaMarketingService


class FakeMetaClient:
    def get(self, path: str, **params: Any) -> dict[str, Any]:
        if path == "me":
            return {"id": "u1", "name": "Owner"}
        return {"data": []}

    def ad_accounts(self) -> list[dict[str, Any]]:
        return [
            {
                "id": "act_1",
                "name": "Main",
                "currency": "UZS",
                "timezone_name": "Asia/Tashkent",
                "account_status": 1,
            }
        ]

    def pages(self) -> list[dict[str, Any]]:
        return [
            {
                "id": "page_1",
                "name": "Page",
                "category": "Retail",
                "instagram_business_account": {"id": "ig_1"},
            }
        ]


def test_meta_connect_does_not_expose_credentials_and_discovers_resources(monkeypatch):
    monkeypatch.setenv("META_ACCESS_TOKEN", "secret-token")
    store = InMemoryCoreDataLayer()
    result = MetaMarketingService(store, client=FakeMetaClient()).connect()
    assert result["status"] == "connected"
    assert "secret-token" not in str(result)
    assert {row["external_id"] for row in result["resources"]} == {"act_1", "page_1", "ig_1"}


def test_meta_mapping_is_explicit_and_deduplicated():
    store = InMemoryCoreDataLayer()
    service = MetaMarketingService(store, client=FakeMetaClient())
    first = service.map_resource(
        organization_id="org-1", resource_type="ad_account", external_id="act_1"
    )
    second = service.map_resource(
        organization_id="org-1", resource_type="ad_account", external_id="act_1"
    )
    assert first["external_id"] == second["external_id"]
    assert len(store.list_meta_records("meta_resource_mappings")) == 1


def test_meta_views_are_registered_and_are_not_sales_attribution():
    assert "ai_meta_ads_daily" in ALLOWED_VIEWS
    assert "ai_instagram_media_daily" in ALLOWED_VIEWS
    assert ai_semantic_graph_registry.get("ai_meta_campaigns")["domain"] == "marketing"
    assert not any("sale" in name and "meta" in name for name in ai_semantic_graph_registry.names())
    assert "access_token" not in str(AIReadOnlySQLService.catalog())
