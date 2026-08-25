"""Strict structured AI input contract builder."""

from __future__ import annotations

from app.core.ai_analytics.models import AIAnalyticsInputContext, AIAnalyticsInputContract
from app.core.analytics.models import AnalyticsBusinessSnapshot


def build_input_contract(snapshot: AnalyticsBusinessSnapshot) -> AIAnalyticsInputContract:
    """Project canonical analytics snapshot into a strict AI input payload."""

    organization_ids = list(snapshot.query.organization_ids)
    if (
        snapshot.query.organization_id is not None
        and snapshot.query.organization_id not in organization_ids
    ):
        organization_ids.append(snapshot.query.organization_id)

    return AIAnalyticsInputContract(
        context=AIAnalyticsInputContext(
            organization_ids=organization_ids,
            period=snapshot.period,
            comparison_period={
                "previous_start": snapshot.period.previous_start,
                "previous_end": snapshot.period.previous_end,
            },
        ),
        executive={
            "business": snapshot.business.model_dump(mode="json"),
            "validation_notes": snapshot.validation_notes,
        },
        sales={
            "top_products": [item.model_dump(mode="json") for item in snapshot.top_products],
            "top_sales_reps": [item.model_dump(mode="json") for item in snapshot.top_sales_reps],
        },
        products={
            "top": [item.model_dump(mode="json") for item in snapshot.top_products],
            "growing": [item.model_dump(mode="json") for item in snapshot.growing_products],
            "declining": [item.model_dump(mode="json") for item in snapshot.declining_products],
            "slow": [item.model_dump(mode="json") for item in snapshot.slow_products],
            "low_stock": [item.model_dump(mode="json") for item in snapshot.low_stock_products],
            "overstock": [item.model_dump(mode="json") for item in snapshot.overstock_products],
            "stockout_risk": [
                item.model_dump(mode="json") for item in snapshot.stockout_risk_products
            ],
        },
        customers={
            "top": [item.model_dump(mode="json") for item in snapshot.top_customers],
            "at_risk": [item.model_dump(mode="json") for item in snapshot.at_risk_customers],
            "inactive": [item.model_dump(mode="json") for item in snapshot.lost_customers],
        },
        inventory={
            "transfer_opportunities": [item.model_dump(mode="json") for item in snapshot.inventory],
        },
        organizations={
            "comparison": [
                item.model_dump(mode="json") for item in snapshot.organization_comparison
            ],
        },
        payments={
            "verified_cash_in": snapshot.business.verified_cash_in.model_dump(mode="json"),
            "payments_received": snapshot.business.payments_received.model_dump(mode="json"),
        },
        returns={
            "customer_return_value": snapshot.business.customer_return_value.model_dump(
                mode="json"
            ),
            "items": [item.model_dump(mode="json") for item in snapshot.returns],
        },
        visits={
            "visits": snapshot.business.visits.model_dump(mode="json"),
            "items": [item.model_dump(mode="json") for item in snapshot.visits],
        },
        finance={
            "verified_cash_out": snapshot.business.verified_cash_out.model_dump(mode="json"),
            "expenses": snapshot.business.expenses.model_dump(mode="json"),
            "cash_flow": snapshot.business.cash_flow.model_dump(mode="json"),
            "items": [item.model_dump(mode="json") for item in snapshot.finance],
        },
        data_quality=snapshot.data_quality.model_dump(mode="json"),
    )
