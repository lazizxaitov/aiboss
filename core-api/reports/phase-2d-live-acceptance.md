# PHASE 2D LIVE ACCEPTANCE

Дата проверки: 12.08.2026
Источник: PostgreSQL + immutable SmartUp RAW
Повторная загрузка SmartUp: нет

## VISITS

- RAW: `888`
- Trusted: `884`
- Canonical: `884`
- Customer linked: `884`
- Sales rep linked: `884`
- Working zone linked: `884`

Из trusted RAW не материализовались `4` wrapper-only ответа без business rows.

## STATUS COVERAGE

| source_status | count | normalized_status |
| --- | ---: | --- |
| `N` | 884 | `new` |

## TIME / DURATION COVERAGE

- `visit_date`: `884 / 884`
- `visit_start_time`: `0 / 884`
- `visit_end_time`: `0 / 884`
- `duration_seconds`: `0 / 884`
- `derived_duration_seconds`: `0 / 884`
- start coordinates: `884 / 884`
- end coordinates: `884 / 884`

Вывод: текущий RAW даёт дату и GPS, но не даёт пригодные start/end timestamps и длительность для business facts.

## VISIT STOCKS

- RAW nested business rows: `0`
- Canonical rows: `0`
- Status: `NO_DATA`

## ASSORTMENT

- В текущем immutable RAW не обнаружено подтверждённых assortment rows.
- Status: `NOT_PRESENT`

## PLANOGRAMS

- В текущем immutable RAW не обнаружено подтверждённых planogram rows.
- Status: `NOT_PRESENT`

## DISPLAYS

- В текущем immutable RAW не обнаружено подтверждённых display/POS rows.
- Status: `NOT_PRESENT`

## QUIZZES

- Top-level `quizzes` key присутствует в trusted RAW.
- Фактические `quiz_sets` в текущем PostgreSQL RAW пустые.
- Canonical quiz answers: `0`
- Status: `RAW_ONLY`

## VISIT EQUIPMENT

- Nested equipment rows: `0`
- Canonical rows: `0`
- Status: `NO_DATA`

## COMMENTS

- Structured comment rows: `0`
- Canonical rows: `0`
- Status: `NO_DATA`

## MEDIA / PHOTO REFERENCES

- SHA/photo references discovered: `0`
- Canonical media assets: `0`
- Status: `NOT_PRESENT`

## VISIT -> ORDER LINKAGE

- Orders with explicit visit reference: `0`
- Sales with explicit visit reference: `0`
- Status: `NOT_PRESENT`

Связь Visit -> Order/Sale не была выведена эвристически.

## ORGANIZATION CAPABILITY MATRIX

| Organization | Filial ID | RAW | Trusted | Canonical | Customer linked | Sales rep linked | Working zone linked | Quizzes | Stocks | Equipment | Comments | Media | Capability |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Администрация | 14475622 | 442 | 442 | 442 | 442 | 442 | 442 | 0 | 0 | 0 | 0 | 0 | AVAILABLE |
| MODAILY | 16114091 | 432 | 432 | 432 | 432 | 432 | 432 | 0 | 0 | 0 | 0 | 0 | AVAILABLE |
| MODAILY ANDIJON | 19392290 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | RAW_ONLY |
| MODAILY NAMANGAN | 19365400 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | RAW_ONLY |
| MODAILY QOQON VA FARGONA | 19330532 | 10 | 10 | 10 | 10 | 10 | 10 | 0 | 0 | 0 | 0 | 0 | AVAILABLE |
| MODAILY SURXANDARYO | 19448306 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | RAW_ONLY |
| SAMO SERVIS | 14479324 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | RAW_ONLY |

## PROVENANCE

Проверка sample rows:

- `canonical_visits.source_raw_record_id` заполнен
- `canonical_visits.source_endpoint = /b/trade/txs/tvt/visit$export`
- `canonical_visits.organization_id` соответствует RAW organization
- `canonical_visits` строятся только из trusted RAW rows

Observed legacy provenance:

- sample canonical visits имеют `request_filial_id = NULL`
- sample canonical visits имеют `response_filial_id = NULL`
- materialization допущена только потому, что строки уже прошли trusted attribution stage и не показали cross-org mismatch

Это означает:

- Provenance: `PASS WITH LEGACY LIMITATION`
- Organization isolation: сохраняется
- Полный request-context в legacy visit RAW отсутствует

## IDEMPOTENCY

Second run:

- `canonical_visits`: duplicates `0`
- `canonical_visit_stocks`: duplicates `0`
- `canonical_visit_quiz_answers`: duplicates `0`
- `canonical_visit_equipments`: duplicates `0`
- `canonical_visit_comments`: duplicates `0`
- `canonical_media_assets`: duplicates `0`

Second run canonical counts не изменились.

## LIVE PREVIEW

- visits count: `884`
- unique customers visited: `884`
- unique sales reps: материализованы и связаны для всех `884` visits
- working zones: материализованы и связаны для всех `884` visits
- planned vs unplanned: `unknown = 884`
- average duration: unavailable from current trusted visit RAW

## ACCEPTANCE STATUS

- Organization isolation: `PASS`
- Customer linkage: `PASS`
- Sales rep linkage: `PASS`
- Working zone linkage: `PASS`
- Nested data preservation: `PASS WITH KNOWN SOURCE LIMITATIONS`
- Media provenance: `PASS`
- Provenance: `PASS WITH LEGACY LIMITATION`
- Idempotency: `PASS`
- Unsafe exclusion: `PASS`

## CRITICAL ISSUES

1. В trusted RAW нет пригодных start/end timestamps, поэтому duration KPI пока не materialized.
2. `quizzes` присутствуют как container, но фактических answer rows в текущем PostgreSQL RAW нет.
3. Для 4 trusted RAW responses есть только wrapper без business `visit_headers`.
4. Для 4 организаций current dataset содержит только единичные RAW rows без materializable visit headers.

## PHASE 2D

`PASS WITH KNOWN SOURCE LIMITATIONS`

## READY FOR PHASE 2E

`YES`

Phase 2E автоматически не запускался.
