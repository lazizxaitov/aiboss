from __future__ import annotations

from unittest.mock import Mock

from app.core.business_data_query import BusinessDataQueryService


def test_generic_sales_query_delegates_validated_dimensions_and_metrics():
    tools = Mock()
    tools.aggregate_sales.return_value = {"available": True, "rows": []}

    result = BusinessDataQueryService(tools).query(
        dataset="sales",
        period="current_week",
        dimensions=["manager"],
        metrics=["revenue", "orders"],
        limit=5,
    )

    assert result["available"] is True
    tools.aggregate_sales.assert_called_once()
    call = tools.aggregate_sales.call_args.kwargs
    assert call["group_by"] == "manager"
    assert call["metrics"] == ["revenue", "orders"]
    assert call["limit"] == 5


def test_generic_query_rejects_unknown_dataset_or_dimension_without_execution():
    tools = Mock()
    service = BusinessDataQueryService(tools)

    dataset_result = service.query(dataset="users")
    dimension_result = service.query(dataset="sales", dimensions=["password"])

    assert dataset_result["available"] is False
    assert dimension_result["available"] is False
    tools.aggregate_sales.assert_not_called()
