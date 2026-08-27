# AI Business OS Architecture

## Core Principle

AI Business OS is not a conventional BI/ERP product with an AI chat layered
on top. The system separates authoritative facts and safe execution from
analytical intelligence:

> **Code provides facts and safe access. AI decides what to investigate and what it means.**

## Responsibilities

### Code and Data Layer

- RAW, Canonical, and Core services are the source of business facts.
- Synchronize and normalize data through the existing pipelines.
- Enforce authentication, permissions, organization scope, and query limits.
- Expose business data through the read-only Business Data Query Layer.
- Execute validated queries and exact mathematical operations.
- Persist analysis results, findings, alerts, and dashboard plans.

The model must never receive unrestricted RAW or SQL access, write access to
business data, provider credentials, or system access.

### AI Layer

- Decide which facts need to be checked.
- Plan and perform multi-step analysis through approved data tools.
- Choose relevant periods, dimensions, and comparisons.
- Investigate patterns, risks, anomalies, and opportunities.
- Deepen the investigation when the evidence requires it.
- Produce structured findings, warnings, recommendations, and dynamic widget plans.

The AI layer must ground every factual claim in returned Canonical/Core data.
Missing data must remain explicitly unavailable; it must not be replaced with
invented values or explanations.

## Analytics Routing

Business Analytics AI is selected only through:

`Settings -> AI Roles -> Business Analytics -> AITaskRouter`

Automatic analytics must use the current `business_analytics` role assignment
and its configured fallback. A change to the role assignment must affect the
next analysis run without requiring a restart. The conversational model may
continue the user dialogue, but complex business analysis is executed by the
`business_analytics` role.

## Automatic Analytics Flow

```text
SmartUp sync
  -> Canonical/Core updated
  -> Business Analytics AI selected by AITaskRouter
  -> AI chooses approved read-only queries
  -> structured findings, alerts, recommendations, and widget plan
  -> persisted and presented in Dashboard/Telegram
```

The scheduler/orchestrator controls when analysis runs. It must not replace
the AI analyst with a hardcoded scenario or a fixed provider/model.

## Prohibited Analytics Design

Do not make business intelligence depend primarily on question-specific rules
such as:

- `if sales_drop > X`
- `if "manager" in question`
- `if "product" in question`

Rules are allowed for infrastructure, validation, permissions, safety, and
resource limits. They are not a substitute for the Business Analytics AI's
investigation and reasoning.

## Change Constraint

Every future AI feature must preserve this boundary:

1. Code supplies authoritative facts and safe, scoped, read-only access.
2. AI chooses what to inspect and interprets the returned evidence.
3. Provider/model selection comes from the configured role router.
4. No implementation may move unrestricted data access or analytical ownership
   into application code merely to simplify an AI workflow.

If a proposed implementation conflicts with this constraint, redesign it before
implementation rather than adding another hardcoded analytics path.
