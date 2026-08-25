"""Product normalizer for SmartUp inventory catalog rows."""

from __future__ import annotations

from app.core.data_layer.normalized import Product
from app.integrations.smartup.models import SmartUpRawRecord

from .base import BaseSmartUpNormalizer, NormalizationResult


class ProductNormalizer(BaseSmartUpNormalizer):
    """Normalize SmartUp product/inventory rows."""

    entity_type = "products"

    def normalize(self, raw_record: SmartUpRawRecord) -> NormalizationResult:
        payload = self._payload_as_dict(raw_record)
        source_external_id = self._clean_text(
            payload.get("product_id")
            or payload.get("inventory_code")
            or payload.get("code")
            or raw_record.external_id,
        )
        name = self._clean_text(
            payload.get("name") or payload.get("short_name") or payload.get("code"),
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
                skip_reason="missing_product_name",
            )

        product = Product(
            organization_id=raw_record.organization_id,
            source_system="smartup",
            source_external_id=source_external_id,
            source_filial_id=raw_record.filial_id,
            source_payload_id=self._clean_text(
                payload.get("product_id") or payload.get("inventory_code") or payload.get("code"),
            ),
            source_created_at=self._parse_datetime(payload.get("created_on")),
            source_updated_at=self._parse_datetime(payload.get("modified_on")),
            name=name,
            category_external_id=self._clean_text(
                payload.get("group_code")
                or payload.get("product_group_code")
                or payload.get("parent_group_code"),
            ),
            sku=self._clean_text(payload.get("code") or payload.get("inventory_code")),
            unit=self._clean_text(payload.get("measure_code") or payload.get("unit_code")),
            metadata={
                "source_entity": raw_record.entity_type,
                "source_endpoint": raw_record.source_endpoint,
                "producer_code": payload.get("producer_code"),
                "gtin": payload.get("gtin"),
                "ikpu": payload.get("ikpu"),
                "tnved": payload.get("tnved"),
            },
        )
        return NormalizationResult(
            entity_type=self.entity_type,
            source_external_id=source_external_id,
            normalized_data=product.model_dump(mode="python"),
        )
