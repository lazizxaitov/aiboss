"""Validation helpers for Phase 3C provider-backed AI analytics."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from app.core.ai_analytics.models import (
    AIInsightCard,
    AIInsightMetric,
    AIProviderResponse,
    AISignal,
    ExecutiveBusinessBrief,
)


def validate_provider_response(
    *,
    deterministic_signals: list[AISignal],
    deterministic_insights: list[AIInsightCard],
    provider_response: AIProviderResponse,
) -> tuple[list[AIInsightCard], list[str]]:
    """Validate provider rewrites against deterministic signal/evidence boundaries."""

    signal_by_id = {signal.signal_id: signal for signal in deterministic_signals}
    deterministic_by_entity = {
        (insight.entity_type, insight.entity_id): insight for insight in deterministic_insights
    }
    validated: list[AIInsightCard] = []
    rejected: list[str] = []

    for index, rewrite in enumerate(provider_response.insights, start=1):
        signal = signal_by_id.get(rewrite.signal_id)
        if signal is None:
            rejected.append(f"insight_{index}: UNKNOWN_SIGNAL_ID")
            continue
        if rewrite.entity_type != signal.entity_type or rewrite.entity_id != signal.entity_id:
            rejected.append(f"insight_{index}: ENTITY_MISMATCH")
            continue
        if rewrite.organization_ids:
            allowed_orgs = {signal.organization_id} if signal.organization_id is not None else set()
            if any(org_id not in allowed_orgs for org_id in rewrite.organization_ids):
                rejected.append(f"insight_{index}: ORGANIZATION_MISMATCH")
                continue
        if not _numeric_claims_are_valid(rewrite.numeric_claims, signal):
            rejected.append(f"insight_{index}: NUMERIC_MISMATCH")
            continue
        if not _finance_semantics_are_valid(rewrite):
            rejected.append(f"insight_{index}: FINANCE_SEMANTICS_VIOLATION")
            continue
        if not _causality_is_safe(rewrite):
            rejected.append(f"insight_{index}: UNSUPPORTED_CAUSALITY")
            continue

        deterministic = deterministic_by_entity.get((rewrite.entity_type, rewrite.entity_id))
        validated.append(
            AIInsightCard(
                id=deterministic.id if deterministic else rewrite.signal_id,
                type=deterministic.type if deterministic else "AI",
                severity=deterministic.severity if deterministic else signal.severity.value.lower(),
                priority=index,
                title=rewrite.title,
                summary=rewrite.summary,
                metrics=[
                    AIInsightMetric(
                        label=label,
                        current=_matching_numeric_claim(label, rewrite.numeric_claims),
                    )
                    for label in rewrite.metric_labels[:3]
                ],
                evidence=[
                    rewrite.fact_statement,
                    rewrite.interpretation,
                    *rewrite.limitations[:2],
                ],
                recommendation=rewrite.recommended_action,
                widget_type=deterministic.widget_type if deterministic else "ai_insight",
                entity_type=rewrite.entity_type,
                entity_id=rewrite.entity_id,
                organization_ids=rewrite.organization_ids,
                period=signal.period,
            )
        )
    return validated, rejected


def build_provider_brief(
    *,
    provider_response: AIProviderResponse,
    deterministic_brief: ExecutiveBusinessBrief,
    validated_insights: list[AIInsightCard],
) -> ExecutiveBusinessBrief:
    """Build provider-assisted brief without losing deterministic safety boundaries."""

    return ExecutiveBusinessBrief(
        headline=provider_response.headline or deterministic_brief.headline,
        business_status=provider_response.executive_summary or deterministic_brief.business_status,
        key_numbers=deterministic_brief.key_numbers,
        top_insights=validated_insights[:4] or deterministic_brief.top_insights,
        risks=[item for item in validated_insights if item.type == "RISK"][:4]
        or deterministic_brief.risks,
        opportunities=[item for item in validated_insights if item.type == "OPPORTUNITY"][:4]
        or deterministic_brief.opportunities,
        organization_watch=[item for item in validated_insights if item.type == "ORGANIZATION"][:4]
        or deterministic_brief.organization_watch,
        data_warnings=[item for item in validated_insights if item.type == "DATA_QUALITY"][:4]
        or deterministic_brief.data_warnings,
    )


def _numeric_claims_are_valid(numeric_claims: list[str], signal: AISignal) -> bool:
    allowed_values: set[Decimal] = set()
    for value in (
        signal.current_value,
        signal.previous_value,
        signal.absolute_change,
        signal.percentage_change,
    ):
        if value is not None:
            allowed_values.add(value.quantize(Decimal("0.01")))

    for raw in numeric_claims:
        parsed = _parse_decimal(raw)
        if parsed is None:
            continue
        normalized = parsed.quantize(Decimal("0.01"))
        if normalized not in allowed_values:
            return False
    return True


def _finance_semantics_are_valid(rewrite) -> bool:  # type: ignore[no-untyped-def]
    text = " ".join(
        [
            rewrite.title,
            rewrite.summary,
            rewrite.fact_statement,
            rewrite.interpretation,
            rewrite.recommended_action,
            *rewrite.limitations,
        ]
    ).lower()
    forbidden = [
        "expenses are zero",
        "cash out = 0",
        "cash out is 0",
        "profit is",
        "net cash flow is",
        "refund received",
    ]
    return not any(fragment in text for fragment in forbidden)


def _causality_is_safe(rewrite) -> bool:  # type: ignore[no-untyped-def]
    combined = " ".join([rewrite.summary, rewrite.interpretation]).lower()
    unsafe = ["because", "из-за", "потому что", "caused by"]
    return not any(marker in combined for marker in unsafe)


def _matching_numeric_claim(label: str, numeric_claims: list[str]) -> str | None:
    for claim in numeric_claims:
        if claim:
            return claim
    return None


def _parse_decimal(value: str | None) -> Decimal | None:
    if value in {None, ""}:
        return None
    try:
        normalized = value.replace("%", "").replace(",", ".").strip()
        return Decimal(normalized)
    except (AttributeError, InvalidOperation):
        return None
