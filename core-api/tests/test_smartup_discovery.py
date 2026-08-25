"""Tests for SmartUp discovery matrix and business OS gap report."""


from fastapi.testclient import TestClient

from app.api.routes.data import get_core_store
from app.core.data_layer.service import InMemoryCoreDataLayer
from app.integrations.smartup.discovery import SmartUpDiscoveryReport
from app.integrations.smartup.mapping import SMARTUP_CORE_MAPPING_V1
from app.integrations.smartup.models import SmartUpOrganization, SmartUpRawRecord
from app.main import app


def _seed_store() -> tuple[InMemoryCoreDataLayer, SmartUpOrganization]:
    store = InMemoryCoreDataLayer()
    organization = store.upsert_smartup_organization(
        SmartUpOrganization(
            name="MODAILY",
            company_id="11300",
            filial_id="16114091",
            project_code="trade",
            is_active=True,
        ),
    )
    store.upsert_smartup_raw_record(
        SmartUpRawRecord(
            organization_id=organization.id,
            filial_id=organization.filial_id,
            entity_type="sales",
            external_id="268805991",
            source_endpoint="/b/trade/txs/tdeal/order$export",
            request_payload={"begin_deal_date": "03.08.2026", "end_deal_date": "10.08.2026"},
            response_payload={
                "deal_id": "268805991",
                "total_amount": "606000",
                "currency_code": "UZS",
                "order_products": [
                    {
                        "product_code": "prod-001",
                        "sold_amount": "606000",
                        "sold_quant": "4",
                    }
                ],
            },
            response_envelope={
                "order": [
                    {
                        "deal_id": "268805991",
                        "filial_code": "M-001",
                        "total_amount": "606000",
                    }
                ]
            },
        ),
    )
    store.upsert_smartup_raw_record(
        SmartUpRawRecord(
            organization_id=organization.id,
            filial_id=organization.filial_id,
            entity_type="visits",
            external_id="visit-001",
            source_endpoint="/b/trade/txs/tvt/visit$export",
            request_payload={"begin_visit_date": "03.08.2026", "end_visit_date": "10.08.2026"},
            response_payload={
                "visit_id": "visit-001",
                "visit_photo_sha": "photo-sha-001",
                "working_zone": "ZONE-1",
            },
        ),
    )
    return store, organization


def _client_for_store(store: InMemoryCoreDataLayer, monkeypatch) -> TestClient:  # noqa: ANN001
    monkeypatch.setattr("app.main.get_core_store", lambda: store)
    app.dependency_overrides[get_core_store] = lambda: store
    return TestClient(app)


def test_smartup_discovery_endpoint_returns_mapping_matrix(monkeypatch) -> None:
    store, organization = _seed_store()
    client = _client_for_store(store, monkeypatch)

    response = client.get(
        "/api/v1/smartup/discovery",
        params={"organization_id": str(organization.id)},
    )

    app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()

    assert payload["source_system"] == "SmartUp"
    assert payload["organizations_count"] == 1
    assert payload["entities_count"] == len(SMARTUP_CORE_MAPPING_V1)
    assert payload["fields_count"] > payload["entities_count"]

    orders = next(item for item in payload["entities"] if item["source_entity"] == "Orders")
    assert orders["core_domain"] == "Sales"
    assert orders["page"] == "Sales / Orders"
    assert orders["field_count"] >= 3

    matrix_row = next(
        row
        for row in payload["matrix"]
        if row["source_entity"] == "Orders" and row["source_field"] == "deal_id"
    )
    assert matrix_row["target_field"] == "external_ref"
    assert matrix_row["business_module"] == "Orders"
    assert matrix_row["analytics_use"].startswith("Revenue")

    org_diff = payload["organization_differences"][0]
    assert org_diff["organization_name"] == "MODAILY"
    assert "Sales drill-down" in org_diff["capabilities"]
    assert "Field Sales" in org_diff["capabilities"]

    assert "Photo Reports" in payload["missing_business_os_pages"]
    assert "Revenue" in payload["missing_dashboard_kpis"]
    assert any(
        item.startswith("Revenue -> Organization") for item in payload["missing_drill_down_paths"]
    )

    assert isinstance(SmartUpDiscoveryReport.model_validate(payload), SmartUpDiscoveryReport)
