from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.marketing_attribution import AttributionError, MarketingAttributionService
from app.core.data_layer.service import InMemoryCoreDataLayer


def _service():
    store = InMemoryCoreDataLayer()
    source = {"external_id": "video-1", "organization_id": "org-1"}
    store.upsert_source_record("youtube_videos", source, ("organization_id", "external_id"))
    sale = SimpleNamespace(id=uuid4(), organization_id="org-1", total_amount=100, currency_code="UZS")
    store.list_canonical_sales = lambda: [sale]
    return store, MarketingAttributionService(store), sale


def test_confirmed_evidence_is_idempotent_and_creates_outcome():
    store, service, sale = _service()
    payload = {"organization_id": "org-1", "source_platform": "youtube", "source_entity_type": "video", "source_entity_id": "video-1", "target_entity_type": "sale", "target_entity_id": str(sale.id), "evidence_type": "first_party_order_link"}
    first = service.ingest(payload)
    second = service.ingest(payload)
    assert first["evidence_id"] == second["evidence_id"]
    assert len(store.list_source_records("marketing_attribution_evidence")) == 1
    assert len(store.list_source_records("marketing_attributed_outcomes")) == 1


def test_same_date_or_name_does_not_create_evidence_without_linkage():
    store, service, sale = _service()
    with pytest.raises(AttributionError):
        service.ingest({"organization_id": "org-1", "source_platform": "youtube", "source_entity_type": "video", "source_entity_id": "video-1", "target_entity_type": "sale", "target_entity_id": str(sale.id), "evidence_type": "bad_date_correlation"})


def test_cross_organization_and_invalid_entities_are_rejected():
    store, service, sale = _service()
    with pytest.raises(AttributionError):
        service.ingest({"organization_id": "org-2", "source_platform": "youtube", "source_entity_type": "video", "source_entity_id": "video-1", "target_entity_type": "sale", "target_entity_id": str(sale.id), "evidence_type": "click_id"})
    with pytest.raises(AttributionError):
        service.ingest({"organization_id": "org-1", "source_platform": "youtube", "source_entity_type": "video", "source_entity_id": "missing", "target_entity_type": "sale", "target_entity_id": str(sale.id), "evidence_type": "click_id"})
