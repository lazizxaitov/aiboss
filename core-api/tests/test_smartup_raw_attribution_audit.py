"""Tests for SmartUp raw organization attribution diagnostics."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.core.data_layer.entities import IngestionBatch, IngestionBatchStatus
from app.core.data_layer.service import InMemoryCoreDataLayer
from app.integrations.smartup.audit import SmartUpDataIntegrityAuditService
from app.integrations.smartup.client import SmartUpApiClient
from app.integrations.smartup.history import SmartUpHistoricalImportRunner
from app.integrations.smartup.mapping import SMARTUP_CORE_MAPPING_V1
from app.integrations.smartup.models import (
    SMARTUP_INTEGRATION_UUID,
    SmartUpOrganization,
    SmartUpRawRecord,
)
from app.integrations.smartup.settings import SmartUpSettings


def _orders_mapping():
    return next(mapping for mapping in SMARTUP_CORE_MAPPING_V1 if mapping.name == "Orders")


def test_history_runner_preserves_full_response_envelope_and_request_context() -> None:
    store = InMemoryCoreDataLayer()
    organization = store.upsert_smartup_organization(
        SmartUpOrganization(
            id=UUID("11111111-1111-1111-1111-111111111111"),
            integration_id=SMARTUP_INTEGRATION_UUID,
            name="Администрация",
            company_id="11300",
            filial_id="14475622",
            project_code="trade",
            is_active=True,
        ),
    )
    client = SmartUpApiClient(
        SmartUpSettings(
            base_url="https://smartup.online",
            username="demo",
            password="secret",
            company_id="11300",
            project_code="trade",
            filial_id=organization.filial_id,
        ),
    )
    runner = SmartUpHistoricalImportRunner(
        client=client,
        target=store,
        business_id=organization.id,
        business_name=organization.name,
        smartup_filial_id=organization.filial_id,
    )
    batch = IngestionBatch(
        batch_id=uuid4(),
        business_id=organization.id,
        source_system_id=None,
        batch_name="Orders · 1 day",
        status=IngestionBatchStatus.RUNNING,
        started_at=datetime(2026, 8, 10, tzinfo=UTC),
        metadata={
            "payload": {
                "begin_deal_date": "10.08.2026",
                "end_deal_date": "10.08.2026",
            },
        },
    )
    mapping = _orders_mapping()
    response_envelope = {
        "order": [
            {
                "deal_id": "268805991",
                "filial_id": "16114091",
                "external_id": "ext-268805991",
                "total_amount": "606000",
                "currency_code": "860",
                "status": "B#N",
                "order_products": [
                    {
                        "product_code": "935",
                        "order_quant": "4",
                        "product_price": "151500",
                        "sold_amount": "606000",
                    },
                ],
            },
        ],
    }

    raw_record = runner._build_raw_record(  # noqa: SLF001 - regression test
        batch=batch,
        mapping=mapping,
        row=response_envelope["order"][0],
        response_envelope=response_envelope,
    )

    assert raw_record.organization_id == organization.id
    assert raw_record.request_filial_id == "14475622"
    assert raw_record.request_company_id == "11300"
    assert raw_record.request_project_code == "trade"
    assert raw_record.response_envelope == response_envelope
    assert raw_record.response_filial_id == "16114091"
    assert raw_record.request_payload["request_filial_id"] == "14475622"
    assert raw_record.request_payload["request_company_id"] == "11300"
    assert raw_record.request_payload["request_project_code"] == "trade"


def test_raw_attribution_audit_flags_mixed_filial_ids() -> None:
    store = InMemoryCoreDataLayer()
    admin = store.upsert_smartup_organization(
        SmartUpOrganization(
            id=UUID("11111111-1111-1111-1111-111111111111"),
            integration_id=SMARTUP_INTEGRATION_UUID,
            name="Администрация",
            company_id="11300",
            filial_id="14475622",
            project_code="trade",
            is_active=True,
        ),
    )
    modaily = store.upsert_smartup_organization(
        SmartUpOrganization(
            id=UUID("22222222-2222-2222-2222-222222222222"),
            integration_id=SMARTUP_INTEGRATION_UUID,
            name="MODAILY",
            company_id="11300",
            filial_id="16114091",
            project_code="trade",
            is_active=True,
        ),
    )

    store.upsert_smartup_raw_record(
        SmartUpRawRecord(
            id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            organization_id=admin.id,
            filial_id=admin.filial_id,
            request_filial_id=admin.filial_id,
            request_company_id="11300",
            request_project_code="trade",
            entity_type="sales",
            external_id="268805991",
            source_endpoint="/b/trade/txs/tdeal/order$export",
            request_payload={"begin_deal_date": "10.08.2026", "end_deal_date": "10.08.2026"},
            response_payload={
                "deal_id": "268805991",
                "filial_id": "16114091",
            },
            response_envelope={
                "order": [{"deal_id": "268805991", "filial_id": "16114091"}],
            },
            response_filial_id="16114091",
        ),
    )
    store.upsert_smartup_raw_record(
        SmartUpRawRecord(
            id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
            organization_id=admin.id,
            filial_id="19330532",
            request_filial_id="19330532",
            entity_type="sales",
            external_id="268805992",
            source_endpoint="/b/trade/txs/tdeal/order$export",
            request_payload={"begin_deal_date": "10.08.2026", "end_deal_date": "10.08.2026"},
            response_payload={
                "deal_id": "268805992",
                "filial_id": "19330532",
            },
            response_envelope={
                "order": [{"deal_id": "268805992", "filial_id": "19330532"}],
            },
            response_filial_id="19330532",
        ),
    )
    store.upsert_smartup_raw_record(
        SmartUpRawRecord(
            id=UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"),
            organization_id=modaily.id,
            filial_id=modaily.filial_id,
            request_filial_id=None,
            request_company_id=None,
            request_project_code=None,
            entity_type="sales",
            external_id="268805993",
            source_endpoint="/b/trade/txs/tdeal/order$export",
            request_payload={"begin_deal_date": "10.08.2026", "end_deal_date": "10.08.2026"},
            response_payload={
                "deal_id": "268805993",
                "filial_id": "16114091",
            },
            response_envelope={
                "order": [{"deal_id": "268805993", "filial_id": "16114091"}],
            },
            response_filial_id="16114091",
        ),
    )
    store.upsert_smartup_raw_record(
        SmartUpRawRecord(
            id=UUID("dddddddd-dddd-dddd-dddd-dddddddddddd"),
            organization_id=modaily.id,
            filial_id=modaily.filial_id,
            request_filial_id=None,
            request_company_id=None,
            request_project_code=None,
            entity_type="sales",
            external_id="268805994",
            source_endpoint="/b/trade/txs/tdeal/order$export",
            request_payload={"begin_deal_date": "10.08.2026", "end_deal_date": "10.08.2026"},
            response_payload={
                "deal_id": "268805994",
                "filial_id": "19392290",
            },
            response_envelope={
                "order": [
                    {"deal_id": "268805994", "filial_id": "16114091"},
                    {"deal_id": "268805995", "filial_id": "19392290"},
                ],
            },
            response_filial_id="16114091",
        ),
    )

    report = SmartUpDataIntegrityAuditService(store).build_raw_attribution_report()

    assert report.total_organizations == 2
    assert report.raw_records == 4
    assert report.organization_mismatch == 1
    assert report.different_response_filial == 1
    assert report.missing_filial == 1
    assert report.ambiguous == 1

    admin_item = next(item for item in report.items if item.organization_id == admin.id)
    assert admin_item.raw_count == 2
    assert admin_item.matching_rows == 0
    assert admin_item.organization_mismatch == 1
    assert admin_item.different_response_filial == 1
    assert admin_item.foreign_filials == {"16114091": 1, "19330532": 1}

    modaily_item = next(item for item in report.items if item.organization_id == modaily.id)
    assert modaily_item.raw_count == 2
    assert modaily_item.ambiguous == 1
    assert modaily_item.missing_filial == 1
    assert modaily_item.foreign_filials == {"19392290": 1}

    issue_statuses = {issue.status for issue in report.issues}
    assert "ORGANIZATION_MISMATCH" in issue_statuses
    assert "RESPONSE_FILIAL_DIFFERS" in issue_statuses
    assert "AMBIGUOUS" in issue_statuses
