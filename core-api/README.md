# AI Business OS Core

Минимальный каркас FastAPI-приложения для будущей платформы AI Business Operating System Core.

## Phase 1 structure

- `app/core/data_layer` - единый слой данных и канонические схемы.
- `app/core/data_layer/migrations` - импорт и нормализация SmartUp данных.
- `app/core/data_layer/schema.py` - точная спецификация таблиц и связей Core Data Layer V1.
- `app/integrations/smartup` - маппинг SmartUp -> Core Data Layer и план синхронизации.
- `app/modules` - будущие бизнес-модули.
- `app/agents` - будущие AI-агенты.
- `app/integrations` - внешние сервисы и LLM-провайдеры.

## Core Data Layer V1

Основные таблицы:

- `businesses`
- `source_systems`
- `contacts`
- `sales`
- `marketing_activities`
- `finance_entries`
- `kpi_snapshots`
- `core_records`
- `ingestion_batches`
- `ingestion_errors`

Ключевая идея:

- все сущности связаны через `business_id`;
- SmartUp импортируется через `ingestion_batches`;
- сырые нормализованные события фиксируются в `core_records`;
- KPI хранятся отдельно для dashboard и AI-агентов.

## SmartUp integration plan

Источник SmartUp сейчас рассматривается как первый внешний источник данных.

Что забираем:

- `legal_person` и `natural_person` для контактов;
- `inventory`, `product_group`, `price_type`, `product_price`, `producer` для каталога и цен;
- `contract` и `room` для контрагентов, договоров и рабочих зон;
- `order`, `return`, `visit`, `cashin` для продаж и клиентской активности;
- `cash_operation`, `bank_operation` для финансов;
- `balance` и `equipment_balance` для складов, остатков и активов;
- `service`, `person_group`, `return_reason` для дополнительных справочников;
- `logistics`, `movement`, `stocktaking`, `writeoff`, `input`, `purchase` для складских и операционных документов;
- `equipment_movement`, `equipment_request` для оборудования и заявок.

Что делает connector:

- строит план синхронизации по группам `master_data`, `sales`, `finance`, `inventory`, `operations`, `assets`;
- готовит payload для каждого endpoint;
- передает внешние данные в слой нормализации, который затем пишет в Core Data Layer.

### SmartUp → Core Data Layer

| SmartUp endpoint | Сейчас сохраняем в ядро |
| --- | --- |
| `legal_person`, `natural_person` | `contacts` + `customers` |
| `inventory` | `products` |
| `product_group`, `person_group`, `return_reason` | `product_categories` |
| `producer` | `customers` как контрагенты / поставщики |
| `room` | `warehouses` |
| `order` | `sales` + `sale_v2` |
| `visit` | `visits` |
| `client payments` | `finance_entries` + `payments` |
| `cash operations`, `bank statements` | `finance_entries` + `bank_operations` |
| `balance` | `inventory_snapshots` + `inventory_balances` |
| `service` | `products` |
| Остальные операционные endpoint'ы | raw-история в `core_records` до появления отдельных канонических моделей |

Если для части endpoint'ов ещё не готов отдельный нормализатор, система всё равно сохраняет сырой ответ в `core_records`, чтобы данные не терялись.

В будущем AI будет работать поверх этого ядра:

- собирать все данные из Core Data Layer;
- анализировать продажи, финансы, маркетинг, склад и визиты;
- давать рекомендации и объяснять отклонения;
- упрощать работу через Dashboard;
- отвечать на пользовательские вопросы на основе реальных данных.

## Установка

```bash
uv sync
```

## Запуск сервера

```bash
uv run fastapi dev app/main.py
```

Адрес приложения:

```text
http://127.0.0.1:8000
```

Swagger:

```text
http://127.0.0.1:8000/docs
```

Health endpoint:

```text
http://127.0.0.1:8000/api/v1/health
```

## Тесты

```bash
uv run pytest
```

## Ruff

Проверка:

```bash
uv run ruff check .
```

Форматирование:

```bash
uv run ruff format .
```

## SmartUp migration CLI

Историческая миграция SmartUp запускается через CLI:

```bash
uv run smartup-migrate history \
  --business-id 11111111-1111-1111-1111-111111111111 \
  --business-name "Example Business" \
  --history-start 2020-01-01
```

Дополнительно можно указать:

- `--history-end`
- `--chunk-days`
- `--base-url`
- `--username`
- `--password`
- `--project-code`
- `--filial-id`
- `--timeout-seconds`
- `--dry-run`
- `--report`

По умолчанию backend берется из `.env`. Сейчас для локальной разработки и тестов используется `sqlite`.
Если нужно, можно явно указать `--storage memory|sqlite|postgres`.

Для офлайн-миграции из подготовленного JSON-экспорта используется отдельная команда:

```bash
uv run smartup-migrate bundle \
  --input path/to/bundle.json \
  --report reports/bundle-report.json
```

Офлайн-режим полезен для отладки до того, как появится разовый доступ к полной истории SmartUp.
