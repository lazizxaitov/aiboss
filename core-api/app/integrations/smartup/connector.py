"""SmartUp connector architecture for future synchronization jobs."""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Protocol

from app.integrations.smartup.mapping import SMARTUP_CORE_MAPPING_V1, SmartUpMapping
from app.integrations.smartup.models import SmartUpMigrationMode
from app.integrations.smartup.profiles import get_request_profile

MAX_SMARTUP_HISTORY_WINDOW_DAYS = 7


class SmartUpTransport(Protocol):
    """Future transport interface for the SmartUp API client."""

    def fetch(self, mapping: SmartUpMapping, payload: dict[str, object]) -> dict[str, object]:
        """Execute a request and return decoded JSON data."""


@dataclass(frozen=True, slots=True)
class SmartUpSyncWindow:
    """Time window used by incremental SmartUp sync jobs."""

    begin: datetime
    end: datetime


@dataclass(frozen=True, slots=True)
class SmartUpSyncTask:
    """Single synchronization task derived from a mapping."""

    mapping_name: str
    endpoint: str
    method: str
    target_table: str
    entity_type: str
    sync_mode: str
    migration_mode: SmartUpMigrationMode
    payload_template: dict[str, object]
    window_start: datetime | None = None
    window_end: datetime | None = None
    window_days: int | None = None
    notes: tuple[str, ...] = ()


@dataclass(slots=True)
class SmartUpConnector:
    """Blueprint for a SmartUp connector.

    The connector does not call the API yet. It prepares the exact sync
    plan that a future transport implementation will execute.
    """

    base_url: str = "https://smartup.online"
    mappings: tuple[SmartUpMapping, ...] = SMARTUP_CORE_MAPPING_V1
    generated_at: datetime | None = None
    tasks: list[SmartUpSyncTask] = field(default_factory=list)

    def build_sync_plan(
        self,
        *,
        window: SmartUpSyncWindow | None = None,
        migration_mode: SmartUpMigrationMode = SmartUpMigrationMode.FULL_BACKFILL,
        history_start: datetime | None = None,
        history_end: datetime | None = None,
        chunk_days: int | None = None,
    ) -> list[SmartUpSyncTask]:
        """Build a deterministic sync plan from the registry."""

        if window is not None:
            tasks = self._build_tasks_with_fixed_window(
                self.mappings,
                migration_mode=migration_mode,
                window=window,
            )
            self.tasks = tasks
            return tasks

        tasks = self._build_tasks(
            self.mappings,
            migration_mode=migration_mode,
            history_start=history_start,
            history_end=history_end,
            chunk_days=chunk_days,
        )
        self.tasks = tasks
        return tasks

    def plan_for_group(
        self,
        group: str,
        *,
        window: SmartUpSyncWindow | None = None,
        migration_mode: SmartUpMigrationMode = SmartUpMigrationMode.FULL_BACKFILL,
        history_start: datetime | None = None,
        history_end: datetime | None = None,
        chunk_days: int | None = None,
    ) -> list[SmartUpSyncTask]:
        """Build a sync plan only for a functional group."""

        group_mappings = tuple(mapping for mapping in self.mappings if mapping.group == group)
        if window is not None:
            return self._build_tasks_with_fixed_window(
                group_mappings,
                migration_mode=migration_mode,
                window=window,
            )
        return self._build_tasks(
            group_mappings,
            migration_mode=migration_mode,
            history_start=history_start,
            history_end=history_end,
            chunk_days=chunk_days,
        )

    def build_history_plan(
        self,
        history_start: datetime,
        history_end: datetime | None = None,
        chunk_days: int = 7,
    ) -> list[SmartUpSyncTask]:
        """Build a full historical backfill plan.

        Endpoints that support date ranges are sliced into windows. Static
        reference endpoints are fetched once because they are not bounded by time.
        """

        return self.build_sync_plan(
            migration_mode=SmartUpMigrationMode.FULL_BACKFILL,
            history_start=history_start,
            history_end=history_end,
            chunk_days=chunk_days,
        )

    def _build_tasks(
        self,
        mappings: tuple[SmartUpMapping, ...],
        *,
        migration_mode: SmartUpMigrationMode,
        history_start: datetime | None,
        history_end: datetime | None,
        chunk_days: int | None,
    ) -> list[SmartUpSyncTask]:
        resolved_end = history_end or datetime.now(UTC)
        tasks: list[SmartUpSyncTask] = []
        for mapping in mappings:
            profile = get_request_profile(mapping.name)
            payload = self._base_payload(mapping)
            if self._is_snapshot_mapping(mapping):
                if (
                    profile is not None
                    and profile.page_size is not None
                    and profile.offset_param
                    and profile.limit_param
                ):
                    payload[profile.offset_param] = 0
                    payload[profile.limit_param] = profile.page_size
                tasks.append(
                    SmartUpSyncTask(
                        mapping_name=mapping.name,
                        endpoint=f"{self.base_url}{mapping.smartup_endpoint}",
                        method=mapping.smartup_method,
                        target_table=mapping.target_table,
                        entity_type=mapping.target_entity,
                        sync_mode=mapping.sync_mode,
                        migration_mode=migration_mode,
                        payload_template=payload,
                        notes=mapping.notes,
                    ),
                )
                continue
            if profile is not None and profile.supports_snapshot:
                tasks.append(
                    SmartUpSyncTask(
                        mapping_name=mapping.name,
                        endpoint=f"{self.base_url}{mapping.smartup_endpoint}",
                        method=mapping.smartup_method,
                        target_table=mapping.target_table,
                        entity_type=mapping.target_entity,
                        sync_mode=mapping.sync_mode,
                        migration_mode=migration_mode,
                        payload_template=payload,
                        notes=mapping.notes,
                    ),
                )
                continue

            if (
                profile is not None
                and profile.supports_history
                and profile.history_start_param
                and profile.history_end_param
                and history_start is not None
            ):
                window_size = self._initial_window_days(mapping, migration_mode, chunk_days)
                for window in self._iter_windows(history_start, resolved_end, window_size):
                    window_payload = dict(payload)
                    window_payload[profile.history_start_param] = _format_smartup_date(
                        window.begin,
                    )
                    window_payload[profile.history_end_param] = _format_smartup_date(window.end)
                    tasks.append(
                        SmartUpSyncTask(
                            mapping_name=mapping.name,
                            endpoint=f"{self.base_url}{mapping.smartup_endpoint}",
                            method=mapping.smartup_method,
                            target_table=mapping.target_table,
                            entity_type=mapping.target_entity,
                            sync_mode=mapping.sync_mode,
                            migration_mode=migration_mode,
                            payload_template=window_payload,
                            window_start=window.begin,
                            window_end=window.end,
                            window_days=window_size,
                            notes=mapping.notes,
                        ),
                    )
                continue

            if (
                profile is not None
                and profile.page_size is not None
                and profile.offset_param
                and profile.limit_param
            ):
                payload[profile.offset_param] = 0
                payload[profile.limit_param] = profile.page_size
                tasks.append(
                    SmartUpSyncTask(
                        mapping_name=mapping.name,
                        endpoint=f"{self.base_url}{mapping.smartup_endpoint}",
                        method=mapping.smartup_method,
                        target_table=mapping.target_table,
                        entity_type=mapping.target_entity,
                        sync_mode=mapping.sync_mode,
                        migration_mode=migration_mode,
                        payload_template=payload,
                        notes=mapping.notes,
                    ),
                )
                continue

            tasks.append(
                SmartUpSyncTask(
                    mapping_name=mapping.name,
                    endpoint=f"{self.base_url}{mapping.smartup_endpoint}",
                    method=mapping.smartup_method,
                    target_table=mapping.target_table,
                    entity_type=mapping.target_entity,
                    sync_mode=mapping.sync_mode,
                    migration_mode=migration_mode,
                    payload_template=payload,
                    notes=mapping.notes,
                ),
            )
        return tasks

    def _build_tasks_with_fixed_window(
        self,
        mappings: tuple[SmartUpMapping, ...],
        *,
        migration_mode: SmartUpMigrationMode,
        window: SmartUpSyncWindow,
    ) -> list[SmartUpSyncTask]:
        tasks: list[SmartUpSyncTask] = []
        for mapping in mappings:
            profile = get_request_profile(mapping.name)
            payload = self._base_payload(mapping)
            if profile is not None and profile.supports_history:
                if profile.history_start_param and profile.history_end_param:
                    payload[profile.history_start_param] = _format_smartup_date(window.begin)
                    payload[profile.history_end_param] = _format_smartup_date(window.end)
            elif (
                profile is not None
                and profile.page_size is not None
                and profile.offset_param
                and profile.limit_param
            ):
                payload[profile.offset_param] = 0
                payload[profile.limit_param] = profile.page_size
            tasks.append(
                SmartUpSyncTask(
                    mapping_name=mapping.name,
                    endpoint=f"{self.base_url}{mapping.smartup_endpoint}",
                    method=mapping.smartup_method,
                    target_table=mapping.target_table,
                    entity_type=mapping.target_entity,
                    sync_mode=mapping.sync_mode,
                    migration_mode=migration_mode,
                    payload_template=payload,
                    window_start=window.begin,
                    window_end=window.end,
                    window_days=max(1, (window.end - window.begin).days or 1),
                    notes=mapping.notes,
                ),
            )
        return tasks
    @staticmethod
    def _initial_window_days(
        mapping: SmartUpMapping,
        migration_mode: SmartUpMigrationMode,
        chunk_days: int | None,
    ) -> int:
        if mapping.name == "Orders":
            if migration_mode == SmartUpMigrationMode.ONE_DAY_CHECK:
                return 1
            if migration_mode == SmartUpMigrationMode.WEEKLY_RECONCILIATION:
                return 7
            if chunk_days is not None and chunk_days > 0:
                return max(1, chunk_days)
            return 30
        if migration_mode == SmartUpMigrationMode.ONE_DAY_CHECK:
            return 1
        if chunk_days is not None and chunk_days > 0:
            return min(chunk_days, MAX_SMARTUP_HISTORY_WINDOW_DAYS)
        if migration_mode == SmartUpMigrationMode.WEEKLY_RECONCILIATION:
            return 7
        return MAX_SMARTUP_HISTORY_WINDOW_DAYS

    @staticmethod
    def _base_payload(mapping: SmartUpMapping) -> dict[str, object]:
        return {
            "source_object": mapping.smartup_object,
            "target_table": mapping.target_table,
            "sync_mode": mapping.sync_mode,
            "key_fields": list(mapping.key_fields),
        }

    @staticmethod
    def _is_snapshot_mapping(mapping: SmartUpMapping) -> bool:
        return mapping.name in {
            "Inventory",
            "Product groups",
            "Price types",
            "Inventory prices",
            "Service export",
            "Producers",
            "Contracts",
            "Workspaces",
            "Person group export",
            "Return reason export",
        }

    @staticmethod
    def _iter_windows(
        start: datetime,
        end: datetime,
        chunk_days: int,
    ) -> list[SmartUpSyncWindow]:
        if chunk_days <= 0:
            msg = "chunk_days must be greater than zero"
            raise ValueError(msg)

        windows: list[SmartUpSyncWindow] = []
        current = start
        delta = timedelta(days=chunk_days)
        while current < end:
            window_end = min(current + delta, end)
            windows.append(SmartUpSyncWindow(begin=current, end=window_end))
            current = window_end
        return windows


def _format_smartup_date(value: datetime) -> str:
    """Format SmartUp dates in the documented dd.mm.yyyy format."""

    return value.date().strftime("%d.%m.%Y")
