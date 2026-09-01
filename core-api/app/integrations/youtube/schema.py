"""Normalized YouTube tables and safe AI projections."""

YOUTUBE_TABLES = {
    "youtube_connections": (
        "id",
        "status",
        "google_subject",
        "google_email",
        "scopes",
        "created_at",
        "updated_at",
        "last_success_at",
        "last_error",
    ),
    "youtube_resource_mappings": (
        "id",
        "organization_id",
        "channel_id",
        "display_name",
        "connection_id",
        "created_at",
        "updated_at",
    ),
    "youtube_channels": (
        "id",
        "organization_id",
        "connection_id",
        "external_id",
        "title",
        "description",
        "custom_url",
        "published_at",
        "country",
        "subscriber_count",
        "video_count",
        "view_count",
        "created_at",
        "updated_at",
    ),
    "youtube_videos": (
        "id",
        "organization_id",
        "channel_id",
        "external_id",
        "title",
        "description",
        "published_at",
        "duration",
        "category_id",
        "live_broadcast_content",
        "privacy_status",
        "content_type",
        "created_at",
        "updated_at",
    ),
    "youtube_channel_analytics_daily": (
        "id",
        "organization_id",
        "channel_id",
        "date",
        "views",
        "estimated_minutes_watched",
        "average_view_duration",
        "average_view_percentage",
        "likes",
        "comments",
        "shares",
        "subscribers_gained",
        "subscribers_lost",
        "created_at",
        "updated_at",
    ),
    "youtube_video_analytics_daily": (
        "id",
        "organization_id",
        "channel_id",
        "video_id",
        "date",
        "views",
        "estimated_minutes_watched",
        "average_view_duration",
        "average_view_percentage",
        "likes",
        "comments",
        "shares",
        "subscribers_gained",
        "subscribers_lost",
        "created_at",
        "updated_at",
    ),
}

_UNIQUE = {
    "youtube_resource_mappings": "UNIQUE (organization_id, channel_id)",
    "youtube_channels": "UNIQUE (connection_id, external_id)",
    "youtube_videos": "UNIQUE (organization_id, external_id)",
    "youtube_channel_analytics_daily": "UNIQUE (organization_id, channel_id, date)",
    "youtube_video_analytics_daily": "UNIQUE (organization_id, channel_id, video_id, date)",
}

YOUTUBE_DDL = tuple(
    f"CREATE TABLE IF NOT EXISTS {table} ("
    + ", ".join(
        f"{column} {'uuid' if column in {'id', 'connection_id', 'organization_id', 'channel_id', 'video_id'} else 'text'}"
        for column in columns
    )
    + ", PRIMARY KEY (id)"
    + (f", {_UNIQUE[table]}" if table in _UNIQUE else "")
    + ")"
    for table, columns in YOUTUBE_TABLES.items()
)

YOUTUBE_VIEW_DEFINITIONS = {
    "ai_youtube_channels": "SELECT organization_id, id, external_id, title, description, custom_url, published_at, country, subscriber_count, video_count, view_count FROM youtube_channels",
    "ai_youtube_videos": "SELECT organization_id, channel_id, id, external_id, title, description, published_at, duration, category_id, live_broadcast_content, privacy_status, content_type FROM youtube_videos",
    "ai_youtube_channel_daily": "SELECT organization_id, channel_id, date, views, estimated_minutes_watched, average_view_duration, average_view_percentage, likes, comments, shares, subscribers_gained, subscribers_lost FROM youtube_channel_analytics_daily",
    "ai_youtube_video_daily": "SELECT organization_id, channel_id, video_id, date, views, estimated_minutes_watched, average_view_duration, average_view_percentage, likes, comments, shares, subscribers_gained, subscribers_lost FROM youtube_video_analytics_daily",
}
YOUTUBE_VIEW_COLUMNS = {
    view: tuple(
        item.strip() for item in definition.split("SELECT ", 1)[1].split(" FROM ", 1)[0].split(",")
    )
    for view, definition in YOUTUBE_VIEW_DEFINITIONS.items()
}
