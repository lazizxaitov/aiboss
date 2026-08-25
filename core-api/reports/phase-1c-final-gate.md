# PHASE 1C — Final Identity & Provenance Gate

Date: 2026-08-11
Status: Completed
Phase 2 started: No

## Customer Identity Audit

Actual source identity fields discovered in RAW:

| Dataset | Source field | Count |
| --- | --- | ---: |
| sales | `person_id` | 214 |
| payments | `client_id` | 156 |
| returns | `person_id` | 2 |
| visits | `visit_headers[].person_id` | 884 |

Summary:

- Raw customer references: `1256`
- Unique source identities, dataset-scoped: `882`
- Unique source identities, organization-scoped: `626`
- Canonical customers: `613`

Conclusion:

- Customer identity is based on real SmartUp IDs, not on customer names.
- Names are labels only, not deduplication keys.

## Cross-Dataset Customer Deduplication

- Duplicate canonical keys `(organization_id, source_external_id)`: `0`
- Same-id / different-name cases: `0`
- Same-name / different-id cases: `1`
  - `Администрация`: `"HOMEMARKETS" MCHJ` -> `15575761`, `18636082`
- Cross-dataset merges:
  - present in 2 datasets and resolved to one canonical customer: `144`
  - present in 3 datasets and resolved to one canonical customer: `56`

Conclusion:

- Deduplication by source identity works.
- Merge by name is not happening.
- Same name with different IDs remains separate, which is correct.

## Customer Organization Semantics

- Shared identities across organizations: `313`

Examples:

- `15575761` -> `Администрация`, `SAMO SERVIS`
- `20288877` -> `Администрация`, `MODAILY QOQON VA FARGONA`

Conclusion:

- The same SmartUp identity can appear in multiple organizations.
- Canonical customer identity must remain organization-local.
- Safe identity key: `organization_id + source_external_id`

## Customer Source Coverage by Organization

| Organization | Canonical | From Sales | From Visits | From Payments | From Returns |
| --- | ---: | ---: | ---: | ---: | ---: |
| Администрация | 300 | 107 | 442 | 78 | 1 |
| MODAILY | 294 | 95 | 432 | 68 | 0 |
| MODAILY QOQON VA FARGONA | 15 | 10 | 10 | 8 | 0 |
| SAMO SERVIS | 4 | 2 | 0 | 2 | 1 |
| MODAILY ANDIJON | 0 | 0 | 0 | 0 | 0 |
| MODAILY NAMANGAN | 0 | 0 | 0 | 0 | 0 |
| MODAILY SURXANDARYO | 0 | 0 | 0 | 0 | 0 |

Additional note:

- `13` raw customer identities were not materialized into canonical customers.
- All `13` belong only to `Администрация`, only to `sales`.

## Legacy Provenance Audit

Legacy definition:

- `request_filial_id IS NULL`

Observed classification:

- `UNSAFE`: `0`
- `UNRESOLVED`: `0`
- `PARTIAL_PROVENANCE`: present
- `SAFE_LEGACY`: not assigned under strict rule because request filial is absent on the row itself

Deterministic attribution evidence:

- all audited legacy transaction rows have `organization_id`
- all audited legacy transaction rows have `batch_id`
- all audited legacy transaction rows have `migration_batches.organization_id = smartup_raw_records.organization_id`

Transaction lineage summary:

| Entity | Total | With Org | With Batch | Batch Org Match | Batch Org Diff |
| --- | ---: | ---: | ---: | ---: | ---: |
| sales | 217 | 217 | 217 | 217 | 0 |
| payments | 159 | 159 | 159 | 159 | 0 |
| visits | 888 | 888 | 888 | 888 | 0 |
| inventory_balances | 11562 | 11562 | 11562 | 11562 | 0 |
| bank_operations | 166 | 166 | 166 | 166 | 0 |
| write_offs | 49 | 49 | 49 | 49 | 0 |
| purchases | 16 | 16 | 16 | 16 | 0 |
| warehouse_receipts | 16 | 16 | 16 | 16 | 0 |
| returns | 7 | 7 | 7 | 7 | 0 |
| return_to_suppliers | 7 | 7 | 7 | 7 | 0 |
| internal_movements | 7 | 7 | 7 | 7 | 0 |
| cross_organizational_movements | 9 | 9 | 9 | 9 | 0 |
| stocktakings | 7 | 7 | 7 | 7 | 0 |

Conclusion:

- Legacy provenance is partial, not verified.
- Organization attribution is still deterministic through immutable row + batch lineage.
- No cross-organization leakage was found in legacy transaction rows.

## Price Semantics

Accepted limitation:

- `canonical_product_prices` verified rows: `5`

This does not block the next phase as long as the system preserves these as separate concepts:

- Master Price
- Transaction Sale Price
- Purchase Cost
- Return Price
- Inventory Cost

## Customer Master Limitation

Accepted limitation:

- SmartUp customer master exports may be empty.

Reference-derived customers remain acceptable when:

- source identity is stable
- organization attribution is safe
- provenance exists

Quality remains `PARTIAL`.

If real customer master data appears later, it must enrich the same canonical customer and must not create duplicates.

## Idempotency

Phase 1 materialization was re-run on the same immutable RAW set.

Result:

- canonical counts stayed stable
- no duplicate canonical rows were created

## Cross-Organization Contamination

Canonical Phase 1 tables checked:

- `canonical_customer_groups`
- `canonical_customers`
- `canonical_product_categories`
- `canonical_products`
- `canonical_warehouses`
- `canonical_price_types`
- `canonical_product_prices`
- `canonical_sales_reps`
- `canonical_working_zones`

Result:

- Cross-org contamination count: `0`

## Final Gate

- CUSTOMER IDENTITY: `PASS`
- CUSTOMER DEDUPLICATION: `PASS`
- CUSTOMER ORGANIZATION ISOLATION: `PASS`
- LEGACY PROVENANCE: `PASS`
- PHASE 2 TRANSACTION SAFETY: `PASS`
- IDEMPOTENCY: `PASS`
- CROSS-ORG CONTAMINATION: `0`

## Phase 2 Ready

`YES`

## Non-Blocking Caveats

- `13` missing customer identities remain only in `Администрация` and only in `sales`
- legacy transaction rows are mostly `PARTIAL_PROVENANCE`, not `VERIFIED`
- master customer export is still optional
- master product price list coverage remains low and does not block transaction canonicalization

## Actual Data-Integrity Blockers

None
