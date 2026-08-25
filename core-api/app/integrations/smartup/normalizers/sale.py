"""Sale normalizer for SmartUp orders."""

from __future__ import annotations

from decimal import Decimal

from app.core.data_layer.normalized import Sale, SaleItem
from app.integrations.smartup.models import SmartUpRawRecord

from .base import BaseSmartUpNormalizer, NormalizationResult, NormalizedEntityData


class SaleNormalizer(BaseSmartUpNormalizer):
    """Normalize SmartUp order rows into sale facts."""

    entity_type = "sales"

    def normalize(self, raw_record: SmartUpRawRecord) -> NormalizationResult:
        payload = self._payload_as_dict(raw_record)
        source_external_id = self._clean_text(
            payload.get("deal_id") or payload.get("external_id") or raw_record.external_id,
        )
        customer_external_id = self._clean_text(
            payload.get("person_code")
            or payload.get("person_id")
            or payload.get("person_name")
            or payload.get("external_customer_id"),
        )
        amount = self._parse_decimal(payload.get("total_amount") or payload.get("amount"))
        sale_at = (
            self._parse_datetime(
                payload.get("deal_time") or payload.get("created_on") or payload.get("occurred_at"),
            )
            or raw_record.imported_at
        )
        if source_external_id is None:
            return NormalizationResult(
                entity_type=self.entity_type,
                source_external_id=None,
                normalized_data={},
                skipped=True,
                skip_reason="missing_source_external_id",
            )

        source_payload_id = self._clean_text(
            payload.get("deal_id")
            or payload.get("external_id")
            or payload.get("order_deal_id")
            or payload.get("person_id"),
        )

        sale = Sale(
            organization_id=raw_record.organization_id,
            source_system="smartup",
            source_external_id=source_external_id,
            source_filial_id=raw_record.filial_id,
            source_payload_id=source_payload_id,
            source_created_at=self._parse_datetime(payload.get("created_on")),
            source_updated_at=self._parse_datetime(payload.get("modified_on")),
            customer_external_id=customer_external_id,
            sale_number=self._clean_text(
                payload.get("deal_id")
                or payload.get("order_deal_id")
                or payload.get("external_id")
                or payload.get("code")
                or payload.get("order_no"),
            ),
            amount=amount,
            currency=self._clean_text(payload.get("currency_code") or payload.get("currency"))
            or "USD",
            status=self._normalize_status(payload.get("status")),
            sale_at=sale_at,
            closed_at=self._parse_datetime(payload.get("delivery_date")),
            metadata={
                "source_entity": raw_record.entity_type,
                "source_endpoint": raw_record.source_endpoint,
            },
        )

        related_entities: list[NormalizedEntityData] = []
        line_items = (
            payload.get("order_products") or payload.get("return_products") or payload.get("items")
        )
        is_return = isinstance(payload.get("return_products"), list)
        if isinstance(line_items, list):
            for index, item in enumerate(line_items, start=1):
                if not isinstance(item, dict):
                    continue
                item_external_id = self._clean_text(
                    item.get("product_code") or item.get("inventory_code") or item.get("code"),
                )
                item_payload_id = self._clean_text(
                    item.get("product_code")
                    or item.get("inventory_code")
                    or item.get("code")
                    or item.get("return_product_id")
                    or item.get("order_item_id"),
                )
                sale_item = SaleItem(
                    organization_id=raw_record.organization_id,
                    source_system="smartup",
                    source_external_id=f"{source_external_id}:{index}",
                    source_filial_id=raw_record.filial_id,
                    source_payload_id=item_payload_id,
                    source_created_at=None,
                    source_updated_at=None,
                    sale_external_id=source_external_id,
                    product_external_id=item_external_id,
                    quantity=self._sale_item_quantity(item, allow_return_quant=is_return),
                    unit_price=self._parse_decimal(
                        item.get("price") or item.get("product_price"),
                        default="0",
                    ),
                    amount=self._parse_decimal(
                        item.get("amount") or item.get("sold_amount") or item.get("total_amount"),
                        default="0",
                    ),
                    currency=sale.currency,
                    metadata={"source_entity": raw_record.entity_type},
                )
                related_entities.append(
                    NormalizedEntityData(
                        entity_type="sale_items",
                        data=sale_item.model_dump(mode="python"),
                    ),
                )

        return NormalizationResult(
            entity_type=self.entity_type,
            source_external_id=source_external_id,
            normalized_data=sale.model_dump(mode="python"),
            related_entities=related_entities,
        )

    def _sale_item_quantity(
        self,
        item: dict[str, object],
        *,
        allow_return_quant: bool = False,
    ) -> Decimal:
        details = item.get("details")
        if isinstance(details, list):
            sold_quant_total = Decimal("0")
            sold_quant_found = False
            for detail in details:
                if not isinstance(detail, dict):
                    continue
                if "sold_quant" not in detail:
                    continue
                sold_quant_total += self._parse_decimal(detail.get("sold_quant"))
                sold_quant_found = True
            if sold_quant_found:
                return sold_quant_total

        if item.get("order_quant") is not None:
            return self._parse_decimal(item.get("order_quant"))
        if item.get("quantity") is not None:
            return self._parse_decimal(item.get("quantity"))
        if allow_return_quant and item.get("return_quant") is not None:
            return self._parse_decimal(item.get("return_quant"))
        return Decimal("0")

    @staticmethod
    def _normalize_status(value: object | None) -> str:
        text = str(value).strip().upper() if value is not None else ""
        if not text:
            return "unknown"
        if "#C" in text or text == "C":
            return "cancelled"
        if "#V" in text:
            return "approved"
        if "#N" in text or text == "N":
            return "new"
        if text == "A":
            return "approved"
        if text in {"WON", "WIN", "SUCCESS", "DONE"}:
            return "won"
        if text in {"LOST", "FAIL", "FAILED"}:
            return "lost"
        return text.lower()
