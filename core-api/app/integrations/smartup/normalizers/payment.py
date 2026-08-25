"""Payment normalizer for SmartUp client payment and cash-in sources."""

from __future__ import annotations

from app.core.data_layer.normalized import Payment
from app.integrations.smartup.models import SmartUpRawRecord

from .base import BaseSmartUpNormalizer, NormalizationResult


class PaymentNormalizer(BaseSmartUpNormalizer):
    """Normalize SmartUp payment-like rows into finance facts."""

    entity_type = "payments"

    def normalize(self, raw_record: SmartUpRawRecord) -> NormalizationResult:
        payload = self._payload_as_dict(raw_record)
        source_external_id = self._clean_text(
            payload.get("cashin_id")
            or payload.get("payment_id")
            or payload.get("external_id")
            or raw_record.external_id,
        )
        if source_external_id is None:
            return NormalizationResult(
                entity_type=self.entity_type,
                source_external_id=None,
                normalized_data={},
                skipped=True,
                skip_reason="missing_source_external_id",
            )

        paid_at = (
            self._parse_datetime(
                payload.get("cashin_date")
                or payload.get("payment_date")
                or payload.get("paid_at")
                or payload.get("occurred_at")
                or payload.get("created_on"),
            )
            or raw_record.imported_at
        )
        payment = Payment(
            organization_id=raw_record.organization_id,
            source_system="smartup",
            source_external_id=source_external_id,
            source_filial_id=raw_record.filial_id,
            source_payload_id=self._clean_text(
                payload.get("cashin_id") or payload.get("payment_id") or payload.get("external_id"),
            ),
            source_created_at=self._parse_datetime(payload.get("created_on")),
            source_updated_at=self._parse_datetime(payload.get("modified_on")),
            sale_external_id=self._clean_text(
                payload.get("deal_id")
                or payload.get("order_id")
                or payload.get("sale_id")
                or payload.get("external_sale_id"),
            ),
            amount=self._parse_decimal(payload.get("amount") or payload.get("payment_amount")),
            currency=self._clean_text(payload.get("currency_code") or payload.get("currency"))
            or "USD",
            paid_at=paid_at,
            method=self._clean_text(
                payload.get("payment_type_code")
                or payload.get("payment_method")
                or payload.get("type"),
            ),
            metadata={
                "source_entity": raw_record.entity_type,
                "source_endpoint": raw_record.source_endpoint,
                "status": payload.get("status"),
            },
        )
        return NormalizationResult(
            entity_type=self.entity_type,
            source_external_id=source_external_id,
            normalized_data=payment.model_dump(mode="python"),
        )
