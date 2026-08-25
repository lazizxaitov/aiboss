"""Tests for the public SmartUp API client surface."""

from types import SimpleNamespace

import httpx
import pytest

from app.integrations.smartup import (
    SMARTUP_PUBLIC_ENDPOINTS_V1,
    SmartUpApiClient,
    SmartUpSettings,
)


def test_smartup_public_endpoint_registry_has_expected_size() -> None:
    assert len(SMARTUP_PUBLIC_ENDPOINTS_V1) == 62
    assert len({spec.method_name for spec in SMARTUP_PUBLIC_ENDPOINTS_V1}) == 62


def test_smartup_public_methods_are_bound() -> None:
    assert hasattr(SmartUpApiClient, "export_order")
    assert hasattr(SmartUpApiClient, "export_inventory_balance")


def test_smartup_public_methods_call_the_expected_paths(monkeypatch) -> None:
    client = SmartUpApiClient(settings=SmartUpSettings())
    calls: list[tuple[str, str, dict[str, object]]] = []

    def fake_request_json(
        self, method: str, endpoint: str, payload: dict[str, object]
    ) -> dict[str, object]:
        calls.append((method, endpoint, payload))
        return {"ok": True}

    monkeypatch.setattr(SmartUpApiClient, "_request_json", fake_request_json)

    order_result = client.export_order({"page": 1})
    inventory_result = client.export_inventory_balance({"date": "2026-07-28"})

    assert order_result == {"ok": True}
    assert inventory_result == {"ok": True}
    assert calls == [
        ("POST", "/b/trade/txs/tdeal/order$export", {"page": 1}),
        ("POST", "/b/anor/mxsx/mkw/balance$export", {"date": "2026-07-28"}),
    ]


def test_smartup_request_uses_env_base_url_and_required_headers(monkeypatch) -> None:
    captured = {}

    class FakeResponse:
        def __init__(self, request, status_code=404, text="Forbidden") -> None:
            self.request = request
            self.status_code = status_code
            self.text = text

        @property
        def is_success(self) -> bool:
            return 200 <= self.status_code < 300

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            captured["client_kwargs"] = kwargs

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def request(self, method, url, json, headers):  # noqa: ANN001
            captured["method"] = method
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers
            request = SimpleNamespace(url=url)
            return FakeResponse(request=request)

    monkeypatch.setattr("httpx.Client", FakeClient)

    client = SmartUpApiClient(
        settings=SmartUpSettings(
            base_url="https://smartup.online",
            project_code="trade",
            filial_id="86401",
            username="demo",
            password="secret",
        ),
    )

    response = client.request_response("POST", "/b/anor/mxsx/mr/legal_person$export", {})

    assert response.status_code == 404
    assert captured["method"] == "POST"
    assert captured["url"] == "https://smartup.online/b/anor/mxsx/mr/legal_person$export"
    assert captured["client_kwargs"]["auth"] is not None
    assert captured["headers"] == {
        "Content-Type": "application/json",
        "lang_code": "ru",
        "company_id": "11300",
        "project_code": "trade",
        "filial_id": "86401",
    }


def test_smartup_request_json_falls_back_to_raw_text(monkeypatch) -> None:
    class FakeResponse:
        def __init__(self) -> None:
            self.status_code = 200
            self.text = "<xml>ok</xml>"
            self.headers = {"Content-Type": "text/xml"}

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            raise ValueError("not json")

    monkeypatch.setattr(
        SmartUpApiClient,
        "request_response",
        lambda self, method, endpoint, payload: FakeResponse(),  # noqa: ARG005
    )

    client = SmartUpApiClient(settings=SmartUpSettings())
    response = client._request_json("POST", "/dummy", {})

    assert response == {"xml": "ok"}


def test_smartup_request_json_raises_status_error_after_reading_body(monkeypatch) -> None:
    class FakeResponse:
        def __init__(self) -> None:
            self.status_code = 400
            self.text = "Bad Request"
            self.headers = {"Content-Type": "text/plain"}
            self.request = httpx.Request("POST", "https://smartup.online/dummy")

        def json(self) -> dict[str, object]:
            raise ValueError("not json")

    monkeypatch.setattr(
        SmartUpApiClient,
        "request_response",
        lambda self, method, endpoint, payload: FakeResponse(),  # noqa: ARG005
    )

    client = SmartUpApiClient(settings=SmartUpSettings())

    with pytest.raises(httpx.HTTPStatusError) as excinfo:
        client._request_json("POST", "/dummy", {})

    assert excinfo.value.response.status_code == 400
    assert excinfo.value.response.text == "Bad Request"


def test_smartup_request_rejects_payloads_over_5000_objects(monkeypatch) -> None:
    client = SmartUpApiClient(settings=SmartUpSettings())

    monkeypatch.setattr("httpx.Client", lambda *args, **kwargs: None)

    payload = {"items": [{"id": index} for index in range(5001)]}

    try:
        client.request_response("POST", "/dummy", payload)
    except ValueError as exc:
        assert "5000 objects" in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("Expected SmartUp request size validation to fail")
