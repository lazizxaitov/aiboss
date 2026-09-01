from typing import Any

from app.integrations.youtube.schema import YOUTUBE_TABLES


class YouTubeRepository:
    def __init__(self, store: Any) -> None:
        self.store = store

    def upsert(self, table: str, values: dict[str, Any], keys: tuple[str, ...]) -> None:
        if table not in YOUTUBE_TABLES or not set(values).issubset(YOUTUBE_TABLES[table]):
            raise ValueError("Unsupported YouTube persistence shape")
        self.store.upsert_source_record(table, values, keys)

    def list(self, table: str, organization_id: str | None = None) -> list[dict[str, Any]]:
        if table not in YOUTUBE_TABLES:
            raise ValueError("Unsupported YouTube table")
        return self.store.list_source_records(table, organization_id)
