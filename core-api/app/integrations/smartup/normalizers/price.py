"""SmartUp price reference normalizers."""

from __future__ import annotations

from decimal import Decimal

from app.core.data_layer.normalized import PriceType, ProductPrice
from app.integrations.smartup.models import SmartUpRawRecord

from .base import BaseSmartUpNormalizer, NormalizationResult, NormalizedEntityData


class PriceTypeNormalizer(BaseSmartUpNormalizer):
    """Normalize SmartUp price type reference rows."""

    entity_type = "price_types"

    def normalize(self, raw_record: SmartUpRawRecord) -> NormalizationResult:
        payload = self._payload_as_dict(raw_record)
        source_external_id = self._clean_text(
            payload.get("code") or payload.get("short_name") or payload.get("name"),
        )
        name = self._clean_text(payload.get("name") or payload.get("short_name") or source_external_id)
        if source_external_id is None or name is None:
            return NormalizationResult(
                entity_type=self.entity_type,
                source_external_id=source_external_id,
                normalized_data={},
                skipped=True,
                skip_reason="missing_price_type_identity",
            )

        price_type = PriceType(
            organization_id=raw_record.organization_id,
            source_system="smartup",
            source_external_id=source_external_id,
            source_filial_id=raw_record.filial_id,
            source_payload_id=self._clean_text(payload.get("code") or payload.get("name")),
            source_created_at=self._parse_datetime(payload.get("created_on")),
            source_updated_at=self._parse_datetime(payload.get("modified_on")),
            code=source_external_id,
            name=name,
            currency_code=self._clean_text(payload.get("currency_code")),
            status=self._clean_text(payload.get("state")),
            metadata={
                "source_entity": raw_record.entity_type,
                "source_endpoint": raw_record.source_endpoint,
                "short_name": payload.get("short_name"),
                "price_type_kind": payload.get("price_type_kind"),
                "with_card": payload.get("with_card"),
            },
        )
        return NormalizationResult(
            entity_type=self.entity_type,
            source_external_id=source_external_id,
            normalized_data=price_type.model_dump(mode="python"),
        )


class ProductPriceNormalizer(BaseSmartUpNormalizer):
    """Normalize SmartUp product price history rows."""

    entity_type = "product_prices"

    def normalize(self, raw_record: SmartUpRawRecord) -> NormalizationResult:
        payload = self._payload_as_dict(raw_record)
        product_external_id = self._clean_text(
            payload.get("inventory_code") or payload.get("product_code") or payload.get("product_id"),
        )
        if product_external_id is None:
            return NormalizationResult(
                entity_type=self.entity_type,
                source_external_id=None,
                normalized_data={},
                skipped=True,
                skip_reason="missing_product_reference",
            )

        price_rows = payload.get("price_type")
        if not isinstance(price_rows, list) or not price_rows:
            return NormalizationResult(
                entity_type=self.entity_type,
                source_external_id=product_external_id,
                normalized_data={},
                skipped=True,
                skip_reason="missing_price_rows",
            )

        normalized_rows: list[ProductPrice] = []
        for index, price_row in enumerate(price_rows, start=1):
            if not isinstance(price_row, dict):
                continue
            source_external_id = self._clean_text(
                price_row.get("price_type_code")
                or price_row.get("card_code")
                or f"{product_external_id}:{index}",
            )
            if source_external_id is None:
                source_external_id = f"{product_external_id}:{index}"
            price = self._parse_decimal(price_row.get("price"))
            normalized_rows.append(
                ProductPrice(
                    organization_id=raw_record.organization_id,
                    source_system="smartup",
                    source_external_id=source_external_id,
                    source_filial_id=raw_record.filial_id,
                    source_payload_id=self._clean_text(
                        payload.get("inventory_code") or payload.get("product_id") or product_external_id,
                    ),
                    source_created_at=self._parse_datetime(payload.get("created_on")),
                    source_updated_at=self._parse_datetime(payload.get("modified_on")),
                    product_external_id=product_external_id,
                    price_type_code=self._clean_text(
                        price_row.get("price_type_code") or price_row.get("card_code"),
                    ),
                    price=price,
                    currency_code=self._clean_text(payload.get("currency_code")),
                    effective_from=self._parse_datetime(payload.get("begin_date")),
                    effective_to=self._parse_datetime(payload.get("end_date")),
                    metadata={
                        "source_entity": raw_record.entity_type,
                        "source_endpoint": raw_record.source_endpoint,
                        "product_id": payload.get("product_id"),
                        "inventory_barcode": payload.get("inventory_barcode"),
                    },
                ),
            )

        if not normalized_rows:
            return NormalizationResult(
                entity_type=self.entity_type,
                source_external_id=product_external_id,
                normalized_data={},
                skipped=True,
                skip_reason="no_price_rows_normalized",
            )

        main = normalized_rows[0]
        related = [
            NormalizedEntityData(entity_type=self.entity_type, data=row.model_dump(mode="python"))
            for row in normalized_rows[1:]
        ]
        return NormalizationResult(
            entity_type=self.entity_type,
            source_external_id=main.source_external_id,
            normalized_data=main.model_dump(mode="python"),
            related_entities=related,
        )
