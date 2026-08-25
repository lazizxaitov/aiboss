"""SmartUp normalization protocol and shared helpers."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol, runtime_checkable

from app.integrations.smartup.models import SmartUpRawRecord


@dataclass(slots=True)
class NormalizedEntityData:
    """One normalized entity payload ready for core upsert."""

    entity_type: str
    data: dict[str, Any]


@dataclass(slots=True)
class NormalizationResult:
    """Result returned by a SmartUp normalizer."""

    entity_type: str
    source_external_id: str | None
    normalized_data: dict[str, Any]
    related_entities: list[NormalizedEntityData] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    skipped: bool = False
    skip_reason: str | None = None


@runtime_checkable
class SmartUpNormalizer(Protocol):
    """Contract implemented by every SmartUp normalizer."""

    entity_type: str

    def normalize(self, raw_record: SmartUpRawRecord) -> NormalizationResult:
        """Normalize one raw SmartUp record."""


class BaseSmartUpNormalizer(ABC):
    """Base class with shared parsing helpers."""

    entity_type: str

    @abstractmethod
    def normalize(self, raw_record: SmartUpRawRecord) -> NormalizationResult:
        """Normalize one raw SmartUp record."""

    @staticmethod
    def _payload_as_dict(raw_record: SmartUpRawRecord) -> dict[str, Any]:
        payload = raw_record.response_payload
        if isinstance(payload, dict):
            return dict(payload)
        return {"items": payload}

    @staticmethod
    def _clean_text(value: object | None) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _parse_decimal(value: object | None, default: str = "0") -> Decimal:
        if isinstance(value, Decimal):
            return value
        if value is None or value == "":
            return Decimal(default)
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            return Decimal(default)

    @staticmethod
    def _parse_datetime(value: object | None) -> datetime | None:
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=UTC)
        if not isinstance(value, str) or not value.strip():
            return None
        candidate = value.strip()
        for fmt in (
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%d.%m.%Y %H:%M:%S",
            "%d.%m.%Y",
            "%Y-%m-%d",
        ):
            try:
                parsed = datetime.strptime(candidate, fmt)
            except ValueError:
                continue
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        return None

    @staticmethod
    def _stable_json(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    def _unsupported(self, raw_record: SmartUpRawRecord, reason: str) -> NormalizationResult:
        return NormalizationResult(
            entity_type=self.entity_type,
            source_external_id=raw_record.external_id,
            normalized_data={},
            skipped=True,
            skip_reason=reason,
        )
