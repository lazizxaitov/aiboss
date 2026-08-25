"""SmartUp normalizer registry."""

from .bank_operation import BankOperationNormalizer
from .base import SmartUpNormalizer
from .category import CategoryNormalizer
from .customer import CustomerNormalizer
from .document import BusinessDocumentNormalizer
from .inventory import InventoryNormalizer
from .payment import PaymentNormalizer
from .price import PriceTypeNormalizer, ProductPriceNormalizer
from .product import ProductNormalizer
from .sale import SaleNormalizer
from .visit import VisitNormalizer
from .warehouse import WarehouseNormalizer

NORMALIZER_REGISTRY: dict[str, SmartUpNormalizer] = {
    "customers": CustomerNormalizer(),
    "product_categories": CategoryNormalizer(),
    "products": ProductNormalizer(),
    "warehouses": WarehouseNormalizer(),
    "sales": SaleNormalizer(),
    "payments": PaymentNormalizer(),
    "price_types": PriceTypeNormalizer(),
    "product_prices": ProductPriceNormalizer(),
    "inventory_balances": InventoryNormalizer(),
    "visits": VisitNormalizer(),
    "bank_operations": BankOperationNormalizer(),
    "returns": BusinessDocumentNormalizer("returns"),
    "purchases": BusinessDocumentNormalizer("purchases"),
    "warehouse_receipts": BusinessDocumentNormalizer("warehouse_receipts"),
    "return_to_suppliers": BusinessDocumentNormalizer("return_to_suppliers"),
    "stocktakings": BusinessDocumentNormalizer("stocktakings"),
    "write_offs": BusinessDocumentNormalizer("write_offs"),
    "cross_organizational_movements": BusinessDocumentNormalizer(
        "cross_organizational_movements",
    ),
    "internal_movements": BusinessDocumentNormalizer("internal_movements"),
    "logistics": BusinessDocumentNormalizer("logistics"),
    "equipment_movements": BusinessDocumentNormalizer("equipment_movements"),
    "equipment_requests": BusinessDocumentNormalizer("equipment_requests"),
}
