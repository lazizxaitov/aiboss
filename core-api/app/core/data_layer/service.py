"""In-memory core data layer for early development and tests."""

from collections.abc import Iterable
from dataclasses import dataclass, field
from uuid import UUID

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


@dataclass(slots=True)
class InMemoryCoreDataLayer(CoreDataReader, CoreDataWriter):
    """Simple in-memory implementation of the core data layer."""

    businesses: dict[UUID, BusinessIdentity] = field(default_factory=dict)
    app_settings: dict[str, AppSetting] = field(default_factory=dict)
    source_systems: dict[UUID, SourceSystem] = field(default_factory=dict)
    contacts: dict[UUID, ContactProfile] = field(default_factory=dict)
    sales: dict[UUID, SaleRecord] = field(default_factory=dict)
    marketing_activities: dict[UUID, MarketingActivity] = field(default_factory=dict)
    finance_entries: dict[UUID, FinanceEntry] = field(default_factory=dict)
    ingestion_batches: dict[UUID, IngestionBatch] = field(default_factory=dict)
    ingestion_errors: dict[UUID, IngestionError] = field(default_factory=dict)
    smartup_organizations: dict[UUID, SmartUpOrganization] = field(default_factory=dict)
    smartup_migration_runs: dict[UUID, SmartUpMigrationRun] = field(default_factory=dict)
    sync_checkpoints: dict[tuple[UUID, str, str], SyncCheckpoint] = field(default_factory=dict)
    migration_batches: dict[UUID, MigrationBatch] = field(default_factory=dict)
    inventory_snapshots: dict[UUID, InventorySnapshot] = field(default_factory=dict)
    smartup_raw_records: dict[UUID, SmartUpRawRecord] = field(default_factory=dict)
    normalization_issues: dict[UUID, NormalizationIssue] = field(default_factory=dict)
    customers: dict[UUID, Customer] = field(default_factory=dict)
    product_categories: dict[UUID, ProductCategory] = field(default_factory=dict)
    products: dict[UUID, Product] = field(default_factory=dict)
    warehouses: dict[UUID, Warehouse] = field(default_factory=dict)
    price_types: dict[UUID, PriceType] = field(default_factory=dict)
    product_prices: dict[UUID, ProductPrice] = field(default_factory=dict)
    sales_v2: dict[UUID, Sale] = field(default_factory=dict)
    sale_items: dict[UUID, SaleItem] = field(default_factory=dict)
    payments: dict[UUID, Payment] = field(default_factory=dict)
    inventory_balances: dict[UUID, InventoryBalance] = field(default_factory=dict)
    visits: dict[UUID, Visit] = field(default_factory=dict)
    bank_operations: dict[UUID, BankOperation] = field(default_factory=dict)
    business_documents: dict[UUID, BusinessDocument] = field(default_factory=dict)
    business_document_items: dict[UUID, BusinessDocumentItem] = field(default_factory=dict)
    canonical_organizations: dict[UUID, CanonicalOrganization] = field(default_factory=dict)
    canonical_customer_groups: dict[UUID, CanonicalCustomerGroup] = field(default_factory=dict)
    canonical_customers: dict[UUID, CanonicalCustomer] = field(default_factory=dict)
    canonical_product_categories: dict[UUID, CanonicalProductCategory] = field(default_factory=dict)
    canonical_products: dict[UUID, CanonicalProduct] = field(default_factory=dict)
    canonical_warehouses: dict[UUID, CanonicalWarehouse] = field(default_factory=dict)
    canonical_price_types: dict[UUID, CanonicalPriceType] = field(default_factory=dict)
    canonical_product_prices: dict[UUID, CanonicalProductPrice] = field(default_factory=dict)
    canonical_sales_reps: dict[UUID, CanonicalSalesRep] = field(default_factory=dict)
    canonical_working_zones: dict[UUID, CanonicalWorkingZone] = field(default_factory=dict)
    meta_records: dict[tuple[str, str], dict[str, object]] = field(default_factory=dict)
    canonical_visits: dict[UUID, CanonicalVisit] = field(default_factory=dict)
    canonical_visit_stocks: dict[UUID, CanonicalVisitStock] = field(default_factory=dict)
    canonical_visit_quiz_answers: dict[UUID, CanonicalVisitQuizAnswer] = field(default_factory=dict)
    canonical_visit_equipments: dict[UUID, CanonicalVisitEquipment] = field(default_factory=dict)
    canonical_visit_comments: dict[UUID, CanonicalVisitComment] = field(default_factory=dict)
    canonical_media_assets: dict[UUID, CanonicalMediaAsset] = field(default_factory=dict)
    canonical_orders: dict[UUID, CanonicalOrder] = field(default_factory=dict)
    canonical_sales: dict[UUID, CanonicalSale] = field(default_factory=dict)
    canonical_sale_items_v2: dict[UUID, CanonicalSaleItem] = field(default_factory=dict)
    canonical_payments: dict[UUID, CanonicalPayment] = field(default_factory=dict)
    canonical_payment_allocations: dict[UUID, CanonicalPaymentAllocation] = field(
        default_factory=dict
    )
    canonical_financial_accounts: dict[UUID, CanonicalFinancialAccount] = field(
        default_factory=dict
    )
    canonical_financial_operations: dict[UUID, CanonicalFinancialOperation] = field(
        default_factory=dict,
    )
    canonical_customer_returns: dict[UUID, CanonicalCustomerReturn] = field(default_factory=dict)
    canonical_customer_return_items: dict[UUID, CanonicalCustomerReturnItem] = field(
        default_factory=dict,
    )
    canonical_inventory_balances: dict[UUID, CanonicalInventoryBalance] = field(
        default_factory=dict
    )
    canonical_purchases: dict[UUID, CanonicalPurchase] = field(default_factory=dict)
    canonical_purchase_items: dict[UUID, CanonicalPurchaseItem] = field(default_factory=dict)
    canonical_warehouse_receipts: dict[UUID, CanonicalWarehouseReceipt] = field(
        default_factory=dict
    )
    canonical_warehouse_receipt_items: dict[UUID, CanonicalWarehouseReceiptItem] = field(
        default_factory=dict,
    )
    canonical_writeoffs: dict[UUID, CanonicalWriteoff] = field(default_factory=dict)
    canonical_writeoff_items: dict[UUID, CanonicalWriteoffItem] = field(default_factory=dict)
    canonical_supplier_returns: dict[UUID, CanonicalSupplierReturn] = field(default_factory=dict)
    canonical_supplier_return_items: dict[UUID, CanonicalSupplierReturnItem] = field(
        default_factory=dict,
    )
    canonical_stocktakings: dict[UUID, CanonicalStocktaking] = field(default_factory=dict)
    canonical_stocktaking_items: dict[UUID, CanonicalStocktakingItem] = field(default_factory=dict)
    canonical_internal_movements: dict[UUID, CanonicalInternalMovement] = field(
        default_factory=dict,
    )
    canonical_internal_movement_items: dict[UUID, CanonicalInternalMovementItem] = field(
        default_factory=dict,
    )
    canonical_cross_org_movements: dict[UUID, CanonicalCrossOrgMovement] = field(
        default_factory=dict,
    )
    canonical_cross_org_movement_items: dict[UUID, CanonicalCrossOrgMovementItem] = field(
        default_factory=dict,
    )
    records: dict[UUID, CoreRecord] = field(default_factory=dict)
    kpis: dict[tuple[UUID, str], KPIValue] = field(default_factory=dict)

    @staticmethod
    def _filter_by_business(
        items: Iterable,
        business_id: UUID | None,
    ) -> list:
        if business_id is None:
            return list(items)
        return [item for item in items if item.business_id == business_id]

    @staticmethod
    def _filter_by_organization(
        items: Iterable,
        organization_id: UUID | None,
    ) -> list:
        if organization_id is None:
            return list(items)
        return [item for item in items if item.organization_id == organization_id]

    def get_business(self, business_id: UUID) -> BusinessIdentity | None:
        return self.businesses.get(business_id)

    def list_businesses(self) -> Iterable[BusinessIdentity]:
        return self.businesses.values()

    def get_app_setting(self, setting_key: str) -> AppSetting | None:
        return self.app_settings.get(setting_key)

    def list_app_settings(self) -> Iterable[AppSetting]:
        return [self.app_settings[key] for key in sorted(self.app_settings)]

    def get_source_system(self, source_system_id: UUID) -> SourceSystem | None:
        return self.source_systems.get(source_system_id)

    def list_source_systems(self, business_id: UUID | None = None) -> Iterable[SourceSystem]:
        return self._filter_by_business(self.source_systems.values(), business_id)

    def get_contact(self, contact_id: UUID) -> ContactProfile | None:
        return self.contacts.get(contact_id)

    def list_contacts(self, business_id: UUID | None = None) -> Iterable[ContactProfile]:
        return self._filter_by_business(self.contacts.values(), business_id)

    def get_sale(self, sale_id: UUID) -> SaleRecord | None:
        return self.sales.get(sale_id)

    def list_sales(self, business_id: UUID | None = None) -> Iterable[SaleRecord]:
        return self._filter_by_business(self.sales.values(), business_id)

    def get_marketing_activity(self, activity_id: UUID) -> MarketingActivity | None:
        return self.marketing_activities.get(activity_id)

    def list_marketing_activities(
        self,
        business_id: UUID | None = None,
    ) -> Iterable[MarketingActivity]:
        return self._filter_by_business(self.marketing_activities.values(), business_id)

    def get_finance_entry(self, entry_id: UUID) -> FinanceEntry | None:
        return self.finance_entries.get(entry_id)

    def list_finance_entries(self, business_id: UUID | None = None) -> Iterable[FinanceEntry]:
        return self._filter_by_business(self.finance_entries.values(), business_id)

    def list_ingestion_batches(self, business_id: UUID | None = None) -> Iterable[IngestionBatch]:
        return self._filter_by_business(self.ingestion_batches.values(), business_id)

    def list_ingestion_errors(self, batch_id: UUID | None = None) -> Iterable[IngestionError]:
        errors = self.ingestion_errors.values()
        if batch_id is not None:
            errors = [error for error in errors if error.batch_id == batch_id]
        return list(errors)

    def list_records(
        self,
        business_id: UUID | None = None,
        kind: CoreRecordKind | None = None,
    ) -> Iterable[CoreRecord]:
        records = self.records.values()
        if business_id is not None:
            records = (record for record in records if record.business_id == business_id)
        if kind is not None:
            records = (record for record in records if record.kind == kind)
        return list(records)

    def list_kpis(self, business_id: UUID | None = None) -> Iterable[KPIValue]:
        kpis = self.kpis.values()
        if business_id is not None:
            kpis = (kpi for kpi in kpis if kpi.business_id == business_id)
        return list(kpis)

    def get_smartup_organization(self, organization_id: UUID) -> SmartUpOrganization | None:
        return self.smartup_organizations.get(organization_id)

    def list_smartup_organizations(
        self,
        integration_id: UUID | None = None,
        is_active: bool | None = None,
    ) -> Iterable[SmartUpOrganization]:
        organizations: Iterable[SmartUpOrganization] = self.smartup_organizations.values()
        if integration_id is not None:
            organizations = (org for org in organizations if org.integration_id == integration_id)
        if is_active is not None:
            organizations = (org for org in organizations if org.is_active is is_active)
        return sorted(
            organizations, key=lambda org: (org.sort_order, org.name.lower(), str(org.id))
        )

    def list_smartup_migration_runs(
        self,
        organization_id: UUID | None = None,
        entity_type: str | None = None,
    ) -> Iterable[SmartUpMigrationRun]:
        runs: Iterable[SmartUpMigrationRun] = self.smartup_migration_runs.values()
        if organization_id is not None:
            runs = (run for run in runs if run.organization_id == organization_id)
        if entity_type is not None:
            runs = (run for run in runs if run.entity_type == entity_type)
        return list(runs)

    def get_sync_checkpoint(
        self,
        organization_id: UUID,
        entity_type: str,
        migration_mode: str,
    ) -> SyncCheckpoint | None:
        return self.sync_checkpoints.get((organization_id, entity_type, migration_mode))

    def list_sync_checkpoints(
        self,
        organization_id: UUID | None = None,
        entity_type: str | None = None,
        migration_mode: str | None = None,
    ) -> Iterable[SyncCheckpoint]:
        checkpoints: Iterable[SyncCheckpoint] = self.sync_checkpoints.values()
        if organization_id is not None:
            checkpoints = (item for item in checkpoints if item.organization_id == organization_id)
        if entity_type is not None:
            checkpoints = (item for item in checkpoints if item.entity_type == entity_type)
        if migration_mode is not None:
            checkpoints = (item for item in checkpoints if item.migration_mode == migration_mode)
        return list(checkpoints)

    def list_migration_batches(
        self,
        organization_id: UUID | None = None,
        entity_type: str | None = None,
        migration_mode: str | None = None,
    ) -> Iterable[MigrationBatch]:
        batches: Iterable[MigrationBatch] = self.migration_batches.values()
        if organization_id is not None:
            batches = (item for item in batches if item.organization_id == organization_id)
        if entity_type is not None:
            batches = (item for item in batches if item.entity_type == entity_type)
        if migration_mode is not None:
            batches = (item for item in batches if item.migration_mode == migration_mode)
        return list(batches)

    def list_inventory_snapshots(
        self,
        organization_id: UUID | None = None,
        product_external_id: str | None = None,
    ) -> Iterable[InventorySnapshot]:
        snapshots: Iterable[InventorySnapshot] = self.inventory_snapshots.values()
        if organization_id is not None:
            snapshots = (item for item in snapshots if item.organization_id == organization_id)
        if product_external_id is not None:
            snapshots = (
                item for item in snapshots if item.product_external_id == product_external_id
            )
        return list(snapshots)

    def get_smartup_raw_record(self, record_id: UUID) -> SmartUpRawRecord | None:
        return self.smartup_raw_records.get(record_id)

    def list_smartup_raw_records(
        self,
        organization_id: UUID | None = None,
        entity_type: str | None = None,
        batch_id: UUID | None = None,
        processing_status: str | None = None,
    ) -> Iterable[SmartUpRawRecord]:
        records: Iterable[SmartUpRawRecord] = self.smartup_raw_records.values()
        if organization_id is not None:
            records = (item for item in records if item.organization_id == organization_id)
        if entity_type is not None:
            records = (item for item in records if item.entity_type == entity_type)
        if batch_id is not None:
            records = (item for item in records if item.batch_id == batch_id)
        if processing_status is not None:
            records = (item for item in records if str(item.processing_status) == processing_status)
        return sorted(records, key=lambda item: (item.imported_at, str(item.id)))

    def list_normalization_issues(
        self,
        raw_record_id: UUID | None = None,
        organization_id: UUID | None = None,
        entity_type: str | None = None,
    ) -> Iterable[NormalizationIssue]:
        issues: Iterable[NormalizationIssue] = self.normalization_issues.values()
        if raw_record_id is not None:
            issues = (item for item in issues if item.raw_record_id == raw_record_id)
        if organization_id is not None:
            issues = (item for item in issues if item.organization_id == organization_id)
        if entity_type is not None:
            issues = (item for item in issues if item.entity_type == entity_type)
        return sorted(issues, key=lambda item: (item.created_at, str(item.id)))

    def get_customer(self, customer_id: UUID) -> Customer | None:
        return self.customers.get(customer_id)

    def list_customers(self, organization_id: UUID | None = None) -> Iterable[Customer]:
        return self._filter_by_organization(self.customers.values(), organization_id)

    def get_product_category(self, category_id: UUID) -> ProductCategory | None:
        return self.product_categories.get(category_id)

    def list_product_categories(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[ProductCategory]:
        return self._filter_by_organization(self.product_categories.values(), organization_id)

    def get_product(self, product_id: UUID) -> Product | None:
        return self.products.get(product_id)

    def list_products(self, organization_id: UUID | None = None) -> Iterable[Product]:
        return self._filter_by_organization(self.products.values(), organization_id)

    def get_warehouse(self, warehouse_id: UUID) -> Warehouse | None:
        return self.warehouses.get(warehouse_id)

    def list_warehouses(self, organization_id: UUID | None = None) -> Iterable[Warehouse]:
        return self._filter_by_organization(self.warehouses.values(), organization_id)

    def get_price_type(self, price_type_id: UUID) -> PriceType | None:
        return self.price_types.get(price_type_id)

    def list_price_types(self, organization_id: UUID | None = None) -> Iterable[PriceType]:
        return self._filter_by_organization(self.price_types.values(), organization_id)

    def get_product_price(self, product_price_id: UUID) -> ProductPrice | None:
        return self.product_prices.get(product_price_id)

    def list_product_prices(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[ProductPrice]:
        return self._filter_by_organization(self.product_prices.values(), organization_id)

    def get_sale_v2(self, sale_id: UUID) -> Sale | None:
        return self.sales_v2.get(sale_id)

    def list_sales_v2(self, organization_id: UUID | None = None) -> Iterable[Sale]:
        return self._filter_by_organization(self.sales_v2.values(), organization_id)

    def get_sale_item(self, sale_item_id: UUID) -> SaleItem | None:
        return self.sale_items.get(sale_item_id)

    def list_sale_items(self, organization_id: UUID | None = None) -> Iterable[SaleItem]:
        return self._filter_by_organization(self.sale_items.values(), organization_id)

    def delete_sale_items_for_sale_external_id(
        self,
        organization_id: UUID,
        sale_external_id: str,
    ) -> None:
        self.sale_items = {
            sale_item_id: sale_item
            for sale_item_id, sale_item in self.sale_items.items()
            if not (
                sale_item.organization_id == organization_id
                and str(sale_item.sale_external_id) == str(sale_external_id)
            )
        }

    def get_payment(self, payment_id: UUID) -> Payment | None:
        return self.payments.get(payment_id)

    def list_payments(self, organization_id: UUID | None = None) -> Iterable[Payment]:
        return self._filter_by_organization(self.payments.values(), organization_id)

    def get_inventory_balance(self, inventory_balance_id: UUID) -> InventoryBalance | None:
        return self.inventory_balances.get(inventory_balance_id)

    def list_inventory_balances(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[InventoryBalance]:
        return self._filter_by_organization(self.inventory_balances.values(), organization_id)

    def get_visit(self, visit_id: UUID) -> Visit | None:
        return self.visits.get(visit_id)

    def list_visits(self, organization_id: UUID | None = None) -> Iterable[Visit]:
        return self._filter_by_organization(self.visits.values(), organization_id)

    def get_bank_operation(self, bank_operation_id: UUID) -> BankOperation | None:
        return self.bank_operations.get(bank_operation_id)

    def list_bank_operations(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[BankOperation]:
        return self._filter_by_organization(self.bank_operations.values(), organization_id)

    def get_business_document(self, document_id: UUID) -> BusinessDocument | None:
        return self.business_documents.get(document_id)

    def list_business_documents(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[BusinessDocument]:
        return self._filter_by_organization(self.business_documents.values(), organization_id)

    def get_business_document_item(self, item_id: UUID) -> BusinessDocumentItem | None:
        return self.business_document_items.get(item_id)

    def list_business_document_items(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[BusinessDocumentItem]:
        return self._filter_by_organization(
            self.business_document_items.values(),
            organization_id,
        )

    def get_canonical_organization(self, organization_id: UUID) -> CanonicalOrganization | None:
        return self.canonical_organizations.get(organization_id)

    def list_canonical_organizations(self) -> Iterable[CanonicalOrganization]:
        return sorted(
            self.canonical_organizations.values(),
            key=lambda item: (item.sort_order, item.name.lower(), str(item.organization_id)),
        )

    def get_canonical_customer_group(self, group_id: UUID) -> CanonicalCustomerGroup | None:
        return self.canonical_customer_groups.get(group_id)

    def list_canonical_customer_groups(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalCustomerGroup]:
        return self._filter_by_organization(
            self.canonical_customer_groups.values(),
            organization_id,
        )

    def get_canonical_customer(self, customer_id: UUID) -> CanonicalCustomer | None:
        return self.canonical_customers.get(customer_id)

    def list_canonical_customers(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalCustomer]:
        return self._filter_by_organization(self.canonical_customers.values(), organization_id)

    def get_canonical_product_category(
        self,
        category_id: UUID,
    ) -> CanonicalProductCategory | None:
        return self.canonical_product_categories.get(category_id)

    def list_canonical_product_categories(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalProductCategory]:
        return self._filter_by_organization(
            self.canonical_product_categories.values(),
            organization_id,
        )

    def get_canonical_product(self, product_id: UUID) -> CanonicalProduct | None:
        return self.canonical_products.get(product_id)

    def list_canonical_products(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalProduct]:
        return self._filter_by_organization(self.canonical_products.values(), organization_id)

    def get_canonical_warehouse(self, warehouse_id: UUID) -> CanonicalWarehouse | None:
        return self.canonical_warehouses.get(warehouse_id)

    def list_canonical_warehouses(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalWarehouse]:
        return self._filter_by_organization(self.canonical_warehouses.values(), organization_id)

    def get_canonical_price_type(self, price_type_id: UUID) -> CanonicalPriceType | None:
        return self.canonical_price_types.get(price_type_id)

    def list_canonical_price_types(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalPriceType]:
        return self._filter_by_organization(self.canonical_price_types.values(), organization_id)

    def get_canonical_product_price(
        self,
        product_price_id: UUID,
    ) -> CanonicalProductPrice | None:
        return self.canonical_product_prices.get(product_price_id)

    def list_canonical_product_prices(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalProductPrice]:
        return self._filter_by_organization(
            self.canonical_product_prices.values(),
            organization_id,
        )

    def get_canonical_sales_rep(self, sales_rep_id: UUID) -> CanonicalSalesRep | None:
        return self.canonical_sales_reps.get(sales_rep_id)

    def list_canonical_sales_reps(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalSalesRep]:
        return self._filter_by_organization(self.canonical_sales_reps.values(), organization_id)

    def get_canonical_working_zone(self, working_zone_id: UUID) -> CanonicalWorkingZone | None:
        return self.canonical_working_zones.get(working_zone_id)

    def list_canonical_working_zones(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalWorkingZone]:
        return self._filter_by_organization(
            self.canonical_working_zones.values(),
            organization_id,
        )

    def get_canonical_visit(self, visit_id: UUID) -> CanonicalVisit | None:
        return self.canonical_visits.get(visit_id)

    def list_canonical_visits(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalVisit]:
        from app.core.data_layer.visit_identity import deduplicate_cross_organization_visits

        rows = self._filter_by_organization(self.canonical_visits.values(), organization_id)
        return deduplicate_cross_organization_visits(rows)

    def get_canonical_visit_stock(self, visit_stock_id: UUID) -> CanonicalVisitStock | None:
        return self.canonical_visit_stocks.get(visit_stock_id)

    def list_canonical_visit_stocks(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalVisitStock]:
        return self._filter_by_organization(self.canonical_visit_stocks.values(), organization_id)

    def get_canonical_visit_quiz_answer(
        self,
        quiz_answer_id: UUID,
    ) -> CanonicalVisitQuizAnswer | None:
        return self.canonical_visit_quiz_answers.get(quiz_answer_id)

    def list_canonical_visit_quiz_answers(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalVisitQuizAnswer]:
        return self._filter_by_organization(
            self.canonical_visit_quiz_answers.values(),
            organization_id,
        )

    def get_canonical_visit_equipment(
        self,
        equipment_id: UUID,
    ) -> CanonicalVisitEquipment | None:
        return self.canonical_visit_equipments.get(equipment_id)

    def list_canonical_visit_equipments(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalVisitEquipment]:
        return self._filter_by_organization(
            self.canonical_visit_equipments.values(),
            organization_id,
        )

    def get_canonical_visit_comment(self, comment_id: UUID) -> CanonicalVisitComment | None:
        return self.canonical_visit_comments.get(comment_id)

    def list_canonical_visit_comments(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalVisitComment]:
        return self._filter_by_organization(
            self.canonical_visit_comments.values(),
            organization_id,
        )

    def get_canonical_media_asset(self, media_asset_id: UUID) -> CanonicalMediaAsset | None:
        return self.canonical_media_assets.get(media_asset_id)

    def list_canonical_media_assets(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalMediaAsset]:
        return self._filter_by_organization(
            self.canonical_media_assets.values(),
            organization_id,
        )

    def get_canonical_order(self, order_id: UUID) -> CanonicalOrder | None:
        return self.canonical_orders.get(order_id)

    def list_canonical_orders(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalOrder]:
        return self._filter_by_organization(self.canonical_orders.values(), organization_id)

    def get_canonical_sale(self, sale_id: UUID) -> CanonicalSale | None:
        return self.canonical_sales.get(sale_id)

    def list_canonical_sales(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalSale]:
        return self._filter_by_organization(self.canonical_sales.values(), organization_id)

    def get_canonical_sale_item(self, sale_item_id: UUID) -> CanonicalSaleItem | None:
        return self.canonical_sale_items_v2.get(sale_item_id)

    def list_canonical_sale_items(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalSaleItem]:
        return self._filter_by_organization(
            self.canonical_sale_items_v2.values(),
            organization_id,
        )

    def get_canonical_payment(self, payment_id: UUID) -> CanonicalPayment | None:
        return self.canonical_payments.get(payment_id)

    def list_canonical_payments(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalPayment]:
        return self._filter_by_organization(self.canonical_payments.values(), organization_id)

    def get_canonical_payment_allocation(
        self,
        allocation_id: UUID,
    ) -> CanonicalPaymentAllocation | None:
        return self.canonical_payment_allocations.get(allocation_id)

    def list_canonical_payment_allocations(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalPaymentAllocation]:
        return self._filter_by_organization(
            self.canonical_payment_allocations.values(),
            organization_id,
        )

    def get_canonical_financial_account(
        self,
        account_id: UUID,
    ) -> CanonicalFinancialAccount | None:
        return self.canonical_financial_accounts.get(account_id)

    def list_canonical_financial_accounts(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalFinancialAccount]:
        return self._filter_by_organization(
            self.canonical_financial_accounts.values(),
            organization_id,
        )

    def get_canonical_financial_operation(
        self,
        operation_id: UUID,
    ) -> CanonicalFinancialOperation | None:
        return self.canonical_financial_operations.get(operation_id)

    def list_canonical_financial_operations(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalFinancialOperation]:
        return self._filter_by_organization(
            self.canonical_financial_operations.values(),
            organization_id,
        )

    def get_canonical_customer_return(
        self,
        customer_return_id: UUID,
    ) -> CanonicalCustomerReturn | None:
        return self.canonical_customer_returns.get(customer_return_id)

    def list_canonical_customer_returns(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalCustomerReturn]:
        from app.core.data_layer.visit_identity import deduplicate_cross_organization_returns

        rows = self._filter_by_organization(
            self.canonical_customer_returns.values(),
            organization_id,
        )
        return deduplicate_cross_organization_returns(rows)

    def get_canonical_customer_return_item(
        self,
        customer_return_item_id: UUID,
    ) -> CanonicalCustomerReturnItem | None:
        return self.canonical_customer_return_items.get(customer_return_item_id)

    def list_canonical_customer_return_items(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalCustomerReturnItem]:
        from app.core.data_layer.visit_identity import deduplicate_cross_organization_return_items

        return (
            self._filter_by_organization(
                self.canonical_customer_return_items.values(),
                organization_id,
            )
            if organization_id is not None
            else deduplicate_cross_organization_return_items(
                self.canonical_customer_return_items.values(),
            )
        )

    def get_canonical_inventory_balance(
        self,
        inventory_balance_id: UUID,
    ) -> CanonicalInventoryBalance | None:
        return self.canonical_inventory_balances.get(inventory_balance_id)

    def list_canonical_inventory_balances(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalInventoryBalance]:
        return self._filter_by_organization(
            self.canonical_inventory_balances.values(),
            organization_id,
        )

    def get_canonical_purchase(self, purchase_id: UUID) -> CanonicalPurchase | None:
        return self.canonical_purchases.get(purchase_id)

    def list_canonical_purchases(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalPurchase]:
        return self._filter_by_organization(self.canonical_purchases.values(), organization_id)

    def get_canonical_purchase_item(self, purchase_item_id: UUID) -> CanonicalPurchaseItem | None:
        return self.canonical_purchase_items.get(purchase_item_id)

    def list_canonical_purchase_items(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalPurchaseItem]:
        return self._filter_by_organization(
            self.canonical_purchase_items.values(),
            organization_id,
        )

    def get_canonical_warehouse_receipt(
        self,
        receipt_id: UUID,
    ) -> CanonicalWarehouseReceipt | None:
        return self.canonical_warehouse_receipts.get(receipt_id)

    def list_canonical_warehouse_receipts(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalWarehouseReceipt]:
        return self._filter_by_organization(
            self.canonical_warehouse_receipts.values(),
            organization_id,
        )

    def get_canonical_warehouse_receipt_item(
        self,
        receipt_item_id: UUID,
    ) -> CanonicalWarehouseReceiptItem | None:
        return self.canonical_warehouse_receipt_items.get(receipt_item_id)

    def list_canonical_warehouse_receipt_items(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalWarehouseReceiptItem]:
        return self._filter_by_organization(
            self.canonical_warehouse_receipt_items.values(),
            organization_id,
        )

    def get_canonical_writeoff(self, writeoff_id: UUID) -> CanonicalWriteoff | None:
        return self.canonical_writeoffs.get(writeoff_id)

    def list_canonical_writeoffs(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalWriteoff]:
        return self._filter_by_organization(self.canonical_writeoffs.values(), organization_id)

    def get_canonical_writeoff_item(self, writeoff_item_id: UUID) -> CanonicalWriteoffItem | None:
        return self.canonical_writeoff_items.get(writeoff_item_id)

    def list_canonical_writeoff_items(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalWriteoffItem]:
        return self._filter_by_organization(
            self.canonical_writeoff_items.values(),
            organization_id,
        )

    def get_canonical_supplier_return(
        self,
        supplier_return_id: UUID,
    ) -> CanonicalSupplierReturn | None:
        return self.canonical_supplier_returns.get(supplier_return_id)

    def list_canonical_supplier_returns(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalSupplierReturn]:
        return self._filter_by_organization(
            self.canonical_supplier_returns.values(),
            organization_id,
        )

    def get_canonical_supplier_return_item(
        self,
        supplier_return_item_id: UUID,
    ) -> CanonicalSupplierReturnItem | None:
        return self.canonical_supplier_return_items.get(supplier_return_item_id)

    def list_canonical_supplier_return_items(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalSupplierReturnItem]:
        return self._filter_by_organization(
            self.canonical_supplier_return_items.values(),
            organization_id,
        )

    def get_canonical_stocktaking(self, stocktaking_id: UUID) -> CanonicalStocktaking | None:
        return self.canonical_stocktakings.get(stocktaking_id)

    def list_canonical_stocktakings(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalStocktaking]:
        return self._filter_by_organization(
            self.canonical_stocktakings.values(),
            organization_id,
        )

    def get_canonical_stocktaking_item(
        self,
        stocktaking_item_id: UUID,
    ) -> CanonicalStocktakingItem | None:
        return self.canonical_stocktaking_items.get(stocktaking_item_id)

    def list_canonical_stocktaking_items(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalStocktakingItem]:
        return self._filter_by_organization(
            self.canonical_stocktaking_items.values(),
            organization_id,
        )

    def get_canonical_internal_movement(
        self,
        movement_id: UUID,
    ) -> CanonicalInternalMovement | None:
        return self.canonical_internal_movements.get(movement_id)

    def list_canonical_internal_movements(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalInternalMovement]:
        return self._filter_by_organization(
            self.canonical_internal_movements.values(),
            organization_id,
        )

    def get_canonical_internal_movement_item(
        self,
        movement_item_id: UUID,
    ) -> CanonicalInternalMovementItem | None:
        return self.canonical_internal_movement_items.get(movement_item_id)

    def list_canonical_internal_movement_items(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalInternalMovementItem]:
        return self._filter_by_organization(
            self.canonical_internal_movement_items.values(),
            organization_id,
        )

    def get_canonical_cross_org_movement(
        self,
        movement_id: UUID,
    ) -> CanonicalCrossOrgMovement | None:
        return self.canonical_cross_org_movements.get(movement_id)

    def list_canonical_cross_org_movements(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalCrossOrgMovement]:
        return self._filter_by_organization(
            self.canonical_cross_org_movements.values(),
            organization_id,
        )

    def get_canonical_cross_org_movement_item(
        self,
        movement_item_id: UUID,
    ) -> CanonicalCrossOrgMovementItem | None:
        return self.canonical_cross_org_movement_items.get(movement_item_id)

    def list_canonical_cross_org_movement_items(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalCrossOrgMovementItem]:
        return self._filter_by_organization(
            self.canonical_cross_org_movement_items.values(),
            organization_id,
        )

    def register_business(self, business: BusinessIdentity) -> BusinessIdentity:
        self.businesses[business.business_id] = business
        return business

    def register_source_system(self, source_system: SourceSystem) -> SourceSystem:
        self.source_systems[source_system.source_system_id] = source_system
        return source_system

    def upsert_contact(self, contact: ContactProfile) -> ContactProfile:
        self.contacts[contact.contact_id] = contact
        return contact

    def upsert_sale(self, sale: SaleRecord) -> SaleRecord:
        self.sales[sale.sale_id] = sale
        return sale

    def upsert_marketing_activity(self, activity: MarketingActivity) -> MarketingActivity:
        self.marketing_activities[activity.activity_id] = activity
        return activity

    def upsert_finance_entry(self, entry: FinanceEntry) -> FinanceEntry:
        self.finance_entries[entry.entry_id] = entry
        return entry

    def upsert_ingestion_batch(self, batch: IngestionBatch) -> IngestionBatch:
        self.ingestion_batches[batch.batch_id] = batch
        return batch

    def record_ingestion_error(self, error: IngestionError) -> IngestionError:
        self.ingestion_errors[error.error_id] = error
        return error

    def ingest_record(self, record: CoreRecord) -> CoreRecord:
        self.records[record.record_id] = record
        return record

    def upsert_kpi(self, kpi: KPIValue) -> KPIValue:
        self.kpis[(kpi.business_id, kpi.metric_key)] = kpi
        return kpi

    def upsert_app_setting(self, setting: AppSetting) -> AppSetting:
        self.app_settings[setting.setting_key] = setting
        return setting

    def upsert_smartup_organization(self, organization: SmartUpOrganization) -> SmartUpOrganization:
        self.smartup_organizations[organization.id] = organization
        return organization

    def delete_smartup_organization(self, organization_id: UUID) -> None:
        self.smartup_organizations.pop(organization_id, None)

    def reset_smartup_data(self) -> None:
        self.businesses.clear()
        self.source_systems.clear()
        self.contacts.clear()
        self.sales.clear()
        self.marketing_activities.clear()
        self.finance_entries.clear()
        self.ingestion_batches.clear()
        self.ingestion_errors.clear()
        self.smartup_migration_runs.clear()
        self.sync_checkpoints.clear()
        self.migration_batches.clear()
        self.inventory_snapshots.clear()
        self.smartup_raw_records.clear()
        self.normalization_issues.clear()
        self.customers.clear()
        self.product_categories.clear()
        self.products.clear()
        self.warehouses.clear()
        self.price_types.clear()
        self.product_prices.clear()
        self.sales_v2.clear()
        self.sale_items.clear()
        self.payments.clear()
        self.inventory_balances.clear()
        self.visits.clear()
        self.bank_operations.clear()
        self.business_documents.clear()
        self.business_document_items.clear()
        self.canonical_organizations.clear()
        self.canonical_customer_groups.clear()
        self.canonical_customers.clear()
        self.canonical_product_categories.clear()
        self.canonical_products.clear()
        self.canonical_warehouses.clear()
        self.canonical_price_types.clear()
        self.canonical_product_prices.clear()
        self.canonical_sales_reps.clear()
        self.canonical_working_zones.clear()
        self.canonical_visits.clear()
        self.canonical_visit_stocks.clear()
        self.canonical_visit_quiz_answers.clear()
        self.canonical_visit_equipments.clear()
        self.canonical_visit_comments.clear()
        self.canonical_media_assets.clear()
        self.canonical_orders.clear()
        self.canonical_sales.clear()
        self.canonical_sale_items_v2.clear()
        self.canonical_payments.clear()
        self.canonical_payment_allocations.clear()
        self.canonical_financial_accounts.clear()
        self.canonical_financial_operations.clear()
        self.canonical_customer_returns.clear()
        self.canonical_customer_return_items.clear()
        self.canonical_inventory_balances.clear()
        self.canonical_purchases.clear()
        self.canonical_purchase_items.clear()
        self.canonical_warehouse_receipts.clear()
        self.canonical_warehouse_receipt_items.clear()
        self.canonical_writeoffs.clear()
        self.canonical_writeoff_items.clear()
        self.canonical_supplier_returns.clear()
        self.canonical_supplier_return_items.clear()
        self.canonical_stocktakings.clear()
        self.canonical_stocktaking_items.clear()
        self.canonical_internal_movements.clear()
        self.canonical_internal_movement_items.clear()
        self.canonical_cross_org_movements.clear()
        self.canonical_cross_org_movement_items.clear()
        self.records.clear()
        self.kpis.clear()

    def upsert_smartup_migration_run(self, run: SmartUpMigrationRun) -> SmartUpMigrationRun:
        self.smartup_migration_runs[run.run_id] = run
        return run

    def upsert_sync_checkpoint(self, checkpoint: SyncCheckpoint) -> SyncCheckpoint:
        self.sync_checkpoints[
            (checkpoint.organization_id, checkpoint.entity_type, checkpoint.migration_mode)
        ] = checkpoint
        return checkpoint

    def upsert_migration_batch(self, batch: MigrationBatch) -> MigrationBatch:
        self.migration_batches[batch.id] = batch
        return batch

    def upsert_inventory_snapshot(self, snapshot: InventorySnapshot) -> InventorySnapshot:
        self.inventory_snapshots[snapshot.id] = snapshot
        return snapshot

    def upsert_smartup_raw_record(self, record: SmartUpRawRecord) -> SmartUpRawRecord:
        self.smartup_raw_records[record.id] = record
        return record

    def upsert_normalization_issue(self, issue: NormalizationIssue) -> NormalizationIssue:
        self.normalization_issues[issue.id] = issue
        return issue

    def upsert_customer(self, customer: Customer) -> Customer:
        self.customers[customer.id] = customer
        return customer

    def upsert_product_category(self, category: ProductCategory) -> ProductCategory:
        self.product_categories[category.id] = category
        return category

    def upsert_product(self, product: Product) -> Product:
        self.products[product.id] = product
        return product

    def upsert_warehouse(self, warehouse: Warehouse) -> Warehouse:
        self.warehouses[warehouse.id] = warehouse
        return warehouse

    def upsert_price_type(self, price_type: PriceType) -> PriceType:
        self.price_types[price_type.id] = price_type
        return price_type

    def upsert_product_price(self, product_price: ProductPrice) -> ProductPrice:
        self.product_prices[product_price.id] = product_price
        return product_price

    def upsert_sale_v2(self, sale: Sale) -> Sale:
        self.sales_v2[sale.id] = sale
        return sale

    def upsert_sale_item(self, sale_item: SaleItem) -> SaleItem:
        self.sale_items[sale_item.id] = sale_item
        return sale_item

    def upsert_payment(self, payment: Payment) -> Payment:
        self.payments[payment.id] = payment
        return payment

    def upsert_inventory_balance(self, inventory_balance: InventoryBalance) -> InventoryBalance:
        self.inventory_balances[inventory_balance.id] = inventory_balance
        return inventory_balance

    def upsert_visit(self, visit: Visit) -> Visit:
        self.visits[visit.id] = visit
        return visit

    def upsert_bank_operation(self, bank_operation: BankOperation) -> BankOperation:
        self.bank_operations[bank_operation.id] = bank_operation
        return bank_operation

    def upsert_business_document(self, document: BusinessDocument) -> BusinessDocument:
        self.business_documents[document.id] = document
        return document

    def upsert_business_document_item(
        self,
        item: BusinessDocumentItem,
    ) -> BusinessDocumentItem:
        self.business_document_items[item.id] = item
        return item

    def upsert_canonical_organization(
        self,
        organization: CanonicalOrganization,
    ) -> CanonicalOrganization:
        self.canonical_organizations[organization.organization_id] = organization
        return organization

    def upsert_canonical_customer_group(
        self,
        group: CanonicalCustomerGroup,
    ) -> CanonicalCustomerGroup:
        self.canonical_customer_groups[group.id] = group
        return group

    def upsert_canonical_customer(self, customer: CanonicalCustomer) -> CanonicalCustomer:
        self.canonical_customers[customer.id] = customer
        return customer

    def upsert_canonical_product_category(
        self,
        category: CanonicalProductCategory,
    ) -> CanonicalProductCategory:
        self.canonical_product_categories[category.id] = category
        return category

    def upsert_canonical_product(self, product: CanonicalProduct) -> CanonicalProduct:
        self.canonical_products[product.id] = product
        return product

    def upsert_canonical_warehouse(self, warehouse: CanonicalWarehouse) -> CanonicalWarehouse:
        self.canonical_warehouses[warehouse.id] = warehouse
        return warehouse

    def upsert_canonical_price_type(self, price_type: CanonicalPriceType) -> CanonicalPriceType:
        self.canonical_price_types[price_type.id] = price_type
        return price_type

    def upsert_canonical_product_price(
        self,
        product_price: CanonicalProductPrice,
    ) -> CanonicalProductPrice:
        self.canonical_product_prices[product_price.id] = product_price
        return product_price

    def upsert_canonical_sales_rep(self, sales_rep: CanonicalSalesRep) -> CanonicalSalesRep:
        self.canonical_sales_reps[sales_rep.id] = sales_rep
        return sales_rep

    def upsert_canonical_working_zone(
        self,
        working_zone: CanonicalWorkingZone,
    ) -> CanonicalWorkingZone:
        self.canonical_working_zones[working_zone.id] = working_zone
        return working_zone

    def upsert_canonical_visit(self, visit: CanonicalVisit) -> CanonicalVisit:
        self.canonical_visits[visit.id] = visit
        return visit

    def upsert_canonical_visit_stock(
        self,
        visit_stock: CanonicalVisitStock,
    ) -> CanonicalVisitStock:
        self.canonical_visit_stocks[visit_stock.id] = visit_stock
        return visit_stock

    def upsert_canonical_visit_quiz_answer(
        self,
        quiz_answer: CanonicalVisitQuizAnswer,
    ) -> CanonicalVisitQuizAnswer:
        self.canonical_visit_quiz_answers[quiz_answer.id] = quiz_answer
        return quiz_answer

    def upsert_canonical_visit_equipment(
        self,
        equipment: CanonicalVisitEquipment,
    ) -> CanonicalVisitEquipment:
        self.canonical_visit_equipments[equipment.id] = equipment
        return equipment

    def upsert_canonical_visit_comment(
        self,
        comment: CanonicalVisitComment,
    ) -> CanonicalVisitComment:
        self.canonical_visit_comments[comment.id] = comment
        return comment

    def upsert_canonical_media_asset(
        self,
        media_asset: CanonicalMediaAsset,
    ) -> CanonicalMediaAsset:
        self.canonical_media_assets[media_asset.id] = media_asset
        return media_asset

    def upsert_canonical_order(self, order: CanonicalOrder) -> CanonicalOrder:
        self.canonical_orders[order.id] = order
        return order

    def upsert_canonical_sale(self, sale: CanonicalSale) -> CanonicalSale:
        self.canonical_sales[sale.id] = sale
        return sale

    def upsert_canonical_sale_item(
        self,
        sale_item: CanonicalSaleItem,
    ) -> CanonicalSaleItem:
        self.canonical_sale_items_v2[sale_item.id] = sale_item
        return sale_item

    def upsert_canonical_payment(self, payment: CanonicalPayment) -> CanonicalPayment:
        self.canonical_payments[payment.id] = payment
        return payment

    def upsert_canonical_payment_allocation(
        self,
        allocation: CanonicalPaymentAllocation,
    ) -> CanonicalPaymentAllocation:
        self.canonical_payment_allocations[allocation.id] = allocation
        return allocation

    def upsert_canonical_financial_account(
        self,
        account: CanonicalFinancialAccount,
    ) -> CanonicalFinancialAccount:
        self.canonical_financial_accounts[account.id] = account
        return account

    def upsert_canonical_financial_operation(
        self,
        operation: CanonicalFinancialOperation,
    ) -> CanonicalFinancialOperation:
        self.canonical_financial_operations[operation.id] = operation
        return operation

    def upsert_canonical_customer_return(
        self,
        customer_return: CanonicalCustomerReturn,
    ) -> CanonicalCustomerReturn:
        self.canonical_customer_returns[customer_return.id] = customer_return
        return customer_return

    def upsert_canonical_customer_return_item(
        self,
        customer_return_item: CanonicalCustomerReturnItem,
    ) -> CanonicalCustomerReturnItem:
        self.canonical_customer_return_items[customer_return_item.id] = customer_return_item
        return customer_return_item

    def upsert_canonical_inventory_balance(
        self,
        inventory_balance: CanonicalInventoryBalance,
    ) -> CanonicalInventoryBalance:
        self.canonical_inventory_balances[inventory_balance.id] = inventory_balance
        return inventory_balance

    def upsert_canonical_purchase(self, purchase: CanonicalPurchase) -> CanonicalPurchase:
        self.canonical_purchases[purchase.id] = purchase
        return purchase

    def upsert_canonical_purchase_item(
        self,
        purchase_item: CanonicalPurchaseItem,
    ) -> CanonicalPurchaseItem:
        self.canonical_purchase_items[purchase_item.id] = purchase_item
        return purchase_item

    def upsert_canonical_warehouse_receipt(
        self,
        receipt: CanonicalWarehouseReceipt,
    ) -> CanonicalWarehouseReceipt:
        self.canonical_warehouse_receipts[receipt.id] = receipt
        return receipt

    def upsert_canonical_warehouse_receipt_item(
        self,
        receipt_item: CanonicalWarehouseReceiptItem,
    ) -> CanonicalWarehouseReceiptItem:
        self.canonical_warehouse_receipt_items[receipt_item.id] = receipt_item
        return receipt_item

    def upsert_canonical_writeoff(self, writeoff: CanonicalWriteoff) -> CanonicalWriteoff:
        self.canonical_writeoffs[writeoff.id] = writeoff
        return writeoff

    def upsert_canonical_writeoff_item(
        self,
        writeoff_item: CanonicalWriteoffItem,
    ) -> CanonicalWriteoffItem:
        self.canonical_writeoff_items[writeoff_item.id] = writeoff_item
        return writeoff_item

    def upsert_canonical_supplier_return(
        self,
        supplier_return: CanonicalSupplierReturn,
    ) -> CanonicalSupplierReturn:
        self.canonical_supplier_returns[supplier_return.id] = supplier_return
        return supplier_return

    def upsert_canonical_supplier_return_item(
        self,
        supplier_return_item: CanonicalSupplierReturnItem,
    ) -> CanonicalSupplierReturnItem:
        self.canonical_supplier_return_items[supplier_return_item.id] = supplier_return_item
        return supplier_return_item

    def upsert_canonical_stocktaking(
        self,
        stocktaking: CanonicalStocktaking,
    ) -> CanonicalStocktaking:
        self.canonical_stocktakings[stocktaking.id] = stocktaking
        return stocktaking

    def upsert_canonical_stocktaking_item(
        self,
        stocktaking_item: CanonicalStocktakingItem,
    ) -> CanonicalStocktakingItem:
        self.canonical_stocktaking_items[stocktaking_item.id] = stocktaking_item
        return stocktaking_item

    def upsert_canonical_internal_movement(
        self,
        movement: CanonicalInternalMovement,
    ) -> CanonicalInternalMovement:
        self.canonical_internal_movements[movement.id] = movement
        return movement

    def upsert_canonical_internal_movement_item(
        self,
        movement_item: CanonicalInternalMovementItem,
    ) -> CanonicalInternalMovementItem:
        self.canonical_internal_movement_items[movement_item.id] = movement_item
        return movement_item

    def upsert_canonical_cross_org_movement(
        self,
        movement: CanonicalCrossOrgMovement,
    ) -> CanonicalCrossOrgMovement:
        self.canonical_cross_org_movements[movement.id] = movement
        return movement

    def upsert_canonical_cross_org_movement_item(
        self,
        movement_item: CanonicalCrossOrgMovementItem,
    ) -> CanonicalCrossOrgMovementItem:
        self.canonical_cross_org_movement_items[movement_item.id] = movement_item
        return movement_item

    def upsert_meta_record(
        self, table: str, values: dict[str, object], keys: tuple[str, ...]
    ) -> None:
        identity = "|".join(str(values.get(key, "")) for key in keys)
        self.meta_records[(table, identity)] = dict(values)

    def list_meta_records(
        self, table: str, organization_id: str | None = None
    ) -> list[dict[str, object]]:
        rows = [row for (row_table, _), row in self.meta_records.items() if row_table == table]
        if organization_id:
            rows = [row for row in rows if str(row.get("organization_id")) == organization_id]
        return rows
