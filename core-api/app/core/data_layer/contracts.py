"""Protocols for future persistent data layer adapters."""

from collections.abc import Iterable
from typing import Protocol
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


class CoreDataReader(Protocol):
    """Read operations exposed by the core data layer."""

    def get_business(self, business_id: UUID) -> BusinessIdentity | None:
        """Return a single business by identifier."""

    def list_businesses(self) -> Iterable[BusinessIdentity]:
        """Return all businesses."""

    def get_app_setting(self, setting_key: str) -> AppSetting | None:
        """Return a single app setting by key."""

    def list_app_settings(self) -> Iterable[AppSetting]:
        """Return all app settings."""

    def get_source_system(self, source_system_id: UUID) -> SourceSystem | None:
        """Return a single source system by identifier."""

    def list_source_systems(
        self,
        business_id: UUID | None = None,
    ) -> Iterable[SourceSystem]:
        """Return source systems with optional business filtering."""

    def get_contact(self, contact_id: UUID) -> ContactProfile | None:
        """Return a single contact by identifier."""

    def list_contacts(self, business_id: UUID | None = None) -> Iterable[ContactProfile]:
        """Return contacts with optional business filtering."""

    def get_sale(self, sale_id: UUID) -> SaleRecord | None:
        """Return a single sale by identifier."""

    def list_sales(self, business_id: UUID | None = None) -> Iterable[SaleRecord]:
        """Return sales with optional business filtering."""

    def get_marketing_activity(self, activity_id: UUID) -> MarketingActivity | None:
        """Return a single marketing activity by identifier."""

    def list_marketing_activities(
        self,
        business_id: UUID | None = None,
    ) -> Iterable[MarketingActivity]:
        """Return marketing activities with optional business filtering."""

    def get_finance_entry(self, entry_id: UUID) -> FinanceEntry | None:
        """Return a single finance entry by identifier."""

    def list_finance_entries(self, business_id: UUID | None = None) -> Iterable[FinanceEntry]:
        """Return finance entries with optional business filtering."""

    def list_ingestion_batches(self, business_id: UUID | None = None) -> Iterable[IngestionBatch]:
        """Return ingestion batches with optional business filtering."""

    def list_ingestion_errors(self, batch_id: UUID | None = None) -> Iterable[IngestionError]:
        """Return ingestion errors with optional batch filtering."""

    def list_records(
        self,
        business_id: UUID | None = None,
        kind: CoreRecordKind | None = None,
    ) -> Iterable[CoreRecord]:
        """Return normalized records with optional filters."""

    def list_kpis(self, business_id: UUID | None = None) -> Iterable[KPIValue]:
        """Return KPI snapshots with optional business filtering."""

    def get_smartup_organization(self, organization_id: UUID) -> SmartUpOrganization | None:
        """Return one SmartUp organization by identifier."""

    def list_smartup_organizations(
        self,
        integration_id: UUID | None = None,
        is_active: bool | None = None,
    ) -> Iterable[SmartUpOrganization]:
        """Return SmartUp organizations with optional filters."""

    def list_smartup_migration_runs(
        self,
        organization_id: UUID | None = None,
        entity_type: str | None = None,
    ) -> Iterable[SmartUpMigrationRun]:
        """Return SmartUp migration runs with optional filters."""

    def get_sync_checkpoint(
        self,
        organization_id: UUID,
        entity_type: str,
        migration_mode: str,
    ) -> SyncCheckpoint | None:
        """Return a sync checkpoint for a specific organization and entity."""

    def list_sync_checkpoints(
        self,
        organization_id: UUID | None = None,
        entity_type: str | None = None,
        migration_mode: str | None = None,
    ) -> Iterable[SyncCheckpoint]:
        """Return sync checkpoints with optional filters."""

    def list_migration_batches(
        self,
        organization_id: UUID | None = None,
        entity_type: str | None = None,
        migration_mode: str | None = None,
    ) -> Iterable[MigrationBatch]:
        """Return migration batches with optional filters."""

    def list_inventory_snapshots(
        self,
        organization_id: UUID | None = None,
        product_external_id: str | None = None,
    ) -> Iterable[InventorySnapshot]:
        """Return inventory snapshots with optional filters."""

    def get_smartup_raw_record(self, record_id: UUID) -> SmartUpRawRecord | None:
        """Return a single raw SmartUp record by identifier."""

    def list_smartup_raw_records(
        self,
        organization_id: UUID | None = None,
        entity_type: str | None = None,
        batch_id: UUID | None = None,
        processing_status: str | None = None,
    ) -> Iterable[SmartUpRawRecord]:
        """Return raw SmartUp records with optional filters."""

    def list_normalization_issues(
        self,
        raw_record_id: UUID | None = None,
        organization_id: UUID | None = None,
        entity_type: str | None = None,
    ) -> Iterable[NormalizationIssue]:
        """Return normalization issues with optional filters."""

    def get_customer(self, customer_id: UUID) -> Customer | None:
        """Return a normalized customer by identifier."""

    def list_customers(self, organization_id: UUID | None = None) -> Iterable[Customer]:
        """Return normalized customers with optional organization filtering."""

    def get_product_category(self, category_id: UUID) -> ProductCategory | None:
        """Return a normalized product category by identifier."""

    def list_product_categories(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[ProductCategory]:
        """Return product categories with optional organization filtering."""

    def get_product(self, product_id: UUID) -> Product | None:
        """Return a normalized product by identifier."""

    def list_products(self, organization_id: UUID | None = None) -> Iterable[Product]:
        """Return products with optional organization filtering."""

    def get_warehouse(self, warehouse_id: UUID) -> Warehouse | None:
        """Return a normalized warehouse by identifier."""

    def list_warehouses(self, organization_id: UUID | None = None) -> Iterable[Warehouse]:
        """Return warehouses with optional organization filtering."""

    def get_price_type(self, price_type_id: UUID) -> PriceType | None:
        """Return a normalized price type by identifier."""

    def list_price_types(self, organization_id: UUID | None = None) -> Iterable[PriceType]:
        """Return price types with optional organization filtering."""

    def get_product_price(self, product_price_id: UUID) -> ProductPrice | None:
        """Return a normalized product price by identifier."""

    def list_product_prices(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[ProductPrice]:
        """Return product prices with optional organization filtering."""

    def get_sale_v2(self, sale_id: UUID) -> Sale | None:
        """Return a normalized sale by identifier."""

    def list_sales_v2(self, organization_id: UUID | None = None) -> Iterable[Sale]:
        """Return normalized sales with optional organization filtering."""

    def get_sale_item(self, sale_item_id: UUID) -> SaleItem | None:
        """Return a normalized sale item by identifier."""

    def list_sale_items(self, organization_id: UUID | None = None) -> Iterable[SaleItem]:
        """Return normalized sale items with optional organization filtering."""

    def delete_sale_items_for_sale_external_id(
        self,
        organization_id: UUID,
        sale_external_id: str,
    ) -> None:
        """Delete normalized sale items for a specific sale external identity."""

    def get_payment(self, payment_id: UUID) -> Payment | None:
        """Return a normalized payment by identifier."""

    def list_payments(self, organization_id: UUID | None = None) -> Iterable[Payment]:
        """Return payments with optional organization filtering."""

    def get_inventory_balance(self, inventory_balance_id: UUID) -> InventoryBalance | None:
        """Return a normalized inventory balance by identifier."""

    def list_inventory_balances(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[InventoryBalance]:
        """Return inventory balances with optional organization filtering."""

    def get_visit(self, visit_id: UUID) -> Visit | None:
        """Return a normalized visit by identifier."""

    def list_visits(self, organization_id: UUID | None = None) -> Iterable[Visit]:
        """Return visits with optional organization filtering."""

    def get_bank_operation(self, bank_operation_id: UUID) -> BankOperation | None:
        """Return a normalized bank operation by identifier."""

    def list_bank_operations(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[BankOperation]:
        """Return bank operations with optional organization filtering."""

    def get_business_document(self, document_id: UUID) -> BusinessDocument | None:
        """Return a normalized business document by identifier."""

    def list_business_documents(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[BusinessDocument]:
        """Return business documents with optional organization filtering."""

    def get_business_document_item(self, item_id: UUID) -> BusinessDocumentItem | None:
        """Return a normalized business document line item by identifier."""

    def list_business_document_items(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[BusinessDocumentItem]:
        """Return business document items with optional organization filtering."""

    def get_canonical_organization(self, organization_id: UUID) -> CanonicalOrganization | None:
        """Return a canonical SmartUp organization by identifier."""

    def list_canonical_organizations(self) -> Iterable[CanonicalOrganization]:
        """Return all canonical SmartUp organizations."""

    def get_canonical_customer_group(self, group_id: UUID) -> CanonicalCustomerGroup | None:
        """Return a canonical SmartUp customer group by identifier."""

    def list_canonical_customer_groups(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalCustomerGroup]:
        """Return canonical customer groups with optional organization filtering."""

    def get_canonical_customer(self, customer_id: UUID) -> CanonicalCustomer | None:
        """Return a canonical SmartUp customer by identifier."""

    def list_canonical_customers(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalCustomer]:
        """Return canonical customers with optional organization filtering."""

    def get_canonical_product_category(
        self,
        category_id: UUID,
    ) -> CanonicalProductCategory | None:
        """Return a canonical SmartUp product category by identifier."""

    def list_canonical_product_categories(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalProductCategory]:
        """Return canonical product categories with optional organization filtering."""

    def get_canonical_product(self, product_id: UUID) -> CanonicalProduct | None:
        """Return a canonical SmartUp product by identifier."""

    def list_canonical_products(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalProduct]:
        """Return canonical products with optional organization filtering."""

    def get_canonical_warehouse(self, warehouse_id: UUID) -> CanonicalWarehouse | None:
        """Return a canonical SmartUp warehouse by identifier."""

    def list_canonical_warehouses(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalWarehouse]:
        """Return canonical warehouses with optional organization filtering."""

    def get_canonical_price_type(self, price_type_id: UUID) -> CanonicalPriceType | None:
        """Return a canonical SmartUp price type by identifier."""

    def list_canonical_price_types(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalPriceType]:
        """Return canonical price types with optional organization filtering."""

    def get_canonical_product_price(self, product_price_id: UUID) -> CanonicalProductPrice | None:
        """Return a canonical SmartUp product price by identifier."""

    def list_canonical_product_prices(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalProductPrice]:
        """Return canonical product prices with optional organization filtering."""

    def get_canonical_sales_rep(self, sales_rep_id: UUID) -> CanonicalSalesRep | None:
        """Return a canonical SmartUp sales representative by identifier."""

    def list_canonical_sales_reps(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalSalesRep]:
        """Return canonical sales representatives with optional organization filtering."""

    def get_canonical_working_zone(self, working_zone_id: UUID) -> CanonicalWorkingZone | None:
        """Return a canonical SmartUp working zone by identifier."""

    def list_canonical_working_zones(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalWorkingZone]:
        """Return canonical working zones with optional organization filtering."""

    def get_canonical_visit(self, visit_id: UUID) -> CanonicalVisit | None:
        """Return a canonical visit by identifier."""

    def list_canonical_visits(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalVisit]:
        """Return canonical visits with optional organization filtering."""

    def get_canonical_visit_stock(self, visit_stock_id: UUID) -> CanonicalVisitStock | None:
        """Return a canonical visit stock row by identifier."""

    def list_canonical_visit_stocks(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalVisitStock]:
        """Return canonical visit stock rows with optional organization filtering."""

    def get_canonical_visit_quiz_answer(
        self,
        quiz_answer_id: UUID,
    ) -> CanonicalVisitQuizAnswer | None:
        """Return a canonical visit quiz answer by identifier."""

    def list_canonical_visit_quiz_answers(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalVisitQuizAnswer]:
        """Return canonical visit quiz answers with optional organization filtering."""

    def get_canonical_visit_equipment(
        self,
        equipment_id: UUID,
    ) -> CanonicalVisitEquipment | None:
        """Return a canonical visit equipment row by identifier."""

    def list_canonical_visit_equipments(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalVisitEquipment]:
        """Return canonical visit equipment rows with optional organization filtering."""

    def get_canonical_visit_comment(self, comment_id: UUID) -> CanonicalVisitComment | None:
        """Return a canonical visit comment by identifier."""

    def list_canonical_visit_comments(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalVisitComment]:
        """Return canonical visit comments with optional organization filtering."""

    def get_canonical_media_asset(self, media_asset_id: UUID) -> CanonicalMediaAsset | None:
        """Return a canonical media asset by identifier."""

    def list_canonical_media_assets(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalMediaAsset]:
        """Return canonical media assets with optional organization filtering."""

    def get_canonical_order(self, order_id: UUID) -> CanonicalOrder | None:
        """Return a canonical order by identifier."""

    def list_canonical_orders(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalOrder]:
        """Return canonical orders with optional organization filtering."""

    def get_canonical_sale(self, sale_id: UUID) -> CanonicalSale | None:
        """Return a canonical realized sale by identifier."""

    def list_canonical_sales(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalSale]:
        """Return canonical sales with optional organization filtering."""

    def get_canonical_sale_item(self, sale_item_id: UUID) -> CanonicalSaleItem | None:
        """Return a canonical sale item by identifier."""

    def list_canonical_sale_items(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalSaleItem]:
        """Return canonical sale items with optional organization filtering."""

    def get_canonical_payment(self, payment_id: UUID) -> CanonicalPayment | None:
        """Return a canonical customer payment by identifier."""

    def list_canonical_payments(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalPayment]:
        """Return canonical customer payments with optional organization filtering."""

    def get_canonical_payment_allocation(
        self,
        allocation_id: UUID,
    ) -> CanonicalPaymentAllocation | None:
        """Return a canonical payment allocation by identifier."""

    def list_canonical_payment_allocations(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalPaymentAllocation]:
        """Return canonical payment allocations with optional organization filtering."""

    def get_canonical_financial_account(
        self,
        account_id: UUID,
    ) -> CanonicalFinancialAccount | None:
        """Return a canonical financial account by identifier."""

    def list_canonical_financial_accounts(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalFinancialAccount]:
        """Return canonical financial accounts with optional organization filtering."""

    def get_canonical_financial_operation(
        self,
        operation_id: UUID,
    ) -> CanonicalFinancialOperation | None:
        """Return a canonical financial operation by identifier."""

    def list_canonical_financial_operations(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalFinancialOperation]:
        """Return canonical financial operations with optional organization filtering."""

    def get_canonical_customer_return(
        self,
        customer_return_id: UUID,
    ) -> CanonicalCustomerReturn | None:
        """Return a canonical customer return by identifier."""

    def list_canonical_customer_returns(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalCustomerReturn]:
        """Return canonical customer returns with optional organization filtering."""

    def get_canonical_customer_return_item(
        self,
        customer_return_item_id: UUID,
    ) -> CanonicalCustomerReturnItem | None:
        """Return a canonical customer return item by identifier."""

    def list_canonical_customer_return_items(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalCustomerReturnItem]:
        """Return canonical customer return items with optional organization filtering."""

    def get_canonical_inventory_balance(
        self,
        inventory_balance_id: UUID,
    ) -> CanonicalInventoryBalance | None:
        """Return a canonical inventory balance snapshot by identifier."""

    def list_canonical_inventory_balances(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalInventoryBalance]:
        """Return canonical inventory balance snapshots with optional organization filtering."""

    def get_canonical_purchase(self, purchase_id: UUID) -> CanonicalPurchase | None:
        """Return a canonical purchase document by identifier."""

    def list_canonical_purchases(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalPurchase]:
        """Return canonical purchase documents with optional organization filtering."""

    def get_canonical_purchase_item(self, purchase_item_id: UUID) -> CanonicalPurchaseItem | None:
        """Return a canonical purchase line item by identifier."""

    def list_canonical_purchase_items(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalPurchaseItem]:
        """Return canonical purchase line items with optional organization filtering."""

    def get_canonical_warehouse_receipt(
        self,
        receipt_id: UUID,
    ) -> CanonicalWarehouseReceipt | None:
        """Return a canonical warehouse receipt by identifier."""

    def list_canonical_warehouse_receipts(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalWarehouseReceipt]:
        """Return canonical warehouse receipts with optional organization filtering."""

    def get_canonical_warehouse_receipt_item(
        self,
        receipt_item_id: UUID,
    ) -> CanonicalWarehouseReceiptItem | None:
        """Return a canonical warehouse receipt line item by identifier."""

    def list_canonical_warehouse_receipt_items(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalWarehouseReceiptItem]:
        """Return canonical warehouse receipt line items with optional organization filtering."""

    def get_canonical_writeoff(self, writeoff_id: UUID) -> CanonicalWriteoff | None:
        """Return a canonical write-off document by identifier."""

    def list_canonical_writeoffs(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalWriteoff]:
        """Return canonical write-off documents with optional organization filtering."""

    def get_canonical_writeoff_item(self, writeoff_item_id: UUID) -> CanonicalWriteoffItem | None:
        """Return a canonical write-off line item by identifier."""

    def list_canonical_writeoff_items(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalWriteoffItem]:
        """Return canonical write-off line items with optional organization filtering."""

    def get_canonical_supplier_return(
        self,
        supplier_return_id: UUID,
    ) -> CanonicalSupplierReturn | None:
        """Return a canonical supplier return document by identifier."""

    def list_canonical_supplier_returns(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalSupplierReturn]:
        """Return canonical supplier return documents with optional organization filtering."""

    def get_canonical_supplier_return_item(
        self,
        supplier_return_item_id: UUID,
    ) -> CanonicalSupplierReturnItem | None:
        """Return a canonical supplier return line item by identifier."""

    def list_canonical_supplier_return_items(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalSupplierReturnItem]:
        """Return canonical supplier return line items with optional organization filtering."""

    def get_canonical_stocktaking(self, stocktaking_id: UUID) -> CanonicalStocktaking | None:
        """Return a canonical stocktaking document by identifier."""

    def list_canonical_stocktakings(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalStocktaking]:
        """Return canonical stocktaking documents with optional organization filtering."""

    def get_canonical_stocktaking_item(
        self,
        stocktaking_item_id: UUID,
    ) -> CanonicalStocktakingItem | None:
        """Return a canonical stocktaking line item by identifier."""

    def list_canonical_stocktaking_items(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalStocktakingItem]:
        """Return canonical stocktaking line items with optional organization filtering."""

    def get_canonical_internal_movement(
        self,
        movement_id: UUID,
    ) -> CanonicalInternalMovement | None:
        """Return a canonical internal movement document by identifier."""

    def list_canonical_internal_movements(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalInternalMovement]:
        """Return canonical internal movement documents with optional organization filtering."""

    def get_canonical_internal_movement_item(
        self,
        movement_item_id: UUID,
    ) -> CanonicalInternalMovementItem | None:
        """Return a canonical internal movement line item by identifier."""

    def list_canonical_internal_movement_items(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalInternalMovementItem]:
        """Return canonical internal movement line items with optional organization filtering."""

    def get_canonical_cross_org_movement(
        self,
        movement_id: UUID,
    ) -> CanonicalCrossOrgMovement | None:
        """Return a canonical cross-organization movement document by identifier."""

    def list_canonical_cross_org_movements(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalCrossOrgMovement]:
        """Return cross-org movements with optional organization filtering."""

    def get_canonical_cross_org_movement_item(
        self,
        movement_item_id: UUID,
    ) -> CanonicalCrossOrgMovementItem | None:
        """Return a canonical cross-organization movement line item by identifier."""

    def list_canonical_cross_org_movement_items(
        self,
        organization_id: UUID | None = None,
    ) -> Iterable[CanonicalCrossOrgMovementItem]:
        """Return cross-org movement line items with optional organization filtering."""


class CoreDataWriter(Protocol):
    """Write operations exposed by the core data layer."""

    def register_business(self, business: BusinessIdentity) -> BusinessIdentity:
        """Persist a business identity."""

    def register_source_system(self, source_system: SourceSystem) -> SourceSystem:
        """Persist a source system."""

    def upsert_contact(self, contact: ContactProfile) -> ContactProfile:
        """Persist or update a contact profile."""

    def upsert_sale(self, sale: SaleRecord) -> SaleRecord:
        """Persist or update a sale record."""

    def upsert_marketing_activity(self, activity: MarketingActivity) -> MarketingActivity:
        """Persist or update a marketing activity."""

    def upsert_finance_entry(self, entry: FinanceEntry) -> FinanceEntry:
        """Persist or update a finance entry."""

    def upsert_ingestion_batch(self, batch: IngestionBatch) -> IngestionBatch:
        """Persist or update an ingestion batch."""

    def record_ingestion_error(self, error: IngestionError) -> IngestionError:
        """Persist an ingestion error."""

    def ingest_record(self, record: CoreRecord) -> CoreRecord:
        """Persist a normalized record."""

    def upsert_kpi(self, kpi: KPIValue) -> KPIValue:
        """Persist or update a KPI snapshot."""

    def upsert_app_setting(self, setting: AppSetting) -> AppSetting:
        """Persist or update an app setting."""

    def upsert_smartup_organization(self, organization: SmartUpOrganization) -> SmartUpOrganization:
        """Persist or update a SmartUp organization."""

    def delete_smartup_organization(self, organization_id: UUID) -> None:
        """Delete a SmartUp organization."""

    def reset_smartup_data(self) -> None:
        """Delete imported SmartUp data while preserving organization settings."""

    def upsert_smartup_migration_run(
        self,
        run: SmartUpMigrationRun,
    ) -> SmartUpMigrationRun:
        """Persist or update a SmartUp migration run."""

    def upsert_sync_checkpoint(self, checkpoint: SyncCheckpoint) -> SyncCheckpoint:
        """Persist or update a sync checkpoint."""

    def upsert_migration_batch(self, batch: MigrationBatch) -> MigrationBatch:
        """Persist or update a migration batch."""

    def upsert_inventory_snapshot(self, snapshot: InventorySnapshot) -> InventorySnapshot:
        """Persist or update an inventory snapshot."""

    def upsert_smartup_raw_record(self, record: SmartUpRawRecord) -> SmartUpRawRecord:
        """Persist or update a raw SmartUp record."""

    def upsert_normalization_issue(self, issue: NormalizationIssue) -> NormalizationIssue:
        """Persist a normalization issue."""

    def upsert_customer(self, customer: Customer) -> Customer:
        """Persist or update a normalized customer."""

    def upsert_product_category(self, category: ProductCategory) -> ProductCategory:
        """Persist or update a normalized product category."""

    def upsert_product(self, product: Product) -> Product:
        """Persist or update a normalized product."""

    def upsert_warehouse(self, warehouse: Warehouse) -> Warehouse:
        """Persist or update a normalized warehouse."""

    def upsert_price_type(self, price_type: PriceType) -> PriceType:
        """Persist or update a normalized price type."""

    def upsert_product_price(self, product_price: ProductPrice) -> ProductPrice:
        """Persist or update a normalized product price."""

    def upsert_sale_v2(self, sale: Sale) -> Sale:
        """Persist or update a normalized sale."""

    def upsert_sale_item(self, sale_item: SaleItem) -> SaleItem:
        """Persist or update a normalized sale item."""

    def upsert_payment(self, payment: Payment) -> Payment:
        """Persist or update a normalized payment."""

    def upsert_inventory_balance(self, inventory_balance: InventoryBalance) -> InventoryBalance:
        """Persist or update a normalized inventory balance."""

    def upsert_visit(self, visit: Visit) -> Visit:
        """Persist or update a normalized visit."""

    def upsert_bank_operation(self, bank_operation: BankOperation) -> BankOperation:
        """Persist or update a normalized bank operation."""

    def upsert_business_document(self, document: BusinessDocument) -> BusinessDocument:
        """Persist or update a normalized business document."""

    def upsert_business_document_item(
        self,
        item: BusinessDocumentItem,
    ) -> BusinessDocumentItem:
        """Persist or update a normalized business document line item."""

    def upsert_canonical_organization(
        self,
        organization: CanonicalOrganization,
    ) -> CanonicalOrganization:
        """Persist or update a canonical SmartUp organization."""

    def upsert_canonical_customer_group(
        self,
        group: CanonicalCustomerGroup,
    ) -> CanonicalCustomerGroup:
        """Persist or update a canonical SmartUp customer group."""

    def upsert_canonical_customer(self, customer: CanonicalCustomer) -> CanonicalCustomer:
        """Persist or update a canonical SmartUp customer."""

    def upsert_canonical_product_category(
        self,
        category: CanonicalProductCategory,
    ) -> CanonicalProductCategory:
        """Persist or update a canonical SmartUp product category."""

    def upsert_canonical_product(self, product: CanonicalProduct) -> CanonicalProduct:
        """Persist or update a canonical SmartUp product."""

    def upsert_canonical_warehouse(self, warehouse: CanonicalWarehouse) -> CanonicalWarehouse:
        """Persist or update a canonical SmartUp warehouse."""

    def upsert_canonical_price_type(self, price_type: CanonicalPriceType) -> CanonicalPriceType:
        """Persist or update a canonical SmartUp price type."""

    def upsert_canonical_product_price(
        self,
        product_price: CanonicalProductPrice,
    ) -> CanonicalProductPrice:
        """Persist or update a canonical SmartUp product price."""

    def upsert_canonical_sales_rep(self, sales_rep: CanonicalSalesRep) -> CanonicalSalesRep:
        """Persist or update a canonical SmartUp sales representative."""

    def upsert_canonical_working_zone(
        self,
        working_zone: CanonicalWorkingZone,
    ) -> CanonicalWorkingZone:
        """Persist or update a canonical SmartUp working zone."""

    def upsert_canonical_visit(self, visit: CanonicalVisit) -> CanonicalVisit:
        """Persist or update a canonical SmartUp visit."""

    def upsert_canonical_visit_stock(
        self,
        visit_stock: CanonicalVisitStock,
    ) -> CanonicalVisitStock:
        """Persist or update a canonical SmartUp visit stock row."""

    def upsert_canonical_visit_quiz_answer(
        self,
        quiz_answer: CanonicalVisitQuizAnswer,
    ) -> CanonicalVisitQuizAnswer:
        """Persist or update a canonical SmartUp visit quiz answer."""

    def upsert_canonical_visit_equipment(
        self,
        equipment: CanonicalVisitEquipment,
    ) -> CanonicalVisitEquipment:
        """Persist or update a canonical SmartUp visit equipment row."""

    def upsert_canonical_visit_comment(
        self,
        comment: CanonicalVisitComment,
    ) -> CanonicalVisitComment:
        """Persist or update a canonical SmartUp visit comment."""

    def upsert_canonical_media_asset(
        self,
        media_asset: CanonicalMediaAsset,
    ) -> CanonicalMediaAsset:
        """Persist or update a canonical SmartUp media asset."""

    def upsert_canonical_order(self, order: CanonicalOrder) -> CanonicalOrder:
        """Persist or update a canonical SmartUp order."""

    def upsert_canonical_sale(self, sale: CanonicalSale) -> CanonicalSale:
        """Persist or update a canonical realized sale."""

    def upsert_canonical_sale_item(
        self,
        sale_item: CanonicalSaleItem,
    ) -> CanonicalSaleItem:
        """Persist or update a canonical sale item."""

    def upsert_canonical_payment(self, payment: CanonicalPayment) -> CanonicalPayment:
        """Persist or update a canonical customer payment."""

    def upsert_canonical_payment_allocation(
        self,
        allocation: CanonicalPaymentAllocation,
    ) -> CanonicalPaymentAllocation:
        """Persist or update a canonical payment allocation."""

    def upsert_canonical_financial_account(
        self,
        account: CanonicalFinancialAccount,
    ) -> CanonicalFinancialAccount:
        """Persist or update a canonical financial account."""

    def upsert_canonical_financial_operation(
        self,
        operation: CanonicalFinancialOperation,
    ) -> CanonicalFinancialOperation:
        """Persist or update a canonical financial operation."""

    def upsert_canonical_customer_return(
        self,
        customer_return: CanonicalCustomerReturn,
    ) -> CanonicalCustomerReturn:
        """Persist or update a canonical customer return."""

    def upsert_canonical_customer_return_item(
        self,
        customer_return_item: CanonicalCustomerReturnItem,
    ) -> CanonicalCustomerReturnItem:
        """Persist or update a canonical customer return item."""

    def upsert_canonical_inventory_balance(
        self,
        inventory_balance: CanonicalInventoryBalance,
    ) -> CanonicalInventoryBalance:
        """Persist or update a canonical inventory balance snapshot."""

    def upsert_canonical_purchase(self, purchase: CanonicalPurchase) -> CanonicalPurchase:
        """Persist or update a canonical purchase document."""

    def upsert_canonical_purchase_item(
        self,
        purchase_item: CanonicalPurchaseItem,
    ) -> CanonicalPurchaseItem:
        """Persist or update a canonical purchase line item."""

    def upsert_canonical_warehouse_receipt(
        self,
        receipt: CanonicalWarehouseReceipt,
    ) -> CanonicalWarehouseReceipt:
        """Persist or update a canonical warehouse receipt."""

    def upsert_canonical_warehouse_receipt_item(
        self,
        receipt_item: CanonicalWarehouseReceiptItem,
    ) -> CanonicalWarehouseReceiptItem:
        """Persist or update a canonical warehouse receipt line item."""

    def upsert_canonical_writeoff(self, writeoff: CanonicalWriteoff) -> CanonicalWriteoff:
        """Persist or update a canonical write-off document."""

    def upsert_canonical_writeoff_item(
        self,
        writeoff_item: CanonicalWriteoffItem,
    ) -> CanonicalWriteoffItem:
        """Persist or update a canonical write-off line item."""

    def upsert_canonical_supplier_return(
        self,
        supplier_return: CanonicalSupplierReturn,
    ) -> CanonicalSupplierReturn:
        """Persist or update a canonical supplier return document."""

    def upsert_canonical_supplier_return_item(
        self,
        supplier_return_item: CanonicalSupplierReturnItem,
    ) -> CanonicalSupplierReturnItem:
        """Persist or update a canonical supplier return line item."""

    def upsert_canonical_stocktaking(
        self,
        stocktaking: CanonicalStocktaking,
    ) -> CanonicalStocktaking:
        """Persist or update a canonical stocktaking document."""

    def upsert_canonical_stocktaking_item(
        self,
        stocktaking_item: CanonicalStocktakingItem,
    ) -> CanonicalStocktakingItem:
        """Persist or update a canonical stocktaking line item."""

    def upsert_canonical_internal_movement(
        self,
        movement: CanonicalInternalMovement,
    ) -> CanonicalInternalMovement:
        """Persist or update a canonical internal movement document."""

    def upsert_canonical_internal_movement_item(
        self,
        movement_item: CanonicalInternalMovementItem,
    ) -> CanonicalInternalMovementItem:
        """Persist or update a canonical internal movement line item."""

    def upsert_canonical_cross_org_movement(
        self,
        movement: CanonicalCrossOrgMovement,
    ) -> CanonicalCrossOrgMovement:
        """Persist or update a canonical cross-organization movement document."""

    def upsert_canonical_cross_org_movement_item(
        self,
        movement_item: CanonicalCrossOrgMovementItem,
    ) -> CanonicalCrossOrgMovementItem:
        """Persist or update a canonical cross-organization movement line item."""


class CoreDataStore(CoreDataReader, CoreDataWriter, Protocol):
    """Combined read and write operations for a core data backend."""
