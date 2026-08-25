"""Resolve normalized SmartUp references inside the core layer."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.core.data_layer.contracts import CoreDataStore


@dataclass(slots=True)
class ExternalReferenceResolver:
    """Resolve SmartUp source references to normalized core entities."""

    store: CoreDataStore

    def resolve(
        self,
        entity_type: str,
        organization_id: UUID,
        source_external_id: str,
    ) -> object | None:
        """Return the matching normalized entity or None."""

        lookup = {
            "customers": self.store.list_customers,
            "product_categories": self.store.list_product_categories,
            "products": self.store.list_products,
            "warehouses": self.store.list_warehouses,
            "price_types": self.store.list_price_types,
            "sales": self.store.list_sales_v2,
            "sale_items": self.store.list_sale_items,
            "payments": self.store.list_payments,
            "inventory_balances": self.store.list_inventory_balances,
            "visits": self.store.list_visits,
            "bank_operations": self.store.list_bank_operations,
            "business_documents": self.store.list_business_documents,
            "business_document_items": self.store.list_business_document_items,
        }.get(entity_type)
        if lookup is None:
            return None
        for item in lookup(organization_id=organization_id):
            if getattr(item, "source_external_id", None) == source_external_id:
                return item
        return None
