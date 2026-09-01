from app.core.ai_readonly_sql import ALLOWED_VIEWS, AIReadOnlySQLService, ai_semantic_graph_registry
from app.core.data_layer.service import InMemoryCoreDataLayer
from app.integrations.youtube.service import YouTubeMarketingService


class FakeYouTubeClient:
    def channels(self):
        return [
            {
                "id": "channel-1",
                "snippet": {"title": "Main Channel"},
                "statistics": {"viewCount": "10"},
            }
        ]


def test_youtube_connection_and_mapping_are_backend_only():
    store = InMemoryCoreDataLayer()
    service = YouTubeMarketingService(store, client=FakeYouTubeClient())
    result = service.connect()
    assert result["status"] == "connected"
    assert "access_token" not in str(result)
    service.map_channel("org-1", "channel-1")
    service.map_channel("org-1", "channel-1")
    assert len(store.list_source_records("youtube_resource_mappings")) == 1


def test_youtube_views_and_semantic_contract_are_available_without_attribution():
    assert {
        "ai_youtube_channels",
        "ai_youtube_videos",
        "ai_youtube_channel_daily",
        "ai_youtube_video_daily",
    }.issubset(ALLOWED_VIEWS)
    environment = AIReadOnlySQLService(InMemoryCoreDataLayer()).semantic_environment(
        include_columns=False
    )
    assert ai_semantic_graph_registry.get("ai_youtube_video_daily")["source"] == "youtube"
    assert any(item["name"] == "ai_youtube_video_daily" for item in environment["datasets"])
    assert not any(
        "youtube" in name and "sale" in name for name in ai_semantic_graph_registry.names()
    )
