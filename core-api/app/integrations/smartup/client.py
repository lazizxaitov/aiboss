"""HTTP client for SmartUp API requests."""

from __future__ import annotations

import json
import logging
from csv import DictReader
from dataclasses import dataclass
from io import StringIO
from typing import Any
from xml.etree import ElementTree as ET

import httpx

from app.integrations.smartup.mapping import SmartUpMapping
from app.integrations.smartup.settings import SmartUpSettings

logger = logging.getLogger(__name__)
SMARTUP_MAX_OBJECTS_PER_REQUEST = 5000


@dataclass(frozen=True, slots=True)
class SmartUpEndpointSpec:
    """Description of a public SmartUp endpoint."""

    name: str
    method_name: str
    path: str
    http_method: str = "POST"


SMARTUP_PUBLIC_ENDPOINTS_V1: tuple[SmartUpEndpointSpec, ...] = (
    SmartUpEndpointSpec("Order / Import", "import_order", "/b/trade/txs/tdeal/order$import"),
    SmartUpEndpointSpec("Order / Export", "export_order", "/b/trade/txs/tdeal/order$export"),
    SmartUpEndpointSpec(
        "Order / Attach data",
        "attach_order_data",
        "/b/trade/txs/tdeal/order$attach_data",
    ),
    SmartUpEndpointSpec(
        "Order / Change status",
        "change_order_status",
        "/b/trade/txs/tdeal/order$change_status",
    ),
    SmartUpEndpointSpec(
        "Order / Import marking codes",
        "import_order_marking_codes",
        "/b/anor/mxsx/mdeal/order$import_order_marking_codes",
    ),
    SmartUpEndpointSpec("Return / Import", "import_return", "/b/anor/mxsx/mdeal/return$import"),
    SmartUpEndpointSpec("Return / Export", "export_return", "/b/anor/mxsx/mdeal/return$export"),
    SmartUpEndpointSpec("Visit / Export", "export_visit", "/b/trade/txs/tvt/visit$export"),
    SmartUpEndpointSpec(
        "Cross-organizational Movement / Import",
        "import_cross_organizational_movement",
        "/b/anor/mxsx/mfm/movement$import",
    ),
    SmartUpEndpointSpec(
        "Cross-organizational Movement / Export",
        "export_cross_organizational_movement",
        "/b/anor/mxsx/mfm/movement$export",
    ),
    SmartUpEndpointSpec(
        "Cross-organizational Movement Status Change",
        "change_cross_organizational_movement_status",
        "/b/anor/mxsx/mfm/movement$change_status",
    ),
    SmartUpEndpointSpec(
        "Internal movement / Import",
        "import_internal_movement",
        "/b/anor/mxsx/mkw/movement$import",
    ),
    SmartUpEndpointSpec(
        "Internal movement / Export",
        "export_internal_movement",
        "/b/anor/mxsx/mkw/movement$export",
    ),
    SmartUpEndpointSpec(
        "Stocktaking / Import",
        "import_stocktaking",
        "/b/anor/mxsx/mkw/stocktaking$import",
    ),
    SmartUpEndpointSpec(
        "Stocktaking / Export",
        "export_stocktaking",
        "/b/anor/mxsx/mkw/stocktaking$export",
    ),
    SmartUpEndpointSpec(
        "Write-off / Import",
        "import_write_off",
        "/b/anor/mxsx/mkw/writeoff$import",
    ),
    SmartUpEndpointSpec(
        "Write-off / Export",
        "export_write_off",
        "/b/anor/mxsx/mkw/writeoff$export",
    ),
    SmartUpEndpointSpec(
        "Return to suppliers / Import",
        "import_return_to_suppliers",
        "/b/anor/mxsx/mkw/return$import",
    ),
    SmartUpEndpointSpec(
        "Return to suppliers / Export",
        "export_return_to_suppliers",
        "/b/anor/mxsx/mkw/return$export",
    ),
    SmartUpEndpointSpec(
        "Receipts to warehouse / Import",
        "import_receipts_to_warehouse",
        "/b/anor/mxsx/mkw/input$import",
    ),
    SmartUpEndpointSpec(
        "Receipts to warehouse / Export",
        "export_receipts_to_warehouse",
        "/b/anor/mxsx/mkw/input$export",
    ),
    SmartUpEndpointSpec("Purchase / Import", "import_purchase", "/b/anor/mxsx/mkw/purchase$import"),
    SmartUpEndpointSpec("Purchase / Export", "export_purchase", "/b/anor/mxsx/mkw/purchase$export"),
    SmartUpEndpointSpec(
        "Logistics / Import",
        "import_logistics",
        "/b/trade/txs/tdeal/logistics$import",
    ),
    SmartUpEndpointSpec(
        "Logistics / Export",
        "export_logistics",
        "/b/trade/txs/tdeal/logistics$export",
    ),
    SmartUpEndpointSpec(
        "Payments from clients / Import",
        "import_payments_from_clients",
        "/b/trade/txs/tcs/cashin$import",
    ),
    SmartUpEndpointSpec(
        "Payments from clients / Export",
        "export_payments_from_clients",
        "/b/trade/txs/tcs/cashin$export",
    ),
    SmartUpEndpointSpec(
        "Cash Operations / Import",
        "import_cash_operations",
        "/b/anor/mxsx/mkcs/cash_operation$import",
    ),
    SmartUpEndpointSpec(
        "Cash Operations / Export",
        "export_cash_operations",
        "/b/anor/mxsx/mkcs/cash_operation$export",
    ),
    SmartUpEndpointSpec(
        "Bank Statements / Import",
        "import_bank_statements",
        "/b/anor/mxsx/mkcs/bank_operation$import",
    ),
    SmartUpEndpointSpec(
        "Bank Statements / Export",
        "export_bank_statements",
        "/b/anor/mxsx/mkcs/bank_operation$export",
    ),
    SmartUpEndpointSpec(
        "Movement / Import",
        "import_equipment_movement",
        "/b/anor/mxsx/mqpf/equipment_movement$import",
    ),
    SmartUpEndpointSpec(
        "Movement / Export",
        "export_equipment_movement",
        "/b/anor/mxsx/mqpf/equipment_movement$export",
    ),
    SmartUpEndpointSpec(
        "Movement / Change",
        "change_equipment_movement_status",
        "/b/anor/mxsx/mqpf/equipment_movement$change_status",
    ),
    SmartUpEndpointSpec(
        "Request / Import",
        "import_equipment_request",
        "/b/anor/mxsx/mqpf/equipment_request$import",
    ),
    SmartUpEndpointSpec(
        "Request / Export",
        "export_equipment_request",
        "/b/anor/mxsx/mqpf/equipment_request$export",
    ),
    SmartUpEndpointSpec(
        "Request / Change",
        "change_equipment_request_status",
        "/b/anor/mxsx/mqpf/equipment_request$change_status",
    ),
    SmartUpEndpointSpec(
        "Inventory / Import",
        "import_inventory",
        "/b/anor/mxsx/mr/inventory$import",
    ),
    SmartUpEndpointSpec(
        "Inventory / Export",
        "export_inventory",
        "/b/anor/mxsx/mr/inventory$export",
    ),
    SmartUpEndpointSpec("Service / Import", "import_service", "/b/anor/mxsx/mr/service$import"),
    SmartUpEndpointSpec("Service / Export", "export_service", "/b/anor/mxsx/mr/service$export"),
    SmartUpEndpointSpec(
        "Product group / Import",
        "import_product_group",
        "/b/anor/mxsx/mr/product_group$import",
    ),
    SmartUpEndpointSpec(
        "Product group / Export",
        "export_product_group",
        "/b/anor/mxsx/mr/product_group$export",
    ),
    SmartUpEndpointSpec(
        "Price type / Import",
        "import_price_type",
        "/b/anor/api/v2/mkr/price_type$import",
    ),
    SmartUpEndpointSpec(
        "Price type / Export",
        "export_price_type",
        "/b/anor/api/v2/mkr/price_type$export",
    ),
    SmartUpEndpointSpec(
        "Inventory price / Import",
        "import_inventory_price",
        "/b/anor/api/v2/mkf/product_price$import",
    ),
    SmartUpEndpointSpec(
        "Inventory price / Export",
        "export_inventory_price",
        "/b/anor/api/v2/mkf/product_price$export",
    ),
    SmartUpEndpointSpec("Producers / Import", "import_producer", "/b/anor/mxsx/mr/producer$import"),
    SmartUpEndpointSpec("Producers / Export", "export_producer", "/b/anor/mxsx/mr/producer$export"),
    SmartUpEndpointSpec(
        "Legal entity / Import",
        "import_legal_entity",
        "/b/anor/mxsx/mr/legal_person$import",
    ),
    SmartUpEndpointSpec(
        "Legal entity / Export",
        "export_legal_entity",
        "/b/anor/mxsx/mr/legal_person$export",
    ),
    SmartUpEndpointSpec(
        "Natural persons / Import",
        "import_natural_person",
        "/b/anor/mxsx/mr/natural_person$import",
    ),
    SmartUpEndpointSpec(
        "Natural persons / Export",
        "export_natural_person",
        "/b/anor/mxsx/mr/natural_person$export",
    ),
    SmartUpEndpointSpec(
        "Persons group / Import",
        "import_person_group",
        "/b/anor/mxsx/mr/person_group$import",
    ),
    SmartUpEndpointSpec(
        "Persons group / Export",
        "export_person_group",
        "/b/anor/mxsx/mr/person_group$export",
    ),
    SmartUpEndpointSpec("Workspaces / Export", "export_workspace", "/b/anor/mxsx/mrf/room$export"),
    SmartUpEndpointSpec("Contract / Import", "import_contract", "/b/anor/mxsx/mkf/contract$import"),
    SmartUpEndpointSpec("Contract / Export", "export_contract", "/b/anor/mxsx/mkf/contract$export"),
    SmartUpEndpointSpec(
        "Return Reason / Import",
        "import_return_reason",
        "/b/anor/mxsx/mdeal/return_reason$import",
    ),
    SmartUpEndpointSpec(
        "Return Reason / Export",
        "export_return_reason",
        "/b/anor/mxsx/mdeal/return_reason$export",
    ),
    SmartUpEndpointSpec(
        "Inventory Balance / Export",
        "export_inventory_balance",
        "/b/anor/mxsx/mkw/balance$export",
    ),
    SmartUpEndpointSpec(
        "Equipment Balance / Export",
        "export_equipment_balance",
        "/b/trade/txs/tvt/equipment_balance$export_data",
    ),
)


@dataclass(slots=True)
class SmartUpApiClient:
    """Typed wrapper around SmartUp HTTP requests."""

    settings: SmartUpSettings

    def request_json(self, mapping: SmartUpMapping, payload: dict[str, Any]) -> dict[str, Any]:
        """Execute a SmartUp request and return parsed JSON."""

        return self._request_json(mapping.smartup_method, mapping.smartup_endpoint, payload)

    def request_response(
        self,
        method: str,
        endpoint: str,
        payload: dict[str, Any],
    ) -> httpx.Response:
        """Execute a SmartUp request and return the upstream response."""

        self._validate_payload_object_count(payload)
        resolved_endpoint = self._resolve_endpoint_path(endpoint)
        url = self._build_url(resolved_endpoint)
        headers = self._build_headers()
        auth = self._build_auth()

        logger.info(
            "SmartUp request method=%s url=%s company_id=%s project_code=%s filial_id=%s",
            method,
            url,
            self.settings.company_id,
            self.settings.project_code,
            self.settings.filial_id,
        )
        with httpx.Client(timeout=self.settings.timeout_seconds, auth=auth) as client:
            response = client.request(method, url, json=payload, headers=headers)

        logger.info(
            (
                "SmartUp upstream response method=%s url=%s "
                "company_id=%s project_code=%s filial_id=%s status=%s body=%s"
            ),
            method,
            url,
            self.settings.company_id,
            self.settings.project_code,
            self.settings.filial_id,
            response.status_code,
            _redact_sensitive_text(response.text),
        )
        return response

    def _request_json(
        self,
        method: str,
        endpoint: str,
        payload: dict[str, Any],
    ) -> Any:
        response = self.request_response(method, endpoint, payload)
        if response.status_code >= 400:
            status_code = response.status_code
            content_type = response.headers.get("Content-Type")
            response_text = response.text
            logger.error(
                (
                    "SmartUp upstream error before JSON parse method=%s endpoint=%s "
                    "company_id=%s project_code=%s filial_id=%s status=%s content_type=%s body=%s "
                    "payload=%s"
                ),
                method,
                endpoint,
                self.settings.company_id,
                self.settings.project_code,
                self.settings.filial_id,
                status_code,
                content_type,
                _redact_sensitive_text(response_text),
                _redact_sensitive_text(json.dumps(payload, ensure_ascii=False, sort_keys=True)),
            )
            raise httpx.HTTPStatusError(
                f"{status_code} response from SmartUp for {endpoint}",
                request=response.request,
                response=response,
            )
        try:
            return response.json()
        except ValueError:
            parsed = self._parse_response_text(
                response.text,
                response.headers.get("Content-Type"),
            )
            if parsed is not None:
                return parsed
            return {
                "_raw_text": response.text,
                "_content_type": response.headers.get("Content-Type"),
            }

    @staticmethod
    def _parse_response_text(text: str, content_type: str | None) -> Any | None:
        stripped = text.strip()
        if not stripped:
            return None

        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            pass

        lowered_content_type = (content_type or "").lower()
        if "xml" in lowered_content_type or stripped.startswith("<"):
            parsed_xml = SmartUpApiClient._parse_xml_text(stripped)
            if parsed_xml is not None:
                return parsed_xml

        if any(marker in lowered_content_type for marker in ("csv", "text/plain", "tab-separated")):
            parsed_csv = SmartUpApiClient._parse_csv_text(stripped)
            if parsed_csv is not None:
                return parsed_csv

        if "\n" in stripped and "," in stripped:
            parsed_csv = SmartUpApiClient._parse_csv_text(stripped)
            if parsed_csv is not None:
                return parsed_csv

        return None

    @staticmethod
    def _parse_csv_text(text: str) -> list[dict[str, str]] | None:
        sample_lines = [line for line in text.splitlines() if line.strip()]
        if len(sample_lines) < 2:
            return None

        delimiters = (",", ";", "\t", "|")
        for delimiter in delimiters:
            try:
                reader = DictReader(StringIO(text), delimiter=delimiter)
                rows = [
                    dict(row)
                    for row in reader
                    if any((value or "").strip() for value in row.values())
                ]
            except Exception:
                continue
            if rows:
                return rows
        return None

    @staticmethod
    def _parse_xml_text(text: str) -> Any | None:
        try:
            root = ET.fromstring(text)
        except ET.ParseError:
            return None

        def convert(node: ET.Element) -> Any:
            children = list(node)
            if not children:
                return (node.text or "").strip()
            grouped: dict[str, list[Any]] = {}
            for child in children:
                grouped.setdefault(child.tag, []).append(convert(child))
            result: dict[str, Any] = {}
            for key, values in grouped.items():
                result[key] = values if len(values) > 1 else values[0]
            return result

        root_children = list(root)
        if not root_children:
            return {root.tag: (root.text or "").strip()}

        grouped_children: dict[str, list[Any]] = {}
        for child in root_children:
            grouped_children.setdefault(child.tag, []).append(convert(child))

        if len(grouped_children) == 1:
            _, values = next(iter(grouped_children.items()))
            return values if len(values) > 1 else values[0]

        return {
            key: values if len(values) > 1 else values[0]
            for key, values in grouped_children.items()
        }

    def _resolve_endpoint_path(self, endpoint: str) -> str:
        """Return the documented endpoint path unchanged.

        SmartUp requests must use the exact paths from the official collection.
        We do not rewrite paths or infer alternate routes here.
        """

        return endpoint

    def _build_url(self, endpoint: str) -> str:
        """Combine the base URL with a relative endpoint path."""

        if endpoint.startswith(("http://", "https://")):
            return endpoint
        return f"{self.settings.base_url.rstrip('/')}{endpoint}"

    def _build_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "lang_code": self.settings.lang_code,
        }
        if self.settings.company_id:
            headers["company_id"] = self.settings.company_id
        if self.settings.project_code:
            headers["project_code"] = self.settings.project_code
        if self.settings.filial_id:
            headers["filial_id"] = self.settings.filial_id
        return headers

    def _build_auth(self) -> httpx.BasicAuth | None:
        username = (self.settings.username or "").strip()
        password = (self.settings.password or "").strip()
        if not username or not password:
            return None
        return httpx.BasicAuth(username, password)

    @staticmethod
    def _validate_payload_object_count(payload: dict[str, Any]) -> None:
        object_count = SmartUpApiClient._count_payload_objects(payload)
        if object_count <= SMARTUP_MAX_OBJECTS_PER_REQUEST:
            return
        msg = (
            "SmartUp request exceeds the documented 5000 objects per request limit: "
            f"{object_count}"
        )
        raise ValueError(msg)

    @staticmethod
    def _count_payload_objects(value: Any) -> int:
        if isinstance(value, list):
            return len(value) + sum(SmartUpApiClient._count_payload_objects(item) for item in value)
        if isinstance(value, dict):
            return sum(SmartUpApiClient._count_payload_objects(item) for item in value.values())
        return 0

    def _post(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request_json("POST", endpoint, payload)


def _redact_sensitive_text(value: str) -> str:
    """Redact obvious secrets from logged SmartUp payloads and responses."""

    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return _redact_sensitive_string(value)
    return json.dumps(_redact_sensitive_value(parsed), ensure_ascii=False)


def _redact_sensitive_value(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            if _is_sensitive_key(str(key)):
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = _redact_sensitive_value(item)
        return redacted
    if isinstance(value, list):
        return [_redact_sensitive_value(item) for item in value]
    if isinstance(value, str):
        return _redact_sensitive_string(value)
    return value


def _redact_sensitive_string(value: str) -> str:
    redacted = value
    for token in (
        "Authorization",
        "authorization",
        "Cookie",
        "cookie",
        "access_token",
        "session_token",
        "id_token",
        "refresh_token",
        "password",
        "token",
    ):
        redacted = redacted.replace(token, "[REDACTED]")
    return redacted


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(
        marker in lowered
        for marker in (
            "authorization",
            "cookie",
            "access_token",
            "session_token",
            "id_token",
            "refresh_token",
            "password",
            "token",
        )
    )


def _make_endpoint_method(spec: SmartUpEndpointSpec):
    def _method(self: SmartUpApiClient, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request_json(spec.http_method, spec.path, payload)

    _method.__name__ = spec.method_name
    _method.__qualname__ = f"SmartUpApiClient.{spec.method_name}"
    _method.__doc__ = f"Call SmartUp endpoint {spec.name}."
    return _method


def _bind_public_endpoint_methods() -> None:
    for spec in SMARTUP_PUBLIC_ENDPOINTS_V1:
        setattr(SmartUpApiClient, spec.method_name, _make_endpoint_method(spec))


_bind_public_endpoint_methods()

assert len(SMARTUP_PUBLIC_ENDPOINTS_V1) == 62
