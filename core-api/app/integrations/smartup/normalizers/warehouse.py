"""Warehouse normalizer for SmartUp room / warehouse catalogs."""

from __future__ import annotations

from app.core.data_layer.normalized import Warehouse
from app.integrations.smartup.models import SmartUpRawRecord

from .base import BaseSmartUpNormalizer, NormalizationResult


class WarehouseNormalizer(BaseSmartUpNormalizer):
    """Normalize SmartUp warehouse catalog rows."""

    entity_type = "warehouses"

    def normalize(self, raw_record: SmartUpRawRecord) -> NormalizationResult:
        payload = self._payload_as_dict(raw_record)
        source_external_id = self._clean_text(
            payload.get("room_id")
            or payload.get("warehouse_id")
            or payload.get("code")
            or raw_record.external_id,
        )
        name = self._clean_text(
            payload.get("room_name") or payload.get("name") or payload.get("code"),
        )
        if source_external_id is None:
            return NormalizationResult(
                entity_type=self.entity_type,
                source_external_id=None,
                normalized_data={},
                skipped=True,
                skip_reason="missing_source_external_id",
            )
        if name is None:
            return NormalizationResult(
                entity_type=self.entity_type,
                source_external_id=source_external_id,
                normalized_data={},
                skipped=True,
                skip_reason="missing_warehouse_name",
            )

        warehouse = Warehouse(
            organization_id=raw_record.organization_id,
            source_system="smartup",
            source_external_id=source_external_id,
            source_filial_id=raw_record.filial_id,
            source_payload_id=self._clean_text(
                payload.get("room_id") or payload.get("warehouse_id") or payload.get("code"),
            ),
            source_created_at=self._parse_datetime(payload.get("created_on")),
            source_updated_at=self._parse_datetime(payload.get("modified_on")),
            name=name,
            code=self._clean_text(
                payload.get("room_code")
                or payload.get("warehouse_code")
                or payload.get("code"),
            ),
            metadata={
                "source_entity": raw_record.entity_type,
                "source_endpoint": raw_record.source_endpoint,
            },
        )
        return NormalizationResult(
            entity_type=self.entity_type,
            source_external_id=source_external_id,
            normalized_data=warehouse.model_dump(mode="python"),
        )
