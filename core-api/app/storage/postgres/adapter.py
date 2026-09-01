"""PostgreSQL storage adapter for the core data layer."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar
from uuid import UUID

from psycopg.types.json import Jsonb

from app.core.data_layer.canonical_v2 import (
    CanonicalCrossOrgMovement,
    CanonicalCrossOrgMovementItem,
    CanonicalCustomer,
    CanonicalCustomerGroup,
    CanonicalCustomerReturn,
    CanonicalCustomerReturnItem,
    CanonicalFinancialAccount,
    CanonicalFinancialOperation,
    CanonicalInternalMovement,
    CanonicalInternalMovementItem,
    CanonicalInventoryBalance,
    CanonicalMediaAsset,
    CanonicalOrder,
    CanonicalOrganization,
    CanonicalPayment,
    CanonicalPaymentAllocation,
    CanonicalPriceType,
    CanonicalProduct,
    CanonicalProductCategory,
    CanonicalProductPrice,
    CanonicalPurchase,
    CanonicalPurchaseItem,
    CanonicalSale,
    CanonicalSaleItem,
    CanonicalSalesRep,
    CanonicalStocktaking,
    CanonicalStocktakingItem,
    CanonicalSupplierReturn,
    CanonicalSupplierReturnItem,
    CanonicalVisit,
    CanonicalVisitComment,
    CanonicalVisitEquipment,
    CanonicalVisitQuizAnswer,
    CanonicalVisitStock,
    CanonicalWarehouse,
    CanonicalWarehouseReceipt,
    CanonicalWarehouseReceiptItem,
    CanonicalWorkingZone,
    CanonicalWriteoff,
    CanonicalWriteoffItem,
)
from app.core.data_layer.contracts import CoreDataReader, CoreDataWriter
from app.core.data_layer.entities import (
    AppSetting,
    BusinessIdentity,
    ContactProfile,
    FinanceEntry,
    IngestionBatch,
    IngestionError,
    MarketingActivity,
    SaleRecord,
    SourceSystem,
)
from app.core.data_layer.models import CoreRecord, CoreRecordKind, KPIValue
from app.core.data_layer.normalized import (
    BankOperation,
    BusinessDocument,
    BusinessDocumentItem,
    Customer,
    InventoryBalance,
    Payment,
    PriceType,
    Product,
    ProductCategory,
    ProductPrice,
    Sale,
    SaleItem,
    Visit,
    Warehouse,
)
from app.integrations.smartup.models import (
    InventorySnapshot,
    MigrationBatch,
    NormalizationIssue,
    SmartUpMigrationRun,
    SmartUpOrganization,
    SmartUpRawRecord,
    SyncCheckpoint,
)
from app.core.ai_readonly_sql import AI_ANALYTICAL_VIEW_DDL, ALLOWED_VIEWS
from app.integrations.meta.schema import META_DDL
from app.integrations.youtube.schema import YOUTUBE_DDL
from app.integrations.attribution_schema import ATTRIBUTION_DDL
from app.storage.postgres.ddl import render_core_data_layer_ddl

Row = dict[str, Any]
ModelT = TypeVar("ModelT")


class PostgresCursor(Protocol):
    """DB-API compatible cursor that returns mapping rows."""

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> Any:
        """Execute a SQL statement."""

    def fetchone(self) -> Row | None:
        """Return one row as a mapping."""

    def fetchall(self) -> list[Row]:
        """Return all rows as mappings."""

    def __enter__(self) -> PostgresCursor:
        """Enter cursor context."""

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        """Exit cursor context."""


class PostgresConnection(Protocol):
    """DB-API compatible connection."""

    def cursor(self) -> PostgresCursor:
        """Open a cursor."""

    def commit(self) -> None:
        """Commit the current transaction."""

    def rollback(self) -> None:
        """Rollback the current transaction."""


PostgresConnectionFactory = Callable[[], PostgresConnection]


@dataclass(slots=True)
class PostgresCoreStore(CoreDataReader, CoreDataWriter):
    """PostgreSQL-backed core data store."""

    connection_factory: PostgresConnectionFactory

    @classmethod
    def from_dsn(cls, dsn: str) -> PostgresCoreStore:
        """Create a store from a PostgreSQL DSN.

        The psycopg import is intentionally lazy so the project can run without
        the dependency until PostgreSQL is enabled.
        """

        def _factory() -> PostgresConnection:
            try:
                import psycopg  # type: ignore[import-not-found]
            except ImportError as exc:  # pragma: no cover - runtime environment dependent
                msg = "psycopg is required for PostgreSQL storage"
                raise RuntimeError(msg) from exc

            return psycopg.connect(dsn)

        return cls(connection_factory=_factory)

    def ensure_schema(self) -> None:
        """Create core tables and indexes if they do not exist."""

        self._ensure_smartup_organization_compatibility()
        self._ensure_migration_batch_compatibility()
        self._ensure_smartup_raw_record_compatibility()
        self._ensure_normalized_entity_compatibility()
        self._execute_many(render_core_data_layer_ddl())
        self._execute_many(list(META_DDL))
        self._execute_many(list(YOUTUBE_DDL))
        self._execute_many(list(ATTRIBUTION_DDL))
        self._execute_many(list(AI_ANALYTICAL_VIEW_DDL))

    def _ensure_smartup_organization_compatibility(self) -> None:
        """Backfill columns needed by the current SmartUp organization model."""

        statements = (
            """
            ALTER TABLE IF EXISTS smartup_organizations
            ADD COLUMN IF NOT EXISTS company_id text DEFAULT '11300'
            """,
            """
            ALTER TABLE IF EXISTS smartup_organizations
            ADD COLUMN IF NOT EXISTS project_code text DEFAULT 'trade'
            """,
            """
            ALTER TABLE IF EXISTS smartup_organizations
            ADD COLUMN IF NOT EXISTS filial_code text
            """,
            """
            ALTER TABLE IF EXISTS smartup_organizations
            ADD COLUMN IF NOT EXISTS sort_order integer DEFAULT 0
            """,
            """
            ALTER TABLE IF EXISTS smartup_organizations
            ADD COLUMN IF NOT EXISTS last_sync_at timestamptz
            """,
            """
            ALTER TABLE IF EXISTS smartup_organizations
            ADD COLUMN IF NOT EXISTS metadata jsonb DEFAULT '{}'::jsonb
            """,
            """
            ALTER TABLE IF EXISTS smartup_organizations
            ADD COLUMN IF NOT EXISTS created_at timestamptz DEFAULT NOW()
            """,
            """
            ALTER TABLE IF EXISTS smartup_organizations
            ADD COLUMN IF NOT EXISTS updated_at timestamptz DEFAULT NOW()
            """,
        )
        self._execute_many(statements)

    def _ensure_migration_batch_compatibility(self) -> None:
        """Backfill columns needed by the current SmartUp migration batch model."""

        statements = (
            """
            ALTER TABLE IF EXISTS migration_batches
            ADD COLUMN IF NOT EXISTS filial_id text
            """,
            """
            ALTER TABLE IF EXISTS migration_batches
            ADD COLUMN IF NOT EXISTS endpoint text
            """,
            """
            ALTER TABLE IF EXISTS migration_batches
            ADD COLUMN IF NOT EXISTS request_payload jsonb
            """,
        )
        self._execute_many(statements)

    def _ensure_smartup_raw_record_compatibility(self) -> None:
        """Backfill columns needed by the current SmartUp raw record model."""

        statements = (
            """
            ALTER TABLE IF EXISTS smartup_raw_records
            ADD COLUMN IF NOT EXISTS request_filial_id text
            """,
            """
            ALTER TABLE IF EXISTS smartup_raw_records
            ADD COLUMN IF NOT EXISTS request_company_id text
            """,
            """
            ALTER TABLE IF EXISTS smartup_raw_records
            ADD COLUMN IF NOT EXISTS request_project_code text
            """,
            """
            ALTER TABLE IF EXISTS smartup_raw_records
            ADD COLUMN IF NOT EXISTS response_envelope jsonb
            """,
            """
            ALTER TABLE IF EXISTS smartup_raw_records
            ADD COLUMN IF NOT EXISTS response_filial_id text
            """,
        )
        self._execute_many(statements)

    def _ensure_normalized_entity_compatibility(self) -> None:
        """Backfill normalized columns required by the current pipeline."""

        statements = (
            """
            ALTER TABLE IF EXISTS normalized_sale_items
            ADD COLUMN IF NOT EXISTS sale_id uuid
            """,
            """
            ALTER TABLE IF EXISTS normalized_sale_items
            ADD COLUMN IF NOT EXISTS product_id uuid
            """,
            """
            ALTER TABLE IF EXISTS normalized_sales
            ADD COLUMN IF NOT EXISTS customer_id uuid
            """,
            """
            ALTER TABLE IF EXISTS normalized_payments
            ADD COLUMN IF NOT EXISTS sale_id uuid
            """,
            """
            ALTER TABLE IF EXISTS normalized_visits
            ADD COLUMN IF NOT EXISTS customer_id uuid
            """,
            """
            ALTER TABLE IF EXISTS normalized_inventory_balances
            ADD COLUMN IF NOT EXISTS warehouse_id uuid
            """,
            """
            ALTER TABLE IF EXISTS normalized_inventory_balances
            ADD COLUMN IF NOT EXISTS product_id uuid
            """,
            """
            ALTER TABLE IF EXISTS normalized_warehouses
            ALTER COLUMN name DROP NOT NULL
            """,
        )
        self._execute_many(statements)

    def get_business(self, business_id: UUID) -> BusinessIdentity | None:
        return self._fetch_one(
            "SELECT * FROM businesses WHERE business_id = %s",
            (business_id,),
            BusinessIdentity,
        )

    def list_businesses(self) -> Iterable[BusinessIdentity]:
        return self._fetch_all(
            "SELECT * FROM businesses ORDER BY created_at", None, BusinessIdentity
        )

    def get_app_setting(self, setting_key: str) -> AppSetting | None:
        return self._fetch_one(
            "SELECT * FROM app_settings WHERE setting_key = %s",
            (setting_key,),
            AppSetting,
        )

    def list_app_settings(self) -> Iterable[AppSetting]:
        return self._fetch_all(
            "SELECT * FROM app_settings ORDER BY setting_key",
            None,
            AppSetting,
        )

    def get_source_system(self, source_system_id: UUID) -> SourceSystem | None:
        return self._fetch_one(
            "SELECT * FROM source_systems WHERE source_system_id = %s",
            (source_system_id,),
            SourceSystem,
        )

    def list_source_systems(self, business_id: UUID | None = None) -> Iterable[SourceSystem]:
        return self._fetch_model_list("source_systems", SourceSystem, business_id)

    def get_contact(self, contact_id: UUID) -> ContactProfile | None:
        return self._fetch_one(
            "SELECT * FROM contacts WHERE contact_id = %s",
            (contact_id,),
            ContactProfile,
        )

    def list_contacts(self, business_id: UUID | None = None) -> Iterable[ContactProfile]:
        return self._fetch_model_list("contacts", ContactProfile, business_id)

    def get_sale(self, sale_id: UUID) -> SaleRecord | None:
        return self._fetch_one("SELECT * FROM sales WHERE sale_id = %s", (sale_id,), SaleRecord)

    def list_sales(self, business_id: UUID | None = None) -> Iterable[SaleRecord]:
        return self._fetch_model_list("sales", SaleRecord, business_id)

    def get_marketing_activity(self, activity_id: UUID) -> MarketingActivity | None:
        return self._fetch_one(
            "SELECT * FROM marketing_activities WHERE activity_id = %s",
            (activity_id,),
            MarketingActivity,
        )

    def list_marketing_activities(
        self, business_id: UUID | None = None
    ) -> Iterable[MarketingActivity]:
        return self._fetch_model_list(
            "marketing_activities",
            MarketingActivity,
            business_id,
        )

    def get_finance_entry(self, entry_id: UUID) -> FinanceEntry | None:
        return self._fetch_one(
            "SELECT * FROM finance_entries WHERE entry_id = %s",
            (entry_id,),
            FinanceEntry,
        )

    def list_finance_entries(self, business_id: UUID | None = None) -> Iterable[FinanceEntry]:
        return self._fetch_model_list("finance_entries", FinanceEntry, business_id)

    def list_ingestion_batches(self, business_id: UUID | None = None) -> Iterable[IngestionBatch]:
        return self._fetch_model_list("ingestion_batches", IngestionBatch, business_id)

    def list_ingestion_errors(self, batch_id: UUID | None = None) -> Iterable[IngestionError]:
        if batch_id is None:
            return self._fetch_all(
                "SELECT * FROM ingestion_errors ORDER BY created_at",
                None,
                IngestionError,
            )
        return self._fetch_all(
            "SELECT * FROM ingestion_errors WHERE batch_id = %s ORDER BY created_at",
            (batch_id,),
            IngestionError,
        )

    def list_records(
        self,
        business_id: UUID | None = None,
        kind: CoreRecordKind | None = None,
    ) -> Iterable[CoreRecord]:
        clauses = []
        params: list[Any] = []
        if business_id is not None:
            clauses.append("business_id = %s")
            params.append(business_id)
        if kind is not None:
            clauses.append("kind = %s")
            params.append(kind.value)
        sql = "SELECT * FROM core_records"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY occurred_at DESC"
        return self._fetch_all(sql, tuple(params) if params else None, CoreRecord)

    def list_kpis(self, business_id: UUID | None = None) -> Iterable[KPIValue]:
        return self._fetch_model_list("kpi_snapshots", KPIValue, business_id)

    def get_smartup_organization(self, organization_id: UUID) -> SmartUpOrganization | None:
        return self._fetch_one(
            "SELECT * FROM smartup_organizations WHERE id = %s",
            (organization_id,),
            SmartUpOrganization,
        )

    def list_smartup_organizations(
        self,
        integration_id: UUID | None = None,
        is_active: bool | None = None,
    ) -> Iterable[SmartUpOrganization]:
        clauses = []
        params: list[Any] = []
        if integration_id is not None:
            clauses.append("integration_id = %s")
            params.append(integration_id)
        if is_active is not None:
            clauses.append("is_active = %s")
            params.append(is_active)
        sql = "SELECT * FROM smartup_organizations"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY sort_order, name, created_at"
        return self._fetch_all(sql, tuple(params) if params else None, SmartUpOrganization)

    def list_smartup_migration_runs(
        self,
        organization_id: UUID | None = None,
        entity_type: str | None = None,
    ) -> Iterable[SmartUpMigrationRun]:
        clauses = []
        params: list[Any] = []
        if organization_id is not None:
            clauses.append("organization_id = %s")
            params.append(organization_id)
        if entity_type is not None:
            clauses.append("entity_type = %s")
            params.append(entity_type)
        sql = "SELECT * FROM smartup_migration_runs"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY started_at DESC"
        return self._fetch_all(sql, tuple(params) if params else None, SmartUpMigrationRun)

    def get_sync_checkpoint(
        self,
        organization_id: UUID,
        entity_type: str,
        migration_mode: str,
    ) -> SyncCheckpoint | None:
        return self._fetch_one(
            """
            SELECT * FROM sync_checkpoints
            WHERE organization_id = %s AND entity_type = %s AND migration_mode = %s
            """.strip(),
            (organization_id, entity_type, migration_mode),
            SyncCheckpoint,
        )

    def list_sync_checkpoints(
        self,
        organization_id: UUID | None = None,
        entity_type: str | None = None,
        migration_mode: str | None = None,
    ) -> Iterable[SyncCheckpoint]:
        clauses = []
        params: list[Any] = []
        if organization_id is not None:
            clauses.append("organization_id = %s")
            params.append(organization_id)
        if entity_type is not None:
            clauses.append("entity_type = %s")
            params.append(entity_type)
        if migration_mode is not None:
            clauses.append("migration_mode = %s")
            params.append(migration_mode)
        sql = "SELECT * FROM sync_checkpoints"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY updated_at DESC"
        return self._fetch_all(sql, tuple(params) if params else None, SyncCheckpoint)

    def list_migration_batches(
        self,
        organization_id: UUID | None = None,
        entity_type: str | None = None,
        migration_mode: str | None = None,
    ) -> Iterable[MigrationBatch]:
        clauses = []
        params: list[Any] = []
        if organization_id is not None:
            clauses.append("organization_id = %s")
            params.append(organization_id)
        if entity_type is not None:
            clauses.append("entity_type = %s")
            params.append(entity_type)
        if migration_mode is not None:
            clauses.append("migration_mode = %s")
            params.append(migration_mode)
        sql = "SELECT * FROM migration_batches"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY started_at DESC"
        return self._fetch_all(sql, tuple(params) if params else None, MigrationBatch)

    def list_inventory_snapshots(
        self,
        organization_id: UUID | None = None,
        product_external_id: str | None = None,
    ) -> Iterable[InventorySnapshot]:
        clauses = []
        params: list[Any] = []
        if organization_id is not None:
            clauses.append("organization_id = %s")
            params.append(organization_id)
        if product_external_id is not None:
            clauses.append("product_external_id = %s")
            params.append(product_external_id)
        sql = "SELECT * FROM inventory_snapshots"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY snapshot_date DESC"
        return self._fetch_all(sql, tuple(params) if params else None, InventorySnapshot)

    def get_smartup_raw_record(self, record_id: UUID) -> SmartUpRawRecord | None:
        return self._fetch_one(
            "SELECT * FROM smartup_raw_records WHERE id = %s",
            (record_id,),
            SmartUpRawRecord,
        )

    def list_smartup_raw_records(
        self,
        organization_id: UUID | None = None,
        entity_type: str | None = None,
        batch_id: UUID | None = None,
        processing_status: str | None = None,
    ) -> Iterable[SmartUpRawRecord]:
        clauses = []
        params: list[Any] = []
        if organization_id is not None:
            clauses.append("organization_id = %s")
            params.append(organization_id)
        if entity_type is not None:
            clauses.append("entity_type = %s")
            params.append(entity_type)
        if batch_id is not None:
            clauses.append("batch_id = %s")
            params.append(batch_id)
        if processing_status is not None:
            clauses.append("processing_status = %s")
            params.append(processing_status)
        sql = "SELECT * FROM smartup_raw_records"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY imported_at DESC"
        return self._fetch_all(sql, tuple(params) if params else None, SmartUpRawRecord)

    def list_normalization_issues(
        self,
        raw_record_id: UUID | None = None,
        organization_id: UUID | None = None,
        entity_type: str | None = None,
    ) -> Iterable[NormalizationIssue]:
        clauses = []
        params: list[Any] = []
        if raw_record_id is not None:
            clauses.append("raw_record_id = %s")
            params.append(raw_record_id)
        if organization_id is not None:
            clauses.append("organization_id = %s")
            params.append(organization_id)
        if entity_type is not None:
            clauses.append("entity_type = %s")
            params.append(entity_type)
        sql = "SELECT * FROM normalization_issues"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at DESC"
        return self._fetch_all(sql, tuple(params) if params else None, NormalizationIssue)

    def get_customer(self, customer_id: UUID) -> Customer | None:
        return self._fetch_one(
            "SELECT * FROM normalized_customers WHERE id = %s",
            (customer_id,),
            Customer,
        )

    def list_customers(self, organization_id: UUID | None = None) -> Iterable[Customer]:
        return self._fetch_source_list("normalized_customers", Customer, organization_id)

    def get_product_category(self, category_id: UUID) -> ProductCategory | None:
        return self._fetch_one(
            "SELECT * FROM normalized_product_categories WHERE id = %s",
            (category_id,),
            ProductCategory,
        )

    def list_product_categories(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[ProductCategory]:
        return self._fetch_source_list(
            "normalized_product_categories",
            ProductCategory,
            organization_id,
        )

    def get_product(self, product_id: UUID) -> Product | None:
        return self._fetch_one(
            "SELECT * FROM normalized_products WHERE id = %s",
            (product_id,),
            Product,
        )

    def list_products(self, organization_id: UUID | None = None) -> Iterable[Product]:
        return self._fetch_source_list("normalized_products", Product, organization_id)

    def get_warehouse(self, warehouse_id: UUID) -> Warehouse | None:
        return self._fetch_one(
            "SELECT * FROM normalized_warehouses WHERE id = %s",
            (warehouse_id,),
            Warehouse,
        )

    def list_warehouses(self, organization_id: UUID | None = None) -> Iterable[Warehouse]:
        return self._fetch_source_list("normalized_warehouses", Warehouse, organization_id)

    def get_sale_v2(self, sale_id: UUID) -> Sale | None:
        return self._fetch_one(
            "SELECT * FROM normalized_sales WHERE id = %s",
            (sale_id,),
            Sale,
        )

    def list_sales_v2(self, organization_id: UUID | None = None) -> Iterable[Sale]:
        return self._fetch_source_list("normalized_sales", Sale, organization_id)

    def get_sale_item(self, sale_item_id: UUID) -> SaleItem | None:
        return self._fetch_one(
            "SELECT * FROM normalized_sale_items WHERE id = %s",
            (sale_item_id,),
            SaleItem,
        )

    def list_sale_items(self, organization_id: UUID | None = None) -> Iterable[SaleItem]:
        return self._fetch_source_list("normalized_sale_items", SaleItem, organization_id)

    def delete_sale_items_for_sale_external_id(
        self,
        organization_id: UUID,
        sale_external_id: str,
    ) -> None:
        self._execute(
            (
                "DELETE FROM normalized_sale_items "
                "WHERE organization_id = %s AND sale_external_id = %s"
            ),
            (organization_id, sale_external_id),
        )

    def get_payment(self, payment_id: UUID) -> Payment | None:
        return self._fetch_one(
            "SELECT * FROM normalized_payments WHERE id = %s",
            (payment_id,),
            Payment,
        )

    def list_payments(self, organization_id: UUID | None = None) -> Iterable[Payment]:
        return self._fetch_source_list("normalized_payments", Payment, organization_id)

    def get_inventory_balance(self, inventory_balance_id: UUID) -> InventoryBalance | None:
        return self._fetch_one(
            "SELECT * FROM normalized_inventory_balances WHERE id = %s",
            (inventory_balance_id,),
            InventoryBalance,
        )

    def list_inventory_balances(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[InventoryBalance]:
        return self._fetch_source_list(
            "normalized_inventory_balances",
            InventoryBalance,
            organization_id,
        )

    def get_visit(self, visit_id: UUID) -> Visit | None:
        return self._fetch_one(
            "SELECT * FROM normalized_visits WHERE id = %s",
            (visit_id,),
            Visit,
        )

    def list_visits(self, organization_id: UUID | None = None) -> Iterable[Visit]:
        return self._fetch_source_list("normalized_visits", Visit, organization_id)

    def get_bank_operation(self, bank_operation_id: UUID) -> BankOperation | None:
        return self._fetch_one(
            "SELECT * FROM normalized_bank_operations WHERE id = %s",
            (bank_operation_id,),
            BankOperation,
        )

    def list_bank_operations(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[BankOperation]:
        return self._fetch_source_list(
            "normalized_bank_operations",
            BankOperation,
            organization_id,
        )

    def get_business_document(self, document_id: UUID) -> BusinessDocument | None:
        return self._fetch_one(
            "SELECT * FROM normalized_business_documents WHERE id = %s",
            (document_id,),
            BusinessDocument,
        )

    def list_business_documents(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[BusinessDocument]:
        return self._fetch_source_list(
            "normalized_business_documents",
            BusinessDocument,
            organization_id,
        )

    def get_business_document_item(self, item_id: UUID) -> BusinessDocumentItem | None:
        return self._fetch_one(
            "SELECT * FROM normalized_business_document_items WHERE id = %s",
            (item_id,),
            BusinessDocumentItem,
        )

    def list_business_document_items(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[BusinessDocumentItem]:
        return self._fetch_source_list(
            "normalized_business_document_items",
            BusinessDocumentItem,
            organization_id,
        )

    def get_canonical_organization(self, organization_id: UUID) -> CanonicalOrganization | None:
        return self._fetch_one(
            "SELECT * FROM canonical_organizations WHERE organization_id = %s",
            (organization_id,),
            CanonicalOrganization,
        )

    def list_canonical_organizations(self) -> Iterable[CanonicalOrganization]:
        return self._fetch_all(
            "SELECT * FROM canonical_organizations ORDER BY sort_order, name, organization_id",
            None,
            CanonicalOrganization,
        )

    def get_canonical_customer_group(self, group_id: UUID) -> CanonicalCustomerGroup | None:
        return self._fetch_one(
            "SELECT * FROM canonical_customer_groups WHERE id = %s",
            (group_id,),
            CanonicalCustomerGroup,
        )

    def list_canonical_customer_groups(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalCustomerGroup]:
        return self._fetch_source_list(
            "canonical_customer_groups",
            CanonicalCustomerGroup,
            organization_id,
        )

    def get_canonical_customer(self, customer_id: UUID) -> CanonicalCustomer | None:
        return self._fetch_one(
            "SELECT * FROM canonical_customers WHERE id = %s",
            (customer_id,),
            CanonicalCustomer,
        )

    def list_canonical_customers(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalCustomer]:
        return self._fetch_source_list("canonical_customers", CanonicalCustomer, organization_id)

    def get_canonical_product_category(
        self,
        category_id: UUID,
    ) -> CanonicalProductCategory | None:
        return self._fetch_one(
            "SELECT * FROM canonical_product_categories WHERE id = %s",
            (category_id,),
            CanonicalProductCategory,
        )

    def list_canonical_product_categories(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalProductCategory]:
        return self._fetch_source_list(
            "canonical_product_categories",
            CanonicalProductCategory,
            organization_id,
        )

    def get_canonical_product(self, product_id: UUID) -> CanonicalProduct | None:
        return self._fetch_one(
            "SELECT * FROM canonical_products WHERE id = %s",
            (product_id,),
            CanonicalProduct,
        )

    def list_canonical_products(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalProduct]:
        return self._fetch_source_list("canonical_products", CanonicalProduct, organization_id)

    def get_canonical_warehouse(self, warehouse_id: UUID) -> CanonicalWarehouse | None:
        return self._fetch_one(
            "SELECT * FROM canonical_warehouses WHERE id = %s",
            (warehouse_id,),
            CanonicalWarehouse,
        )

    def list_canonical_warehouses(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalWarehouse]:
        return self._fetch_source_list("canonical_warehouses", CanonicalWarehouse, organization_id)

    def get_canonical_price_type(self, price_type_id: UUID) -> CanonicalPriceType | None:
        return self._fetch_one(
            "SELECT * FROM canonical_price_types WHERE id = %s",
            (price_type_id,),
            CanonicalPriceType,
        )

    def list_canonical_price_types(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalPriceType]:
        return self._fetch_source_list("canonical_price_types", CanonicalPriceType, organization_id)

    def get_canonical_product_price(self, product_price_id: UUID) -> CanonicalProductPrice | None:
        return self._fetch_one(
            "SELECT * FROM canonical_product_prices WHERE id = %s",
            (product_price_id,),
            CanonicalProductPrice,
        )

    def list_canonical_product_prices(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalProductPrice]:
        return self._fetch_source_list(
            "canonical_product_prices",
            CanonicalProductPrice,
            organization_id,
        )

    def get_canonical_sales_rep(self, sales_rep_id: UUID) -> CanonicalSalesRep | None:
        return self._fetch_one(
            "SELECT * FROM canonical_sales_reps WHERE id = %s",
            (sales_rep_id,),
            CanonicalSalesRep,
        )

    def list_canonical_sales_reps(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalSalesRep]:
        return self._fetch_source_list("canonical_sales_reps", CanonicalSalesRep, organization_id)

    def get_canonical_working_zone(self, working_zone_id: UUID) -> CanonicalWorkingZone | None:
        return self._fetch_one(
            "SELECT * FROM canonical_working_zones WHERE id = %s",
            (working_zone_id,),
            CanonicalWorkingZone,
        )

    def list_canonical_working_zones(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalWorkingZone]:
        return self._fetch_source_list(
            "canonical_working_zones",
            CanonicalWorkingZone,
            organization_id,
        )

    def get_canonical_visit(self, visit_id: UUID) -> CanonicalVisit | None:
        return self._fetch_one(
            "SELECT * FROM canonical_visits WHERE id = %s",
            (visit_id,),
            CanonicalVisit,
        )

    def list_canonical_visits(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalVisit]:
        from app.core.data_layer.visit_identity import deduplicate_cross_organization_visits

        rows = self._fetch_source_list("canonical_visits", CanonicalVisit, organization_id)
        return deduplicate_cross_organization_visits(rows)

    def get_canonical_visit_stock(self, visit_stock_id: UUID) -> CanonicalVisitStock | None:
        return self._fetch_one(
            "SELECT * FROM canonical_visit_stocks WHERE id = %s",
            (visit_stock_id,),
            CanonicalVisitStock,
        )

    def list_canonical_visit_stocks(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalVisitStock]:
        return self._fetch_source_list(
            "canonical_visit_stocks",
            CanonicalVisitStock,
            organization_id,
        )

    def get_canonical_visit_quiz_answer(
        self,
        quiz_answer_id: UUID,
    ) -> CanonicalVisitQuizAnswer | None:
        return self._fetch_one(
            "SELECT * FROM canonical_visit_quiz_answers WHERE id = %s",
            (quiz_answer_id,),
            CanonicalVisitQuizAnswer,
        )

    def list_canonical_visit_quiz_answers(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalVisitQuizAnswer]:
        return self._fetch_source_list(
            "canonical_visit_quiz_answers",
            CanonicalVisitQuizAnswer,
            organization_id,
        )

    def get_canonical_visit_equipment(
        self,
        equipment_id: UUID,
    ) -> CanonicalVisitEquipment | None:
        return self._fetch_one(
            "SELECT * FROM canonical_visit_equipments WHERE id = %s",
            (equipment_id,),
            CanonicalVisitEquipment,
        )

    def list_canonical_visit_equipments(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalVisitEquipment]:
        return self._fetch_source_list(
            "canonical_visit_equipments",
            CanonicalVisitEquipment,
            organization_id,
        )

    def get_canonical_visit_comment(self, comment_id: UUID) -> CanonicalVisitComment | None:
        return self._fetch_one(
            "SELECT * FROM canonical_visit_comments WHERE id = %s",
            (comment_id,),
            CanonicalVisitComment,
        )

    def list_canonical_visit_comments(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalVisitComment]:
        return self._fetch_source_list(
            "canonical_visit_comments",
            CanonicalVisitComment,
            organization_id,
        )

    def get_canonical_media_asset(self, media_asset_id: UUID) -> CanonicalMediaAsset | None:
        return self._fetch_one(
            "SELECT * FROM canonical_media_assets WHERE id = %s",
            (media_asset_id,),
            CanonicalMediaAsset,
        )

    def list_canonical_media_assets(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalMediaAsset]:
        return self._fetch_source_list(
            "canonical_media_assets",
            CanonicalMediaAsset,
            organization_id,
        )

    def get_canonical_order(self, order_id: UUID) -> CanonicalOrder | None:
        return self._fetch_one(
            "SELECT * FROM canonical_orders WHERE id = %s",
            (order_id,),
            CanonicalOrder,
        )

    def list_canonical_orders(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalOrder]:
        return self._fetch_source_list("canonical_orders", CanonicalOrder, organization_id)

    def get_canonical_sale(self, sale_id: UUID) -> CanonicalSale | None:
        return self._fetch_one(
            "SELECT * FROM canonical_sales WHERE id = %s",
            (sale_id,),
            CanonicalSale,
        )

    def list_canonical_sales(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalSale]:
        return self._fetch_source_list("canonical_sales", CanonicalSale, organization_id)

    def get_canonical_sale_item(self, sale_item_id: UUID) -> CanonicalSaleItem | None:
        return self._fetch_one(
            "SELECT * FROM canonical_sale_items WHERE id = %s",
            (sale_item_id,),
            CanonicalSaleItem,
        )

    def list_canonical_sale_items(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalSaleItem]:
        return self._fetch_source_list(
            "canonical_sale_items",
            CanonicalSaleItem,
            organization_id,
        )

    def get_canonical_payment(self, payment_id: UUID) -> CanonicalPayment | None:
        return self._fetch_one(
            "SELECT * FROM canonical_payments WHERE id = %s",
            (payment_id,),
            CanonicalPayment,
        )

    def list_canonical_payments(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalPayment]:
        return self._fetch_source_list("canonical_payments", CanonicalPayment, organization_id)

    def get_canonical_payment_allocation(
        self,
        allocation_id: UUID,
    ) -> CanonicalPaymentAllocation | None:
        return self._fetch_one(
            "SELECT * FROM canonical_payment_allocations WHERE id = %s",
            (allocation_id,),
            CanonicalPaymentAllocation,
        )

    def list_canonical_payment_allocations(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalPaymentAllocation]:
        return self._fetch_source_list(
            "canonical_payment_allocations",
            CanonicalPaymentAllocation,
            organization_id,
        )

    def get_canonical_financial_account(
        self,
        account_id: UUID,
    ) -> CanonicalFinancialAccount | None:
        return self._fetch_one(
            "SELECT * FROM canonical_financial_accounts WHERE id = %s",
            (account_id,),
            CanonicalFinancialAccount,
        )

    def list_canonical_financial_accounts(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalFinancialAccount]:
        return self._fetch_source_list(
            "canonical_financial_accounts",
            CanonicalFinancialAccount,
            organization_id,
        )

    def get_canonical_financial_operation(
        self,
        operation_id: UUID,
    ) -> CanonicalFinancialOperation | None:
        return self._fetch_one(
            "SELECT * FROM canonical_financial_operations WHERE id = %s",
            (operation_id,),
            CanonicalFinancialOperation,
        )

    def list_canonical_financial_operations(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalFinancialOperation]:
        return self._fetch_source_list(
            "canonical_financial_operations",
            CanonicalFinancialOperation,
            organization_id,
        )

    def get_canonical_customer_return(
        self,
        customer_return_id: UUID,
    ) -> CanonicalCustomerReturn | None:
        return self._fetch_one(
            "SELECT * FROM canonical_customer_returns WHERE id = %s",
            (customer_return_id,),
            CanonicalCustomerReturn,
        )

    def list_canonical_customer_returns(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalCustomerReturn]:
        from app.core.data_layer.visit_identity import deduplicate_cross_organization_returns

        rows = self._fetch_source_list(
            "canonical_customer_returns",
            CanonicalCustomerReturn,
            organization_id,
        )
        return deduplicate_cross_organization_returns(rows)

    def get_canonical_customer_return_item(
        self,
        customer_return_item_id: UUID,
    ) -> CanonicalCustomerReturnItem | None:
        return self._fetch_one(
            "SELECT * FROM canonical_customer_return_items WHERE id = %s",
            (customer_return_item_id,),
            CanonicalCustomerReturnItem,
        )

    def list_canonical_customer_return_items(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalCustomerReturnItem]:
        from app.core.data_layer.visit_identity import deduplicate_cross_organization_return_items

        rows = self._fetch_source_list(
            "canonical_customer_return_items",
            CanonicalCustomerReturnItem,
            organization_id,
        )
        return (
            rows
            if organization_id is not None
            else deduplicate_cross_organization_return_items(rows)
        )

    def get_canonical_inventory_balance(
        self,
        inventory_balance_id: UUID,
    ) -> CanonicalInventoryBalance | None:
        return self._fetch_one(
            "SELECT * FROM canonical_inventory_balances WHERE id = %s",
            (inventory_balance_id,),
            CanonicalInventoryBalance,
        )

    def list_canonical_inventory_balances(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalInventoryBalance]:
        return self._fetch_source_list(
            "canonical_inventory_balances",
            CanonicalInventoryBalance,
            organization_id,
        )

    def get_canonical_purchase(self, purchase_id: UUID) -> CanonicalPurchase | None:
        return self._fetch_one(
            "SELECT * FROM canonical_purchases WHERE id = %s",
            (purchase_id,),
            CanonicalPurchase,
        )

    def list_canonical_purchases(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalPurchase]:
        return self._fetch_source_list("canonical_purchases", CanonicalPurchase, organization_id)

    def get_canonical_purchase_item(self, purchase_item_id: UUID) -> CanonicalPurchaseItem | None:
        return self._fetch_one(
            "SELECT * FROM canonical_purchase_items WHERE id = %s",
            (purchase_item_id,),
            CanonicalPurchaseItem,
        )

    def list_canonical_purchase_items(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalPurchaseItem]:
        return self._fetch_source_list(
            "canonical_purchase_items",
            CanonicalPurchaseItem,
            organization_id,
        )

    def get_canonical_warehouse_receipt(
        self,
        receipt_id: UUID,
    ) -> CanonicalWarehouseReceipt | None:
        return self._fetch_one(
            "SELECT * FROM canonical_warehouse_receipts WHERE id = %s",
            (receipt_id,),
            CanonicalWarehouseReceipt,
        )

    def list_canonical_warehouse_receipts(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalWarehouseReceipt]:
        return self._fetch_source_list(
            "canonical_warehouse_receipts",
            CanonicalWarehouseReceipt,
            organization_id,
        )

    def get_canonical_warehouse_receipt_item(
        self,
        receipt_item_id: UUID,
    ) -> CanonicalWarehouseReceiptItem | None:
        return self._fetch_one(
            "SELECT * FROM canonical_warehouse_receipt_items WHERE id = %s",
            (receipt_item_id,),
            CanonicalWarehouseReceiptItem,
        )

    def list_canonical_warehouse_receipt_items(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalWarehouseReceiptItem]:
        return self._fetch_source_list(
            "canonical_warehouse_receipt_items",
            CanonicalWarehouseReceiptItem,
            organization_id,
        )

    def get_canonical_writeoff(self, writeoff_id: UUID) -> CanonicalWriteoff | None:
        return self._fetch_one(
            "SELECT * FROM canonical_writeoffs WHERE id = %s",
            (writeoff_id,),
            CanonicalWriteoff,
        )

    def list_canonical_writeoffs(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalWriteoff]:
        return self._fetch_source_list("canonical_writeoffs", CanonicalWriteoff, organization_id)

    def get_canonical_writeoff_item(self, writeoff_item_id: UUID) -> CanonicalWriteoffItem | None:
        return self._fetch_one(
            "SELECT * FROM canonical_writeoff_items WHERE id = %s",
            (writeoff_item_id,),
            CanonicalWriteoffItem,
        )

    def list_canonical_writeoff_items(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalWriteoffItem]:
        return self._fetch_source_list(
            "canonical_writeoff_items",
            CanonicalWriteoffItem,
            organization_id,
        )

    def get_canonical_supplier_return(
        self,
        supplier_return_id: UUID,
    ) -> CanonicalSupplierReturn | None:
        return self._fetch_one(
            "SELECT * FROM canonical_supplier_returns WHERE id = %s",
            (supplier_return_id,),
            CanonicalSupplierReturn,
        )

    def list_canonical_supplier_returns(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalSupplierReturn]:
        return self._fetch_source_list(
            "canonical_supplier_returns",
            CanonicalSupplierReturn,
            organization_id,
        )

    def get_canonical_supplier_return_item(
        self,
        supplier_return_item_id: UUID,
    ) -> CanonicalSupplierReturnItem | None:
        return self._fetch_one(
            "SELECT * FROM canonical_supplier_return_items WHERE id = %s",
            (supplier_return_item_id,),
            CanonicalSupplierReturnItem,
        )

    def list_canonical_supplier_return_items(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalSupplierReturnItem]:
        return self._fetch_source_list(
            "canonical_supplier_return_items",
            CanonicalSupplierReturnItem,
            organization_id,
        )

    def get_canonical_stocktaking(self, stocktaking_id: UUID) -> CanonicalStocktaking | None:
        return self._fetch_one(
            "SELECT * FROM canonical_stocktakings WHERE id = %s",
            (stocktaking_id,),
            CanonicalStocktaking,
        )

    def list_canonical_stocktakings(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalStocktaking]:
        return self._fetch_source_list(
            "canonical_stocktakings",
            CanonicalStocktaking,
            organization_id,
        )

    def get_canonical_stocktaking_item(
        self,
        stocktaking_item_id: UUID,
    ) -> CanonicalStocktakingItem | None:
        return self._fetch_one(
            "SELECT * FROM canonical_stocktaking_items WHERE id = %s",
            (stocktaking_item_id,),
            CanonicalStocktakingItem,
        )

    def list_canonical_stocktaking_items(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalStocktakingItem]:
        return self._fetch_source_list(
            "canonical_stocktaking_items",
            CanonicalStocktakingItem,
            organization_id,
        )

    def get_canonical_internal_movement(
        self,
        movement_id: UUID,
    ) -> CanonicalInternalMovement | None:
        return self._fetch_one(
            "SELECT * FROM canonical_internal_movements WHERE id = %s",
            (movement_id,),
            CanonicalInternalMovement,
        )

    def list_canonical_internal_movements(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalInternalMovement]:
        return self._fetch_source_list(
            "canonical_internal_movements",
            CanonicalInternalMovement,
            organization_id,
        )

    def get_canonical_internal_movement_item(
        self,
        movement_item_id: UUID,
    ) -> CanonicalInternalMovementItem | None:
        return self._fetch_one(
            "SELECT * FROM canonical_internal_movement_items WHERE id = %s",
            (movement_item_id,),
            CanonicalInternalMovementItem,
        )

    def list_canonical_internal_movement_items(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalInternalMovementItem]:
        return self._fetch_source_list(
            "canonical_internal_movement_items",
            CanonicalInternalMovementItem,
            organization_id,
        )

    def get_canonical_cross_org_movement(
        self,
        movement_id: UUID,
    ) -> CanonicalCrossOrgMovement | None:
        return self._fetch_one(
            "SELECT * FROM canonical_cross_org_movements WHERE id = %s",
            (movement_id,),
            CanonicalCrossOrgMovement,
        )

    def list_canonical_cross_org_movements(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalCrossOrgMovement]:
        return self._fetch_source_list(
            "canonical_cross_org_movements",
            CanonicalCrossOrgMovement,
            organization_id,
        )

    def get_canonical_cross_org_movement_item(
        self,
        movement_item_id: UUID,
    ) -> CanonicalCrossOrgMovementItem | None:
        return self._fetch_one(
            "SELECT * FROM canonical_cross_org_movement_items WHERE id = %s",
            (movement_item_id,),
            CanonicalCrossOrgMovementItem,
        )

    def list_canonical_cross_org_movement_items(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalCrossOrgMovementItem]:
        return self._fetch_source_list(
            "canonical_cross_org_movement_items",
            CanonicalCrossOrgMovementItem,
            organization_id,
        )

    def register_business(self, business: BusinessIdentity) -> BusinessIdentity:
        self._upsert(
            "businesses",
            "business_id",
            business.model_dump(mode="python"),
            update_columns=(
                "name",
                "legal_name",
                "display_name",
                "external_ref",
                "metadata",
                "updated_at",
            ),
        )
        return business

    def register_source_system(self, source_system: SourceSystem) -> SourceSystem:
        self._upsert(
            "source_systems",
            "source_system_id",
            source_system.model_dump(mode="python"),
            update_columns=(
                "business_id",
                "name",
                "source_type",
                "external_ref",
                "metadata",
                "updated_at",
            ),
        )
        return source_system

    def upsert_contact(self, contact: ContactProfile) -> ContactProfile:
        self._upsert(
            "contacts",
            "contact_id",
            contact.model_dump(mode="python"),
            update_columns=(
                "business_id",
                "full_name",
                "email",
                "phone",
                "source",
                "external_ref",
                "metadata",
                "updated_at",
            ),
        )
        return contact

    def upsert_sale(self, sale: SaleRecord) -> SaleRecord:
        self._upsert(
            "sales",
            "sale_id",
            sale.model_dump(mode="python"),
            update_columns=(
                "business_id",
                "contact_id",
                "external_ref",
                "amount",
                "currency",
                "stage",
                "occurred_at",
                "closed_at",
                "source",
                "metadata",
                "updated_at",
            ),
        )
        return sale

    def upsert_marketing_activity(self, activity: MarketingActivity) -> MarketingActivity:
        self._upsert(
            "marketing_activities",
            "activity_id",
            activity.model_dump(mode="python"),
            update_columns=(
                "business_id",
                "external_ref",
                "channel",
                "campaign_name",
                "impressions",
                "clicks",
                "conversions",
                "spend",
                "occurred_at",
                "source",
                "metadata",
                "updated_at",
            ),
        )
        return activity

    def upsert_finance_entry(self, entry: FinanceEntry) -> FinanceEntry:
        self._upsert(
            "finance_entries",
            "entry_id",
            entry.model_dump(mode="python"),
            update_columns=(
                "business_id",
                "external_ref",
                "entry_type",
                "category",
                "amount",
                "currency",
                "occurred_at",
                "source",
                "metadata",
                "updated_at",
            ),
        )
        return entry

    def upsert_ingestion_batch(self, batch: IngestionBatch) -> IngestionBatch:
        self._upsert(
            "ingestion_batches",
            "batch_id",
            batch.model_dump(mode="python"),
            update_columns=(
                "business_id",
                "source_system_id",
                "batch_name",
                "status",
                "started_at",
                "finished_at",
                "stats",
                "metadata",
                "updated_at",
            ),
        )
        return batch

    def record_ingestion_error(self, error: IngestionError) -> IngestionError:
        self._upsert(
            "ingestion_errors",
            "error_id",
            error.model_dump(mode="python"),
            update_columns=(
                "batch_id",
                "business_id",
                "source_row_key",
                "entity_type",
                "error_code",
                "error_message",
                "raw_payload",
                "metadata",
                "updated_at",
            ),
        )
        return error

    def ingest_record(self, record: CoreRecord) -> CoreRecord:
        self._upsert(
            "core_records",
            "record_id",
            record.model_dump(mode="python"),
            update_columns=(
                "business_id",
                "source",
                "source_type",
                "kind",
                "payload",
                "occurred_at",
                "ingested_at",
                "metadata",
                "updated_at",
            ),
        )
        return record

    def upsert_kpi(self, kpi: KPIValue) -> KPIValue:
        self._upsert(
            "kpi_snapshots",
            "kpi_id",
            kpi.model_dump(mode="python"),
            update_columns=(
                "business_id",
                "metric_key",
                "value",
                "unit",
                "period_start",
                "period_end",
                "recorded_at",
                "metadata",
                "updated_at",
            ),
        )
        return kpi

    def upsert_app_setting(self, setting: AppSetting) -> AppSetting:
        values = setting.model_dump(mode="python")
        columns = list(values.keys())
        placeholders = ", ".join(["%s"] * len(columns))
        assignments = ", ".join(
            [
                "setting_value = EXCLUDED.setting_value",
                "metadata = EXCLUDED.metadata",
                "updated_at = NOW()",
            ]
        )
        sql = (
            f"INSERT INTO app_settings ({', '.join(columns)}) "
            f"VALUES ({placeholders}) "
            "ON CONFLICT (setting_key) DO UPDATE SET "
            f"{assignments}"
        )
        params = self._adapt_params(values[column] for column in columns)
        self._execute(sql, params)
        return setting

    def upsert_smartup_organization(self, organization: SmartUpOrganization) -> SmartUpOrganization:
        self._upsert(
            "smartup_organizations",
            "id",
            organization.model_dump(mode="python"),
            update_columns=(
                "integration_id",
                "name",
                "company_id",
                "filial_id",
                "filial_code",
                "project_code",
                "is_active",
                "sort_order",
                "last_sync_at",
                "metadata",
                "updated_at",
            ),
        )
        return organization

    def delete_smartup_organization(self, organization_id: UUID) -> None:
        self._execute("DELETE FROM smartup_organizations WHERE id = %s", (organization_id,))

    def reset_smartup_data(self) -> None:
        self._execute_many(
            [
                """
                TRUNCATE TABLE
                    businesses,
                    source_systems,
                    contacts,
                    sales,
                    marketing_activities,
                    finance_entries,
                    ingestion_batches,
                    ingestion_errors,
                    core_records,
                    kpi_snapshots,
                    app_settings,
                    smartup_migration_runs,
                    sync_checkpoints,
                    migration_batches,
                    inventory_snapshots,
                    smartup_raw_records,
                    normalization_issues,
                    normalized_customers,
                    normalized_product_categories,
                    normalized_products,
                    normalized_warehouses,
                    normalized_price_types,
                    normalized_product_prices,
                    normalized_sales,
                    normalized_sale_items,
                    normalized_payments,
                    normalized_inventory_balances,
                    normalized_visits,
                    normalized_bank_operations,
                    normalized_business_documents,
                    normalized_business_document_items,
                    canonical_organizations,
                    canonical_customer_groups,
                    canonical_customers,
                    canonical_product_categories,
                    canonical_products,
                    canonical_warehouses,
                    canonical_price_types,
                    canonical_product_prices,
                    canonical_sales_reps,
                    canonical_working_zones
                RESTART IDENTITY CASCADE
                """,
            ],
        )

    def upsert_smartup_migration_run(self, run: SmartUpMigrationRun) -> SmartUpMigrationRun:
        self._upsert(
            "smartup_migration_runs",
            "run_id",
            run.model_dump(mode="python"),
            update_columns=(
                "organization_id",
                "entity_type",
                "started_at",
                "completed_at",
                "status",
                "imported_count",
                "updated_count",
                "skipped_count",
                "failed_count",
                "error_message",
                "metadata",
                "updated_at",
            ),
        )
        return run

    def upsert_sync_checkpoint(self, checkpoint: SyncCheckpoint) -> SyncCheckpoint:
        self._upsert(
            "sync_checkpoints",
            "id",
            checkpoint.model_dump(mode="python"),
            update_columns=(
                "organization_id",
                "entity_type",
                "migration_mode",
                "period_start",
                "period_end",
                "last_successful_date",
                "last_successful_external_id",
                "status",
                "attempts",
                "last_error",
                "metadata",
                "updated_at",
            ),
        )
        return checkpoint

    def upsert_migration_batch(self, batch: MigrationBatch) -> MigrationBatch:
        self._upsert(
            "migration_batches",
            "id",
            batch.model_dump(mode="python"),
            update_columns=(
                "organization_id",
                "entity_type",
                "migration_mode",
                "date_from",
                "date_to",
                "status",
                "received_count",
                "inserted_count",
                "updated_count",
                "skipped_count",
                "failed_count",
                "upstream_status",
                "upstream_response",
                "started_at",
                "finished_at",
                "problematic_date",
                "error_message",
                "metadata",
                "updated_at",
            ),
        )
        return batch

    def upsert_inventory_snapshot(self, snapshot: InventorySnapshot) -> InventorySnapshot:
        self._upsert(
            "inventory_snapshots",
            "id",
            snapshot.model_dump(mode="python"),
            update_columns=(
                "organization_id",
                "warehouse_external_id",
                "product_external_id",
                "quantity",
                "snapshot_date",
                "source_system",
                "imported_at",
                "metadata",
                "updated_at",
            ),
        )
        return snapshot

    def upsert_smartup_raw_record(self, record: SmartUpRawRecord) -> SmartUpRawRecord:
        self._upsert(
            "smartup_raw_records",
            "id",
            record.model_dump(mode="python"),
            update_columns=(
                "organization_id",
                "filial_id",
                "request_filial_id",
                "request_company_id",
                "request_project_code",
                "entity_type",
                "external_id",
                "source_endpoint",
                "request_payload",
                "response_payload",
                "response_envelope",
                "response_filial_id",
                "source_created_at",
                "source_updated_at",
                "imported_at",
                "batch_id",
                "checksum",
                "processing_status",
                "processing_error",
                "updated_at",
            ),
        )
        return record

    def upsert_normalization_issue(self, issue: NormalizationIssue) -> NormalizationIssue:
        self._upsert(
            "normalization_issues",
            "id",
            issue.model_dump(mode="python"),
            update_columns=(
                "raw_record_id",
                "organization_id",
                "entity_type",
                "issue_type",
                "field_name",
                "message",
                "source_value",
                "severity",
                "created_at",
            ),
        )
        return issue

    def upsert_customer(self, customer: Customer) -> Customer:
        self._upsert(
            "normalized_customers",
            "id",
            customer.model_dump(mode="python"),
            update_columns=(
                "organization_id",
                "source_system",
                "source_external_id",
                "source_filial_id",
                "source_payload_id",
                "source_created_at",
                "source_updated_at",
                "imported_at",
                "last_synced_at",
                "name",
                "display_name",
                "phone",
                "email",
                "metadata",
                "updated_at",
            ),
        )
        return customer

    def upsert_product_category(self, category: ProductCategory) -> ProductCategory:
        self._upsert(
            "normalized_product_categories",
            "id",
            category.model_dump(mode="python"),
            update_columns=(
                "organization_id",
                "source_system",
                "source_external_id",
                "source_filial_id",
                "source_payload_id",
                "source_created_at",
                "source_updated_at",
                "imported_at",
                "last_synced_at",
                "name",
                "parent_external_id",
                "metadata",
                "updated_at",
            ),
        )
        return category

    def upsert_product(self, product: Product) -> Product:
        self._upsert(
            "normalized_products",
            "id",
            product.model_dump(mode="python"),
            update_columns=(
                "organization_id",
                "source_system",
                "source_external_id",
                "source_filial_id",
                "source_payload_id",
                "source_created_at",
                "source_updated_at",
                "imported_at",
                "last_synced_at",
                "name",
                "category_external_id",
                "sku",
                "unit",
                "metadata",
                "updated_at",
            ),
        )
        return product

    def upsert_warehouse(self, warehouse: Warehouse) -> Warehouse:
        self._upsert(
            "normalized_warehouses",
            "id",
            warehouse.model_dump(mode="python"),
            update_columns=(
                "organization_id",
                "source_system",
                "source_external_id",
                "source_filial_id",
                "source_payload_id",
                "source_created_at",
                "source_updated_at",
                "imported_at",
                "last_synced_at",
                "name",
                "code",
                "metadata",
                "updated_at",
            ),
        )
        return warehouse

    def get_price_type(self, price_type_id: UUID) -> PriceType | None:
        return self._fetch_one(
            "SELECT * FROM normalized_price_types WHERE id = %s",
            (price_type_id,),
            PriceType,
        )

    def list_price_types(self, organization_id: UUID | None = None) -> Iterable[PriceType]:
        return self._fetch_source_list("normalized_price_types", PriceType, organization_id)

    def get_product_price(self, product_price_id: UUID) -> ProductPrice | None:
        return self._fetch_one(
            "SELECT * FROM normalized_product_prices WHERE id = %s",
            (product_price_id,),
            ProductPrice,
        )

    def list_product_prices(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[ProductPrice]:
        return self._fetch_source_list("normalized_product_prices", ProductPrice, organization_id)

    def upsert_price_type(self, price_type: PriceType) -> PriceType:
        self._upsert(
            "normalized_price_types",
            "id",
            price_type.model_dump(mode="python"),
            update_columns=(
                "organization_id",
                "source_system",
                "source_external_id",
                "source_filial_id",
                "source_payload_id",
                "source_created_at",
                "source_updated_at",
                "imported_at",
                "last_synced_at",
                "code",
                "name",
                "currency_code",
                "status",
                "metadata",
                "updated_at",
            ),
        )
        return price_type

    def upsert_product_price(self, product_price: ProductPrice) -> ProductPrice:
        self._upsert(
            "normalized_product_prices",
            "id",
            product_price.model_dump(mode="python"),
            update_columns=(
                "organization_id",
                "source_system",
                "source_external_id",
                "source_filial_id",
                "source_payload_id",
                "source_created_at",
                "source_updated_at",
                "imported_at",
                "last_synced_at",
                "product_id",
                "product_external_id",
                "price_type_id",
                "price_type_code",
                "price",
                "currency_code",
                "effective_from",
                "effective_to",
                "metadata",
                "updated_at",
            ),
        )
        return product_price

    def upsert_sale_v2(self, sale: Sale) -> Sale:
        self._upsert(
            "normalized_sales",
            "id",
            sale.model_dump(mode="python"),
            update_columns=(
                "organization_id",
                "source_system",
                "source_external_id",
                "source_filial_id",
                "source_payload_id",
                "source_created_at",
                "source_updated_at",
                "imported_at",
                "last_synced_at",
                "customer_id",
                "customer_external_id",
                "sale_number",
                "amount",
                "currency",
                "status",
                "sale_at",
                "closed_at",
                "metadata",
                "updated_at",
            ),
        )
        return sale

    def upsert_sale_item(self, sale_item: SaleItem) -> SaleItem:
        self._upsert(
            "normalized_sale_items",
            "id",
            sale_item.model_dump(mode="python"),
            update_columns=(
                "organization_id",
                "source_system",
                "source_external_id",
                "source_filial_id",
                "source_payload_id",
                "source_created_at",
                "source_updated_at",
                "imported_at",
                "last_synced_at",
                "sale_id",
                "sale_external_id",
                "product_id",
                "product_external_id",
                "quantity",
                "unit_price",
                "amount",
                "currency",
                "metadata",
                "updated_at",
            ),
        )
        return sale_item

    def upsert_payment(self, payment: Payment) -> Payment:
        self._upsert(
            "normalized_payments",
            "id",
            payment.model_dump(mode="python"),
            update_columns=(
                "organization_id",
                "source_system",
                "source_external_id",
                "source_filial_id",
                "source_payload_id",
                "source_created_at",
                "source_updated_at",
                "imported_at",
                "last_synced_at",
                "sale_id",
                "sale_external_id",
                "amount",
                "currency",
                "paid_at",
                "method",
                "metadata",
                "updated_at",
            ),
        )
        return payment

    def upsert_inventory_balance(self, inventory_balance: InventoryBalance) -> InventoryBalance:
        self._upsert(
            "normalized_inventory_balances",
            "id",
            inventory_balance.model_dump(mode="python"),
            update_columns=(
                "organization_id",
                "source_system",
                "source_external_id",
                "source_filial_id",
                "source_payload_id",
                "source_created_at",
                "source_updated_at",
                "imported_at",
                "last_synced_at",
                "warehouse_id",
                "product_id",
                "warehouse_external_id",
                "product_external_id",
                "quantity",
                "balance_at",
                "metadata",
                "updated_at",
            ),
        )
        return inventory_balance

    def upsert_visit(self, visit: Visit) -> Visit:
        self._upsert(
            "normalized_visits",
            "id",
            visit.model_dump(mode="python"),
            update_columns=(
                "organization_id",
                "source_system",
                "source_external_id",
                "source_filial_id",
                "source_payload_id",
                "source_created_at",
                "source_updated_at",
                "imported_at",
                "last_synced_at",
                "customer_id",
                "customer_external_id",
                "visited_at",
                "status",
                "metadata",
                "updated_at",
            ),
        )
        return visit

    def upsert_bank_operation(self, bank_operation: BankOperation) -> BankOperation:
        self._upsert(
            "normalized_bank_operations",
            "id",
            bank_operation.model_dump(mode="python"),
            update_columns=(
                "organization_id",
                "source_system",
                "source_external_id",
                "source_filial_id",
                "source_payload_id",
                "source_created_at",
                "source_updated_at",
                "imported_at",
                "last_synced_at",
                "amount",
                "currency",
                "occurred_at",
                "operation_type",
                "description",
                "metadata",
                "updated_at",
            ),
        )
        return bank_operation

    def upsert_business_document(self, document: BusinessDocument) -> BusinessDocument:
        self._upsert(
            "normalized_business_documents",
            "id",
            document.model_dump(mode="python"),
            update_columns=(
                "organization_id",
                "source_system",
                "source_external_id",
                "source_filial_id",
                "source_payload_id",
                "source_created_at",
                "source_updated_at",
                "imported_at",
                "last_synced_at",
                "document_type",
                "document_number",
                "status",
                "document_at",
                "counterparty_external_id",
                "warehouse_external_id",
                "product_external_id",
                "quantity",
                "amount",
                "currency",
                "metadata",
                "updated_at",
            ),
        )
        return document

    def upsert_business_document_item(
        self,
        item: BusinessDocumentItem,
    ) -> BusinessDocumentItem:
        self._upsert(
            "normalized_business_document_items",
            "id",
            item.model_dump(mode="python"),
            update_columns=(
                "organization_id",
                "source_system",
                "source_external_id",
                "source_filial_id",
                "source_payload_id",
                "source_created_at",
                "source_updated_at",
                "imported_at",
                "last_synced_at",
                "document_id",
                "line_number",
                "item_type",
                "product_external_id",
                "warehouse_external_id",
                "counterparty_external_id",
                "quantity",
                "unit_price",
                "amount",
                "currency",
                "metadata",
                "updated_at",
            ),
        )
        return item

    def upsert_canonical_organization(
        self,
        organization: CanonicalOrganization,
    ) -> CanonicalOrganization:
        self._upsert(
            "canonical_organizations",
            "organization_id",
            organization.model_dump(mode="python"),
            update_columns=(
                "name",
                "company_id",
                "filial_id",
                "filial_code",
                "project_code",
                "is_active",
                "sort_order",
                "source_system",
                "source_endpoint",
                "source_external_id",
                "source_raw_record_id",
                "request_filial_id",
                "response_filial_id",
                "request_company_id",
                "request_project_code",
                "source_raw_batch_id",
                "data_quality_status",
                "imported_at",
                "last_synced_at",
                "metadata",
                "updated_at",
            ),
        )
        return organization

    def upsert_canonical_customer_group(
        self,
        group: CanonicalCustomerGroup,
    ) -> CanonicalCustomerGroup:
        self._upsert(
            "canonical_customer_groups",
            "id",
            group.model_dump(mode="python"),
            update_columns=(
                "organization_id",
                "source_system",
                "source_endpoint",
                "source_external_id",
                "source_raw_record_id",
                "request_filial_id",
                "response_filial_id",
                "request_company_id",
                "request_project_code",
                "source_raw_batch_id",
                "data_quality_status",
                "imported_at",
                "last_synced_at",
                "group_id",
                "code",
                "name",
                "customer_kind",
                "state",
                "group_types",
                "metadata",
                "updated_at",
            ),
        )
        return group

    def upsert_canonical_customer(self, customer: CanonicalCustomer) -> CanonicalCustomer:
        self._upsert(
            "canonical_customers",
            "id",
            customer.model_dump(mode="python"),
            update_columns=(
                "organization_id",
                "source_system",
                "source_endpoint",
                "source_external_id",
                "source_raw_record_id",
                "request_filial_id",
                "response_filial_id",
                "request_company_id",
                "request_project_code",
                "source_raw_batch_id",
                "data_quality_status",
                "imported_at",
                "last_synced_at",
                "person_id",
                "code",
                "name",
                "short_name",
                "main_phone",
                "email",
                "address",
                "groups",
                "state",
                "customer_kind",
                "tin",
                "metadata",
                "updated_at",
            ),
        )
        return customer

    def upsert_canonical_product_category(
        self,
        category: CanonicalProductCategory,
    ) -> CanonicalProductCategory:
        self._upsert(
            "canonical_product_categories",
            "id",
            category.model_dump(mode="python"),
            update_columns=(
                "organization_id",
                "source_system",
                "source_endpoint",
                "source_external_id",
                "source_raw_record_id",
                "request_filial_id",
                "response_filial_id",
                "request_company_id",
                "request_project_code",
                "source_raw_batch_id",
                "data_quality_status",
                "imported_at",
                "last_synced_at",
                "group_id",
                "code",
                "name",
                "product_kind",
                "state",
                "group_types",
                "metadata",
                "updated_at",
            ),
        )
        return category

    def upsert_canonical_product(self, product: CanonicalProduct) -> CanonicalProduct:
        self._upsert(
            "canonical_products",
            "id",
            product.model_dump(mode="python"),
            update_columns=(
                "organization_id",
                "source_system",
                "source_endpoint",
                "source_external_id",
                "source_raw_record_id",
                "request_filial_id",
                "response_filial_id",
                "request_company_id",
                "request_project_code",
                "source_raw_batch_id",
                "data_quality_status",
                "imported_at",
                "last_synced_at",
                "product_id",
                "code",
                "name",
                "short_name",
                "measure_code",
                "article_code",
                "producer_code",
                "barcodes",
                "inventory_kinds",
                "groups",
                "state",
                "source_kind",
                "gtin",
                "ikpu",
                "box_quant",
                "box_type_code",
                "litr",
                "marking_group_code",
                "sector_codes",
                "tnved",
                "weight_brutto",
                "weight_netto",
                "metadata",
                "updated_at",
            ),
        )
        return product

    def upsert_canonical_warehouse(self, warehouse: CanonicalWarehouse) -> CanonicalWarehouse:
        self._upsert(
            "canonical_warehouses",
            "id",
            warehouse.model_dump(mode="python"),
            update_columns=(
                "organization_id",
                "source_system",
                "source_endpoint",
                "source_external_id",
                "source_raw_record_id",
                "request_filial_id",
                "response_filial_id",
                "request_company_id",
                "request_project_code",
                "source_raw_batch_id",
                "data_quality_status",
                "imported_at",
                "last_synced_at",
                "warehouse_id",
                "warehouse_code",
                "warehouse_name",
                "state",
                "source_kind",
                "metadata",
                "updated_at",
            ),
        )
        return warehouse

    def upsert_canonical_price_type(self, price_type: CanonicalPriceType) -> CanonicalPriceType:
        self._upsert(
            "canonical_price_types",
            "id",
            price_type.model_dump(mode="python"),
            update_columns=(
                "organization_id",
                "source_system",
                "source_endpoint",
                "source_external_id",
                "source_raw_record_id",
                "request_filial_id",
                "response_filial_id",
                "request_company_id",
                "request_project_code",
                "source_raw_batch_id",
                "data_quality_status",
                "imported_at",
                "last_synced_at",
                "price_type_id",
                "code",
                "name",
                "short_name",
                "currency_code",
                "price_type_kind",
                "with_card",
                "state",
                "metadata",
                "updated_at",
            ),
        )
        return price_type

    def upsert_canonical_product_price(
        self,
        product_price: CanonicalProductPrice,
    ) -> CanonicalProductPrice:
        self._upsert(
            "canonical_product_prices",
            "id",
            product_price.model_dump(mode="python"),
            update_columns=(
                "organization_id",
                "source_system",
                "source_endpoint",
                "source_external_id",
                "source_raw_record_id",
                "request_filial_id",
                "response_filial_id",
                "request_company_id",
                "request_project_code",
                "source_raw_batch_id",
                "data_quality_status",
                "imported_at",
                "last_synced_at",
                "product_id",
                "product_code",
                "inventory_code",
                "inventory_barcode",
                "price_type_id",
                "price_type_code",
                "price_type_card_code",
                "price",
                "currency_code",
                "state",
                "metadata",
                "updated_at",
            ),
        )
        return product_price

    def upsert_canonical_sales_rep(self, sales_rep: CanonicalSalesRep) -> CanonicalSalesRep:
        self._upsert(
            "canonical_sales_reps",
            "id",
            sales_rep.model_dump(mode="python"),
            update_columns=(
                "organization_id",
                "source_system",
                "source_endpoint",
                "source_external_id",
                "source_raw_record_id",
                "request_filial_id",
                "response_filial_id",
                "request_company_id",
                "request_project_code",
                "source_raw_batch_id",
                "data_quality_status",
                "imported_at",
                "last_synced_at",
                "sales_manager_id",
                "sales_manager_code",
                "sales_manager_name",
                "role",
                "state",
                "source_kind",
                "metadata",
                "updated_at",
            ),
        )
        return sales_rep

    def upsert_canonical_working_zone(
        self,
        working_zone: CanonicalWorkingZone,
    ) -> CanonicalWorkingZone:
        self._upsert(
            "canonical_working_zones",
            "id",
            working_zone.model_dump(mode="python"),
            update_columns=(
                "organization_id",
                "source_system",
                "source_endpoint",
                "source_external_id",
                "source_raw_record_id",
                "request_filial_id",
                "response_filial_id",
                "request_company_id",
                "request_project_code",
                "source_raw_batch_id",
                "data_quality_status",
                "imported_at",
                "last_synced_at",
                "room_id",
                "room_code",
                "room_name",
                "state",
                "source_kind",
                "metadata",
                "updated_at",
            ),
        )
        return working_zone

    def upsert_canonical_visit(self, visit: CanonicalVisit) -> CanonicalVisit:
        values = visit.model_dump(mode="python")
        self._upsert(
            "canonical_visits",
            "id",
            values,
            update_columns=tuple(key for key in values if key != "id"),
        )
        return visit

    def upsert_canonical_visit_stock(
        self,
        visit_stock: CanonicalVisitStock,
    ) -> CanonicalVisitStock:
        values = visit_stock.model_dump(mode="python")
        self._upsert(
            "canonical_visit_stocks",
            "id",
            values,
            update_columns=tuple(key for key in values if key != "id"),
        )
        return visit_stock

    def upsert_canonical_visit_quiz_answer(
        self,
        quiz_answer: CanonicalVisitQuizAnswer,
    ) -> CanonicalVisitQuizAnswer:
        values = quiz_answer.model_dump(mode="python")
        self._upsert(
            "canonical_visit_quiz_answers",
            "id",
            values,
            update_columns=tuple(key for key in values if key != "id"),
        )
        return quiz_answer

    def upsert_canonical_visit_equipment(
        self,
        equipment: CanonicalVisitEquipment,
    ) -> CanonicalVisitEquipment:
        values = equipment.model_dump(mode="python")
        self._upsert(
            "canonical_visit_equipments",
            "id",
            values,
            update_columns=tuple(key for key in values if key != "id"),
        )
        return equipment

    def upsert_canonical_visit_comment(
        self,
        comment: CanonicalVisitComment,
    ) -> CanonicalVisitComment:
        values = comment.model_dump(mode="python")
        self._upsert(
            "canonical_visit_comments",
            "id",
            values,
            update_columns=tuple(key for key in values if key != "id"),
        )
        return comment

    def upsert_canonical_media_asset(
        self,
        media_asset: CanonicalMediaAsset,
    ) -> CanonicalMediaAsset:
        values = media_asset.model_dump(mode="python")
        self._upsert(
            "canonical_media_assets",
            "id",
            values,
            update_columns=tuple(key for key in values if key != "id"),
        )
        return media_asset

    def upsert_canonical_order(self, order: CanonicalOrder) -> CanonicalOrder:
        self._upsert(
            "canonical_orders",
            "id",
            order.model_dump(mode="python"),
            update_columns=(
                "organization_id",
                "source_system",
                "source_endpoint",
                "source_external_id",
                "source_raw_record_id",
                "request_filial_id",
                "response_filial_id",
                "request_company_id",
                "request_project_code",
                "source_raw_batch_id",
                "data_quality_status",
                "imported_at",
                "last_synced_at",
                "order_id",
                "deal_id",
                "external_document_id",
                "order_number",
                "delivery_number",
                "order_at",
                "delivery_date",
                "customer_id",
                "customer_external_id",
                "customer_code",
                "customer_name",
                "sales_rep_id",
                "sales_rep_external_id",
                "working_zone_id",
                "working_zone_external_id",
                "source_status_code",
                "source_status_name",
                "normalized_status",
                "display_status",
                "total_amount",
                "currency_code",
                "source_currency_code",
                "item_count",
                "ordered_quantity",
                "sold_quantity",
                "has_realization_evidence",
                "metadata",
                "updated_at",
            ),
        )
        return order

    def upsert_canonical_sale(self, sale: CanonicalSale) -> CanonicalSale:
        self._upsert(
            "canonical_sales",
            "id",
            sale.model_dump(mode="python"),
            update_columns=(
                "organization_id",
                "source_system",
                "source_endpoint",
                "source_external_id",
                "source_raw_record_id",
                "request_filial_id",
                "response_filial_id",
                "request_company_id",
                "request_project_code",
                "source_raw_batch_id",
                "data_quality_status",
                "imported_at",
                "last_synced_at",
                "sale_id",
                "order_id",
                "order_external_id",
                "deal_id",
                "sale_number",
                "sale_at",
                "closed_at",
                "customer_id",
                "customer_external_id",
                "customer_code",
                "customer_name",
                "sales_rep_id",
                "sales_rep_external_id",
                "working_zone_id",
                "working_zone_external_id",
                "source_status_code",
                "source_status_name",
                "normalized_status",
                "display_status",
                "total_amount",
                "currency_code",
                "source_currency_code",
                "item_count",
                "ordered_quantity",
                "sold_quantity",
                "returned_quantity",
                "realization_basis",
                "metadata",
                "updated_at",
            ),
        )
        return sale

    def upsert_canonical_sale_item(
        self,
        sale_item: CanonicalSaleItem,
    ) -> CanonicalSaleItem:
        self._upsert(
            "canonical_sale_items",
            "id",
            sale_item.model_dump(mode="python"),
            update_columns=(
                "organization_id",
                "source_system",
                "source_endpoint",
                "source_external_id",
                "source_raw_record_id",
                "request_filial_id",
                "response_filial_id",
                "request_company_id",
                "request_project_code",
                "source_raw_batch_id",
                "data_quality_status",
                "imported_at",
                "last_synced_at",
                "sale_id",
                "order_id",
                "sale_external_id",
                "order_external_id",
                "line_number",
                "product_id",
                "product_external_id",
                "product_code",
                "product_name",
                "warehouse_id",
                "warehouse_external_id",
                "warehouse_code",
                "price_type_id",
                "price_type_code",
                "source_status_code",
                "ordered_quantity",
                "sold_quantity",
                "returned_quantity",
                "unit_price",
                "amount",
                "vat_percent",
                "vat_amount",
                "margin_amount",
                "currency_code",
                "source_currency_code",
                "has_realization_evidence",
                "metadata",
                "updated_at",
            ),
        )
        return sale_item

    def upsert_canonical_payment(self, payment: CanonicalPayment) -> CanonicalPayment:
        self._upsert(
            "canonical_payments",
            "id",
            payment.model_dump(mode="python"),
            update_columns=(
                "organization_id",
                "source_system",
                "source_endpoint",
                "source_external_id",
                "source_raw_record_id",
                "request_filial_id",
                "response_filial_id",
                "request_company_id",
                "request_project_code",
                "source_raw_batch_id",
                "data_quality_status",
                "imported_at",
                "last_synced_at",
                "payment_id",
                "cashin_id",
                "cashin_number",
                "paid_at",
                "cashin_date",
                "cashin_time",
                "customer_id",
                "customer_external_id",
                "customer_code",
                "customer_name",
                "cashbox_code",
                "bank_account_code",
                "source_payment_type_code",
                "normalized_payment_type",
                "amount",
                "currency_code",
                "source_currency_code",
                "posted",
                "purpose",
                "subfilial_code",
                "metadata",
                "updated_at",
            ),
        )
        return payment

    def upsert_canonical_payment_allocation(
        self,
        allocation: CanonicalPaymentAllocation,
    ) -> CanonicalPaymentAllocation:
        self._upsert(
            "canonical_payment_allocations",
            "id",
            allocation.model_dump(mode="python"),
            update_columns=(
                "organization_id",
                "source_system",
                "source_endpoint",
                "source_external_id",
                "source_raw_record_id",
                "request_filial_id",
                "response_filial_id",
                "request_company_id",
                "request_project_code",
                "source_raw_batch_id",
                "data_quality_status",
                "imported_at",
                "last_synced_at",
                "payment_id",
                "sale_id",
                "sale_external_id",
                "order_id",
                "order_external_id",
                "allocated_amount",
                "currency_code",
                "allocation_type",
                "source_reference",
                "metadata",
                "updated_at",
            ),
        )
        return allocation

    def upsert_canonical_financial_account(
        self,
        account: CanonicalFinancialAccount,
    ) -> CanonicalFinancialAccount:
        values = account.model_dump(mode="python")
        self._upsert(
            "canonical_financial_accounts",
            "id",
            values,
            update_columns=tuple(key for key in values if key != "id"),
        )
        return account

    def upsert_canonical_financial_operation(
        self,
        operation: CanonicalFinancialOperation,
    ) -> CanonicalFinancialOperation:
        values = operation.model_dump(mode="python")
        self._upsert(
            "canonical_financial_operations",
            "id",
            values,
            update_columns=tuple(key for key in values if key != "id"),
        )
        return operation

    def upsert_canonical_customer_return(
        self,
        customer_return: CanonicalCustomerReturn,
    ) -> CanonicalCustomerReturn:
        self._upsert(
            "canonical_customer_returns",
            "id",
            customer_return.model_dump(mode="python"),
            update_columns=(
                "organization_id",
                "source_system",
                "source_endpoint",
                "source_external_id",
                "source_raw_record_id",
                "request_filial_id",
                "response_filial_id",
                "request_company_id",
                "request_project_code",
                "source_raw_batch_id",
                "data_quality_status",
                "imported_at",
                "last_synced_at",
                "return_id",
                "deal_id",
                "order_deal_id",
                "external_document_id",
                "return_number",
                "return_at",
                "booked_at",
                "delivery_date",
                "customer_id",
                "customer_external_id",
                "customer_code",
                "customer_name",
                "sales_rep_id",
                "sales_rep_external_id",
                "source_status_code",
                "source_status_name",
                "normalized_status",
                "display_status",
                "total_amount",
                "currency_code",
                "source_currency_code",
                "return_reason_id",
                "return_reason_code",
                "linked_order_id",
                "linked_order_external_id",
                "linked_sale_id",
                "linked_sale_external_id",
                "item_count",
                "returned_quantity",
                "metadata",
                "updated_at",
            ),
        )
        return customer_return

    def upsert_canonical_customer_return_item(
        self,
        customer_return_item: CanonicalCustomerReturnItem,
    ) -> CanonicalCustomerReturnItem:
        self._upsert(
            "canonical_customer_return_items",
            "id",
            customer_return_item.model_dump(mode="python"),
            update_columns=(
                "organization_id",
                "source_system",
                "source_endpoint",
                "source_external_id",
                "source_raw_record_id",
                "request_filial_id",
                "response_filial_id",
                "request_company_id",
                "request_project_code",
                "source_raw_batch_id",
                "data_quality_status",
                "imported_at",
                "last_synced_at",
                "customer_return_id",
                "return_external_id",
                "line_number",
                "product_id",
                "product_external_id",
                "product_code",
                "product_name",
                "warehouse_id",
                "warehouse_external_id",
                "warehouse_code",
                "price_type_id",
                "price_type_code",
                "returned_quantity",
                "unit_price",
                "amount",
                "vat_percent",
                "vat_amount",
                "margin_amount",
                "currency_code",
                "source_currency_code",
                "linked_order_id",
                "linked_sale_id",
                "metadata",
                "updated_at",
            ),
        )
        return customer_return_item

    def upsert_canonical_inventory_balance(
        self,
        inventory_balance: CanonicalInventoryBalance,
    ) -> CanonicalInventoryBalance:
        values = inventory_balance.model_dump(mode="python")
        self._upsert(
            "canonical_inventory_balances",
            "id",
            values,
            update_columns=tuple(key for key in values if key != "id"),
        )
        return inventory_balance

    def upsert_canonical_purchase(self, purchase: CanonicalPurchase) -> CanonicalPurchase:
        values = purchase.model_dump(mode="python")
        self._upsert(
            "canonical_purchases",
            "id",
            values,
            update_columns=tuple(key for key in values if key != "id"),
        )
        return purchase

    def upsert_canonical_purchase_item(
        self,
        purchase_item: CanonicalPurchaseItem,
    ) -> CanonicalPurchaseItem:
        values = purchase_item.model_dump(mode="python")
        self._upsert(
            "canonical_purchase_items",
            "id",
            values,
            update_columns=tuple(key for key in values if key != "id"),
        )
        return purchase_item

    def upsert_canonical_warehouse_receipt(
        self,
        receipt: CanonicalWarehouseReceipt,
    ) -> CanonicalWarehouseReceipt:
        values = receipt.model_dump(mode="python")
        self._upsert(
            "canonical_warehouse_receipts",
            "id",
            values,
            update_columns=tuple(key for key in values if key != "id"),
        )
        return receipt

    def upsert_canonical_warehouse_receipt_item(
        self,
        receipt_item: CanonicalWarehouseReceiptItem,
    ) -> CanonicalWarehouseReceiptItem:
        values = receipt_item.model_dump(mode="python")
        self._upsert(
            "canonical_warehouse_receipt_items",
            "id",
            values,
            update_columns=tuple(key for key in values if key != "id"),
        )
        return receipt_item

    def upsert_canonical_writeoff(self, writeoff: CanonicalWriteoff) -> CanonicalWriteoff:
        values = writeoff.model_dump(mode="python")
        self._upsert(
            "canonical_writeoffs",
            "id",
            values,
            update_columns=tuple(key for key in values if key != "id"),
        )
        return writeoff

    def upsert_canonical_writeoff_item(
        self,
        writeoff_item: CanonicalWriteoffItem,
    ) -> CanonicalWriteoffItem:
        values = writeoff_item.model_dump(mode="python")
        self._upsert(
            "canonical_writeoff_items",
            "id",
            values,
            update_columns=tuple(key for key in values if key != "id"),
        )
        return writeoff_item

    def upsert_canonical_supplier_return(
        self,
        supplier_return: CanonicalSupplierReturn,
    ) -> CanonicalSupplierReturn:
        values = supplier_return.model_dump(mode="python")
        self._upsert(
            "canonical_supplier_returns",
            "id",
            values,
            update_columns=tuple(key for key in values if key != "id"),
        )
        return supplier_return

    def upsert_canonical_supplier_return_item(
        self,
        supplier_return_item: CanonicalSupplierReturnItem,
    ) -> CanonicalSupplierReturnItem:
        values = supplier_return_item.model_dump(mode="python")
        self._upsert(
            "canonical_supplier_return_items",
            "id",
            values,
            update_columns=tuple(key for key in values if key != "id"),
        )
        return supplier_return_item

    def upsert_canonical_stocktaking(
        self,
        stocktaking: CanonicalStocktaking,
    ) -> CanonicalStocktaking:
        values = stocktaking.model_dump(mode="python")
        self._upsert(
            "canonical_stocktakings",
            "id",
            values,
            update_columns=tuple(key for key in values if key != "id"),
        )
        return stocktaking

    def upsert_canonical_stocktaking_item(
        self,
        stocktaking_item: CanonicalStocktakingItem,
    ) -> CanonicalStocktakingItem:
        values = stocktaking_item.model_dump(mode="python")
        self._upsert(
            "canonical_stocktaking_items",
            "id",
            values,
            update_columns=tuple(key for key in values if key != "id"),
        )
        return stocktaking_item

    def upsert_canonical_internal_movement(
        self,
        movement: CanonicalInternalMovement,
    ) -> CanonicalInternalMovement:
        values = movement.model_dump(mode="python")
        self._upsert(
            "canonical_internal_movements",
            "id",
            values,
            update_columns=tuple(key for key in values if key != "id"),
        )
        return movement

    def upsert_canonical_internal_movement_item(
        self,
        movement_item: CanonicalInternalMovementItem,
    ) -> CanonicalInternalMovementItem:
        values = movement_item.model_dump(mode="python")
        self._upsert(
            "canonical_internal_movement_items",
            "id",
            values,
            update_columns=tuple(key for key in values if key != "id"),
        )
        return movement_item

    def upsert_canonical_cross_org_movement(
        self,
        movement: CanonicalCrossOrgMovement,
    ) -> CanonicalCrossOrgMovement:
        values = movement.model_dump(mode="python")
        self._upsert(
            "canonical_cross_org_movements",
            "id",
            values,
            update_columns=tuple(key for key in values if key != "id"),
        )
        return movement

    def upsert_canonical_cross_org_movement_item(
        self,
        movement_item: CanonicalCrossOrgMovementItem,
    ) -> CanonicalCrossOrgMovementItem:
        values = movement_item.model_dump(mode="python")
        self._upsert(
            "canonical_cross_org_movement_items",
            "id",
            values,
            update_columns=tuple(key for key in values if key != "id"),
        )
        return movement_item

    def _fetch_model_list(
        self,
        table: str,
        model_cls: type[ModelT],
        business_id: UUID | None,
    ) -> list[ModelT]:
        sql = f"SELECT * FROM {table}"
        params: tuple[Any, ...] | None = None
        if business_id is not None:
            sql += " WHERE business_id = %s"
            params = (business_id,)
        sql += " ORDER BY created_at"
        return self._fetch_all(sql, params, model_cls)

    def _fetch_source_list(
        self,
        table: str,
        model_cls: type[ModelT],
        organization_id: UUID | None,
    ) -> list[ModelT]:
        sql = f"SELECT * FROM {table}"
        params: tuple[Any, ...] | None = None
        if organization_id is not None:
            sql += " WHERE organization_id = %s"
            params = (organization_id,)
        sql += " ORDER BY created_at"
        return self._fetch_all(sql, params, model_cls)

    def _fetch_one(
        self,
        sql: str,
        params: tuple[Any, ...] | None,
        model_cls: type[ModelT],
    ) -> ModelT | None:
        rows = self._fetch_rows(sql, params)
        if not rows:
            return None
        return model_cls.model_validate(rows[0])

    def _fetch_all(
        self,
        sql: str,
        params: tuple[Any, ...] | None,
        model_cls: type[ModelT],
    ) -> list[ModelT]:
        rows = self._fetch_rows(sql, params)
        return [model_cls.model_validate(row) for row in rows]

    def _fetch_rows(self, sql: str, params: tuple[Any, ...] | None) -> list[Row]:
        connection = self.connection_factory()
        try:
            with connection.cursor() as cursor:
                cursor.execute(sql, params)
                rows = cursor.fetchall()
                if not rows:
                    return []
                if isinstance(rows[0], Mapping):
                    return [dict(row) for row in rows]
                description = getattr(cursor, "description", None) or ()
                columns = [column[0] for column in description]
            return [dict(zip(columns, row, strict=False)) for row in rows]
        finally:
            _close_connection(connection)

    def execute_ai_readonly_sql(
        self,
        sql: str,
        params: tuple[Any, ...] = (),
        *,
        statement_timeout_ms: int,
    ) -> list[Row]:
        """Execute a previously validated AI query in a read-only transaction."""

        timeout_ms = int(statement_timeout_ms)
        if timeout_ms < 0:
            raise ValueError("statement_timeout_ms must be non-negative")
        connection = self.connection_factory()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET TRANSACTION READ ONLY")
                # PostgreSQL does not accept a bind placeholder as the value of
                # SET LOCAL. The value is validated as an integer first, then
                # emitted as a duration literal with no user-controlled SQL.
                cursor.execute(f"SET LOCAL statement_timeout = '{timeout_ms}ms'")
                cursor.execute(sql, params)
                rows = cursor.fetchall()
                if not rows:
                    return []
                if isinstance(rows[0], Mapping):
                    result = [dict(row) for row in rows]
                else:
                    description = getattr(cursor, "description", None) or ()
                    result = [
                        dict(zip([column[0] for column in description], row, strict=False))
                        for row in rows
                    ]
            connection.rollback()
            return result
        except Exception:
            connection.rollback()
            raise
        finally:
            _close_connection(connection)

    def describe_ai_views(self) -> dict[str, Any]:
        """Read the exact published analytical view schema from PostgreSQL."""

        rows = self._fetch_rows(
            """
            SELECT table_name, column_name, data_type, udt_name, is_nullable
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = ANY(%s)
            ORDER BY table_name, ordinal_position
            """,
            (list(ALLOWED_VIEWS),),
        )
        schema: dict[str, Any] = {}
        for row in rows:
            view = str(row.get("table_name") or "")
            column = str(row.get("column_name") or "")
            if not view or not column:
                continue
            schema.setdefault(view, {"columns": []})["columns"].append(
                {
                    "name": column,
                    "type": str(row.get("data_type") or row.get("udt_name") or "unknown"),
                    "nullable": str(row.get("is_nullable") or "YES") == "YES",
                }
            )
        return schema

    def upsert_meta_record(
        self, table: str, values: Mapping[str, Any], keys: tuple[str, ...]
    ) -> None:
        from app.integrations.meta.schema import META_TABLES
        from app.integrations.youtube.schema import YOUTUBE_TABLES
        from app.integrations.attribution_schema import ATTRIBUTION_TABLES
        tables = {**META_TABLES, **YOUTUBE_TABLES, **ATTRIBUTION_TABLES}

        if table not in tables or not set(values).issubset(tables[table]):
            raise ValueError("Unsupported Meta table or column")
        columns = list(values)
        placeholders = ", ".join(["%s"] * len(columns))
        conflict = ", ".join(keys)
        updates = ", ".join(
            f"{column}=EXCLUDED.{column}" for column in columns if column not in keys
        )
        if not updates:
            updates = f"{keys[0]}={table}.{keys[0]}"
        sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders}) ON CONFLICT ({conflict}) DO UPDATE SET {updates}"
        self._execute(sql, self._adapt_params(values[column] for column in columns))

    def list_meta_records(self, table: str, organization_id: str | None = None) -> list[Row]:
        from app.integrations.meta.schema import META_TABLES
        from app.integrations.youtube.schema import YOUTUBE_TABLES
        from app.integrations.attribution_schema import ATTRIBUTION_TABLES
        tables = {**META_TABLES, **YOUTUBE_TABLES, **ATTRIBUTION_TABLES}

        if table not in tables:
            raise ValueError("Unsupported Meta table")
        sql = f"SELECT * FROM {table}"
        params: tuple[Any, ...] = ()
        if "organization_id" in tables[table] and organization_id:
            sql += " WHERE organization_id = %s"
            params = (organization_id,)
        return self._fetch_rows(sql, params)

    def upsert_source_record(self, table: str, values: Mapping[str, Any], keys: tuple[str, ...]) -> None:
        self.upsert_meta_record(table, values, keys)

    def list_source_records(self, table: str, organization_id: str | None = None) -> list[Row]:
        return self.list_meta_records(table, organization_id)

    def _execute_many(self, statements: list[str]) -> None:
        connection = self.connection_factory()
        try:
            with connection.cursor() as cursor:
                for statement in statements:
                    cursor.execute(statement)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            _close_connection(connection)

    def _upsert(
        self,
        table: str,
        key_column: str,
        values: Mapping[str, Any],
        *,
        update_columns: tuple[str, ...],
    ) -> None:
        columns = list(values.keys())
        placeholders = ", ".join(["%s"] * len(columns))
        assignments = ", ".join(
            f"{column} = EXCLUDED.{column}" for column in update_columns if column != "updated_at"
        )
        if "updated_at" in update_columns:
            assignments = (
                f"{assignments}, updated_at = NOW()" if assignments else "updated_at = NOW()"
            )
        sql = (
            f"INSERT INTO {table} ({', '.join(columns)}) "
            f"VALUES ({placeholders}) "
            f"ON CONFLICT ({key_column}) DO UPDATE SET {assignments}"
        )
        params = self._adapt_params(values[column] for column in columns)
        self._execute(sql, params)

    def _execute(self, sql: str, params: tuple[Any, ...]) -> None:
        connection = self.connection_factory()
        try:
            with connection.cursor() as cursor:
                cursor.execute(sql, params)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            _close_connection(connection)

    @staticmethod
    def _adapt_params(values: Iterable[Any]) -> tuple[Any, ...]:
        """Adapt Python values into psycopg-friendly parameters."""

        return tuple(_adapt_param(value) for value in values)


def _close_connection(connection: Any) -> None:
    """Release per-operation connections without assuming test doubles expose close()."""

    close = getattr(connection, "close", None)
    if callable(close):
        close()


def _adapt_param(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return Jsonb(value)
    return value
