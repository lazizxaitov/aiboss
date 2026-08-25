import type { ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { MetricTile } from "@/components/ui/metric-tile";
import { SectionHeading } from "@/components/ui/section-heading";
import { Surface } from "@/components/ui/surface";
import { getDashboardOverview } from "@/lib/core-api";
import { formatMoneyValue, parseMoneyValue } from "@/lib/money";
import type { ModuleConfig } from "@/modules/shared/types";

type ModuleScreenProps = {
  module: ModuleConfig;
};

type OverviewCard = {
  label: string;
  value: string;
  note: string;
};

type MetricTileVariant = NonNullable<Parameters<typeof MetricTile>[0]["variant"]>;

function workspaceStatsFor(
  kind: ModuleConfig["kind"],
  overview: Awaited<ReturnType<typeof getDashboardOverview>>,
  fallback?: ModuleConfig["stats"],
) {
  const revenue = metricByLabel(overview.business_metrics, "Выручка");
  const received = metricByLabel(overview.business_metrics, "Получено денег");
  const expenses = metricByLabel(overview.business_metrics, "Расходы");
  const flow = metricByLabel(overview.business_metrics, "Чистый поток");
  const soldUnits = metricByLabel(overview.business_metrics, "Продано единиц");
  const deals = metricByLabel(overview.executive_summary, "Сделки");
  const signals = overview.signals.length;
  const businesses = overview.businesses.length;
  const products = overview.top_products.length;
  const payments = overview.recent_payments.length;
  const recommendations = overview.recommendations.length;

  switch (kind) {
    case "sales":
      return [
        { label: revenue?.label ?? "Выручка", value: revenue?.value ?? "0 UZS", note: revenue?.note ?? "по продажам" },
        { label: deals?.label ?? "Сделки", value: deals?.value ?? "0", note: deals?.note ?? "по периоду" },
        { label: soldUnits?.label ?? "Продано единиц", value: soldUnits?.value ?? "0", note: soldUnits?.note ?? "строк товаров" },
      ];
    case "finance":
      return [
        { label: revenue?.label ?? "Выручка", value: revenue?.value ?? "0 UZS", note: revenue?.note ?? "по продажам" },
        { label: received?.label ?? "Получено денег", value: received?.value ?? "0 UZS", note: received?.note ?? "по платежам" },
        { label: flow?.label ?? "Чистый поток", value: flow?.value ?? "0 UZS", note: flow?.note ?? "баланс периода" },
      ];
    case "marketing":
      return [
        { label: "Сигналы", value: `${signals}`, note: "маркетинговые и бизнес-сигналы" },
        { label: "Платежи", value: `${payments}`, note: "покупки и поступления" },
        { label: "Выручка", value: revenue?.value ?? "0 UZS", note: revenue?.note ?? "по продажам" },
      ];
    case "inventory":
      return [
        { label: "Бизнесы", value: `${businesses}`, note: "подключённые организации" },
        { label: "Товаров", value: `${products}`, note: "позиции каталога" },
        { label: "Расходы", value: expenses?.value ?? "0 UZS", note: expenses?.note ?? "по операциям" },
      ];
    case "telegram":
      return [
        { label: "Сигналы", value: `${signals}`, note: "упоминания и события" },
        { label: "Рекомендации", value: `${recommendations}`, note: "что сделать дальше" },
        { label: "Платежи", value: `${payments}`, note: "связанные транзакции" },
      ];
    case "alerts":
      return [
        { label: "Сигналы", value: `${signals}`, note: "проверка отклонений" },
        { label: "Продано", value: soldUnits?.value ?? "0", note: soldUnits?.note ?? "единиц" },
        { label: "Товары", value: `${products}`, note: "активные позиции" },
      ];
    case "ceo":
      return [
        { label: "Выручка", value: revenue?.value ?? "0 UZS", note: revenue?.note ?? "по продажам" },
        { label: "Сделки", value: deals?.value ?? "0", note: deals?.note ?? "по периоду" },
        { label: "Сигналы", value: `${signals}`, note: "что требует внимания" },
      ];
    case "recommendations":
      return [
        { label: "Рекомендации", value: `${recommendations}`, note: "сформировано AI" },
        { label: "Сигналы", value: `${signals}`, note: "входные данные" },
        { label: "Выручка", value: revenue?.value ?? "0 UZS", note: revenue?.note ?? "по продажам" },
      ];
    default:
      return fallback ?? [];
  }
}

export async function ModuleScreen({ module }: ModuleScreenProps) {
  const overview = await getDashboardOverview();

  return (
    <section className="space-y-6">
      <SectionHeading
        eyebrow={module.eyebrow}
        title={module.title}
        description={module.description}
      />

      {module.kind === "sales" ? (
        <SalesWorkspace module={module} overview={overview} />
      ) : module.kind === "finance" ? (
        <FinanceWorkspace module={module} overview={overview} />
      ) : module.kind === "marketing" ? (
        <MarketingWorkspace module={module} overview={overview} />
      ) : module.kind === "inventory" ? (
        <InventoryWorkspace module={module} overview={overview} />
      ) : module.kind === "telegram" ? (
        <TelegramWorkspace module={module} overview={overview} />
      ) : module.kind === "alerts" ? (
        <AlertsWorkspace module={module} overview={overview} />
      ) : module.kind === "ceo" ? (
        <CEOWorkspace module={module} overview={overview} />
      ) : (
        <RecommendationsWorkspace module={module} overview={overview} />
      )}
    </section>
  );
}

function SalesWorkspace({
  module,
  overview,
}: {
  module: ModuleConfig;
  overview: Awaited<ReturnType<typeof getDashboardOverview>>;
}) {
  const revenue = metricByLabel(overview.business_metrics, "Выручка");
  const expense = metricByLabel(overview.business_metrics, "Расходы");
  const flow = metricByLabel(overview.business_metrics, "Чистый поток");

  return (
    <div className="space-y-6">
      <StatsShelf stats={workspaceStatsFor(module.kind, overview, module.stats)} />

      <div className="space-y-6">
        <Surface className="overflow-hidden p-6 sm:p-8">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="accent">{module.accent ?? "Продажи"}</Badge>
            <Badge variant="soft">{overview.analysis_engine}</Badge>
            <Badge>{overview.freshness}</Badge>
          </div>

          <div className="mt-5 space-y-4">
            <div className="space-y-3">
              <p className="text-xs uppercase tracking-[0.28em] text-slate-400">Продажи и воронка</p>
              <h3 className="text-2xl font-semibold tracking-[-0.05em] text-[#f4f7fb]">
                Воронка, выручка и текущая нагрузка
              </h3>
              <p className="max-w-2xl text-sm leading-7 text-slate-400">{overview.analysis_note}</p>
            </div>

            <div className="space-y-4">
              <TrendPanel trend={overview.trend} title="Динамика продаж" badge="Динамика" />
              <ComparisonPanel
                title="Поток продаж"
                badge="Потоки"
                items={[
                  { label: revenue?.label ?? "Выручка", value: revenue?.value ?? "0 USD", note: revenue?.note ?? "по проводкам" },
                  { label: expense?.label ?? "Расходы", value: expense?.value ?? "0 USD", note: expense?.note ?? "по операциям" },
                  { label: flow?.label ?? "Чистый поток", value: flow?.value ?? "0 USD", note: flow?.note ?? "баланс периода" },
                ]}
              />
            </div>
          </div>
        </Surface>

        <div className="space-y-6">
          <SignalBoard title="Сигналы продаж" badge="Приоритеты" signals={overview.signals} />
          <SourceCloud
            title="Источники продаж"
            badge="Источники"
            items={["Организации", "Воронка продаж", "CRM-активность", "Записи ядра"]}
          />
          <DetailListPanel
            title="Последние сделки"
            badge="Продажи"
            subtitle="Свежие продажи, суммы и статусы"
            items={overview.recent_sales.slice(0, 6)}
            emptyLabel="Сделки пока не загружены."
            renderItem={(sale) => (
                <div
                  key={sale.sale_id}
                  className="rounded-[18px] border border-[#3a3d43] bg-[#2E3137] px-4 py-3 transition hover:border-[#4a4e56] hover:bg-[#343840]/80"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="truncate font-semibold tracking-[-0.03em] text-[#f4f7fb]">{sale.sale_number}</p>
                      <p className="mt-1 truncate text-sm text-slate-400">
                        {sale.business_name}
                        {sale.contact_name ? ` · ${sale.contact_name}` : ""}
                      </p>
                      <p className="mt-2 truncate text-xs text-slate-400">
                        {sale.items_count} строк · {sale.products_count} товаров
                      </p>
                    </div>
                    <Badge variant="soft">{sale.stage}</Badge>
                  </div>
                  <div className="mt-3 text-sm font-medium text-[#f4f7fb]">{formatMoneyValue(sale.amount)}</div>
                </div>
            )}
          />
          <DetailListPanel
            title="Топ товаров"
            badge="Ассортимент"
            subtitle="Что продаётся чаще и какие позиции активнее всего"
            items={overview.top_products.slice(0, 6)}
            emptyLabel="Товары пока не загружены."
            renderItem={(product) => (
                <div
                  key={product.product_id}
                  className="rounded-[18px] border border-[#3a3d43] bg-[#2E3137] px-4 py-3 transition hover:border-[#4a4e56] hover:bg-[#343840]/80"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="truncate font-semibold tracking-[-0.03em] text-[#f4f7fb]">{product.name}</p>
                      <p className="mt-1 truncate text-sm text-slate-400">
                        {product.business_name}
                        {product.category ? ` · ${product.category}` : ""}
                      </p>
                      <p className="mt-2 truncate text-xs text-slate-400">
                        {product.sold_quantity} продано · {product.stock_quantity} в остатке
                      </p>
                    </div>
                    <Badge variant="accent">{formatMoneyValue(product.sold_amount)}</Badge>
                  </div>
                </div>
            )}
          />
        </div>
      </div>
    </div>
  );
}

function FinanceWorkspace({
  module,
  overview,
}: {
  module: ModuleConfig;
  overview: Awaited<ReturnType<typeof getDashboardOverview>>;
}) {
  const revenue = metricByLabel(overview.business_metrics, "Выручка");
  const expense = metricByLabel(overview.business_metrics, "Расходы");
  const flow = metricByLabel(overview.business_metrics, "Чистый поток");

  return (
    <div className="space-y-6">
      <StatsShelf stats={workspaceStatsFor(module.kind, overview, module.stats)} />

      <div className="space-y-6">
        <Surface className="p-6 sm:p-8">
          <PanelTitle eyebrow={module.accent ?? "Финансы"} title="Денежный поток и P&L" badge={overview.freshness} />
          <p className="mt-3 max-w-2xl text-sm leading-7 text-slate-400">
            Финансовый экран читает проводки из ядра и сразу показывает выручку, расходы, поток и финансовый итог.
          </p>

          <div className="mt-6 space-y-4">
            <ComparisonPanel
              title="Финансовое сравнение"
              badge="Поток"
              items={[
                { label: revenue?.label ?? "Выручка", value: revenue?.value ?? "0 USD", note: revenue?.note ?? "по проводкам" },
                { label: expense?.label ?? "Расходы", value: expense?.value ?? "0 USD", note: expense?.note ?? "по операциям" },
                { label: flow?.label ?? "Чистый поток", value: flow?.value ?? "0 USD", note: flow?.note ?? "чистый результат" },
              ]}
            />
            <TrendPanel trend={overview.trend} title="Финансовая динамика" badge="12 месяцев" />
          </div>

          <div className="mt-6 space-y-4">
            <DetailListPanel
              title="Последние платежи"
              badge="Платежи"
              subtitle="Поступления по сделкам и методы оплаты"
              items={overview.recent_payments.slice(0, 6)}
              emptyLabel="Платежи пока не загружены."
              renderItem={(payment) => (
                <div
                  key={payment.payment_id}
                  className="rounded-[18px] border border-[#3a3d43] bg-[#2E3137] px-4 py-3 transition hover:border-[#4a4e56] hover:bg-[#343840]/80"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="truncate font-semibold tracking-[-0.03em] text-[#f4f7fb]">
                        {payment.sale_number ?? "Без номера сделки"}
                      </p>
                      <p className="mt-1 truncate text-sm text-slate-400">{payment.business_name}</p>
                      <p className="mt-2 truncate text-xs text-slate-400">
                        {payment.method ?? "Метод не указан"} · {payment.paid_at}
                      </p>
                    </div>
                    <span className="text-sm font-semibold text-[#f4f7fb]">{formatMoneyValue(payment.amount, payment.currency)}</span>
                  </div>
                </div>
              )}
            />
            <DetailListPanel
              title="Бизнесы по выручке"
              badge="Рейтинг"
              subtitle="Кто приносит больше выручки и где выше поток"
              items={[...overview.businesses].sort((a, b) => extractNumber(b.revenue) - extractNumber(a.revenue)).slice(0, 6)}
              emptyLabel="Бизнесы пока не загружены."
              renderItem={(business) => (
                <div
                  key={business.business_id}
                  className="rounded-[18px] border border-[#3a3d43] bg-[#2E3137] px-4 py-3 transition hover:border-[#4a4e56] hover:bg-[#343840]/80"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="truncate font-semibold tracking-[-0.03em] text-[#f4f7fb]">{business.name}</p>
                      <p className="mt-1 truncate text-sm text-slate-400">
                        {business.external_ref ?? "Без external_ref"} · {business.sales} сделок
                      </p>
                      <p className="mt-2 truncate text-xs text-slate-400">
                        {business.source_systems} источн. · {business.contacts} контактов
                      </p>
                    </div>
                    <Badge variant="soft">{business.contacts} контактов</Badge>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2 text-sm text-slate-400">
                    <span>{formatMoneyValue(business.revenue)}</span>
                    <span>{formatMoneyValue(business.expense)}</span>
                    <span>{formatMoneyValue(business.net_flow)}</span>
                  </div>
                </div>
              )}
            />
          </div>
        </Surface>

        <SourceCloud
          title="Что тянем в финансы"
          badge="Источники"
          items={["Финансовое ядро", "Платежи и проводки", "Доходы и расходы", "Снимки KPI и партии"]}
        />
        <InsightStack title="Следующие действия" badge="Шаги" items={module.actions ?? []} />
      </div>
    </div>
  );
}

function MarketingWorkspace({
  module,
  overview,
}: {
  module: ModuleConfig;
  overview: Awaited<ReturnType<typeof getDashboardOverview>>;
}) {
  const marketing = metricByLabel(overview.business_metrics, "Маркетинг");
  const romi = metricByLabel(overview.business_metrics, "ROMI");
  const cac = metricByLabel(overview.business_metrics, "CAC");

  return (
    <div className="space-y-6">
      <StatsShelf stats={workspaceStatsFor(module.kind, overview, module.stats)} />

      <div className="space-y-6">
        <Surface className="p-6 sm:p-8">
          <PanelTitle eyebrow={module.accent ?? "Маркетинг"} title="Каналы, бюджет и эффективность" badge={overview.analysis_engine} />
          <p className="mt-3 max-w-2xl text-sm leading-7 text-slate-400">
            Маркетинговый экран объединяет каналы, бюджеты и реакцию аудитории. Данные подтягиваются из общего ядра и истории бизнеса.
          </p>

          <div className="mt-6 space-y-4">
            <MiniBarPanel
              title="Маркетинговый ритм"
              badge="Каналы"
              note="Маркетинг, ROMI и CAC как отдельные рабочие полосы."
              labels={["Маркетинг", "ROMI", "CAC", "Рост"]}
              values={[
                extractNumber(marketing?.value ?? "0"),
                Math.max(extractNumber(romi?.value ?? "0"), 1),
                Math.max(extractNumber(cac?.value ?? "0"), 1),
                overview.trend.values.reduce((sum, value) => sum + value, 0),
              ]}
            />
            <TrendPanel trend={overview.trend} title="Маркетинговая динамика" badge="Динамика" />
          </div>
        </Surface>

        <div className="space-y-6">
          <SignalBoard title="Каналы и реакция" badge={`${overview.signals.length} шт.`} signals={overview.signals} />
          <SourceCloud
            title="Данные из ядра"
            badge="Источники"
            items={["Маркетинговая активность", "Каналы и кампании", "Клики, конверсии и расходы", "Бизнес-выводы"]}
          />
          <InsightStack title="Что сделать дальше" badge="Шаги" items={module.actions ?? []} />
        </div>
      </div>
    </div>
  );
}

function InventoryWorkspace({
  module,
  overview,
}: {
  module: ModuleConfig;
  overview: Awaited<ReturnType<typeof getDashboardOverview>>;
}) {
  return (
    <div className="space-y-6">
      <StatsShelf stats={workspaceStatsFor(module.kind, overview, module.stats)} />

      <div className="space-y-6">
        <Surface className="p-6 sm:p-8">
          <PanelTitle eyebrow={module.accent ?? "Остатки"} title="Склад и готовность ядра" badge={overview.freshness} />
          <p className="mt-3 max-w-2xl text-sm leading-7 text-slate-400">
            Склад показывает остатки, движение товаров и готовность складского слоя в ядре данных.
          </p>

          <div className="mt-6 space-y-4">
            <StructurePanel title="Структура ядра" badge="Структура" structure={overview.structure} />
            <TrendPanel trend={overview.trend} title="История активности и роста" badge="Источники" />
          </div>

          <div className="mt-6 space-y-4">
            {overview.signals.slice(0, 2).map((signal) => (
              <div key={signal.title} className="rounded-[20px] border border-[#3a3d43] bg-[#343840] p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="font-semibold tracking-[-0.03em] text-[#f4f7fb]">{signal.title}</p>
                    <p className="mt-1 text-sm leading-5 text-slate-400">{signal.note}</p>
                  </div>
                  <Badge variant="soft">{signal.badge}</Badge>
                </div>
              </div>
            ))}
          </div>

          <div className="mt-6 space-y-4">
            <DetailListPanel
              title="Остатки по складу"
              badge="Склад"
              subtitle="Запасы, склады и товары"
              items={overview.inventory.slice(0, 6)}
              emptyLabel="Остатки пока не загружены."
              renderItem={(item) => (
                <div
                  key={`${item.warehouse_name}-${item.product_name}-${item.balance_at}`}
                  className="rounded-[18px] border border-[#3a3d43] bg-[#2E3137] px-4 py-3 transition hover:border-[#4a4e56] hover:bg-[#343840]/80"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="truncate font-semibold tracking-[-0.03em] text-[#f4f7fb]">{item.product_name}</p>
                      <p className="mt-1 truncate text-sm text-slate-400">
                        {item.warehouse_name} · {item.business_name}
                      </p>
                      <p className="mt-2 truncate text-xs text-slate-400">{formatDateTimeShort(item.balance_at)}</p>
                    </div>
                    <span className="text-sm font-semibold text-[#f4f7fb]">{item.quantity}</span>
                  </div>
                </div>
              )}
            />
            <DetailListPanel
              title="Топ товаров"
              badge="Продажи"
              subtitle="Какие позиции продаются лучше всего"
              items={overview.top_products.slice(0, 6)}
              emptyLabel="Товаров пока нет."
              renderItem={(product) => (
                <div
                  key={product.product_id}
                  className="rounded-[18px] border border-[#3a3d43] bg-[#2E3137] px-4 py-3 transition hover:border-[#4a4e56] hover:bg-[#343840]/80"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="truncate font-semibold tracking-[-0.03em] text-[#f4f7fb]">{product.name}</p>
                      <p className="mt-1 truncate text-sm text-slate-400">{product.business_name}</p>
                      <p className="mt-2 truncate text-xs text-slate-400">
                        {product.sold_quantity} продано · {product.stock_quantity} в остатке
                      </p>
                    </div>
                    <Badge variant="accent">{formatMoneyValue(product.sold_amount)}</Badge>
                  </div>
                </div>
              )}
            />
          </div>
        </Surface>

        <div className="space-y-6">
          <SourceCloud
            title="Организации бизнеса"
            badge="Источники"
            items={["Организации", "Складские источники", "Товарные позиции", "Проверка целостности данных"]}
          />
          <InsightStack title="Что делать дальше" badge="Шаги" items={module.actions ?? []} />
        </div>
      </div>
    </div>
  );
}

function TelegramWorkspace({
  module,
  overview,
}: {
  module: ModuleConfig;
  overview: Awaited<ReturnType<typeof getDashboardOverview>>;
}) {
  return (
    <div className="space-y-6">
      <StatsShelf stats={workspaceStatsFor(module.kind, overview, module.stats)} />

      <div className="space-y-6">
        <Surface className="p-6 sm:p-8">
          <PanelTitle eyebrow={module.accent ?? "Телеграм"} title="Сообщения, каналы и реакции" badge={overview.analysis_engine} />
          <p className="mt-3 max-w-2xl text-sm leading-7 text-slate-400">
            Модуль показывает каналы, сообщения и реакцию аудитории как часть общей картины бизнеса.
          </p>

          <div className="mt-6 space-y-4">
            <SignalBoard title="Коммуникационные сигналы" badge="Телеграм" signals={overview.signals} />
            <MiniBarPanel
              title="Ритм канала"
              badge="Ритм канала"
              note="Охват, сообщения и реакция аудитории как отдельные полосы."
              labels={["Каналы", "Сообщения", "Охват", "Триггеры"]}
              values={[
                extractNumber(module.stats?.[0]?.value ?? "0"),
                extractNumber(module.stats?.[1]?.value ?? "0"),
                extractNumber(module.stats?.[2]?.value ?? "0"),
                overview.trend.values.reduce((sum, value) => sum + value, 0),
              ]}
            />
          </div>
        </Surface>

        <div className="space-y-6">
          <SourceCloud
            title="Телеграм-источники"
            badge="Источники"
            items={["Телеграм-каналы", "Сообщения и реакции", "Связь с маркетингом", "Триггеры для руководителя"]}
          />
          <InsightStack title="Поток выводов" badge="Выводы" items={overview.ai_insights.slice(0, 3)} />
          <InsightStack title="Следующий шаг" badge="Шаги" items={module.actions ?? []} />
        </div>
      </div>
    </div>
  );
}

function AlertsWorkspace({
  module,
  overview,
}: {
  module: ModuleConfig;
  overview: Awaited<ReturnType<typeof getDashboardOverview>>;
}) {
  return (
    <div className="space-y-6">
      <StatsShelf stats={workspaceStatsFor(module.kind, overview, module.stats)} />

      <div className="space-y-6">
        <Surface className="p-6 sm:p-8">
          <PanelTitle eyebrow={module.accent ?? "Сигналы"} title="Сигналы и приоритеты" badge={overview.signals.length.toString()} />
          <p className="mt-3 max-w-2xl text-sm leading-7 text-slate-400">
            Этот экран показывает важные события без шума. Всё, что не требует внимания, отсеивается. Остаются только приоритеты и их смысл.
          </p>

          <div className="mt-6 space-y-4">
            <SignalBoard title="Приоритетные сигналы" badge="Сигналы" signals={overview.signals} />
            <MiniBarPanel
              title="Интенсивность"
              badge="Приоритет"
              note="Каждый уровень сигнала имеет свою полосу и помогает быстро понять риск."
              labels={overview.signals.map((signal, index) => String(index + 1))}
              values={overview.signals.map((_, index) => 100 - index * 18)}
            />
          </div>
        </Surface>

        <div className="space-y-6">
          <InsightStack title="Что важно видеть" badge="Бизнес" items={overview.ai_insights.slice(0, 4)} />
          <SourceCloud title="Откуда приходят сигналы" badge="Источники" items={module.points} />
        </div>
      </div>
    </div>
  );
}

function CEOWorkspace({
  module,
  overview,
}: {
  module: ModuleConfig;
  overview: Awaited<ReturnType<typeof getDashboardOverview>>;
}) {
  const rankedBusinesses = [...overview.businesses].sort((a, b) => extractNumber(b.revenue) - extractNumber(a.revenue));

  return (
    <div className="space-y-6">
      <StatsShelf stats={overview.executive_summary as ModuleConfig["stats"]} />

      <div className="space-y-6">
        <Surface className="p-6 sm:p-8">
          <PanelTitle eyebrow={module.accent ?? "Руководитель"} title="Единый стратегический обзор" badge={overview.analysis_engine} />
          <p className="mt-3 max-w-3xl text-sm leading-7 text-slate-400">
            Руководительский экран собирает картину бизнеса в один обзор: активность, потоки, риски и дальнейшие шаги.
          </p>

          <div className="mt-6 space-y-4">
            <TrendPanel trend={overview.trend} title="Динамика бизнеса" badge={overview.trend.badge} />
            <StructurePanel title="Структура бизнеса" badge="Структура" structure={overview.structure} />
          </div>

          <div className="mt-6 space-y-4">
            <DetailListPanel
              title="Бизнесы и потоки"
              badge="Организации"
              subtitle="Выручка, расходы и чистый поток по каждой организации"
              items={rankedBusinesses.slice(0, 6)}
              emptyLabel="Бизнесы пока не загружены."
              renderItem={(business) => (
                <div
                  key={business.business_id}
                  className="rounded-[18px] border border-[#3a3d43] bg-[#2E3137] px-4 py-3 transition hover:border-[#4a4e56] hover:bg-[#343840]/80"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="truncate font-semibold tracking-[-0.03em] text-[#f4f7fb]">{business.name}</p>
                      <p className="mt-1 truncate text-sm text-slate-400">
                        {business.external_ref ?? "Без external_ref"} · {business.sales} сделок
                      </p>
                      <p className="mt-2 truncate text-xs text-slate-400">
                        {business.contacts} контактов · {business.source_systems} источн.
                      </p>
                    </div>
                    <Badge variant="soft">{business.contacts} контактов</Badge>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2 text-sm text-slate-400">
                    <span>{formatMoneyValue(business.revenue)}</span>
                    <span>{formatMoneyValue(business.expense)}</span>
                    <span>{formatMoneyValue(business.net_flow)}</span>
                  </div>
                </div>
              )}
            />
            <DetailListPanel
              title="Последние продажи"
              badge="Сделки"
              subtitle="Что продано и по какой сумме"
              items={overview.recent_sales.slice(0, 6)}
              emptyLabel="Продажи пока не загружены."
              renderItem={(sale) => (
                <div
                  key={sale.sale_id}
                  className="rounded-[18px] border border-[#3a3d43] bg-[#2E3137] px-4 py-3 transition hover:border-[#4a4e56] hover:bg-[#343840]/80"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="truncate font-semibold tracking-[-0.03em] text-[#f4f7fb]">{sale.sale_number}</p>
                      <p className="mt-1 truncate text-sm text-slate-400">{sale.business_name}</p>
                      <p className="mt-2 truncate text-xs text-slate-400">
                        {sale.items_count} строк · {sale.products_count} товаров
                      </p>
                    </div>
                    <Badge variant="soft">{sale.stage}</Badge>
                  </div>
                  <div className="mt-3 text-sm font-semibold text-[#f4f7fb]">{formatMoneyValue(sale.amount, sale.currency)}</div>
                </div>
              )}
            />
          </div>
        </Surface>

        <div className="space-y-6">
          <SignalBoard title="Сигналы под контролем" badge="Руководитель" signals={overview.signals} />
          <InsightStack title="Бизнес-выводы" badge="Выводы" items={overview.ai_insights} />
        </div>
      </div>

      <div className="space-y-6">
        <SourceCloud title="Приоритеты и контекст" badge="Действия" items={module.actions ?? []} />
        <SourceCloud title="Источники обзора" badge="Источники" items={module.sources ?? []} />
      </div>
    </div>
  );
}

function RecommendationsWorkspace({
  module,
  overview,
}: {
  module: ModuleConfig;
  overview: Awaited<ReturnType<typeof getDashboardOverview>>;
}) {
  return (
    <div className="space-y-6">
      <StatsShelf stats={workspaceStatsFor(module.kind, overview, module.stats)} />

      <div className="space-y-6">
        <Surface className="p-6 sm:p-8">
          <PanelTitle eyebrow={module.accent ?? "Рекомендации"} title="Следующий лучший шаг" badge="Бизнес" />
          <p className="mt-3 max-w-3xl text-sm leading-7 text-slate-400">
            Рекомендации строятся поверх всей истории. Здесь нет абстракций: только реальные подсказки, связанные с данными из ядра.
          </p>

          <div className="mt-6 space-y-4">
            <InsightStack title="Рекомендации по приоритету" badge="Приоритеты" items={overview.ai_insights} />
            <MiniBarPanel
              title="Сила рекомендации"
              badge="Влияние"
              note="Каждый шаг можно оценивать по влиянию на бизнес."
              labels={overview.ai_insights.map((_, index) => `#${index + 1}`)}
              values={overview.ai_insights.map((_, index) => 100 - index * 17)}
            />
          </div>
        </Surface>

        <div className="space-y-6">
          <SignalBoard title="Что влияет на рекомендации" badge="Сигналы" signals={overview.signals} />
          <SourceCloud title="Контекст для решений" badge="Источники" items={[...(module.points ?? []), ...(module.sources ?? [])]} />
        </div>
      </div>
    </div>
  );
}

function DetailListPanel<T>({
  title,
  badge,
  subtitle,
  items,
  emptyLabel,
  renderItem,
}: {
  title: string;
  badge: string;
  subtitle: string;
  items: T[];
  emptyLabel: string;
  renderItem: (item: T, index: number) => ReactNode;
}) {
  return (
    <Surface className="p-6 sm:p-7">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-[0.24em] text-slate-400">{badge}</p>
          <h4 className="mt-2 text-lg font-semibold tracking-[-0.04em] text-[#f4f7fb]">{title}</h4>
          <p className="mt-1 text-sm leading-6 text-slate-400">{subtitle}</p>
        </div>
        <Badge variant="soft">{items.length}</Badge>
      </div>

      <div className="mt-4 max-h-[460px] space-y-2 overflow-y-auto pr-1">
        {items.length ? (
          items.map((item, index) => renderItem(item, index))
        ) : (
          <div className="rounded-[20px] border border-dashed border-[#3a3d43] bg-[#343840] p-4 text-sm text-slate-400">
            {emptyLabel}
          </div>
        )}
      </div>
    </Surface>
  );
}

function PanelTitle({
  eyebrow,
  title,
  badge,
}: {
  eyebrow: string;
  title: string;
  badge?: string;
}) {
  return (
    <div className="flex items-start justify-between gap-3">
      <div>
        <p className="text-xs uppercase tracking-[0.28em] text-slate-400">{eyebrow}</p>
        <h3 className="mt-2 text-2xl font-semibold tracking-[-0.05em] text-[#f4f7fb]">{title}</h3>
      </div>
      {badge ? <Badge variant="soft">{badge}</Badge> : null}
    </div>
  );
}

function TrendPanel({
  title,
  badge,
  trend,
}: {
  title: string;
  badge: string;
  trend: Awaited<ReturnType<typeof getDashboardOverview>>["trend"];
}) {
  const maxValue = Math.max(...trend.values, 1);

  return (
    <div className="rounded-[26px] border border-[#3a3d43] bg-[linear-gradient(180deg,#2E3137_0%,#26292e_100%)] p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-[0.24em] text-slate-400">{badge}</p>
          <h4 className="mt-2 text-lg font-semibold tracking-[-0.04em] text-[#f4f7fb]">{title}</h4>
          <p className="mt-1 text-sm leading-5 text-slate-400">{trend.description}</p>
        </div>
        <Badge variant="accent">{trend.badge}</Badge>
      </div>

      <div className="mt-5 grid grid-cols-12 items-end gap-2">
        {trend.values.map((value, index) => {
          const height = Math.max(12, Math.round((value / maxValue) * 100));

          return (
            <div key={trend.labels[index] ?? index} className="flex flex-col items-center gap-2">
              <div className="flex h-[120px] w-full items-end rounded-[18px] bg-[#2E3137]/70 px-1.5 py-1.5">
                <div
                  className="w-full rounded-t-2xl bg-gradient-to-t from-yellow-300 to-amber-400"
                  style={{ height: `${height}%` }}
                />
              </div>
              <span className="text-[11px] text-slate-400">{trend.labels[index]}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function StatsShelf({ stats }: { stats?: ModuleConfig["stats"] }) {
  if (!stats?.length) {
    return null;
  }

  return (
    <div className="flex gap-3 overflow-x-auto pb-1">
      {stats.map((stat) => (
        <div key={stat.label} className="min-w-[260px] flex-1">
          <MetricTile
            label={stat.label}
            value={stat.value}
            note={stat.note}
            size="compact"
            variant={metricVariantForLabel(stat.label)}
          />
        </div>
      ))}
    </div>
  );
}

function MiniBarPanel({
  title,
  badge,
  labels,
  values,
  note,
}: {
  title: string;
  badge: string;
  labels: string[];
  values: number[];
  note: string;
}) {
  const maxValue = Math.max(...values, 1);

  return (
    <div className="rounded-[26px] border border-[#3a3d43] bg-[linear-gradient(180deg,#2E3137_0%,#26292e_100%)] p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-[0.24em] text-slate-400">{badge}</p>
          <h4 className="mt-2 text-lg font-semibold tracking-[-0.04em] text-[#f4f7fb]">{title}</h4>
          <p className="mt-1 text-sm leading-5 text-slate-400">{note}</p>
        </div>
        <Badge variant="accent">{badge}</Badge>
      </div>

      <div
        className="mt-5 grid items-end gap-2"
        style={{ gridTemplateColumns: `repeat(${Math.max(values.length, 1)}, minmax(0, 1fr))` }}
      >
        {values.map((value, index) => {
          const height = Math.max(10, Math.round((value / maxValue) * 100));
          return (
            <div key={`${labels[index] ?? "bar"}-${index}`} className="flex flex-col items-center gap-2">
              <div className="flex h-[130px] w-full items-end rounded-[18px] bg-[#2E3137]/70 px-1.5 py-1.5">
                <div className="w-full rounded-t-2xl bg-gradient-to-t from-yellow-300 via-amber-400 to-amber-300" style={{ height: `${height}%` }} />
              </div>
              <span className="text-[11px] text-slate-400">{labels[index]}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function ComparisonPanel({
  title,
  badge,
  items,
}: {
  title: string;
  badge: string;
  items: Array<{ label: string; value: string; note: string; color?: string }>;
}) {
  const maxValue = Math.max(...items.map((item) => extractNumber(item.value)), 1);

  return (
    <div className="rounded-[26px] border border-[#3a3d43] bg-[#2E3137] p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-[0.24em] text-slate-400">{badge}</p>
          <h4 className="mt-2 text-lg font-semibold tracking-[-0.04em] text-[#f4f7fb]">{title}</h4>
        </div>
        <Badge variant="soft">{items.length}</Badge>
      </div>

      <div className="mt-4 grid gap-3">
        {items.map((item) => {
          const width = Math.max(8, Math.round((extractNumber(item.value) / maxValue) * 100));
          return (
            <div key={item.label} className="rounded-[18px] border border-[#3a3d43] bg-[#343840] p-3">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="font-medium text-[#f4f7fb]">{item.label}</p>
                  <p className="mt-1 text-sm leading-5 text-slate-400">{item.note}</p>
                </div>
                <p className="shrink-0 font-semibold tracking-[-0.03em] text-[#f4f7fb]">{item.value}</p>
              </div>
              <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-[#2E3137]">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-yellow-300 via-amber-400 to-amber-300"
                  style={{ width: `${width}%`, background: item.color ?? undefined }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function StructurePanel({
  title,
  badge,
  structure,
}: {
  title: string;
  badge: string;
  structure: Awaited<ReturnType<typeof getDashboardOverview>>["structure"];
}) {
  const total = Math.max(structure.reduce((sum, item) => sum + extractNumber(item.value), 0), 100);
  const sections = structure.map((item) => `${item.color} ${extractNumber(item.value)}%`);

  return (
    <div className="rounded-[26px] border border-[#3a3d43] bg-[linear-gradient(180deg,#2E3137_0%,#26292e_100%)] p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-[0.24em] text-slate-400">{badge}</p>
          <h4 className="mt-2 text-lg font-semibold tracking-[-0.04em] text-[#f4f7fb]">{title}</h4>
        </div>
        <Badge variant="soft">{structure.length}</Badge>
      </div>

      <div className="mt-5 space-y-4">
        <div className="flex items-center justify-center">
          <div
            className="relative flex h-40 w-40 items-center justify-center rounded-full border border-[#3a3d43] bg-[#2E3137] shadow-[inset_0_0_0_12px_#3a3d43]"
            style={{
              background: `conic-gradient(${sections.join(", ")})`,
            }}
          >
            <div className="flex h-24 w-24 flex-col items-center justify-center rounded-full border border-[#3a3d43] bg-[#2E3137] text-center">
              <p className="text-xs uppercase tracking-[0.24em] text-slate-400">Структура</p>
              <p className="mt-1 text-2xl font-semibold tracking-[-0.05em] text-[#f4f7fb]">
                {Math.round(total / Math.max(structure.length, 1))}%
              </p>
            </div>
          </div>
        </div>

        <div className="space-y-3">
          {structure.map((item) => (
            <div key={item.label} className="rounded-[18px] border border-[#3a3d43] bg-[#2E3137] p-3">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: item.color }} />
                    <p className="font-medium text-[#f4f7fb]">{item.label}</p>
                  </div>
                  <p className="mt-1 text-sm leading-5 text-slate-400">{item.note}</p>
                </div>
                <p className="shrink-0 font-semibold tracking-[-0.03em] text-[#f4f7fb]">{item.value}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function SignalBoard({
  title,
  badge,
  signals,
}: {
  title: string;
  badge: string;
  signals: Awaited<ReturnType<typeof getDashboardOverview>>["signals"];
}) {
  return (
    <div className="rounded-[26px] border border-[#3a3d43] bg-[#2E3137] p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-[0.24em] text-slate-400">{badge}</p>
          <h4 className="mt-2 text-lg font-semibold tracking-[-0.04em] text-[#f4f7fb]">{title}</h4>
        </div>
        <Badge variant="soft">{signals.length}</Badge>
      </div>

      <div className="mt-4 grid gap-3">
        {signals.map((signal, index) => (
          <div key={`${signal.title}-${index}`} className="rounded-[18px] border border-[#3a3d43] bg-[#343840] p-3">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="font-medium tracking-[-0.03em] text-[#f4f7fb]">{signal.title}</p>
                <p className="mt-1 text-sm leading-5 text-slate-400">{signal.note}</p>
              </div>
              <Badge variant="soft">{signal.badge}</Badge>
            </div>
            <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-[#2E3137]">
              <div
                className="h-full rounded-full bg-gradient-to-r from-yellow-300 via-amber-400 to-amber-300"
                style={{ width: `${Math.max(22, 100 - index * 15)}%` }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function SourceCloud({
  title,
  badge,
  items,
}: {
  title: string;
  badge: string;
  items: string[];
}) {
  return (
    <div className="rounded-[26px] border border-[#3a3d43] bg-[linear-gradient(180deg,#2E3137_0%,#26292e_100%)] p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-[0.24em] text-slate-400">{badge}</p>
          <h4 className="mt-2 text-lg font-semibold tracking-[-0.04em] text-[#f4f7fb]">{title}</h4>
        </div>
        <Badge variant="soft">{items.length}</Badge>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        {items.map((item) => (
          <span
            key={item}
            className="rounded-full border border-[#3a3d43] bg-[#2E3137] px-3 py-1.5 text-sm leading-5 text-slate-200"
          >
            {item}
          </span>
        ))}
      </div>
    </div>
  );
}

function InsightStack({
  title,
  badge,
  items,
}: {
  title: string;
  badge: string;
  items: string[];
}) {
  return (
    <div className="rounded-[26px] border border-[#3a3d43] bg-[#2E3137] p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-[0.24em] text-slate-400">{badge}</p>
          <h4 className="mt-2 text-lg font-semibold tracking-[-0.04em] text-[#f4f7fb]">{title}</h4>
        </div>
        <Badge variant="accent">Бизнес</Badge>
      </div>

      <div className="mt-4 grid gap-3">
        {items.map((item, index) => (
          <div key={`${item}-${index}`} className="rounded-[18px] border border-[#3a3d43] bg-[#343840] p-3">
            <div className="flex items-start gap-3">
              <span className="mt-1 h-2.5 w-2.5 shrink-0 rounded-full bg-[#FFF27A]" />
              <p className="text-sm leading-6 text-slate-200">{item}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function metricVariantForLabel(label: string): MetricTileVariant {
  const normalized = label.toLowerCase();

  if (normalized.includes("выруч")) {
    return "revenue";
  }

  if (normalized.includes("расход")) {
    return "expense";
  }

  if (normalized.includes("поток") || normalized.includes("cash") || normalized.includes("p&l")) {
    return "flow";
  }

  if (normalized.includes("маркет")) {
    return "marketing";
  }

  if (normalized.includes("cac") || normalized.includes("стоим")) {
    return "cac";
  }

  if (normalized.includes("romi")) {
    return "romi";
  }

  return "default";
}

function extractNumber(value: string) {
  return parseMoneyValue(value);
}

function formatDateTimeShort(value: string | null | undefined) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function metricByLabel(cards: OverviewCard[], label: string) {
  return cards.find((card) => card.label === label);
}
