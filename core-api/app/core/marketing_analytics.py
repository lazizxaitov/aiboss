"""Marketing Analytics: aggregates stored Meta (Instagram/ads) and YouTube
data into one read-optimized payload for the Marketing Analytics dashboard
page (repurposed from the old "Руководитель"/CEO placeholder page).

This intentionally does NOT go through `AIReadOnlySQLService` — that layer
forbids JOINs entirely, and showing "top Instagram posts" or "top YouTube
videos" needs joining media/video rows with their insight/analytics rows.
Instead this reads the same normalized tables directly through the existing
`MetaRepository`/`YouTubeRepository` (the same repositories the sync code
in `app/integrations/meta/service.py` and `app/integrations/youtube/service.py`
writes through) and joins them in Python — small, per-organization datasets,
so this is cheap and works identically against Postgres or the in-memory
test store.
"""

from __future__ import annotations

from typing import Any

from app.integrations.meta.repository import MetaRepository
from app.integrations.youtube.repository import YouTubeRepository


def _to_number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _to_int(value: Any) -> int:
    return int(_to_number(value))


class MarketingAnalyticsService:
    def __init__(self, store: Any) -> None:
        self.store = store
        self.meta = MetaRepository(store)
        self.youtube = YouTubeRepository(store)

    def build(self, organization_id: str | None = None) -> dict[str, Any]:
        instagram_posts = self._instagram_posts(organization_id)
        youtube_videos = self._youtube_videos(organization_id)
        meta_ads = self._meta_ads_summary(organization_id)

        summary = {
            "instagram_posts": len(instagram_posts),
            "instagram_total_reach": sum(item["reach"] for item in instagram_posts),
            "instagram_total_engagement": sum(item["engagement"] for item in instagram_posts),
            "youtube_videos": len(youtube_videos),
            "youtube_total_views": sum(item["views"] for item in youtube_videos),
            "meta_ad_spend": meta_ads["spend"],
            "meta_ad_impressions": meta_ads["impressions"],
        }
        return {
            "summary": summary,
            "top_instagram_posts": instagram_posts[:10],
            "top_youtube_videos": youtube_videos[:10],
            "meta_ads": meta_ads,
        }

    def _instagram_posts(self, organization_id: str | None) -> list[dict[str, Any]]:
        media_by_id = {row["id"]: row for row in self.meta.list("meta_instagram_media", organization_id)}
        accounts_by_id = {
            row["id"]: row for row in self.meta.list("meta_instagram_accounts", organization_id)
        }
        posts: dict[str, dict[str, Any]] = {}
        latest_date_stop: dict[str, str] = {}
        for insight in self.meta.list("meta_instagram_media_insights_daily", organization_id):
            media_id = insight.get("media_id")
            media = media_by_id.get(media_id)
            if not media or not media_id:
                continue
            date_stop = str(insight.get("date_stop") or "")
            if media_id in latest_date_stop and date_stop < latest_date_stop[media_id]:
                # Keep only the freshest snapshot per post (media insights are
                # point-in-time, not truly additive daily rows).
                continue
            latest_date_stop[media_id] = date_stop
            likes = _to_int(insight.get("likes"))
            comments = _to_int(insight.get("comments"))
            saves = _to_int(insight.get("saves"))
            shares = _to_int(insight.get("shares"))
            account = accounts_by_id.get(media.get("account_id"), {})
            posts[media_id] = {
                "external_id": media.get("external_id"),
                "caption": (media.get("caption") or "").strip()[:160],
                "media_type": media.get("media_type"),
                "permalink": media.get("permalink"),
                "published_at": media.get("published_at"),
                "account_username": account.get("username"),
                "likes": likes,
                "comments": comments,
                "reach": _to_int(insight.get("reach")),
                "impressions": _to_int(insight.get("impressions")),
                "saves": saves,
                "shares": shares,
                "engagement": likes + comments + saves + shares,
            }
        return sorted(posts.values(), key=lambda item: item["engagement"], reverse=True)

    def _youtube_videos(self, organization_id: str | None) -> list[dict[str, Any]]:
        videos_by_id = {row["id"]: row for row in self.youtube.list("youtube_videos", organization_id)}
        channels_by_id = {
            row["id"]: row for row in self.youtube.list("youtube_channels", organization_id)
        }
        totals: dict[str, dict[str, int]] = {}
        for row in self.youtube.list("youtube_video_analytics_daily", organization_id):
            video_id = row.get("video_id")
            if video_id not in videos_by_id:
                continue
            bucket = totals.setdefault(video_id, {"views": 0, "likes": 0, "comments": 0, "shares": 0})
            bucket["views"] += _to_int(row.get("views"))
            bucket["likes"] += _to_int(row.get("likes"))
            bucket["comments"] += _to_int(row.get("comments"))
            bucket["shares"] += _to_int(row.get("shares"))

        results: list[dict[str, Any]] = []
        for video_id, video in videos_by_id.items():
            stats = totals.get(video_id, {"views": 0, "likes": 0, "comments": 0, "shares": 0})
            channel = channels_by_id.get(video.get("channel_id"), {})
            results.append(
                {
                    "external_id": video.get("external_id"),
                    "title": video.get("title"),
                    "published_at": video.get("published_at"),
                    "channel_title": channel.get("title"),
                    **stats,
                }
            )
        results.sort(key=lambda item: item["views"], reverse=True)
        return results

    def _meta_ads_summary(self, organization_id: str | None) -> dict[str, Any]:
        spend = 0.0
        impressions = 0
        reach = 0
        clicks = 0
        for row in self.meta.list("meta_ads_insights_daily", organization_id):
            spend += _to_number(row.get("spend"))
            impressions += _to_int(row.get("impressions"))
            reach += _to_int(row.get("reach"))
            clicks += _to_int(row.get("clicks"))
        return {"spend": round(spend, 2), "impressions": impressions, "reach": reach, "clicks": clicks}
