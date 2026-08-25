# PHASE 2C.1 — INVENTORY LINKAGE REPAIR GATE

Date: 2026-08-12  
Source: existing immutable SmartUp RAW in PostgreSQL  
SmartUp re-download: no  
Scope: inventory linkage audit and deterministic repair only

## What was repaired

- Added deterministic receipt-item product fallback:
  - `warehouse_receipt_item.purchase_item_external_id`
  - exact match to `purchase_item.purchase_item_id`
  - same `organization_id` only
- Added in-process purchase-item → product index for Phase 2C materialization.
- Did **not** add any heuristic matching by product name.
- Did **not** fabricate warehouse identity where RAW has no warehouse key.

## Tests

- `uv run pytest tests/test_canonical_v2.py -q`
- Result: `7 passed`

## PURCHASE ITEM PRODUCT LINKAGE AUDIT

Total canonical purchase items: `162`  
Product linked: `20`  
Unresolved: `142`  
Linkage: `12.35%`

### Unresolved reasons

- `serial_or_card_only_no_product_identity`: `142`

### Actual RAW evidence

For unresolved purchase items, SmartUp RAW contains rows like:

- `purchase_item_id`
- `serial_number`
- `inventory_kind = E`
- `quantity`
- `price`

But does **not** contain:

- `product_id`
- `product_code`
- `inventory_code`
- `barcode`
- `product_article_code`

Example unresolved purchase RAW item:

- `purchase_item_id = 91857983`
- `serial_number = MBP010`
- `product_code = NULL`
- `product_article_code = NULL`

### Conclusion

These 142 purchase items cannot be linked to canonical products deterministically from current immutable RAW.

## RAW PRODUCT IDENTITY DISCOVERY

### Observed identity candidates in unresolved purchase items

- `purchase_items[].product_id`: absent
- `purchase_items[].product_code`: absent
- `purchase_items[].inventory_code`: absent
- `purchase_items[].product_article_code`: absent
- `purchase_items[].serial_number`: present
- `purchase_items[].card_code`: absent

### Matching against canonical products

Canonical products are currently keyed by proven fields from inventory/reference RAW:

- `source_external_id`
- `product_id`
- `code`
- `article_code`

No canonical product metadata matched unresolved serials such as:

- `MBP009`
- `MBP010`
- `MP025`

Serial-only equipment rows therefore remain unresolved.

## RECEIPT ITEM PRODUCT LINKAGE AUDIT

Total canonical receipt items: `162`  
Product linked: `20`  
Unresolved: `142`  
Linkage: `12.35%`

### Unresolved reasons

- `purchase_item_link_present_but_purchase_product_unresolved`: `142`

### Actual RAW evidence

All 162 receipt items contain exact purchase linkage:

- `purchase_id`
- `purchase_item_id`

Deterministic relation check:

- receipt rows with `purchase_item_external_id`: `162`
- receipt rows joinable to canonical purchase items by exact `purchase_item_id`: `162`

### Repair result

The new fallback works correctly for rows where the linked purchase item already has a resolved canonical product.

Live verified result:

- receipt items inheriting product through purchase item: `20`

Remaining 142 receipt items stay unresolved for the same reason as purchases:

- linked purchase items themselves have no deterministic product identity in RAW

## PURCHASE ↔ RECEIPT RELATION

Status: `PASS`

Exact typed relation exists and is preserved through:

- `warehouse_receipt_items.purchase_item_external_id`
- `purchase_items.purchase_item_id`

This relation is deterministic and organization-local.

No date/amount inference is used.

## WAREHOUSE LINKAGE AUDIT

### Purchases

Total: `14`  
Linked: `4`  
Unresolved: `10`

### Receipts

Total: `14`  
Linked: `4`  
Unresolved: `10`

### Why only 4/14 link

For 4 purchase headers and 4 receipt headers, RAW contains:

- `warehouse_code = 123`

For the remaining 10 + 10 headers:

- `warehouse_code = NULL`
- `warehouse_external_id = NULL`

Therefore unresolved reason is:

- `missing warehouse id/code in RAW header`

No deterministic warehouse key exists for those documents.

## WAREHOUSE DISCOVERY EXPANSION

Actual warehouse evidence discovered from RAW:

- `balance$export`
- `purchase$export`
- `input$export`
- `order$export`
- `return$export`

Current canonical warehouses include mixed evidence forms:

- warehouse code only, e.g. `123`
- warehouse id only, e.g. `104014`, `124495`
- named operational warehouse-like entities from order/return datasets

### Important limitation

Some current canonical warehouses originate from sales/order operational contexts.
They are preserved as-is, but they are not sufficient to repair purchase/receipt headers where RAW gives no warehouse identifier at all.

## CANONICAL WAREHOUSE MERGE

Status: `PARTIAL`

Deterministic merge is only possible when at least one stable identifier exists:

- `warehouse_id`
- `warehouse_code`

No safe merge by name alone was performed.

## LEGACY PROVENANCE

Inventory-domain RAW rows lacking `request_filial_id`:

- `inventory_balances`: `11,562`
- `purchases`: `16`
- `warehouse_receipts`: `16`
- `stocktakings`: `7`
- `internal_movements`: `7`

### Classification

- `inventory_balances`: `PARTIAL_PROVENANCE`
- `purchases`: `PARTIAL_PROVENANCE`
- `warehouse_receipts`: `PARTIAL_PROVENANCE`
- `stocktakings`: `RAW_WRAPPER_ONLY`
- `internal_movements`: `RAW_WRAPPER_ONLY`

Reason:

- rows are still organization-attributable through immutable stored organization context
- but original request filial metadata is incomplete in legacy RAW

## INVENTORY BALANCE GRAIN

Canonical inventory balance rows: `11,562`

Unique counts:

- organizations: `6`
- warehouse keys: `2`
- product external ids: `168`
- snapshot dates: `8`
- card_code values: `1`
- serial_number values: `1`

### Grain

`organization + warehouse + product + card + serial + snapshot_date`

### Current-stock derivation rule

For each:

- `organization_id`
- `warehouse`
- `product`
- `card/serial` if applicable

take the latest valid snapshot only.

Do **not** sum all historical balance snapshots.

Status: `READY`

## Latest stock sample

- `MODAILY | 123 | 000 | 2026-08-11 05:00:00+05 | 2.0000`
- `MODAILY | — | 001 | 2026-08-11 05:00:00+05 | 1.0000`
- `MODAILY | 123 | 002 | 2026-08-11 05:00:00+05 | 1000.0000`
- `MODAILY | 123 | 904 | 2026-08-11 05:00:00+05 | 2.0000`
- `MODAILY | — | 973 | 2026-08-11 05:00:00+05 | 7.0000`

## COST SEMANTICS AUDIT

Observed inventory-domain money fields:

- purchase line `price` → purchase unit cost
- purchase line `base_price` → alternate/base cost field when present
- receipt line `price` → inbound receipt price
- balance `input_price` → inventory snapshot valuation cost
- line `amount` in canonical layer → `quantity * unit_price`
- `vat_amount`, `vat_percent` preserved separately where present

Rules preserved:

- purchase cost != sale price
- receipt cost != cash expense
- balance valuation != revenue

## SUPPLIER RETURNS / STOCKTAKINGS / INTERNAL MOVEMENTS

### Supplier returns

Status: `NO_DATA`

- raw rows: `0`

### Stocktakings

Status: `RAW_WRAPPER_ONLY`

- raw rows: `7`
- payload shape: `limits + stocktaking`
- `stocktaking` wrapper list present but empty

### Internal movements

Status: `RAW_WRAPPER_ONLY`

- raw rows: `7`
- payload shape: `limits + movement`
- `movement` wrapper list present but empty

## ORGANIZATION ISOLATION

Status: `PASS`

No cross-organization deterministic linkage was introduced.

Receipt fallback uses:

- same `organization_id`
- exact `purchase_item_id`

only.

## PROVENANCE

Status: `PASS WITH LEGACY LIMITATION`

- canonical rows preserve `source_raw_record_id`
- receipt↔purchase linkage is traceable
- some legacy inventory-domain RAW lacks `request_filial_id`

## IDEMPOTENCY

Status: `PASS`

Phase 2C materialization executed twice on the same immutable RAW.

Counts before and after second run:

- purchase items: unchanged `162`
- receipt items: unchanged `162`
- purchase warehouse linkage: unchanged `4/14`
- receipt warehouse linkage: unchanged `4/14`
- duplicates introduced: `0`

## FINAL GATE

### PURCHASE ITEMS

Total: `162`  
Product linked: `20`  
Unresolved: `142`  
Linkage %: `12.35%`  
Unresolved reasons:

- `serial_or_card_only_no_product_identity = 142`

### RECEIPT ITEMS

Total: `162`  
Product linked: `20`  
Unresolved: `142`  
Linkage %: `12.35%`  
Unresolved reasons:

- `purchase_item_link_present_but_purchase_product_unresolved = 142`

### PURCHASE WAREHOUSE

Total: `14`  
Linked: `4`  
Unresolved: `10`

### RECEIPT WAREHOUSE

Total: `14`  
Linked: `4`  
Unresolved: `10`

### WAREHOUSES

Canonical: `25`  
Identity coverage: `partial`  
Merged/enriched: `deterministic only`  
Unresolved: documents without warehouse keys remain unresolved

### INVENTORY BALANCES

Total: `11,562`  
Grain: `organization + warehouse + product + card + serial + snapshot_date`  
Latest-snapshot rule: `confirmed`  
Current-stock derivation ready: `YES`

### Product linkage

Status: `PASS WITH FIXES`

What is fixed:

- receipt items now support exact product inheritance from linked purchase items

What remains:

- purchase items with serial-only equipment rows cannot be linked without real product identity from SmartUp RAW

### Warehouse linkage

Status: `PASS WITH LIMITATION`

What is fixed:

- no false warehouse inference

What remains:

- 10/14 purchase headers and 10/14 receipt headers have no warehouse identity in current RAW

### PHASE 2C

Status: `PASS WITH FIXES`

### READY FOR PHASE 2D

`NO`

### Actual blockers

1. `142` purchase items still have no deterministic product identity in immutable RAW.
2. The same `142` receipt items remain unresolved because their linked purchase items are unresolved.
3. `10/14` purchase headers and `10/14` receipt headers still lack warehouse identity in RAW.
4. Legacy inventory provenance is partial for older stored RAW rows.

These are real data-coverage blockers, not pipeline guessing issues.
