"""Visit normalizer for SmartUp visit rows."""

from __future__ import annotations

from app.core.data_layer.normalized import Visit
from app.integrations.smartup.models import SmartUpRawRecord

from .base import BaseSmartUpNormalizer, NormalizationResult


class VisitNormalizer(BaseSmartUpNormalizer):
    """Normalize SmartUp visit rows."""

    entity_type = "visits"

    def normalize(self, raw_record: SmartUpRawRecord) -> NormalizationResult:
        payload = self._payload_as_dict(raw_record)
        if "visit_headers" in payload and isinstance(payload.get("visit_headers"), list):
            visit_headers = payload.get("visit_headers")
            if isinstance(visit_headers, list) and visit_headers:
                first_header = next(
                    (item for item in visit_headers if isinstance(item, dict)),
                    None,
                )
                if first_header is not None:
                    payload = {**payload, **first_header}
        source_external_id = self._clean_text(
            payload.get("visit_id")
            or payload.get("external_id")
            or payload.get("visit_header_id")
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

        visited_at = (
            self._parse_datetime(
                payload.get("visit_date") or payload.get("visited_at") or payload.get("created_on"),
            )
            or raw_record.imported_at
        )
        visit = Visit(
            organization_id=raw_record.organization_id,
            source_system="smartup",
            source_external_id=source_external_id,
            source_filial_id=raw_record.filial_id,
            source_payload_id=self._clean_text(
                payload.get("visit_id")
                or payload.get("external_id")
                or payload.get("visit_header_id"),
            ),
            source_created_at=self._parse_datetime(payload.get("created_on")),
            source_updated_at=self._parse_datetime(payload.get("modified_on")),
            customer_external_id=self._clean_text(
                payload.get("person_code")
                or payload.get("person_id")
                or payload.get("customer_code")
                or payload.get("contact_code"),
            ),
            visited_at=visited_at,
            status=self._clean_text(payload.get("visit_status") or payload.get("status")),
            metadata={
                "source_entity": raw_record.entity_type,
                "source_endpoint": raw_record.source_endpoint,
            },
        )
        return NormalizationResult(
            entity_type=self.entity_type,
            source_external_id=source_external_id,
            normalized_data=visit.model_dump(mode="python"),
        )
