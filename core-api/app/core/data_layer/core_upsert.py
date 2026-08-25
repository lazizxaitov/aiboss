"""Upsert normalized SmartUp entities into the core data layer."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from app.core.data_layer.contracts import CoreDataStore
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

type NormalizedModel = (
    Customer
    | ProductCategory
    | Product
    | Warehouse
    | Sale
    | SaleItem
    | Payment
    | InventoryBalance
    | Visit
    | BankOperation
    | BusinessDocument
    | BusinessDocumentItem
)

_MODEL_BY_ENTITY_TYPE: dict[str, type[Any]] = {
    "customers": Customer,
    "product_categories": ProductCategory,
    "products": Product,
    "warehouses": Warehouse,
    "price_types": PriceType,
    "product_prices": ProductPrice,
    "sales": Sale,
    "sale_items": SaleItem,
    "payments": Payment,
    "inventory_balances": InventoryBalance,
    "visits": Visit,
    "bank_operations": BankOperation,
    "business_documents": BusinessDocument,
    "business_document_items": BusinessDocumentItem,
}


@dataclass(slots=True)
class UpsertOutcome:
    """Outcome of one normalized entity upsert."""

    action: str
    entity_id: UUID


class CoreUpsertService:
    """Persist normalized SmartUp entities in the core data layer."""

    def __init__(self, store: CoreDataStore) -> None:
        self.store = store

    def upsert_entity(self, entity_type: str, payload: dict[str, Any]) -> UpsertOutcome:
        """Upsert one normalized entity by type."""

        model_cls = _MODEL_BY_ENTITY_TYPE.get(entity_type)
        if model_cls is None:
            msg = f"Unsupported normalized entity type: {entity_type}"
            raise ValueError(msg)
        model = model_cls.model_validate(payload)
        if model.source_external_id is None:
            msg = f"source_external_id is required for {entity_type}"
            raise ValueError(msg)
        entity_id = self._stable_entity_id(
            organization_id=model.organization_id,
            entity_type=entity_type,
            source_system=model.source_system,
            source_external_id=model.source_external_id,
        )
        normalized = model.model_copy(
            update={
                "id": entity_id,
                "last_synced_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            },
        )
        existing = self._fetch_existing(entity_type, entity_id)
        self._persist(entity_type, normalized)
        if existing is None:
            action = "inserted"
        elif self._comparison_payload(existing) == self._comparison_payload(normalized):
            action = "unchanged"
        else:
            action = "updated"
        return UpsertOutcome(action=action, entity_id=entity_id)

    def upsert_related_entities(
        self,
        related_entities: list[tuple[str, dict[str, Any]]],
    ) -> list[UpsertOutcome]:
        """Upsert all related normalized entities."""

        outcomes: list[UpsertOutcome] = []
        for entity_type, payload in related_entities:
            outcomes.append(self.upsert_entity(entity_type, payload))
        return outcomes

    def upsert_normalized_record(
        self,
        entity_type: str,
        payload: dict[str, Any],
        related_entities: list[tuple[str, dict[str, Any]]] | None = None,
    ) -> list[UpsertOutcome]:
        """Upsert a normalized entity and its children."""

        outcomes = [self.upsert_entity(entity_type, payload)]
        if related_entities:
            outcomes.extend(self.upsert_related_entities(related_entities))
        return outcomes

    def _persist(self, entity_type: str, model: NormalizedModel) -> None:
        if entity_type == "customers":
            self.store.upsert_customer(model)
        elif entity_type == "product_categories":
            self.store.upsert_product_category(model)
        elif entity_type == "products":
            self.store.upsert_product(model)
        elif entity_type == "warehouses":
            self.store.upsert_warehouse(model)
        elif entity_type == "price_types":
            self.store.upsert_price_type(model)
        elif entity_type == "product_prices":
            self.store.upsert_product_price(model)
        elif entity_type == "sales":
            self.store.upsert_sale_v2(model)
        elif entity_type == "sale_items":
            self.store.upsert_sale_item(model)
        elif entity_type == "payments":
            self.store.upsert_payment(model)
        elif entity_type == "inventory_balances":
            self.store.upsert_inventory_balance(model)
        elif entity_type == "visits":
            self.store.upsert_visit(model)
        elif entity_type == "bank_operations":
            self.store.upsert_bank_operation(model)
        elif entity_type == "business_documents":
            self.store.upsert_business_document(model)
        elif entity_type == "business_document_items":
            self.store.upsert_business_document_item(model)
        else:  # pragma: no cover - defensive guard
            msg = f"Unsupported entity type: {entity_type}"
            raise ValueError(msg)

    def _fetch_existing(self, entity_type: str, entity_id: UUID) -> NormalizedModel | None:
        if entity_type == "customers":
            return self.store.get_customer(entity_id)
        if entity_type == "product_categories":
            return self.store.get_product_category(entity_id)
        if entity_type == "products":
            return self.store.get_product(entity_id)
        if entity_type == "warehouses":
            return self.store.get_warehouse(entity_id)
        if entity_type == "price_types":
            return self.store.get_price_type(entity_id)
        if entity_type == "product_prices":
            return self.store.get_product_price(entity_id)
        if entity_type == "sales":
            return self.store.get_sale_v2(entity_id)
        if entity_type == "sale_items":
            return self.store.get_sale_item(entity_id)
        if entity_type == "payments":
            return self.store.get_payment(entity_id)
        if entity_type == "inventory_balances":
            return self.store.get_inventory_balance(entity_id)
        if entity_type == "visits":
            return self.store.get_visit(entity_id)
        if entity_type == "bank_operations":
            return self.store.get_bank_operation(entity_id)
        if entity_type == "business_documents":
            return self.store.get_business_document(entity_id)
        if entity_type == "business_document_items":
            return self.store.get_business_document_item(entity_id)
        return None

    @staticmethod
    def _stable_entity_id(
        *,
        organization_id: UUID,
        entity_type: str,
        source_system: str,
        source_external_id: str,
    ) -> UUID:
        return uuid5(
            NAMESPACE_URL,
            f"smartup:normalized:{organization_id}:{source_system}:{entity_type}:{source_external_id}",
        )

    @staticmethod
    def _comparison_payload(model: NormalizedModel) -> dict[str, Any]:
        payload = model.model_dump(mode="python")
        for key in ("created_at", "updated_at", "last_synced_at", "imported_at"):
            payload.pop(key, None)
        return payload


def _normalize_relation_payloads(
    payloads: list[dict[str, Any]],
    entity_type: str,
) -> list[tuple[str, dict[str, Any]]]:
    return [(entity_type, payload) for payload in payloads]
