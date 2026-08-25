"""Tests for SmartUp connection checks and migration orchestration."""

from datetime import UTC, datetime
from uuid import UUID

import httpx

from app.core.data_layer.entities import (
    IngestionBatch,
    IngestionBatchStatus,
    IngestionError,
    SourceSystem,
)
from app.core.data_layer.service import InMemoryCoreDataLayer
from app.integrations.smartup.models import SmartUpMigrationMode, SmartUpRawRecord
from app.integrations.smartup.operations import (
    SmartUpAccessPayload,
    SmartUpAccountService,
    SmartUpHistoryMigrationRequest,
    SmartUpMigrationOrganizationInput,
    SmartUpMigrationOrganizationResult,
    SmartUpMigrationSummary,
    SmartUpOrganizationCreateRequest,
    SmartUpResolvedAuth,
)
from app.integrations.smartup.settings import SmartUpSettings


def test_smartup_connection_requires_filial_id() -> None:
    service = SmartUpAccountService(target=InMemoryCoreDataLayer())

    response = service.check_connection(
        SmartUpAccessPayload(
            base_url="https://smartup.online",
            username="demo",
            password="secret",
            filial_id="",
        ),
    )

    assert response.connected is False
    assert response.code == "SMARTUP_FILIAL_ID_REQUIRED"
    assert response.message == (
        "Укажите filial_id организации из профиля SmartUp или получите его у администратора SmartUp"
    )
    assert response.upstream_status is None
    assert response.requested_url == "https://smartup.online/b/anor/mxsx/mrf/room$export"


def test_smartup_connection_returns_access_denied_for_404(monkeypatch) -> None:
    service = SmartUpAccountService(target=InMemoryCoreDataLayer())

    def fake_resolve_organization_auth(self, organization, payload=None, **kwargs):  # noqa: ANN001
        return SmartUpResolvedAuth(
            payload=SmartUpAccessPayload(
                base_url="https://smartup.online",
                username=payload.username,
                password=payload.password,
                project_code=organization.project_code,
                filial_id=organization.filial_id,
            ),
            source="payload",
            credentials_available=True,
        )

    def fake_build_client_for_organization(self, organization, payload=None, **kwargs):  # noqa: ANN001
        class FakeClient:
            def __init__(self) -> None:
                self.settings = SmartUpSettings(
                    base_url="https://smartup.online",
                    project_code=organization.project_code,
                    filial_id=organization.filial_id,
                    username=(payload.username if payload is not None else ""),
                    password=(payload.password if payload is not None else ""),
                )

            def _build_url(self, endpoint):  # noqa: ANN001
                return f"https://smartup.online{endpoint}"

            def request_response(self, method, endpoint, body):  # noqa: ANN001
                request = httpx.Request(
                    "POST", "https://smartup.online/b/anor/mxsx/mrf/room$export"
                )
                return httpx.Response(404, request=request, text="Forbidden")

        return FakeClient()

    monkeypatch.setattr(
        SmartUpAccountService,
        "resolve_organization_auth",
        fake_resolve_organization_auth,
    )
    monkeypatch.setattr(
        SmartUpAccountService,
        "build_client_for_organization",
        fake_build_client_for_organization,
    )

    response = service.check_connection(
        SmartUpAccessPayload(
            base_url="https://api.greenwhite.uz",
            username="demo",
            password="secret",
            filial_id="86401",
        ),
    )

    assert response.connected is False
    assert response.code == "SMARTUP_ACCESS_DENIED"
    assert response.message == (
        "Пользователь не имеет доступа к endpoint, проекту или выбранной организации"
    )
    assert response.upstream_status == 404
    assert response.upstream_response == "Forbidden"
    assert response.requested_url == "https://smartup.online/b/anor/mxsx/mrf/room$export"
    assert response.project_code == "trade"
    assert response.filial_id == "86401"


def test_smartup_connection_accepts_login_alias_and_persists_credentials_after_success(
    monkeypatch,
) -> None:
    store = InMemoryCoreDataLayer()
    service = SmartUpAccountService(target=store)
    organization = service.create_organization(
        SmartUpOrganizationCreateRequest(
            name="Acme",
            company_id="11300",
            filial_id="14475622",
            project_code="trade",
            is_active=True,
        ),
    )
    captured: dict[str, object] = {}

    def fake_resolve_organization_auth(self, organization_arg, payload=None, **kwargs):  # noqa: ANN001
        captured["payload_username"] = payload.username if payload is not None else None
        captured["payload_password"] = payload.password if payload is not None else None
        return SmartUpResolvedAuth(
            payload=SmartUpAccessPayload(
                base_url="https://smartup.online",
                username=payload.username if payload is not None else "",
                password=payload.password if payload is not None else "",
                project_code=organization_arg.project_code,
                filial_id=organization_arg.filial_id,
            ),
            source="payload",
            credentials_available=True,
        )

    def fake_build_client_for_organization(self, organization_arg, payload=None, **kwargs):  # noqa: ANN001
        captured["organization_id"] = organization_arg.id
        captured["client_username"] = payload.username if payload is not None else None
        captured["client_password"] = payload.password if payload is not None else None

        class FakeClient:
            def __init__(self) -> None:
                self.settings = SmartUpSettings(
                    base_url="https://smartup.online",
                    project_code=organization_arg.project_code,
                    filial_id=organization_arg.filial_id,
                    username=payload.username if payload is not None else "",
                    password=payload.password if payload is not None else "",
                )

            def _build_url(self, endpoint):  # noqa: ANN001
                return f"https://smartup.online{endpoint}"

            def request_response(self, method, endpoint, body):  # noqa: ANN001
                request = httpx.Request(
                    "POST", "https://smartup.online/b/anor/mxsx/mrf/room$export"
                )
                return httpx.Response(200, request=request, text="{}")

        return FakeClient()

    monkeypatch.setattr(
        SmartUpAccountService,
        "resolve_organization_auth",
        fake_resolve_organization_auth,
    )
    monkeypatch.setattr(
        SmartUpAccountService,
        "build_client_for_organization",
        fake_build_client_for_organization,
    )

    response = service.check_connection(
        organization.id,
        SmartUpAccessPayload.model_validate(
            {
                "base_url": "https://smartup.online",
                "login": "demo",
                "password": "secret",
                "filial_id": organization.filial_id,
            },
        ),
    )

    setting = store.get_app_setting(f"smartup:organization_credentials:{organization.id}")

    assert response.connected is True
    assert captured["organization_id"] == organization.id
    assert captured["payload_username"] == "demo"
    assert captured["payload_password"] == "secret"
    assert captured["client_username"] == "demo"
    assert captured["client_password"] == "secret"
    assert setting is not None
    assert setting.setting_value["username"] == "demo"
    assert setting.setting_value["password"] == "secret"


def test_smartup_connection_does_not_persist_invalid_credentials(monkeypatch) -> None:
    store = InMemoryCoreDataLayer()
    service = SmartUpAccountService(target=store)
    organization = service.create_organization(
        SmartUpOrganizationCreateRequest(
            name="Acme",
            company_id="11300",
            filial_id="14475622",
            project_code="trade",
            is_active=True,
        ),
    )

    def fake_resolve_organization_auth(self, organization_arg, payload=None, **kwargs):  # noqa: ANN001
        return SmartUpResolvedAuth(
            payload=SmartUpAccessPayload(
                base_url="https://smartup.online",
                username=payload.username if payload is not None else "",
                password=payload.password if payload is not None else "",
                project_code=organization_arg.project_code,
                filial_id=organization_arg.filial_id,
            ),
            source="payload",
            credentials_available=True,
        )

    def fake_build_client_for_organization(self, organization_arg, payload=None, **kwargs):  # noqa: ANN001
        class FakeClient:
            def __init__(self) -> None:
                self.settings = SmartUpSettings(
                    base_url="https://smartup.online",
                    project_code=organization_arg.project_code,
                    filial_id=organization_arg.filial_id,
                    username=payload.username if payload is not None else "",
                    password=payload.password if payload is not None else "",
                )

            def _build_url(self, endpoint):  # noqa: ANN001
                return f"https://smartup.online{endpoint}"

            def request_response(self, method, endpoint, body):  # noqa: ANN001
                request = httpx.Request(
                    "POST", "https://smartup.online/b/anor/mxsx/mrf/room$export"
                )
                return httpx.Response(401, request=request, text="Требуется авторизация")

        return FakeClient()

    monkeypatch.setattr(
        SmartUpAccountService,
        "resolve_organization_auth",
        fake_resolve_organization_auth,
    )
    monkeypatch.setattr(
        SmartUpAccountService,
        "build_client_for_organization",
        fake_build_client_for_organization,
    )

    response = service.check_connection(
        organization.id,
        SmartUpAccessPayload.model_validate(
            {
                "base_url": "https://smartup.online",
                "username": "demo",
                "password": "wrong",
                "filial_id": organization.filial_id,
            },
        ),
    )

    setting = store.get_app_setting(f"smartup:organization_credentials:{organization.id}")

    assert response.connected is False
    assert response.upstream_status == 401
    assert setting is None


def test_smartup_history_migration_uses_manual_organization_list(monkeypatch) -> None:
    service = SmartUpAccountService(target=InMemoryCoreDataLayer())
    seen_calls: list[tuple[str, str | None, str | None]] = []

    monkeypatch.setattr(SmartUpAccountService, "build_client", lambda self, payload: object())

    class FakeRunner:
        def __init__(
            self,
            *,
            client,  # noqa: ANN001
            target,  # noqa: ANN001
            business_id: UUID,
            business_name: str,
            business_external_ref: str | None = None,
            smartup_filial_id: str | None = None,
            smartup_filial_code: str | None = None,
            connector=None,  # noqa: ANN001
        ) -> None:
            seen_calls.append((business_name, business_external_ref, smartup_filial_id))

        def run(self, *, history_start, history_end, chunk_days, migration_mode):  # noqa: ANN001
            assert history_start.tzinfo is UTC
            assert history_end.tzinfo is UTC
            assert chunk_days == 30
            assert migration_mode == SmartUpMigrationMode.FULL_BACKFILL
            return {"batches": 1, "records": 3, "errors": 0}

    monkeypatch.setattr(
        "app.integrations.smartup.operations.SmartUpHistoricalImportRunner",
        FakeRunner,
    )

    response = service.migrate_history(
        SmartUpHistoryMigrationRequest(
            base_url="https://smartup.online",
            username="demo",
            password="secret",
            filial_id="86401",
            history_start=datetime(2026, 7, 22, tzinfo=UTC),
            history_end=datetime(2026, 7, 29, tzinfo=UTC),
            chunk_days=7,
            organizations=[
                SmartUpMigrationOrganizationInput(
                    name="Acme",
                    filial_id="10",
                    selected=True,
                ),
                SmartUpMigrationOrganizationInput(
                    name="Beta",
                    filial_id="11",
                    selected=False,
                ),
                SmartUpMigrationOrganizationInput(
                    name="Gamma",
                    filial_id="12",
                    selected=True,
                ),
            ],
        ),
    )

    assert response.status == "completed"
    assert response.organizations_count == 2
    assert [organization.name for organization in response.organizations] == ["Acme", "Gamma"]
    assert seen_calls == [("Acme", "10", "10"), ("Gamma", "12", "12")]
    assert response.summary.batches == 2
    assert response.summary.records == 0


def test_smartup_discover_filial_codes_updates_organizations_from_raw_orders() -> None:
    store = InMemoryCoreDataLayer()
    service = SmartUpAccountService(target=store)
    organization = service.create_organization(
        SmartUpOrganizationCreateRequest(
            name="Acme",
            company_id="11300",
            filial_id="14475622",
            project_code="trade",
            is_active=True,
        ),
    )

    store.upsert_smartup_raw_record(
        SmartUpRawRecord(
            organization_id=organization.id,
            filial_id="14475622",
            request_filial_id="14475622",
            entity_type="sales",
            source_endpoint="/b/trade/txs/tdeal/order$export",
            response_filial_id="14475622",
            response_payload={
                "order": [
                    {
                        "deal_id": "268805991",
                        "filial_id": "14475622",
                        "filial_code": "16114091",
                        "currency_code": "860",
                    }
                ],
            },
        ),
    )

    response = service.discover_filial_codes()
    updated = store.get_smartup_organization(organization.id)

    assert response.items
    assert response.items[0].filial_code == "16114091"
    assert response.items[0].status == "found"
    assert updated is not None
    assert updated.filial_code == "16114091"


def test_smartup_discover_filial_codes_uses_response_envelope_when_payload_lacks_code() -> None:
    store = InMemoryCoreDataLayer()
    service = SmartUpAccountService(target=store)
    organization = service.create_organization(
        SmartUpOrganizationCreateRequest(
            name="Acme Envelope",
            company_id="11300",
            filial_id="14475622",
            project_code="trade",
            is_active=True,
        ),
    )

    store.upsert_smartup_raw_record(
        SmartUpRawRecord(
            organization_id=organization.id,
            filial_id="14475622",
            request_filial_id="14475622",
            entity_type="sales",
            source_endpoint="/b/trade/txs/tdeal/order$export",
            response_filial_id="14475622",
            response_payload={
                "order": [
                    {
                        "deal_id": "268805991",
                        "currency_code": "860",
                    }
                ],
            },
            response_envelope={
                "order": [
                    {
                        "deal_id": "268805991",
                        "filial_id": "14475622",
                        "filial_code": "16114091",
                        "currency_code": "860",
                    }
                ],
            },
        ),
    )

    response = service.discover_filial_codes()
    updated = store.get_smartup_organization(organization.id)

    assert response.items
    assert response.items[0].filial_code == "16114091"
    assert response.items[0].status == "found"
    assert updated is not None
    assert updated.filial_code == "16114091"


def test_smartup_discover_filial_codes_ignores_contaminated_raw_rows() -> None:
    store = InMemoryCoreDataLayer()
    service = SmartUpAccountService(target=store)
    organization = service.create_organization(
        SmartUpOrganizationCreateRequest(
            name="Acme Mixed",
            company_id="11300",
            filial_id="14475622",
            project_code="trade",
            is_active=True,
        ),
    )
    service.create_organization(
        SmartUpOrganizationCreateRequest(
            name="Other Org",
            company_id="11300",
            filial_id="16114091",
            project_code="trade",
            is_active=True,
        ),
    )

    store.upsert_smartup_raw_record(
        SmartUpRawRecord(
            organization_id=organization.id,
            filial_id="14475622",
            request_filial_id="14475622",
            entity_type="sales",
            source_endpoint="/b/trade/txs/tdeal/order$export",
            response_filial_id="19330532",
            response_payload={
                "order": [
                    {
                        "deal_id": "268805991",
                        "filial_code": "16114091",
                        "currency_code": "860",
                    }
                ],
            },
        ),
    )

    response = service.discover_filial_codes()
    updated = store.get_smartup_organization(organization.id)

    assert response.items
    assert response.items[0].filial_code is None
    assert response.items[0].status == "not_found"
    assert updated is not None
    assert updated.filial_code is None


def test_smartup_build_client_persists_org_credentials_for_manual_migration() -> None:
    store = InMemoryCoreDataLayer()
    service = SmartUpAccountService(target=store)
    organization = service.create_organization(
        SmartUpOrganizationCreateRequest(
            name="Acme",
            company_id="11300",
            filial_id="14475622",
            project_code="trade",
            is_active=True,
        ),
    )

    client = service.build_client(
        SmartUpAccessPayload(
            base_url="https://smartup.online",
            username="demo",
            password="secret",
            filial_id=organization.filial_id,
            project_code=organization.project_code,
        ),
        organization,
    )

    setting = store.get_app_setting(f"smartup:organization_credentials:{organization.id}")
    assert setting is not None
    assert setting.setting_value["organization_id"] == str(organization.id)
    assert setting.setting_value["company_id"] == organization.company_id
    assert setting.setting_value["filial_id"] == organization.filial_id
    assert setting.setting_value["project_code"] == organization.project_code
    assert setting.setting_value["username"] == "demo"
    assert setting.setting_value["password"] == "secret"
    assert client.settings.username == "demo"
    assert client.settings.password == "secret"


def test_smartup_history_migration_reports_batch_errors(monkeypatch) -> None:
    service = SmartUpAccountService(target=InMemoryCoreDataLayer())

    monkeypatch.setattr(SmartUpAccountService, "build_client", lambda self, payload: object())

    class FakeRunner:
        def __init__(
            self,
            *,
            client,  # noqa: ANN001
            target,  # noqa: ANN001
            business_id: UUID,
            business_name: str,
            business_external_ref: str | None = None,
            smartup_filial_id: str | None = None,
            smartup_filial_code: str | None = None,
            connector=None,  # noqa: ANN001
        ) -> None:
            self.target = target
            self.business_id = business_id
            self.business_external_ref = business_external_ref or "acme"

        def run(self, *, history_start, history_end, chunk_days):  # noqa: ANN001
            source_system = self.target.register_source_system(
                SourceSystem(
                    business_id=self.business_id,
                    name="SmartUp",
                    source_type="erp",
                    external_ref=self.business_external_ref,
                ),
            )
            batch = self.target.upsert_ingestion_batch(
                IngestionBatch(
                    business_id=self.business_id,
                    source_system_id=source_system.source_system_id,
                    batch_name="Legal entities initial",
                    status=IngestionBatchStatus.FAILED,
                    started_at=datetime(2026, 7, 28, tzinfo=UTC),
                    finished_at=datetime(2026, 7, 28, tzinfo=UTC),
                    metadata={
                        "endpoint": "/b/anor/mxsx/mr/legal_person$export",
                        "payload": {"offset": 0, "limit": 50},
                    },
                ),
            )
            self.target.record_ingestion_error(
                IngestionError(
                    batch_id=batch.batch_id,
                    business_id=self.business_id,
                    entity_type="legal_person",
                    error_code="HTTPStatusError",
                    error_message="Запрашиваемая страница или ресурс не найдены.",
                    metadata={
                        "endpoint": "/b/anor/mxsx/mr/legal_person$export",
                        "payload": {"offset": 0, "limit": 50},
                    },
                ),
            )
            return {"batches": 1, "records": 0, "errors": 1}

    monkeypatch.setattr(
        "app.integrations.smartup.operations.SmartUpHistoricalImportRunner",
        FakeRunner,
    )

    response = service.migrate_history(
        SmartUpHistoryMigrationRequest(
            base_url="https://smartup.online",
            username="demo",
            password="secret",
            filial_id="86401",
            organizations=[
                SmartUpMigrationOrganizationInput(
                    name="Acme",
                    filial_id="10",
                    selected=True,
                ),
            ],
        ),
    )

    assert response.summary.errors == 1
    assert response.batch_errors
    error = response.batch_errors[0]
    assert error.organization_name == "Acme"
    assert error.source_endpoint == "/b/anor/mxsx/mr/legal_person$export"
    assert error.requested_url == "/b/anor/mxsx/mr/legal_person$export"
    assert error.error_code == "HTTPStatusError"
    assert "не найдены" in error.error_message


def test_smartup_one_day_check_forces_one_day_window(monkeypatch) -> None:
    service = SmartUpAccountService(target=InMemoryCoreDataLayer())
    seen_chunk_days: list[int] = []

    monkeypatch.setattr(SmartUpAccountService, "build_client", lambda self, payload: object())

    class FakeRunner:
        def __init__(
            self,
            *,
            client,  # noqa: ANN001
            target,  # noqa: ANN001
            business_id: UUID,
            business_name: str,
            business_external_ref: str | None = None,
            smartup_filial_id: str | None = None,
            smartup_filial_code: str | None = None,
            connector=None,  # noqa: ANN001
        ) -> None:
            self.target = target
            self.business_id = business_id
            self.business_external_ref = business_external_ref or "acme"

        def run(self, *, history_start, history_end, chunk_days, migration_mode):  # noqa: ANN001
            seen_chunk_days.append(chunk_days)
            assert migration_mode == SmartUpMigrationMode.ONE_DAY_CHECK
            return {"batches": 1, "records": 0, "errors": 0}

    monkeypatch.setattr(
        "app.integrations.smartup.operations.SmartUpHistoricalImportRunner",
        FakeRunner,
    )

    response = service.migrate_history(
        SmartUpHistoryMigrationRequest(
            base_url="https://smartup.online",
            username="demo",
            password="secret",
            filial_id="86401",
            migration_mode=SmartUpMigrationMode.ONE_DAY_CHECK,
            organizations=[
                SmartUpMigrationOrganizationInput(
                    name="Acme",
                    filial_id="10",
                    selected=True,
                ),
            ],
        ),
    )

    assert response.status == "completed"
    assert seen_chunk_days == [1]


def test_smartup_migrate_organization_materializes_canonical_v2(monkeypatch) -> None:
    store = InMemoryCoreDataLayer()
    service = SmartUpAccountService(target=store)
    organization = service.create_organization(
        SmartUpOrganizationCreateRequest(
            name="Acme",
            company_id="11300",
            filial_id="14475622",
            project_code="trade",
            is_active=True,
        ),
    )
    canonical_calls: list[list[UUID]] = []

    def fake_migrate_organization_with_client(self, **kwargs):  # noqa: ANN001
        result = SmartUpMigrationOrganizationResult(
            organization_id=organization.id,
            name=organization.name,
            company_id=organization.company_id,
            filial_id=organization.filial_id,
            project_code=organization.project_code,
            summary=SmartUpMigrationSummary(organizations=1),
            counters={"batches": 1, "records": 2, "errors": 0},
            runs=[],
        )
        return result, [], [], {"batches": 1, "records": 2, "errors": 0}, SmartUpMigrationSummary(
            organizations=1,
        )

    monkeypatch.setattr(
        SmartUpAccountService,
        "discover_filial_codes",
        lambda self: None,
    )
    monkeypatch.setattr(
        SmartUpAccountService,
        "_get_required_organization",
        lambda self, organization_id: organization,
    )
    monkeypatch.setattr(
        SmartUpAccountService,
        "_migrate_organization_with_client",
        fake_migrate_organization_with_client,
    )
    monkeypatch.setattr(
        SmartUpAccountService,
        "_touch_organization_sync",
        lambda self, organization_id: None,
    )
    monkeypatch.setattr(
        SmartUpAccountService,
        "_materialize_canonical_v2",
        lambda self, organization_ids=None: canonical_calls.append(list(organization_ids or [])),
    )

    response = service.migrate_organization(
        organization.id,
        SmartUpAccessPayload(
            base_url="https://smartup.online",
            username="demo",
            password="secret",
            filial_id=organization.filial_id,
            project_code=organization.project_code,
        ),
    )

    assert response.status == "completed"
    assert canonical_calls == [[organization.id]]
