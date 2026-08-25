"""Bank operation normalizer for SmartUp cash and bank sources."""

from __future__ import annotations

from app.core.data_layer.normalized import BankOperation
from app.integrations.smartup.models import SmartUpRawRecord

from .base import BaseSmartUpNormalizer, NormalizationResult


class BankOperationNormalizer(BaseSmartUpNormalizer):
    """Normalize SmartUp bank/cash operation rows."""

    entity_type = "bank_operations"

    def normalize(self, raw_record: SmartUpRawRecord) -> NormalizationResult:
        payload = self._payload_as_dict(raw_record)
        source_external_id = self._clean_text(
            payload.get("operation_id")
            or payload.get("bank_operation_id")
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

        occurred_at = (
            self._parse_datetime(
                payload.get("operation_date")
                or payload.get("date")
                or payload.get("occurred_at")
                or payload.get("created_on")
                or payload.get("modified_on"),
            )
            or raw_record.imported_at
        )
        operation = BankOperation(
            organization_id=raw_record.organization_id,
            source_system="smartup",
            source_external_id=source_external_id,
            source_filial_id=raw_record.filial_id,
            source_payload_id=self._clean_text(
                payload.get("operation_id")
                or payload.get("bank_operation_id")
                or payload.get("external_id"),
            ),
            source_created_at=self._parse_datetime(payload.get("created_on")),
            source_updated_at=self._parse_datetime(payload.get("modified_on")),
            amount=self._parse_decimal(payload.get("amount") or payload.get("sum")),
            currency=self._clean_text(payload.get("currency_code") or payload.get("currency"))
            or "USD",
            occurred_at=occurred_at,
            operation_type=self._clean_text(
                payload.get("operation_type")
                or payload.get("cash_operation_type")
                or payload.get("kind")
                or payload.get("debit_credit"),
            )
            or "unknown",
            description=self._clean_text(
                payload.get("description") or payload.get("note") or payload.get("memo"),
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
            normalized_data=operation.model_dump(mode="python"),
        )
