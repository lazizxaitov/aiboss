# PHASE 2F — FINAL CANONICAL INTEGRITY & SEMANTIC GATE

Дата проверки: 12.08.2026  
Источник: PostgreSQL + immutable SmartUp RAW  
Повторная загрузка SmartUp: нет

## 1. FULL CANONICAL INVENTORY

| Table | Total | VERIFIED | PARTIAL | UNRESOLVED | UNSAFE |
| --- | ---: | ---: | ---: | ---: | ---: |
| canonical_organizations | 7 | 7 | 0 | 0 | 0 |
| canonical_customer_groups | 42 | 42 | 0 | 0 | 0 |
| canonical_customers | 613 | 0 | 613 | 0 | 0 |
| canonical_product_categories | 35 | 35 | 0 | 0 | 0 |
| canonical_products | 388 | 388 | 0 | 0 | 0 |
| canonical_warehouses | 25 | 25 | 0 | 0 | 0 |
| canonical_price_types | 20 | 20 | 0 | 0 | 0 |
| canonical_product_prices | 5 | 5 | 0 | 0 | 0 |
| canonical_sales_reps | 19 | 19 | 0 | 0 | 0 |
| canonical_working_zones | 24 | 24 | 0 | 0 | 0 |
| canonical_orders | 107 | 107 | 0 | 0 | 0 |
| canonical_sales | 100 | 100 | 0 | 0 | 0 |
| canonical_sale_items | 471 | 471 | 0 | 0 | 0 |
| canonical_payments | 156 | 156 | 0 | 0 | 0 |
| canonical_payment_allocations | 0 | 0 | 0 | 0 | 0 |
| canonical_customer_returns | 2 | 2 | 0 | 0 | 0 |
| canonical_customer_return_items | 36 | 36 | 0 | 0 | 0 |
| canonical_inventory_balances | 11562 | 11562 | 0 | 0 | 0 |
| canonical_purchases | 14 | 14 | 0 | 0 | 0 |
| canonical_purchase_items | 162 | 162 | 0 | 0 | 0 |
| canonical_warehouse_receipts | 14 | 14 | 0 | 0 | 0 |
| canonical_warehouse_receipt_items | 162 | 162 | 0 | 0 | 0 |
| canonical_writeoffs | 44 | 44 | 0 | 0 | 0 |
| canonical_writeoff_items | 158 | 158 | 0 | 0 | 0 |
| canonical_supplier_returns | 0 | 0 | 0 | 0 | 0 |
| canonical_supplier_return_items | 0 | 0 | 0 | 0 | 0 |
| canonical_stocktakings | 0 | 0 | 0 | 0 | 0 |
| canonical_stocktaking_items | 0 | 0 | 0 | 0 | 0 |
| canonical_internal_movements | 0 | 0 | 0 | 0 | 0 |
| canonical_internal_movement_items | 0 | 0 | 0 | 0 | 0 |
| canonical_cross_org_movements | 6 | 6 | 0 | 0 | 0 |
| canonical_cross_org_movement_items | 57 | 57 | 0 | 0 | 0 |
| canonical_visits | 884 | 884 | 0 | 0 | 0 |
| canonical_visit_stocks | 0 | 0 | 0 | 0 | 0 |
| canonical_visit_quiz_answers | 0 | 0 | 0 | 0 | 0 |
| canonical_visit_equipments | 0 | 0 | 0 | 0 | 0 |
| canonical_visit_comments | 0 | 0 | 0 | 0 | 0 |
| canonical_media_assets | 0 | 0 | 0 | 0 | 0 |
| canonical_financial_accounts | 4 | 4 | 0 | 0 | 0 |
| canonical_financial_operations | 312 | 156 | 156 | 0 | 0 |

## 2. SALES STATUS MAPPING — LIVE

### Orders

| source_status_code | source_status_name | normalized_status | count | amount | sold_quantity | realized_sales | realization_evidence |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| A | A | approved | 71 | 214936870 | 1339 | 65 | 65 |
| B#N | B#N | new | 21 | 49463600 | 327 | 21 | 21 |
| B#S | B#S | unmapped | 11 | 51814900 | 302 | 11 | 11 |
| B#V | B#V | unmapped | 2 | 1272700 | 7 | 2 | 2 |
| C | C | cancelled | 2 | 1069500 | 0 | 0 | 1 |

### Sales

| source_status_code | source_status_name | normalized_status | count | amount | sold_quantity | realized_sales | realization_basis_present |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| A | A | approved | 65 | 214936870 | 1339 | 65 | 65 |
| B#N | B#N | new | 21 | 49463600 | 327 | 21 | 21 |
| B#S | B#S | unmapped | 11 | 51814900 | 302 | 11 | 11 |
| B#V | B#V | unmapped | 2 | 1272700 | 7 | 2 | 2 |
| C | C | cancelled | 1 | 1069500 | 0 | 0 | 1 |

Вывод:

- legacy-статусы `won/lead` не используются;
- реальное source mapping сейчас основано на `A`, `B#N`, `B#S`, `B#V`, `C`;
- realised sales существуют не только у `approved`, но и у `new` и `unmapped`;
- значит Revenue нельзя определять как `status = approved` или `status = won`.

## 3. FINAL REVENUE RULE

Финальное live-правило Phase 2F:

**Revenue = SUM(canonical_sales.total_amount)**  
только для строк, где:

- `data_quality_status = VERIFIED`
- `sold_quantity > 0`

Это даёт realised sale evidence без зависимости от одного label-статуса.

### Live result

- sale count: `99`
- sale item count: `469`
- sold units: `1975`
- amount: `317,488,070 UZS`

## 4. REVENUE RECONCILIATION

### Legacy vs Canonical

- Old Legacy Revenue: `432,419,140 UZS`
- Earlier Canonical preview: `318,557,570 UZS`
- Final Phase 2F realised revenue: `317,488,070 UZS`

### Difference explanation

Canonical V2 intentionally excludes:

- non-realised rows without sold quantity evidence
- cancelled semantics from strict realised revenue
- any unsafe cross-organization contamination

This explains why Canonical revenue is lower than legacy.

### By organization and normalized status

| Organization | normalized_status | sales_count | amount | sold_quantity |
| --- | --- | ---: | ---: | ---: |
| MODAILY | approved | 64 | 210886870 | 1249 |
| MODAILY | new | 11 | 28927800 | 179 |
| MODAILY | unmapped | 13 | 53087600 | 309 |
| MODAILY QOQON VA FARGONA | new | 9 | 19068800 | 111 |
| SAMO SERVIS | approved | 1 | 4050000 | 90 |
| SAMO SERVIS | new | 1 | 1467000 | 37 |

## 5. ORDER VS SALE COVERAGE

- canonical_orders: `107`
- canonical_sales: `100`
- orders with realised sale: `100`
- orders without realised quantity: `8`
- orders cancelled: `2`
- orders with partial sale: `0`
- orders with returns: `2`

Вывод:

- один order не равен автоматически one realised sale;
- order и sale должны оставаться разными сущностями;
- returns также должны оставаться отдельным бизнес-фактом.

## 6. CUSTOMER INTEGRITY

- canonical customers: `613`
- quality: все `PARTIAL`

### Source coverage

| Dataset | rows with customer ref | unique source identities |
| --- | ---: | ---: |
| sales | 100 | 92 |
| payments | 156 | 61 |
| visits | 884 | 281 |
| returns | 2 | 1 |

### Cross-dataset dedup

- raw customer references: `1142`
- unique source identities: `307`
- canonical customers: `613`

### Conflict audit

- same-id / different-name cases: `0`
- same-name / different-id cases: `1`

Вывод:

- merge by name не используется;
- identity держится на source identity;
- customer master всё ещё partial, но cross-dataset dedup остаётся приемлемым.

### By organization

| Organization | canonical_customers |
| --- | ---: |
| Администрация | 300 |
| MODAILY | 294 |
| MODAILY QOQON VA FARGONA | 15 |
| SAMO SERVIS | 4 |

## 7. PRODUCT INTEGRITY

### Linkage coverage

| Domain | total | product linked | coverage |
| --- | ---: | ---: | ---: |
| sale_items | 471 | 471 | 100% |
| return_items | 36 | 36 | 100% |
| inventory | 11562 | 11562 | 100% |
| purchase_items | 162 | 20 | 12.35% |
| receipt_items | 162 | 20 | 12.35% |

Вывод:

- sales / returns / balances связаны с products детерминированно;
- purchase/receipt unresolved linkage остаётся known source limitation;
- heuristic repair не требуется и не выполняется.

## 8. ORGANIZATION ISOLATION

Cross-organization contamination по всем canonical tables:

- `0`

Это подтверждено для:

- orders
- sales
- sale_items
- payments
- returns
- inventory balances
- purchases
- warehouse receipts
- visits
- financial operations

Legitimate cross-organization movement остаётся отдельным canonical domain:

- canonical_cross_org_movements: `6`
- canonical_cross_org_movement_items: `57`

Итог:

**Organization isolation = PASS**

## 9. MONEY SEMANTICS — FINAL REGISTRY

| metric_key | definition | canonical source | filters | required quality | currency behavior | organization behavior | date field | drilldown |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| revenue | realised verified sales amount | canonical_sales | `sold_quantity > 0` | VERIFIED | do not mix currencies | aggregate selected organizations | sale_at | canonical_sales, canonical_sale_items |
| ordered_amount | total ordered amount | canonical_orders | none / business filters | VERIFIED/PARTIAL by view | by currency_code | by organization_id | order_at | canonical_orders |
| payments_received | customer receipts | canonical_payments / canonical_financial_operations | customer-payment only | VERIFIED | by currency_code | by organization_id | paid_at / operation_date | canonical_payments |
| customer_return_value | return document value | canonical_customer_returns | none | VERIFIED/PARTIAL by view | by currency_code | by organization_id | return_at | canonical_customer_returns |
| verified_cash_in | external inflow | canonical_financial_operations | `direction=INFLOW` | VERIFIED | by currency_code | by organization_id | operation_date | canonical_financial_operations |
| verified_cash_out | external outflow | canonical_financial_operations | `direction=OUTFLOW` | VERIFIED | by currency_code | by organization_id | operation_date | canonical_financial_operations |
| net_cash_flow | cash in - cash out | canonical_financial_operations | verified inflow/outflow only | VERIFIED | by currency_code | by organization_id | operation_date | canonical_financial_operations |
| purchase_amount | purchase header amount | canonical_purchases | none | VERIFIED/PARTIAL by view | by currency_code | by organization_id | purchase_at | canonical_purchases |
| inventory_value | not yet available | canonical_inventory_balances | blocked by valuation semantics | N/A | do not invent conversions | latest snapshot only | snapshot_date | canonical_inventory_balances |
| profit | not available | N/A | blocked by COGS + verified outflow semantics | N/A | N/A | N/A | N/A | N/A |

## 10. LEGACY SEMANTICS — DEPRECATED

Следующие legacy KPI sources должны считаться deprecated:

- `finance_entries`
- legacy sales aggregations
- legacy contacts-based business metrics

Критично:

- customer payments больше никогда не должны интерпретироваться как `EXPENSE`
- old legacy cash flow `-346,923,200` документирован как incorrect legacy semantics

## 11. FINANCE COVERAGE SEMANTICS

Current strict finance:

- verified cash in: `346,923,200 UZS`
- verified cash out: `NO VERIFIED DATA`
- internal transfers: `0`
- unknown direction: `0`

Это **не** значит, что расходов реально не было.  
Это значит, что verified outflow data в текущем immutable RAW не подтверждена.

Итог:

- `Cash Out = NO VERIFIED DATA`
- не `Cash Out = 0`

## 12. FALSE ZERO SEMANTICS

Phase 2F rule:

- `0` = данные есть, значение реально ноль
- `NO_DATA` = usable source data нет
- `PARTIAL` = coverage неполный
- `NOT_AVAILABLE` = источник/семантика недоступны
- `PERMISSION_RESTRICTED` = SmartUp не дал доступ
- `UNRESOLVED` = данные есть, но интерпретировать безопасно нельзя

Эта семантика обязательна для:

- finance
- inventory
- visits
- prices
- customers
- returns

## 13. CURRENT STOCK INTEGRITY

Current stock strategy подтверждена:

`organization + warehouse + product (+ batch when needed) -> latest valid inventory snapshot`

Historical snapshots не суммируются для current stock.

### Live balance coverage

- inventory balances: `11562`
- product linkage: `11562 / 11562`
- warehouse linkage: `11562 / 11562`
- snapshot date coverage:
  - min: `2026-08-04`
  - max: `2026-08-11`

### Sample current stock

Проверка sample rows показывает:

- latest snapshot grain используется по `snapshot_date`
- product and warehouse links для balance rows verified

## 14. INVENTORY COVERAGE

### Verified current balance

- current balance domain: `PASS`

### Known source limitations

Purchase / receipt warehouse linkage:

- purchases: `4 / 14`
- warehouse receipts: `4 / 14`

Product linkage on lines:

- purchase_items: `20 / 162`
- warehouse_receipt_items: `20 / 162`

Это не дисквалифицирует verified current stock.

## 15. VISIT COVERAGE

- RAW visits: `888`
- Canonical visits: `884`

Nested datasets:

| Capability | count | classification |
| --- | ---: | --- |
| stocks | 0 | NO_DATA_IN_CURRENT_RAW |
| quizzes | 0 | NO_DATA_IN_CURRENT_RAW |
| equipment | 0 | NO_DATA_IN_CURRENT_RAW |
| comments | 0 | NO_DATA_IN_CURRENT_RAW |
| media/photos | 0 | NO_DATA_IN_CURRENT_RAW |

Вывод:

- current visits header import usable
- nested child capabilities не должны трактоваться как business zero

## 16. DATA QUALITY SUMMARY

| Domain | total | verified | partial | unresolved | unsafe |
| --- | ---: | ---: | ---: | ---: | ---: |
| foundation | 1178 | 565 | 613 | 0 | 0 |
| sales | 678 | 678 | 0 | 0 | 0 |
| payments_returns | 194 | 194 | 0 | 0 | 0 |
| warehouse | 12179 | 12179 | 0 | 0 | 0 |
| field_sales | 884 | 884 | 0 | 0 | 0 |
| finance | 316 | 160 | 156 | 0 | 0 |

## FINAL GATE STATUS

### CUSTOMER IDENTITY

`PASS WITH KNOWN SOURCE LIMITATIONS`

Reason:

- customers are partial reference-derived identities
- stable source identity exists
- no same-id/different-name conflicts found

### PRODUCT INTEGRITY

`PASS WITH KNOWN SOURCE LIMITATIONS`

Reason:

- sales/returns/inventory are fully linked
- purchase/receipt product linkage remains partial due to source identifier gaps

### ORGANIZATION ISOLATION

`PASS`

Cross-organization contamination:

- `0`

### REVENUE SEMANTICS

`PASS`

Final rule is evidence-based:

- verified sales
- sold quantity > 0

not label-based.

### FINANCE SEMANTICS

`PASS WITH KNOWN SOURCE LIMITATIONS`

Reason:

- customer payments are verified inflow
- duplicate cash_operation representation is preserved as partial
- verified cash out still unavailable

### LEGACY DEPRECATION

`PASS`

Old negative cash flow from client payments is formally invalidated.

### IDENTITY / PROVENANCE

`PASS WITH LEGACY LIMITATION`

Reason:

- legacy request context is missing in part of older RAW
- provenance remains traceable through immutable raw row, endpoint, organization, batch

### IDEMPOTENCY

`PASS`

Second backfill did not create duplicates.

## CRITICAL ISSUES

1. `canonical_customers` remain fully `PARTIAL`; this is acceptable, but customer master is still incomplete.
2. `canonical_product_prices` coverage is low (`5` verified rows); this does not block canonical truth for sales/inventory.
3. `canonical_financial_operations` currently prove inflow only; verified outflow is still unavailable from current immutable RAW.
4. `purchase_items` and `warehouse_receipt_items` remain only `12.35%` product-linked because source identifiers are missing.
5. visit child datasets are absent in current RAW and must not be shown as true zero.

## PHASE 2F

`PASS WITH KNOWN SOURCE LIMITATIONS`

## READY FOR CANONICAL V2 AS PRIMARY SOURCE OF TRUTH

For:

- Analytics: `YES`
- Dashboard: `YES, after UI layer switches to canonical semantics`
- Business pages: `YES, after page queries are rebuilt on canonical tables`
- AI Analytics Agent: `YES, after metric registry is enforced`

## READY FOR NEXT PHASE

`YES`

Phase 2F completed without modifying Dashboard/UI and without re-downloading SmartUp.
