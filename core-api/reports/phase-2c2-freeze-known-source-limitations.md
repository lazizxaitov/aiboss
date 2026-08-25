# PHASE 2C.2 — FREEZE KNOWN SOURCE LIMITATIONS

Date: 2026-08-12

## Scope

Applied only to Phase 2C canonical inventory / warehouse foundation.

No heuristic repair was introduced.
No SmartUp RAW was deleted or modified.
No UI, AI, or unrelated canonical domains were changed.

## Implemented Rules

### 1. Quality status freeze

- Purchase and warehouse receipt line items with no deterministic product identity are now explicitly marked:
  - `data_quality_status = unresolved`
- Purchase and warehouse receipt headers that remain document-valid but have no deterministic warehouse identity are now marked:
  - `data_quality_status = partial`
- Such rows are no longer treated as `verified`.

### 2. No fake zero / no fake placeholders

- Missing product linkage is preserved as `NULL`
- Missing warehouse linkage is preserved as `NULL`
- No `Unknown Product`
- No `Unknown Warehouse`
- No artificial quantity fallback
- Rows expose:
  - `metadata.unresolved_reason = UNRESOLVED_SOURCE_REFERENCE`

### 3. Source limitation registry

Added normalization issue category:

- `SMARTUP_SOURCE_IDENTIFIER_MISSING`

Captured through `normalization_issues` with:

- `entity_type = purchases | warehouse_receipts`
- `organization_id`
- `raw_record_id`
- `missing_identity_type = PRODUCT | WAREHOUSE`
- `available_source_fields`

### 4. Coverage metadata for future analytics/UI

Added coverage metadata to canonical purchase / receipt headers and line items:

- `product_linkage_coverage`
- `warehouse_linkage_coverage`
- `document_amount_coverage`

These are stored in canonical row `metadata.coverage`.

## Effective Analytics Policy

### Allowed for document-level analytics

Purchases / receipts may still contribute to:

- document count
- supplier
- date
- currency
- total amount

when those fields are independently verified from source RAW.

### Restricted for product / warehouse analytics

The following must use only deterministically linked rows:

- purchase quantity by product
- purchase cost by product
- warehouse movement by SKU
- stock movement by product
- warehouse-level product analytics

Unresolved rows are intentionally excluded by default from SKU / warehouse analytics.

## Preserved Source Semantics

- `serial_number` remains raw source metadata only
- It is **not** treated as canonical product identity
- This keeps future equipment / asset canonicalization open without polluting inventory product identity

## Live Limitation Baseline

These source limitations remain accepted and frozen:

- purchase items total: `162`
- purchase items linked to product: `20`
- purchase items unresolved: `142`
- warehouse receipt items total: `162`
- warehouse receipt items linked to product: `20`
- warehouse receipt items unresolved: `142`
- receipt -> purchase item linkage: `162 / 162`
- purchase warehouse linkage: `4 / 14`
- receipt warehouse linkage: `4 / 14`

Interpretation:

- unresolved 142 purchase items have no deterministic product identity in immutable RAW
- unresolved 142 receipt items are unresolved for the same source reason or because linked purchase item remains unresolved
- 10 / 14 purchase and receipt headers have no deterministic warehouse identity in immutable RAW

## Validation

Targeted tests:

```bash
uv run pytest tests/test_canonical_v2.py -q
```

Result:

```text
8 passed in 0.30s
```

## Final Status

### PHASE 2C

PASS WITH KNOWN SOURCE LIMITATIONS

### READY FOR PHASE 2D

YES

## Explicit Non-Goals

This phase did **not** attempt to:

- invent missing product links
- invent missing warehouse links
- remap `serial_number` into products
- backfill missing source identifiers heuristically
- change unrelated exporters or dashboard logic

