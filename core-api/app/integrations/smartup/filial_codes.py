"""Verified SmartUp filial-code resolution helpers.

The SmartUp integration must never infer ``filial_code`` from ``filial_id`` or
reuse a code that is not explicitly proven for the current organization and
filial. These helpers centralize the verification logic so discovery, history
imports, and request builders all use the same source of truth.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from app.integrations.smartup.models import SmartUpOrganization, SmartUpRawRecord

_VERIFIED_FILIAL_CODE_BY_FILIAL_ID_KEY = "smartup_verified_filial_code_by_filial_id"
_VERIFIED_FILIAL_ID_KEY = "smartup_verified_filial_id"
_VERIFIED_FILIAL_CODE_KEY = "smartup_verified_filial_code"
_VERIFIED_FILIAL_CODE_SOURCE_KEY = "smartup_verified_filial_code_source"
_VERIFIED_FILIAL_CODE_RAW_RECORD_ID_KEY = "smartup_verified_filial_code_raw_record_id"


def clean_text(value: object | None) -> str | None:
    """Return a trimmed string or ``None`` when no usable value is present."""

    if value is None:
        return None
    text = str(value).strip()
    return text or None


def resolve_filial_code(
    organization: SmartUpOrganization,
    raw_records: Iterable[SmartUpRawRecord] | None = None,
) -> str | None:
    """Return the verified filial code for the current organization, if any."""

    filial_id = clean_text(getattr(organization, "filial_id", None))
    if not filial_id:
        return None

    metadata = getattr(organization, "metadata", None)
    if isinstance(metadata, dict):
        mapping = metadata.get(_VERIFIED_FILIAL_CODE_BY_FILIAL_ID_KEY)
        if isinstance(mapping, dict):
            entry = mapping.get(filial_id)
            if isinstance(entry, dict):
                entry_filial_id = clean_text(entry.get("filial_id"))
                entry_code = clean_text(entry.get("filial_code"))
                source = clean_text(
                    entry.get("source") or metadata.get(_VERIFIED_FILIAL_CODE_SOURCE_KEY),
                )
                if (
                    entry_filial_id == filial_id
                    and entry_code
                    and entry_code != filial_id
                    and source in {"env", "manual"}
                ):
                    return entry_code
                if (
                    entry_filial_id == filial_id
                    and entry_code
                    and entry_code != filial_id
                    and source == "order_export"
                    and raw_records is not None
                ):
                    discovered, _ = discover_verified_filial_code_from_raw_records(
                        raw_records,
                        filial_id,
                    )
                    if discovered == entry_code:
                        return entry_code

        verified_filial_id = clean_text(metadata.get(_VERIFIED_FILIAL_ID_KEY))
        verified_filial_code = clean_text(metadata.get(_VERIFIED_FILIAL_CODE_KEY))
        verified_source = clean_text(metadata.get(_VERIFIED_FILIAL_CODE_SOURCE_KEY))
        if (
            verified_filial_id == filial_id
            and verified_filial_code
            and verified_filial_code != filial_id
            and verified_source in {"env", "manual"}
        ):
            return verified_filial_code
        if (
            verified_filial_id == filial_id
            and verified_filial_code
            and verified_filial_code != filial_id
            and verified_source == "order_export"
            and raw_records is not None
        ):
            discovered, _ = discover_verified_filial_code_from_raw_records(
                raw_records,
                filial_id,
            )
            if discovered == verified_filial_code:
                return verified_filial_code

    return None


def get_verified_filial_code(
    organization: SmartUpOrganization,
    raw_records: Iterable[SmartUpRawRecord] | None = None,
) -> str | None:
    """Backward-compatible alias for the strict filial-code resolver."""

    return resolve_filial_code(organization, raw_records)


def mark_verified_filial_code(
    organization: SmartUpOrganization,
    filial_code: str,
    *,
    source: str,
    raw_record_id: UUID | None = None,
) -> SmartUpOrganization:
    """Persist a verified filial-code mapping on the organization metadata."""

    filial_id = clean_text(getattr(organization, "filial_id", None))
    resolved_code = clean_text(filial_code)
    if not filial_id or not resolved_code or resolved_code == filial_id:
        return organization

    metadata = dict(getattr(organization, "metadata", None) or {})
    mapping = metadata.get(_VERIFIED_FILIAL_CODE_BY_FILIAL_ID_KEY)
    if isinstance(mapping, dict):
        normalized_mapping = dict(mapping)
    else:
        normalized_mapping = {}
    normalized_mapping[filial_id] = {
        "filial_id": filial_id,
        "filial_code": resolved_code,
        "source": source,
        "raw_record_id": str(raw_record_id) if raw_record_id is not None else None,
        "verified_at": datetime.now(UTC).isoformat(),
    }
    metadata[_VERIFIED_FILIAL_CODE_BY_FILIAL_ID_KEY] = normalized_mapping
    metadata[_VERIFIED_FILIAL_ID_KEY] = filial_id
    metadata[_VERIFIED_FILIAL_CODE_KEY] = resolved_code
    metadata[_VERIFIED_FILIAL_CODE_SOURCE_KEY] = source
    if raw_record_id is not None:
        metadata[_VERIFIED_FILIAL_CODE_RAW_RECORD_ID_KEY] = str(raw_record_id)

    return organization.model_copy(
        update={
            "filial_code": resolved_code,
            "metadata": metadata,
            "updated_at": datetime.now(UTC),
        },
    )


def clear_unverified_filial_code(
    organization: SmartUpOrganization,
) -> SmartUpOrganization:
    """Clear stale filial-code metadata that is not backed by verified evidence."""

    filial_id = clean_text(getattr(organization, "filial_id", None))
    if not filial_id:
        return organization

    if resolve_filial_code(organization):
        return organization

    metadata = dict(getattr(organization, "metadata", None) or {})
    metadata.pop(_VERIFIED_FILIAL_ID_KEY, None)
    metadata.pop(_VERIFIED_FILIAL_CODE_KEY, None)
    metadata.pop(_VERIFIED_FILIAL_CODE_SOURCE_KEY, None)
    metadata.pop(_VERIFIED_FILIAL_CODE_RAW_RECORD_ID_KEY, None)

    mapping = metadata.get(_VERIFIED_FILIAL_CODE_BY_FILIAL_ID_KEY)
    if isinstance(mapping, dict):
        normalized_mapping = {
            key: value for key, value in mapping.items() if clean_text(key) != filial_id
        }
        if normalized_mapping:
            metadata[_VERIFIED_FILIAL_CODE_BY_FILIAL_ID_KEY] = normalized_mapping
        else:
            metadata.pop(_VERIFIED_FILIAL_CODE_BY_FILIAL_ID_KEY, None)

    if getattr(organization, "filial_code", None) is None and metadata == getattr(
        organization,
        "metadata",
        None,
    ):
        return organization

    return organization.model_copy(
        update={
            "filial_code": None,
            "metadata": metadata,
            "updated_at": datetime.now(UTC),
        },
    )


def discover_verified_filial_code_from_raw_records(
    raw_records: list[SmartUpRawRecord] | tuple[SmartUpRawRecord, ...] | Any,
    expected_filial_id: str,
) -> tuple[str | None, UUID | None]:
    """Find a verified ``filial_code`` from raw records for one filial.

    The code is accepted only when it appears in the same record node that also
    contains a matching ``filial_id``. This prevents accidental reuse of a code
    from another filial nested in contaminated payloads.
    """

    normalized_expected = clean_text(expected_filial_id)
    if not normalized_expected:
        return None, None

    for record in raw_records:
        if not _is_trusted_filial_code_record(record, normalized_expected):
            continue
        payload = getattr(record, "response_envelope", None) or getattr(
            record,
            "response_payload",
            None,
        )
        discovered = _discover_verified_filial_code_from_payload(payload, normalized_expected)
        if discovered:
            return discovered, getattr(record, "id", None)
    return None, None


def _is_trusted_filial_code_record(record: SmartUpRawRecord, expected_filial_id: str) -> bool:
    requested = clean_text(getattr(record, "request_filial_id", None))
    source = clean_text(getattr(record, "filial_id", None))
    response = clean_text(getattr(record, "response_filial_id", None))
    return (
        requested in {None, expected_filial_id}
        and source in {None, expected_filial_id}
        and (response in {None, expected_filial_id})
    )


def _discover_verified_filial_code_from_payload(
    payload: object, expected_filial_id: str
) -> str | None:
    if isinstance(payload, dict):
        current_filial_id = clean_text(payload.get("filial_id"))
        current_filial_code = clean_text(payload.get("filial_code"))
        if current_filial_id == expected_filial_id and current_filial_code:
            return current_filial_code
        for value in payload.values():
            discovered = _discover_verified_filial_code_from_payload(value, expected_filial_id)
            if discovered:
                return discovered
    elif isinstance(payload, list):
        for item in payload:
            discovered = _discover_verified_filial_code_from_payload(item, expected_filial_id)
            if discovered:
                return discovered
    return None
