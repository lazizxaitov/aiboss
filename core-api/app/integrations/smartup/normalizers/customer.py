"""Customer normalizer for SmartUp legal and natural persons."""

from __future__ import annotations

from app.core.data_layer.normalized import Customer
from app.integrations.smartup.models import SmartUpRawRecord

from .base import BaseSmartUpNormalizer, NormalizationResult


class CustomerNormalizer(BaseSmartUpNormalizer):
    """Normalize SmartUp customer-like records."""

    entity_type = "customers"

    def normalize(self, raw_record: SmartUpRawRecord) -> NormalizationResult:
        payload = self._payload_as_dict(raw_record)
        source_external_id = self._clean_text(
            payload.get("person_id") or payload.get("code") or raw_record.external_id,
        )
        name = self._clean_text(
            payload.get("name") or payload.get("short_name") or payload.get("person_name")
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
                skip_reason="missing_customer_name",
            )

        customer = Customer(
            organization_id=raw_record.organization_id,
            source_system="smartup",
            source_external_id=source_external_id,
            source_filial_id=raw_record.filial_id,
            source_payload_id=self._clean_text(payload.get("person_id") or payload.get("code")),
            source_created_at=self._parse_datetime(payload.get("created_on")),
            source_updated_at=self._parse_datetime(payload.get("modified_on")),
            name=name,
            display_name=self._clean_text(payload.get("short_name")),
            phone=self._clean_text(payload.get("main_phone") or payload.get("phone")),
            email=self._clean_text(payload.get("email")),
            metadata={
                "source_entity": raw_record.entity_type,
                "state": payload.get("state"),
                "source_endpoint": raw_record.source_endpoint,
            },
        )
        warnings = []
        if payload.get("state") is None:
            warnings.append("missing_state")
        return NormalizationResult(
            entity_type=self.entity_type,
            source_external_id=source_external_id,
            normalized_data=customer.model_dump(mode="python"),
            warnings=warnings,
        )
