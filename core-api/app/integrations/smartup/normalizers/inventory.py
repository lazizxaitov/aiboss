"""Inventory balance normalizer for SmartUp stock snapshots."""

from __future__ import annotations

from app.core.data_layer.normalized import InventoryBalance
from app.integrations.smartup.models import SmartUpRawRecord

from .base import BaseSmartUpNormalizer, NormalizationResult


class InventoryNormalizer(BaseSmartUpNormalizer):
    """Normalize SmartUp stock balance rows into inventory snapshots."""

    entity_type = "inventory_balances"

    def normalize(self, raw_record: SmartUpRawRecord) -> NormalizationResult:
        payload = self._payload_as_dict(raw_record)
        warehouse_external_id = self._clean_text(
            payload.get("warehouse_code")
            or payload.get("warehouse_id")
            or payload.get("room_code")
            or payload.get("room_id"),
        )
        product_external_id = self._clean_text(
            payload.get("product_code")
            or payload.get("inventory_code")
            or payload.get("product_id")
            or payload.get("code"),
        )
        if warehouse_external_id is None or product_external_id is None:
            return NormalizationResult(
                entity_type=self.entity_type,
                source_external_id=None,
                normalized_data={},
                skipped=True,
                skip_reason="missing_warehouse_or_product_reference",
            )

        balance_at = (
            self._parse_datetime(
                payload.get("date")
                or payload.get("balance_date")
                or payload.get("created_on"),
            )
            or raw_record.imported_at
        )
        source_external_id = self._clean_text(
            payload.get("balance_id")
            or payload.get("external_id")
            or f"{warehouse_external_id}:{product_external_id}:{balance_at.isoformat()}",
        )
        balance = InventoryBalance(
            organization_id=raw_record.organization_id,
            source_system="smartup",
            source_external_id=source_external_id,
            source_filial_id=raw_record.filial_id,
            source_payload_id=self._clean_text(
                payload.get("balance_id") or payload.get("external_id") or source_external_id,
            ),
            source_created_at=self._parse_datetime(payload.get("created_on")),
            source_updated_at=self._parse_datetime(payload.get("modified_on")),
            warehouse_external_id=warehouse_external_id,
            product_external_id=product_external_id,
            quantity=self._parse_decimal(
                payload.get("quantity") or payload.get("balance") or payload.get("qty"),
            ),
            balance_at=balance_at,
            metadata={
                "source_entity": raw_record.entity_type,
                "source_endpoint": raw_record.source_endpoint,
            },
        )
        return NormalizationResult(
            entity_type=self.entity_type,
            source_external_id=source_external_id,
            normalized_data=balance.model_dump(mode="python"),
        )
