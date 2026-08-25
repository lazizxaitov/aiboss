"""SmartUp request profiles used by the connector and importer."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SmartUpRequestProfile:
    """Describes how to fetch and page a SmartUp endpoint."""

    response_key: str
    supports_history: bool = False
    supports_snapshot: bool = False
    history_start_param: str | None = None
    history_end_param: str | None = None
    offset_param: str | None = None
    limit_param: str | None = None
    page_size: int | None = None


SMARTUP_REQUEST_PROFILES: dict[str, SmartUpRequestProfile] = {
    "Legal entities": SmartUpRequestProfile(
        response_key="legal_person",
        supports_history=True,
        history_start_param="begin_created_on",
        history_end_param="end_created_on",
    ),
    "Natural persons": SmartUpRequestProfile(
        response_key="natural_person",
        supports_history=True,
        history_start_param="begin_created_on",
        history_end_param="end_created_on",
    ),
    "Inventory": SmartUpRequestProfile(
        response_key="inventory",
        supports_history=True,
        history_start_param="begin_created_on",
        history_end_param="end_created_on",
    ),
    "Product groups": SmartUpRequestProfile(
        response_key="product_group",
        supports_history=True,
        history_start_param="begin_created_on",
        history_end_param="end_created_on",
    ),
    "Price types": SmartUpRequestProfile(
        response_key="data",
        supports_history=False,
        offset_param="offset",
        limit_param="limit",
        page_size=50,
    ),
    "Inventory prices": SmartUpRequestProfile(
        response_key="inventory",
        supports_history=False,
    ),
    "Service export": SmartUpRequestProfile(
        response_key="service",
        supports_history=True,
        history_start_param="begin_created_on",
        history_end_param="end_created_on",
    ),
    "Purchase export": SmartUpRequestProfile(
        response_key="purchase",
        supports_history=True,
        history_start_param="begin_purchase_date",
        history_end_param="end_purchase_date",
    ),
    "Receipts to warehouse export": SmartUpRequestProfile(
        response_key="input",
        supports_history=True,
        history_start_param="begin_input_date",
        history_end_param="end_input_date",
    ),
    "Return to suppliers export": SmartUpRequestProfile(
        response_key="return",
        supports_history=True,
        history_start_param="begin_return_date",
        history_end_param="end_return_date",
    ),
    "Stocktaking export": SmartUpRequestProfile(
        response_key="stocktaking",
        supports_history=True,
        history_start_param="begin_stocktaking_date",
        history_end_param="end_stocktaking_date",
    ),
    "Write-off export": SmartUpRequestProfile(
        response_key="writeoff",
        supports_history=True,
        history_start_param="begin_writeoff_date",
        history_end_param="end_writeoff_date",
    ),
    "Cross-organizational movement export": SmartUpRequestProfile(
        response_key="movement",
        supports_history=True,
        history_start_param="begin_from_date",
        history_end_param="end_from_date",
    ),
    "Internal movement export": SmartUpRequestProfile(
        response_key="movement",
        supports_history=True,
        history_start_param="begin_from_movement_date",
        history_end_param="end_from_movement_date",
    ),
    "Logistics export": SmartUpRequestProfile(
        response_key="logistics",
        supports_history=False,
    ),
    "Movement export": SmartUpRequestProfile(
        response_key="equipment_movement",
        supports_history=True,
        history_start_param="begin_movement_date",
        history_end_param="end_movement_date",
    ),
    "Request export": SmartUpRequestProfile(
        response_key="equipment_request",
        supports_history=True,
        history_start_param="begin_request_date",
        history_end_param="end_request_date",
    ),
    "Person group export": SmartUpRequestProfile(
        response_key="person_group",
        supports_history=True,
        history_start_param="begin_created_on",
        history_end_param="end_created_on",
    ),
    "Return reason export": SmartUpRequestProfile(
        response_key="return_reason",
        supports_history=False,
    ),
    "Producers": SmartUpRequestProfile(
        response_key="producer",
        supports_history=True,
        history_start_param="begin_created_on",
        history_end_param="end_created_on",
    ),
    "Contracts": SmartUpRequestProfile(
        response_key="contract",
        supports_history=True,
        history_start_param="begin_created_on",
        history_end_param="end_created_on",
    ),
    "Workspaces": SmartUpRequestProfile(
        response_key="room",
        supports_history=True,
        history_start_param="begin_created_on",
        history_end_param="end_created_on",
    ),
    "Orders": SmartUpRequestProfile(
        response_key="order",
        supports_history=True,
        history_start_param="begin_deal_date",
        history_end_param="end_deal_date",
    ),
    "Returns": SmartUpRequestProfile(
        response_key="return",
        supports_history=True,
        history_start_param="begin_return_date",
        history_end_param="end_return_date",
    ),
    "Visits": SmartUpRequestProfile(
        response_key="visit",
        supports_history=True,
        history_start_param="begin_visit_date",
        history_end_param="end_visit_date",
    ),
    "Cross-organizational Movement": SmartUpRequestProfile(
        response_key="movement",
        supports_history=True,
        history_start_param="begin_from_date",
        history_end_param="end_from_date",
    ),
    "Internal movement": SmartUpRequestProfile(
        response_key="movement",
        supports_history=True,
        history_start_param="begin_from_movement_date",
        history_end_param="end_from_movement_date",
    ),
    "Stocktaking": SmartUpRequestProfile(
        response_key="stocktaking",
        supports_history=True,
        history_start_param="begin_stocktaking_date",
        history_end_param="end_stocktaking_date",
    ),
    "Write-off": SmartUpRequestProfile(
        response_key="writeoff",
        supports_history=True,
        history_start_param="begin_writeoff_date",
        history_end_param="end_writeoff_date",
    ),
    "Return to suppliers": SmartUpRequestProfile(
        response_key="return",
        supports_history=True,
        history_start_param="begin_return_date",
        history_end_param="end_return_date",
    ),
    "Receipts to warehouse": SmartUpRequestProfile(
        response_key="input",
        supports_history=True,
        history_start_param="begin_input_date",
        history_end_param="end_input_date",
    ),
    "Purchase": SmartUpRequestProfile(
        response_key="purchase",
        supports_history=True,
        history_start_param="begin_purchase_date",
        history_end_param="end_purchase_date",
    ),
    "Payments from clients": SmartUpRequestProfile(
        response_key="cashin",
        supports_history=True,
        history_start_param="begin_cashin_date",
        history_end_param="end_cashin_date",
    ),
    "Client payments": SmartUpRequestProfile(
        response_key="cashin",
        supports_history=True,
        history_start_param="begin_cashin_date",
        history_end_param="end_cashin_date",
    ),
    "Cash Operations": SmartUpRequestProfile(
        response_key="cash_operation",
        supports_history=True,
        history_start_param="begin_operation_date",
        history_end_param="end_operation_date",
    ),
    "Bank Statements": SmartUpRequestProfile(
        response_key="bank_operation",
        supports_history=True,
        history_start_param="begin_operation_date",
        history_end_param="end_operation_date",
    ),
    "Inventory Balance": SmartUpRequestProfile(
        response_key="balance",
        supports_history=True,
        history_start_param="begin_date",
        history_end_param="end_date",
    ),
    "Equipment Balance": SmartUpRequestProfile(
        response_key="data",
        supports_history=False,
        offset_param="offset",
        limit_param="limit",
        page_size=50,
    ),
}


def get_request_profile(mapping_name: str) -> SmartUpRequestProfile | None:
    """Return a request profile for a SmartUp mapping name."""

    normalized = _normalize_name(mapping_name)
    if mapping_name in SMARTUP_REQUEST_PROFILES:
        return SMARTUP_REQUEST_PROFILES[mapping_name]

    return next(
        (
            profile
            for name, profile in SMARTUP_REQUEST_PROFILES.items()
            if _normalize_name(name) == normalized
        ),
        None,
    )


def _normalize_name(name: str) -> str:
    lowered = name.lower().strip()
    for suffix in (" / export", " / import", " export", " import"):
        if lowered.endswith(suffix):
            return lowered[: -len(suffix)].strip()
    return lowered
