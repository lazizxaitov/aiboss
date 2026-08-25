"""Bootstrap SmartUp organizations from environment configuration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from logging import getLogger
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, Field

from app.core.data_layer.contracts import CoreDataStore
from app.integrations.smartup.filial_codes import (
    clear_unverified_filial_code,
    mark_verified_filial_code,
    resolve_filial_code,
)
from app.integrations.smartup.models import SMARTUP_INTEGRATION_UUID, SmartUpOrganization
from app.integrations.smartup.settings import SmartUpOrganizationConfig, SmartUpSettings

logger = getLogger(__name__)


class SmartUpEnvBootstrapResponse(BaseModel):
    """Response returned after syncing organizations from env."""

    source: str = "env"
    loaded: int
    organizations: list[SmartUpOrganization] = Field(default_factory=list)


@dataclass(slots=True)
class SmartUpEnvBootstrapResult:
    """Internal bootstrap result."""

    organizations: list[SmartUpOrganization]


def bootstrap_smartup_organizations_from_env(
    store: CoreDataStore,
    settings: SmartUpSettings | None = None,
) -> SmartUpEnvBootstrapResult:
    """Create or update SmartUp organizations from SMARTUP_ORGANIZATIONS."""

    smartup_settings = settings or SmartUpSettings()
    organizations = smartup_settings.organizations
    if not organizations:
        return SmartUpEnvBootstrapResult(organizations=[])

    existing = list(store.list_smartup_organizations(integration_id=SMARTUP_INTEGRATION_UUID))
    existing_by_key = {
        _organization_key(org.company_id, org.filial_id, org.project_code): org for org in existing
    }
    allowed_keys = {
        _organization_key(
            item.company_id.strip(),
            item.filial_id.strip(),
            item.project_code.strip(),
        )
        for item in organizations
    }

    synced: list[SmartUpOrganization] = []
    for sort_order, item in enumerate(organizations):
        normalized = _normalize_organization_config(item)
        match = existing_by_key.get(
            _organization_key(normalized.company_id, normalized.filial_id, normalized.project_code),
        )
        verified_raw_records = []
        if match is not None:
            verified_raw_records = list(store.list_smartup_raw_records(organization_id=match.id))
        organization_id = (
            match.id
            if match is not None
            else uuid5(
                NAMESPACE_URL,
                f"smartup:organization:{normalized.company_id}:{normalized.filial_id}:{normalized.project_code}",
            )
        )
        organization = SmartUpOrganization(
            id=organization_id,
            integration_id=SMARTUP_INTEGRATION_UUID,
            name=normalized.name,
            company_id=normalized.company_id,
            filial_id=normalized.filial_id,
            filial_code=(
                resolve_filial_code(match, verified_raw_records) if match is not None else None
            ),
            project_code=normalized.project_code,
            is_active=True,
            sort_order=sort_order,
            last_sync_at=match.last_sync_at if match is not None else None,
            created_at=match.created_at if match is not None else datetime.now(UTC),
            updated_at=datetime.now(UTC),
            metadata={
                **(match.metadata if match is not None else {}),
                "bootstrap_source": "env",
                "bootstrap_loaded_at": datetime.now(UTC).isoformat(),
            },
        )
        if normalized.filial_code:
            organization = mark_verified_filial_code(
                organization,
                normalized.filial_code,
                source="env",
            )
        organization = clear_unverified_filial_code(organization)
        store.upsert_smartup_organization(organization)
        synced.append(organization)

    for org in existing:
        if _organization_key(org.company_id, org.filial_id, org.project_code) not in allowed_keys:
            store.delete_smartup_organization(org.id)

    logger.info("Bootstrapped %s SmartUp organizations from env", len(synced))
    return SmartUpEnvBootstrapResult(organizations=synced)


def _normalize_organization_config(item: SmartUpOrganizationConfig) -> SmartUpOrganizationConfig:
    return SmartUpOrganizationConfig(
        name=item.name.strip(),
        company_id=item.company_id.strip(),
        filial_id=item.filial_id.strip(),
        filial_code=item.filial_code.strip() if item.filial_code else None,
        project_code=item.project_code.strip(),
    )


def _organization_key(company_id: str, filial_id: str, project_code: str) -> tuple[str, str, str]:
    return company_id.strip(), filial_id.strip(), project_code.strip()
