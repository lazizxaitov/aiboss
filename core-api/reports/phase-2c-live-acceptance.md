# PHASE 2C LIVE ACCEPTANCE

Date: 2026-08-12  
Source: immutable SmartUp RAW already stored in PostgreSQL  
SmartUp re-download: no  
Scope: canonical inventory / warehouse transaction layer only

## Runtime

- Canonical tests: `6 passed`
- Live Phase 2C materialization on PostgreSQL: `41.271s`
- Second Phase 2C run for idempotency: `0 duplicates created`

## INVENTORY BALANCES

- RAW materialized rows: `11,562`
- Trusted rows materialized: `11,562`
- Canonical rows: `11,562`
- VERIFIED: `11,562`
- PARTIAL: `0`
- UNRESOLVED: `0`
- UNSAFE excluded: `0`
- Products linked: `11,562 / 11,562`
- Warehouses linked: `11,562 / 11,562`
- Grain: `organization + warehouse + product + batch_number + card_code + serial_number + snapshot_date`
- Current-stock strategy:
  - do not sum all historical balance exports together
  - take latest snapshot per grain
  - then aggregate by organization / warehouse / product

## PURCHASES

- Canonical documents: `14`
- Canonical items: `162`
- VERIFIED documents: `14`
- Verified item rows: `162`
- Unresolved wrapper/raw rows: `2`
- Supplier linkage:
  - supplier code preserved when present
  - no separate canonical supplier table yet
- Product linkage: `20 / 162`
- Warehouse linkage on headers: `4 / 14`
- Currency:
  - `860 -> UZS` normalized correctly
- Amount semantics:
  - preserved as purchase unit cost / purchase line amount
  - not treated as expense

## WAREHOUSE RECEIPTS

- Canonical documents: `14`
- Canonical items: `162`
- VERIFIED documents: `14`
- Unresolved wrapper/raw rows: `2`
- Product linkage: `20 / 162`
- Warehouse linkage on headers: `4 / 14`
- Purchase linkage:
  - `purchase_id` and `purchase_item_id` preserved on receipt items when present
- Semantics:
  - receipts stay separate from purchases
  - no forced merge

## WRITEOFFS

- Canonical documents: `44`
- Canonical items: `158`
- VERIFIED documents: `44`
- Unresolved wrapper/raw rows: `5`
- Product linkage: `158 / 158`
- Warehouse linkage: `44 / 44`
- Quantity preserved: yes
- Amount preserved: yes
- Currency normalized: `UZS`

## SUPPLIER RETURNS

- RAW wrapper responses present: `7`
- Materializable business rows discovered: `0`
- Canonical documents: `0`
- Canonical items: `0`
- Interpretation:
  - current immutable RAW contains only empty wrapper responses
  - no business facts were fabricated

## STOCKTAKINGS

- RAW wrapper responses present: `7`
- Materializable business rows discovered: `0`
- Canonical documents: `0`
- Canonical items: `0`

## INTERNAL MOVEMENTS

- RAW wrapper responses present: `7`
- Materializable business rows discovered: `0`
- Canonical documents: `0`
- Canonical items: `0`

## CROSS-ORGANIZATION MOVEMENTS

- Canonical documents: `6`
- Canonical items: `57`
- VERIFIED documents: `6`
- Unresolved wrapper/raw rows: `3`
- Product linkage: `57 / 57`
- Warehouse linkage on request-side document warehouse: `4 / 6`
- Source / destination organization evidence:
  - source and destination filial codes are preserved when present in RAW
  - some current rows still have missing `from_filial_code` / `to_filial_code`
- Semantics:
  - preserved as transfer documents
  - not treated as sale / purchase / contamination

## ORGANIZATION BREAKDOWN

### canonical_inventory_balances

- MODAILY: `2,232`
- MODAILY ANDIJON: `88`
- MODAILY NAMANGAN: `80`
- MODAILY QOQON VA FARGONA: `178`
- MODAILY SURXANDARYO: `88`
- SAMO SERVIS: `8,896`
- Администрация: `0`

### canonical_purchases

- Администрация: `7`
- MODAILY: `2`
- MODAILY ANDIJON: `1`
- MODAILY NAMANGAN: `2`
- MODAILY QOQON VA FARGONA: `2`

### canonical_warehouse_receipts

- Администрация: `7`
- MODAILY: `2`
- MODAILY ANDIJON: `1`
- MODAILY NAMANGAN: `2`
- MODAILY QOQON VA FARGONA: `2`

### canonical_writeoffs

- Администрация: `22`
- MODAILY: `22`

### canonical_cross_org_movements

- Администрация: `2`
- MODAILY: `2`
- MODAILY ANDIJON: `1`
- MODAILY QOQON VA FARGONA: `1`

## CURRENT STOCK PREVIEW

Latest valid snapshot per balance grain:

- MODAILY
  - rows: `279`
  - unique products: `13`
  - warehouses: `1`
  - total quantity: `46,571`
  - zero-stock rows: `0`
  - negative-stock rows: `0`
  - valuation preview: `46,571,000 UZS`

- MODAILY ANDIJON
  - rows: `11`
  - unique products: `11`
  - warehouses: `0`
  - total quantity: `445`
  - valuation preview: `59,120,800 UZS`

- MODAILY NAMANGAN
  - rows: `10`
  - unique products: `10`
  - warehouses: `0`
  - total quantity: `387`
  - valuation preview: `52,569,920 UZS`

- MODAILY QOQON VA FARGONA
  - rows: `31`
  - unique products: `11`
  - warehouses: `0`
  - total quantity: `783`
  - valuation preview: `109,564,960 UZS`

- MODAILY SURXANDARYO
  - rows: `11`
  - unique products: `11`
  - warehouses: `0`
  - total quantity: `55`
  - valuation preview: `8,087,325 UZS`

- SAMO SERVIS
  - rows: `1,112`
  - unique products: `155`
  - warehouses: `0`
  - total quantity: `137,387`
  - valuation preview: `137,891,189.2 UZS`

## INVENTORY VALUATION

Status: `PARTIAL`

Reason:

- valuation can be estimated from `input_price * quantity` for balance rows where `input_price` exists
- this is inventory-cost evidence
- this is not yet a fully audited accounting valuation model across all warehouse datasets

## BUSINESS READABLE EXAMPLES

### Inventory balances

- MODAILY · 2026-08-04 · warehouse `123` · product `935` · qty `13,972` · input price `1,000` · valuation `13,972,000`
- MODAILY · 2026-08-05 · warehouse `123` · product `935` · qty `13,861` · input price `1,000` · valuation `13,861,000`
- MODAILY · 2026-08-06 · warehouse `123` · product `935` · qty `13,729` · input price `1,000` · valuation `13,729,000`
- MODAILY · 2026-08-07 · warehouse `123` · product `935` · qty `13,688` · input price `1,000` · valuation `13,688,000`
- MODAILY · 2026-08-09 · warehouse `123` · product `935` · qty `13,639` · input price `1,000` · valuation `13,639,000`

### Purchases

- MODAILY NAMANGAN · purchase `0000000003` · items `4` · total qty `4` · currency `UZS`
- MODAILY ANDIJON · purchase `0000000003` · items `10` · total qty `10` · currency `UZS`
- Администрация · purchase `0000000003` · items `4` · total qty `4` · currency `UZS`
- Администрация · purchase `0000000003` · items `10` · total qty `10` · currency `UZS`
- Администрация · purchase `0000000004` · items `3` · total qty `3` · currency `UZS`

### Warehouse receipts

- MODAILY NAMANGAN · receipt `0000000003` · items `4` · total qty `4`
- MODAILY ANDIJON · receipt `0000000003` · items `10` · total qty `10`
- Администрация · receipt `0000000003` · items `4` · total qty `4`
- Администрация · receipt `0000000003` · items `10` · total qty `10`
- Администрация · receipt `0000000004` · items `3` · total qty `3`

### Writeoffs

- MODAILY · writeoff `0000000491` · warehouse `123` · items `1` · qty `5` · amount `5,000 UZS`
- Администрация · writeoff `0000000491` · warehouse `123` · items `1` · qty `5` · amount `5,000 UZS`
- Администрация · writeoff `0000000492` · warehouse `123` · items `2` · qty `27` · amount `27,000 UZS`
- MODAILY · writeoff `0000000492` · warehouse `123` · items `2` · qty `27` · amount `27,000 UZS`
- Администрация · writeoff `0000000489` · warehouse `123` · items `12` · qty `80` · amount `80,000 UZS`

### Cross-organization movements

- Администрация · movement `1873` · source warehouse `123` · items `9` · qty `140` · amount `17,702,400 UZS`
- MODAILY ANDIJON · movement `1873` · source warehouse `123` · items `9` · qty `140` · amount `17,702,400 UZS`
- MODAILY · movement `1873` · source warehouse `123` · items `9` · qty `140` · amount `17,702,400 UZS`
- Администрация · movement `1943` · source warehouse `123` · items `10` · qty `450` · amount `65,617,600 UZS`
- MODAILY QOQON VA FARGONA · movement `1943` · source warehouse `123` · items `10` · qty `450` · amount `65,617,600 UZS`

## PROVENANCE

Sample canonical → RAW proof is present for:

- `canonical_inventory_balances`
- `canonical_purchases`
- `canonical_warehouse_receipts`
- `canonical_writeoffs`
- `canonical_cross_org_movements`

Observed provenance issue:

- these current RAW rows are legacy imports
- `request_filial_id` and `response_filial_id` are often `NULL` in the stored raw rows for warehouse datasets
- canonical rows still retain `source_raw_record_id` and endpoint provenance
- therefore provenance is present but not fully request-context-complete

Status: `PARTIAL`

## ORGANIZATION ISOLATION

Cross-organization contamination checks on canonical tables:

- `canonical_inventory_balances`: `0`
- `canonical_purchases`: `0`
- `canonical_purchase_items`: `0`
- `canonical_warehouse_receipts`: `0`
- `canonical_warehouse_receipt_items`: `0`
- `canonical_writeoffs`: `0`
- `canonical_writeoff_items`: `0`
- `canonical_cross_org_movements`: `0`
- `canonical_cross_org_movement_items`: `0`

Interpretation:

- no canonical row is currently stored under a different organization than its canonical record context
- cross-org movement rows remain explicit movement facts, not contamination

Status: `PASS`

## QUANTITY SEMANTICS

Status: `PASS`

Preserved separately:

- balance quantity
- purchase quantity
- receipt quantity
- writeoff quantity
- cross-org transfer quantity

Not fabricated:

- stocktaking book / actual / difference
- supplier return quantity
- internal movement quantity

because current immutable RAW does not contain materializable business rows for those datasets.

## COST SEMANTICS

Status: `PASS WITH FIXES`

Preserved:

- balance input price
- balance valuation estimate
- purchase unit cost
- writeoff document amount
- cross-org transfer amount / base amount

Not mixed with:

- sale unit price
- payment amount
- revenue

Outstanding gap:

- not all purchase / receipt lines can be linked to canonical products yet
- some headers still have no linked canonical warehouse

## SNAPSHOT DUPLICATION HANDLING

Status: `PASS`

Rule applied:

- inventory balances are not summed blindly across historical exports
- latest snapshot per proven grain is used for current-stock preview

## IDEMPOTENCY

Second Phase 2C run on the same PostgreSQL RAW:

- `canonical_inventory_balances`: before `11,562` → after `11,562` → duplicates `0`
- `canonical_purchases`: `14` → `14` → duplicates `0`
- `canonical_purchase_items`: `162` → `162` → duplicates `0`
- `canonical_warehouse_receipts`: `14` → `14` → duplicates `0`
- `canonical_warehouse_receipt_items`: `162` → `162` → duplicates `0`
- `canonical_writeoffs`: `44` → `44` → duplicates `0`
- `canonical_writeoff_items`: `158` → `158` → duplicates `0`
- `canonical_cross_org_movements`: `6` → `6` → duplicates `0`
- `canonical_cross_org_movement_items`: `57` → `57` → duplicates `0`

Status: `PASS`

## UNSAFE EXCLUSION

Status: `PASS`

Phase 2C only materialized rows from trusted RAW status set:

- `CONSISTENT`
- `LEGACY_MISSING_REQUEST_CONTEXT`

Unsafe warehouse rows produced zero canonical facts.

## CRITICAL ISSUES

1. `canonical_purchase_items` product linkage is only `20 / 162`
2. `canonical_warehouse_receipt_items` product linkage is only `20 / 162`
3. purchase / receipt warehouse linkage is only `4 / 14`
4. cross-org header warehouse linkage is only `4 / 6`
5. warehouse-domain RAW provenance is legacy-partial because request/response filial context is often missing in stored RAW
6. supplier returns / stocktakings / internal movements currently have no materializable business rows in immutable RAW
7. purchase and receipt document dates are frequently absent in current RAW payloads, so many documents materialize with partial document-time semantics

## FINAL STATUS

- Organization isolation: `PASS`
- Product linkage: `FAIL`
- Warehouse linkage: `FAIL`
- Quantity semantics: `PASS`
- Cost semantics: `PASS WITH FIXES`
- Snapshot duplication handling: `PASS`
- Provenance: `FAIL`
- Idempotency: `PASS`
- Unsafe exclusion: `PASS`

## PHASE 2C

Result: `PASS WITH FIXES`

## READY FOR PHASE 2D

`NO`

### Actual blockers

1. Purchase and receipt product linkage must be repaired before downstream analytics can trust warehouse inflow by product.
2. Purchase and receipt warehouse linkage must be repaired before warehouse-level stock movement analytics are safe.
3. Warehouse-domain legacy provenance needs explicit classification in acceptance logic because request/response filial context is missing in many stored RAW rows.

Phase 2D should not start until these three blockers are resolved or explicitly accepted.
