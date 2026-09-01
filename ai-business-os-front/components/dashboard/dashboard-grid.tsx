"use client";

import { type ChangeEvent, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import {
  Responsive,
  type LayoutItem,
  type ResponsiveLayouts,
} from "react-grid-layout/legacy";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Drawer } from "@/components/ui/drawer";
import { FilterChip } from "@/components/ui/filter-chip";
import { Dropdown } from "@/components/ui/dropdown";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Surface } from "@/components/ui/surface";
import { useBusinessContext } from "@/components/business/business-context-provider";
import { AiPreviewBanner } from "@/components/dashboard/ai-preview-banner";
import { AiSuggestionsButton } from "@/components/dashboard/ai-suggestions-button";
import { AiSuggestionsDrawer } from "@/components/dashboard/ai-suggestions-drawer";
import { useDashboardManifest, useOptionalDashboardManifest } from "@/components/dashboard/dashboard-manifest-provider";
import { cn } from "@/lib/cn";
import {
  dedupeWidgets,
  dedupeWidgetSignatures,
  snapWidgetSemanticSize,
  widgetLayoutGroup,
  widgetCanResize,
} from "@/lib/launcher/layout-engine";
import {
  createDevelopmentLauncherSuggestions,
  evaluateLauncherSuggestion,
} from "@/lib/launcher/ai-suggestions";
import {
  breakpointForWidth,
  composeResponsiveLauncherLayouts,
  createDefaultLauncherState,
  deriveLauncherOrder,
  LAUNCHER_BREAKPOINTS,
  LAUNCHER_COLUMNS,
  normalizeLauncherState,
  updateLauncherWidgetSize,
} from "@/lib/launcher/composer";
import {
  clearLauncherState,
  loadLauncherState,
  saveLauncherState,
} from "@/lib/launcher/state-persistence";
import {
  clampSize,
  getLauncherVariantFromGrid,
  launcherSemanticSizeOptions,
  semanticSizeToLauncherSize,
} from "@/lib/launcher/size-mapping";
import { getWidgetSizeContract } from "@/lib/launcher/widget-registry";
import type {
  LauncherSemanticSize,
  LauncherState,
  LauncherSuggestion,
  LauncherSuggestionPreview,
  LauncherWidgetVariant,
} from "@/lib/launcher/types";
import {
  type AnalyticsDataStatus,
  type AnalyticsMetricValue,
  type DashboardManifestDataQuality,
  type DashboardSemanticSize,
  type DashboardManifestWidget,
  type DashboardWidgetType,
} from "@/lib/core-api";
import { getAiProviders, getAiRouting, getDashboardAIAnalysisStatus, getDashboardAIInsights, getDashboardManifest, runDashboardAIAnalysis, streamAiChat, type AiProvider } from "@/lib/core-api";

type SerializedMetricValue = AnalyticsMetricValue;

type ExecutiveNumber = {
  label?: string;
  current?: string | number | null;
  previous?: string | number | null;
  delta?: string | number | null;
  direction?: string | null;
};

type SerializedProductRow = {
  product_id?: string | null;
  product_external_id?: string | null;
  product_name?: string | null;
  organization_id?: string | null;
  organization_name?: string | null;
  sold_units?: SerializedMetricValue;
  revenue?: SerializedMetricValue;
  orders_count?: SerializedMetricValue;
  customers_count?: SerializedMetricValue;
  average_selling_price?: SerializedMetricValue;
  returns_quantity?: SerializedMetricValue;
  returns_amount?: SerializedMetricValue;
  return_rate?: SerializedMetricValue;
  current_stock?: SerializedMetricValue;
  stock_value?: SerializedMetricValue;
  sales_velocity_7d?: SerializedMetricValue;
  sales_velocity_30d?: SerializedMetricValue;
  days_of_stock?: SerializedMetricValue;
  sales_change_pct?: SerializedMetricValue;
  units_change_pct?: SerializedMetricValue;
  revenue_change_pct?: SerializedMetricValue;
  classification?: string | null;
  classification_tags?: string[];
  stockout_risk?: string | null;
  first_sale_date?: string | null;
  last_sale_date?: string | null;
  data_status?: AnalyticsDataStatus;
};

type SerializedCustomerRow = {
  customer_external_id?: string | null;
  customer_name?: string | null;
  organization_ids?: string[];
  orders_count?: SerializedMetricValue;
  revenue?: SerializedMetricValue;
  sold_units?: SerializedMetricValue;
  average_order_value?: SerializedMetricValue;
  days_since_last_order?: SerializedMetricValue;
  purchase_frequency?: SerializedMetricValue;
  returns_count?: SerializedMetricValue;
  returns_amount?: SerializedMetricValue;
  visits_count?: SerializedMetricValue;
  products_count?: SerializedMetricValue;
  organizations_count?: SerializedMetricValue;
  customer_value_score?: SerializedMetricValue;
  segment?: string | null;
  first_order_date?: string | null;
  last_order_date?: string | null;
  data_status?: AnalyticsDataStatus;
};

type SerializedOrganizationRow = {
  organization_id: string;
  organization_name: string;
  metrics: Record<string, SerializedMetricValue>;
  products_sold?: SerializedMetricValue;
  sales_reps?: SerializedMetricValue;
  visits?: SerializedMetricValue;
  stock?: SerializedMetricValue;
  data_status?: AnalyticsDataStatus;
};

type SerializedInventoryOpportunity = {
  product_external_id?: string | null;
  product_name?: string | null;
  from_organization_id?: string;
  from_organization_name?: string;
  to_organization_id?: string;
  to_organization_name?: string;
  source_stock?: SerializedMetricValue;
  destination_stock?: SerializedMetricValue;
  source_days?: SerializedMetricValue;
  destination_days?: SerializedMetricValue;
  source_velocity?: SerializedMetricValue;
  destination_velocity?: SerializedMetricValue;
  reason?: string | null;
};

type SerializedSalesRepRow = {
  sales_rep_external_id?: string | null;
  sales_rep_name?: string | null;
  organization_id?: string | null;
  organization_name?: string | null;
  visits_count?: SerializedMetricValue;
  orders_count?: SerializedMetricValue;
  revenue?: SerializedMetricValue;
  sold_units?: SerializedMetricValue;
  average_order_value?: SerializedMetricValue;
  conversion_rate?: SerializedMetricValue;
  last_visit_date?: string | null;
  data_status?: AnalyticsDataStatus;
};

type SerializedAIInsight = {
  id?: string;
  type?: string;
  severity?: string;
  title?: string;
  summary?: string;
  recommendation?: string | null;
  confidence?: number | null;
  metric_key?: string | null;
  entity_type?: string | null;
  entity_id?: string | null;
  organization_ids?: string[];
  metrics?: ExecutiveNumber[];
  evidence?: unknown[];
  tags?: string[];
};

type ChatTile = {
  title: string;
  icon: "chat" | "head";
};

type ModelItem = {
  providerId: string;
  name: string;
  models: Array<{ id: string; name: string; available?: boolean }>;
  icon: "ollama" | "chatgpt" | "claude" | "grok" | "deepseek" | "generic";
};

type ChatAttachment = {
  id: string;
  name: string;
  type: string;
  size: number;
  kind: "file" | "image";
  content: string | null;
  dataUrl: string | null;
};

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  text: string;
  attachments: ChatAttachment[];
  providerName?: string;
  modelName?: string;
};

type AssistantFileAttachment = {
  id: string;
  name: string;
  type: string;
  content: string;
  size: number;
};

const QUICK_ACTION_PROMPTS: Record<string, string> = {
  "Обсудить продажи":
    "Проведи краткий анализ продаж по текущей выбранной организации и текущему периоду. Покажи выручку, количество заказов, средний заказ, проданные единицы и возвраты. Затем выдели самые важные изменения или проблемы и кратко объясни, на что руководителю стоит обратить внимание. Используй только реальные данные AI Business OS. Если каких-либо данных нет, прямо скажи об этом.",
  "Проверить склад":
    "Проверь текущее состояние склада по выбранной организации. Найди товары с риском дефицита, отсутствующими остатками, необычными остатками или другими доступными товарными сигналами. Сначала покажи наиболее важные проблемы, затем дай краткие рекомендации руководителю. Используй только реальные данные AI Business OS. Не придумывай остатки или проблемы, которых нет в данных.",
  "Собрать сводку":
    "Подготовь краткую управленческую сводку по текущей организации и выбранному периоду. Включи основные показатели бизнеса: выручку, заказы, средний заказ, проданные единицы, возвраты и другие доступные важные показатели. После цифр выдели 3 самых важных вывода для руководителя и действия, которые стоит рассмотреть. Используй только реальные данные AI Business OS.",
  "Создать виджет через ИИ":
    "Я хочу создать новый виджет для панели AI Business OS. Помоги определить, какой виджет нужен. Сначала спроси меня, какую информацию или показатель я хочу видеть на виджете. Не создавай виджет, пока не получишь от меня описание.",
};

type WidgetCatalogItem = {
  widget_type: DashboardWidgetType;
  title: string;
  description: string;
};

const CUSTOM_WIDGETS_STORAGE_KEY = "ai-business-os:dashboard-custom-widgets:v1";
const CHAT_STATE_STORAGE_KEY = "ai-business-os:dashboard-chat:v1";
const AI_THOUGHTS_STORAGE_KEY = "ai-business-os:dashboard-ai-thoughts:v1";

type AIThought = { label: string; title: string; text: string };

function loadCachedAIThoughts(): AIThought[] {
  if (typeof window === "undefined") return [];
  try {
    const parsed = JSON.parse(window.sessionStorage.getItem(AI_THOUGHTS_STORAGE_KEY) ?? "null");
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((item): item is AIThought => (
      item !== null
      && typeof item === "object"
      && typeof item.label === "string"
      && typeof item.title === "string"
      && typeof item.text === "string"
    ));
  } catch {
    return [];
  }
}

function cacheAIThoughts(thoughts: AIThought[]) {
  try {
    window.sessionStorage.setItem(AI_THOUGHTS_STORAGE_KEY, JSON.stringify(thoughts));
  } catch {
    // Keep the in-memory result when browser storage is unavailable.
  }
}
const ALL_WIDGET_TYPES: DashboardWidgetType[] = [
  "kpi",
  "trend",
  "line_chart",
  "bar_chart",
  "ranking",
  "table",
  "alert",
  "product_alert",
  "customer_alert",
  "inventory_alert",
  "watchlist",
  "organization_comparison",
  "product_ranking",
  "customer_ranking",
  "inventory_risk",
  "visit_summary",
  "data_quality",
  "sales_rep_performance",
  "ai_insight",
  "ai_recommendation",
  "photo_alert",
];

function readStoredCustomWidgets() {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(CUSTOM_WIDGETS_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    return Array.isArray(parsed) ? (parsed as DashboardManifestWidget[]) : [];
  } catch {
    return [];
  }
}

function storeCustomWidgets(widgets: DashboardManifestWidget[]) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(CUSTOM_WIDGETS_STORAGE_KEY, JSON.stringify(widgets));
  } catch {
    // Ignore persistence failures. The grid still works with in-memory state.
  }
}

function widgetCatalogTitle(widgetType: DashboardWidgetType) {
  switch (widgetType) {
    case "kpi":
      return "KPI";
    case "trend":
      return "Динамика";
    case "line_chart":
      return "Линейный график";
    case "bar_chart":
      return "Столбчатый график";
    case "ranking":
      return "Рейтинг";
    case "table":
      return "Таблица";
    case "alert":
      return "Сигнал";
    case "product_alert":
      return "Товарный сигнал";
    case "customer_alert":
      return "Клиентский сигнал";
    case "inventory_alert":
      return "Складской сигнал";
    case "watchlist":
      return "На контроле";
    case "organization_comparison":
      return "Сравнение организаций";
    case "product_ranking":
      return "Топ товаров";
    case "customer_ranking":
      return "Топ клиентов";
    case "inventory_risk":
      return "Риски запасов";
    case "visit_summary":
      return "Визиты";
    case "data_quality":
      return "Качество данных";
    case "sales_rep_performance":
      return "Менеджеры";
    case "ai_insight":
      return "AI вывод";
    case "ai_recommendation":
      return "AI рекомендация";
    case "photo_alert":
      return "Фото-сигнал";
    default:
      return widgetType;
  }
}

function widgetCatalogDescription(widgetType: DashboardWidgetType) {
  switch (widgetType) {
    case "kpi":
      return "Одна ключевая метрика с крупным числом.";
    case "trend":
    case "line_chart":
    case "bar_chart":
      return "График динамики по периоду.";
    case "ranking":
    case "product_ranking":
    case "customer_ranking":
      return "Список лидеров с ранжированием.";
    case "table":
    case "organization_comparison":
      return "Табличное сравнение показателей.";
    case "alert":
    case "product_alert":
    case "customer_alert":
    case "inventory_alert":
    case "photo_alert":
      return "Сигнал с рекомендацией и доказательствами.";
    case "watchlist":
      return "Сводка важных сигналов.";
    case "inventory_risk":
      return "Риски по остаткам и перемещениям.";
    case "visit_summary":
      return "Краткая сводка по визитам и менеджерам.";
    case "data_quality":
      return "Статус качества данных и ограничения.";
    case "sales_rep_performance":
      return "Показатели по менеджерам продаж.";
    case "ai_insight":
    case "ai_recommendation":
      return "Подсказка или рекомендация от AI.";
    default:
      return "Готовый виджет для дашборда.";
  }
}

function createMetricPreview(value: number, previous: number, unit = "number"): SerializedMetricValue {
  return {
    value,
    previous_value: previous,
    delta: value - previous,
    percent_delta: previous === 0 ? null : ((value - previous) / previous) * 100,
    unit,
    status: "AVAILABLE",
    data_status: "AVAILABLE",
    coverage: 1,
    confidence: 0.98,
    currency: unit === "currency" ? "UZS" : null,
    record_count: 42,
    note: "Шаблонные данные для превью",
  };
}

function buildWidgetPreviewPayload(widgetType: DashboardWidgetType, organizationName: string): Record<string, unknown> {
  const series = [
    { organization_name: organizationName, value: 128000 },
    { organization_name: "Сегмент 2", value: 94000 },
    { organization_name: "Сегмент 3", value: 151000 },
  ];

  switch (widgetType) {
    case "kpi":
      return { metric: createMetricPreview(128000, 118000, "currency"), metric_key: "revenue" };
    case "trend":
    case "line_chart":
    case "bar_chart":
      return {
        metric: createMetricPreview(128000, 118000, "currency"),
        series,
        period_label: "За последние 30 дней",
      };
    case "organization_comparison":
      return {
        rows: [
          {
            organization_id: "org-1",
            organization_name: organizationName,
            metrics: {
              revenue: createMetricPreview(128000, 118000, "currency"),
              orders: createMetricPreview(840, 790),
              sold_units: createMetricPreview(1420, 1330),
              payments_received: createMetricPreview(121500, 117200, "currency"),
              customers: createMetricPreview(210, 198),
            },
          },
          {
            organization_id: "org-2",
            organization_name: "Сравнение 2",
            metrics: {
              revenue: createMetricPreview(97000, 90500, "currency"),
              orders: createMetricPreview(630, 590),
              sold_units: createMetricPreview(1010, 960),
              payments_received: createMetricPreview(94000, 90500, "currency"),
              customers: createMetricPreview(174, 162),
            },
          },
        ],
      };
    case "product_ranking":
    case "ranking":
      return {
        rows: [
          {
            product_name: "Товар A",
            organization_name: organizationName,
            revenue: createMetricPreview(54000, 48200, "currency"),
            sold_units: createMetricPreview(420, 390),
            current_stock: createMetricPreview(88, 75),
            orders_count: createMetricPreview(112, 101),
          },
          {
            product_name: "Товар B",
            organization_name: organizationName,
            revenue: createMetricPreview(47000, 44000, "currency"),
            sold_units: createMetricPreview(380, 360),
            current_stock: createMetricPreview(61, 54),
            orders_count: createMetricPreview(98, 90),
          },
        ],
      };
    case "customer_ranking":
      return {
        rows: [
          {
            customer_name: "Клиент А",
            orders_count: createMetricPreview(14, 12),
            revenue: createMetricPreview(64000, 58000, "currency"),
            sold_units: createMetricPreview(240, 220),
            days_since_last_order: createMetricPreview(5, 7),
          },
          {
            customer_name: "Клиент B",
            orders_count: createMetricPreview(11, 10),
            revenue: createMetricPreview(52000, 50100, "currency"),
            sold_units: createMetricPreview(190, 175),
            days_since_last_order: createMetricPreview(9, 11),
          },
        ],
      };
    case "inventory_risk":
      return {
        low_stock: [
          {
            product_name: "Товар A",
            organization_name: organizationName,
            current_stock: createMetricPreview(12, 18),
            days_of_stock: createMetricPreview(4, 5),
            sales_velocity_30d: createMetricPreview(80, 72),
          },
        ],
        overstock: [
          {
            product_name: "Товар B",
            organization_name: organizationName,
            current_stock: createMetricPreview(310, 280),
            days_of_stock: createMetricPreview(48, 42),
            sales_velocity_30d: createMetricPreview(18, 16),
          },
        ],
        stockout_risk: [
          {
            product_name: "Товар C",
            organization_name: organizationName,
            current_stock: createMetricPreview(8, 14),
            days_of_stock: createMetricPreview(2, 4),
            sales_velocity_30d: createMetricPreview(92, 85),
          },
        ],
        transfer_opportunities: [],
      };
    case "visit_summary":
      return {
        metric: createMetricPreview(426, 398),
        sales_reps: [
          {
            sales_rep_name: "Менеджер 1",
            organization_name: organizationName,
            visits_count: createMetricPreview(62, 58),
            orders_count: createMetricPreview(18, 15),
            revenue: createMetricPreview(21500, 18800, "currency"),
            sold_units: createMetricPreview(154, 143),
            conversion_rate: createMetricPreview(29, 26),
          },
        ],
      };
    case "data_quality":
      return {
        items: [
          {
            metric_key: "revenue",
            data_status: "AVAILABLE",
            coverage: 0.95,
            confidence: 0.98,
            message: "Данные по выручке подтверждены.",
            missing_fields: [],
          },
          {
            metric_key: "orders",
            data_status: "PARTIAL",
            coverage: 0.84,
            confidence: 0.9,
            message: "Часть данных по заказам требует уточнения.",
            missing_fields: ["source_channel"],
          },
        ],
        notes: ["Шаблонные данные для preview", "Показывается текущее состояние структуры."],
      };
    case "watchlist":
      return {
        rows: [
          {
            id: "watch-1",
            title: "Проверить продажи",
            summary: `В ${organizationName} есть сигнал по динамике продаж.`,
            severity: "warning",
            recommendation: "Посмотри последние сделки и выдели сильные товары.",
            evidence: ["Продажи", "Тренд"],
          },
          {
            id: "watch-2",
            title: "Проверить склад",
            summary: "Есть риск дефицита по части ассортимента.",
            severity: "attention",
            recommendation: "Сверь остатки и переноси приоритет на дефицитные позиции.",
            evidence: ["Остатки", "Склад"],
          },
        ],
      };
    case "alert":
    case "product_alert":
    case "customer_alert":
    case "inventory_alert":
    case "photo_alert":
    case "ai_insight":
    case "ai_recommendation":
      return {
        id: `preview-${widgetType}`,
        type: widgetType,
        severity: "warning",
        title: widgetCatalogTitle(widgetType),
        summary: `Шаблонный сигнал для ${organizationName}.`,
        recommendation: "Сформировать действия по этому сигналу.",
        metrics: [
          { label: "Влияние", current: 18, delta: 4 },
          { label: "Тренд", current: 72, delta: 6 },
        ],
        evidence: ["Шаблон", "Preview"],
      };
    default:
      return {
        metric: createMetricPreview(128000, 118000, "currency"),
        rows: [
          {
            title: "Сегмент A",
            summary: `Превью для ${organizationName}.`,
            severity: "info",
          },
        ],
      };
  }
}

function statusLabel(status: AnalyticsDataStatus, compact = false) {
  switch (status) {
    case "AVAILABLE":
      return compact ? "Подтверждено" : "Данные подтверждены";
    case "PARTIAL":
      return compact ? "Частично" : "Частичное покрытие";
    case "NO_DATA":
      return "Нет данных";
    case "NO_VERIFIED_DATA":
      return compact ? "Нет данных" : "Недостаточно данных";
    case "UNRESOLVED":
      return compact ? "Не определено" : "Недостаточно данных";
    case "PERMISSION_RESTRICTED":
      return "Нет доступа к данным";
    case "INSUFFICIENT_HISTORY":
      return compact ? "Мало истории" : "Недостаточно истории";
    case "ANALYSIS_PENDING":
      return compact ? "Обновляется" : "Анализ обновляется";
    case "NOT_SUPPORTED":
      return "Не поддерживается";
    default:
      return "Недоступно";
  }
}

function statusVariant(status: AnalyticsDataStatus): "accent" | "soft" | "dark" | "neutral" {
  switch (status) {
    case "PARTIAL":
    case "ANALYSIS_PENDING":
      return "accent";
    case "AVAILABLE":
      return "soft";
    case "NO_DATA":
    case "NO_VERIFIED_DATA":
    case "UNRESOLVED":
    case "PERMISSION_RESTRICTED":
    case "NOT_SUPPORTED":
    case "INSUFFICIENT_HISTORY":
      return "neutral";
    default:
      return "neutral";
  }
}

type FallbackWidgetInput = {
  widget_id: string;
  widget_type: DashboardManifestWidget["widget_type"];
  title: string;
  subtitle?: string | null;
  semantic_size: DashboardSemanticSize;
  priority: number;
  summary?: string | null;
  payload?: Record<string, unknown>;
};

function fallbackWidgetFlow(widgetType: DashboardManifestWidget["widget_type"]): DashboardManifestWidget["flow"] {
  switch (widgetType) {
    case "ai_recommendation":
    case "watchlist":
    case "customer_ranking":
    case "trend":
      return "wide";
    default:
      return "horizontal";
  }
}

function fallbackWidgetAspect(widgetType: DashboardManifestWidget["widget_type"]): DashboardManifestWidget["preferred_aspect"] {
  switch (widgetType) {
    case "ai_recommendation":
    case "watchlist":
    case "customer_ranking":
    case "trend":
      return "tall";
    default:
      return "square";
  }
}

function fallbackWidgetDensity(widgetType: DashboardManifestWidget["widget_type"]): DashboardManifestWidget["content_density"] {
  switch (widgetType) {
    case "ai_recommendation":
    case "watchlist":
    case "customer_ranking":
    case "trend":
      return "medium";
    default:
      return "low";
  }
}

function createFallbackWidget({
  widget_id,
  widget_type,
  title,
  subtitle = null,
  semantic_size,
  priority,
  summary = null,
  payload = {},
}: FallbackWidgetInput): DashboardManifestWidget {
  return {
    widget_id,
    widget_type,
    source_type: "PERMANENT",
    title,
    subtitle,
    metric_keys: [],
    signal_ids: [],
    entity_type: null,
    entity_id: null,
    organization_ids: [],
    semantic_size,
    priority,
    priority_reason: "Локальный шаблон дашборда",
    min_size: semantic_size,
    preferred_size: semantic_size,
    max_size: semantic_size,
    supports_horizontal_expand: true,
    supports_vertical_expand: true,
    supports_internal_scroll: true,
    flow: fallbackWidgetFlow(widget_type),
    preferred_aspect: fallbackWidgetAspect(widget_type),
    content_density: fallbackWidgetDensity(widget_type),
    scroll_behavior: "internal",
    removable_by_ai: false,
    movable_by_ai: true,
    resizable_by_ai: false,
    locked_position: false,
    locked_size: false,
    pinned: false,
    hidden: false,
    drilldown: null,
    summary,
    data_status: "ANALYSIS_PENDING",
    payload,
  };
}

function createId(prefix: string) {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function createConversationId() {
  return globalThis.crypto?.randomUUID?.() ?? createId("conversation");
}

function formatBytes(size: number) {
  if (!Number.isFinite(size) || size <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let value = size;
  let index = 0;
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024;
    index += 1;
  }
  return `${value.toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

function isTextFile(file: File) {
  if (file.type.startsWith("text/")) return true;
  const extension = file.name.split(".").pop()?.toLowerCase() ?? "";
  return new Set(["txt", "md", "csv", "json", "yaml", "yml", "xml", "html", "htm", "ts", "tsx", "js", "jsx", "py", "sql", "log"]).has(extension);
}

function isImageFile(file: File) {
  return file.type.startsWith("image/");
}

function readFileAsDataUrl(file: File) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(reader.error ?? new Error("Не удалось прочитать файл."));
    reader.onload = () => resolve(String(reader.result ?? ""));
    reader.readAsDataURL(file);
  });
}

async function buildAttachmentDraft(file: File): Promise<ChatAttachment> {
  const kind: ChatAttachment["kind"] = isImageFile(file) ? "image" : "file";
  let content: string | null = null;
  let dataUrl: string | null = null;

  if (kind === "image") {
    try {
      dataUrl = await readFileAsDataUrl(file);
    } catch {
      dataUrl = null;
    }
  } else if (isTextFile(file)) {
    try {
      content = await file.text();
    } catch {
      content = null;
    }
  }

  return {
    id: createId("attachment"),
    name: file.name,
    type: file.type || "application/octet-stream",
    size: file.size,
    kind,
    content,
    dataUrl,
  };
}

function buildAttachmentPrompt(attachments: ChatAttachment[]) {
  if (!attachments.length) return "";
  const lines = ["Вложенные файлы:"];
  for (const attachment of attachments) {
    lines.push(`- ${attachment.name} (${attachment.type}, ${formatBytes(attachment.size)})`);
    if (attachment.kind === "image") {
      lines.push("  Это изображение. Используй его содержимое, если модель поддерживает картинки.");
    } else if (attachment.content) {
      lines.push("  Содержимое:");
      lines.push(attachment.content.trim().slice(0, 4000) || "Пустой файл.");
    } else {
      lines.push("  Содержимое не извлечено, используй только метаданные.");
    }
  }
  return lines.join("\n");
}

function buildMessageContent(message: ChatMessage): string | Array<{ type: "text"; text: string } | { type: "image_url"; image_url: { url: string } }> {
  if (message.role !== "user") {
    return message.text;
  }

  const parts: Array<{ type: "text"; text: string } | { type: "image_url"; image_url: { url: string } }> = [];
  const trimmedText = message.text.trim();

  if (trimmedText) {
    parts.push({ type: "text", text: trimmedText });
  }

  if (message.attachments.length) {
    parts.push({ type: "text", text: buildAttachmentPrompt(message.attachments) });
    for (const attachment of message.attachments) {
      if (attachment.kind === "image" && attachment.dataUrl) {
        parts.push({ type: "image_url", image_url: { url: attachment.dataUrl } });
      }
    }
  }

  if (!parts.length) {
    return "";
  }

  if (parts.length === 1 && parts[0].type === "text") {
    return parts[0].text;
  }

  return parts;
}

function parseAssistantFiles(rawText: string) {
  const matches = [...rawText.matchAll(/```file(?:\s+name="([^"]+)")?(?:\s+type="([^"]+)")?\s*\n([\s\S]*?)```/gi)];
  const attachments: AssistantFileAttachment[] = matches.map((match, index) => {
    const content = match[3].trim();
    return {
      id: createId("assistant-file"),
      name: match[1] || `file-${index + 1}.txt`,
      type: match[2] || "text/plain",
      content,
      size: new Blob([content]).size,
    };
  });
  const text = rawText
    .replace(/```file(?:\s+name="([^"]+)")?(?:\s+type="([^"]+)")?\s*\n[\s\S]*?```/gi, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
  return { text, attachments };
}

const FALLBACK_DASHBOARD_DATA_QUALITY: DashboardManifestDataQuality = {
  overall_status: "ANALYSIS_PENDING",
  surfaced_items: [],
  notes: [
    "Данные подгрузятся из базы, как только backend ответит.",
    "Структура дашборда показывается сразу, без ожидания manifest.",
  ],
};

const FALLBACK_DASHBOARD_WIDGETS: DashboardManifestWidget[] = [
  createFallbackWidget({
    widget_id: "fallback-revenue",
    widget_type: "kpi",
    title: "Выручка",
    semantic_size: "S",
    priority: 1,
    payload: { metric: { value: null, unit: "currency", currency: "UZS", data_status: "ANALYSIS_PENDING" } },
  }),
  createFallbackWidget({
    widget_id: "fallback-orders",
    widget_type: "kpi",
    title: "Заказы",
    semantic_size: "S",
    priority: 2,
    payload: { metric: { value: null, unit: "number", data_status: "ANALYSIS_PENDING" } },
  }),
  createFallbackWidget({
    widget_id: "fallback-sold-units",
    widget_type: "kpi",
    title: "Продано единиц",
    semantic_size: "S",
    priority: 3,
    payload: { metric: { value: null, unit: "number", data_status: "ANALYSIS_PENDING" } },
  }),
  createFallbackWidget({
    widget_id: "fallback-average-order",
    widget_type: "kpi",
    title: "Средний заказ",
    semantic_size: "S",
    priority: 4,
    payload: { metric: { value: null, unit: "currency", currency: "UZS", data_status: "ANALYSIS_PENDING" } },
  }),
  createFallbackWidget({
    widget_id: "fallback-received-money",
    widget_type: "kpi",
    title: "Поступления",
    semantic_size: "S",
    priority: 5,
    payload: { metric: { value: null, unit: "currency", currency: "UZS", data_status: "ANALYSIS_PENDING" } },
  }),
  createFallbackWidget({
    widget_id: "fallback-summary",
    widget_type: "ai_recommendation",
    title: "Краткая сводка",
    semantic_size: "L",
    priority: 6,
    summary: "Ключевые выводы появятся после загрузки данных.",
    payload: {
      headline: "Краткая сводка",
      business_status: "Сводка обновляется из базы.",
      top_insights: [],
      risks: [],
      opportunities: [],
      data_warnings: [],
    },
  }),
  createFallbackWidget({
    widget_id: "fallback-product-signals",
    widget_type: "watchlist",
    title: "Товарные сигналы",
    subtitle: "Собранные товарные предупреждения в одной карточке",
    semantic_size: "L",
    priority: 7,
    summary: "Сигналы товаров будут показаны после обновления данных.",
    payload: { rows: [] },
  }),
  createFallbackWidget({
    widget_id: "fallback-customer-signal",
    widget_type: "customer_ranking",
    title: "Клиентский сигнал",
    semantic_size: "L",
    priority: 8,
    summary: "Список клиентов появится после загрузки данных.",
    payload: { rows: [] },
  }),
  createFallbackWidget({
    widget_id: "fallback-dynamics",
    widget_type: "trend",
    title: "Динамика выручки",
    semantic_size: "L",
    priority: 9,
    summary: "За весь период",
    payload: { metric: { value: null, unit: "currency", currency: "UZS", data_status: "ANALYSIS_PENDING" }, series: [] },
  }),
  createFallbackWidget({
    widget_id: "fallback-data-quality",
    widget_type: "data_quality",
    title: "Качество данных",
    semantic_size: "M",
    priority: 10,
    payload: { items: [], notes: FALLBACK_DASHBOARD_DATA_QUALITY.notes },
  }),
];

export function DashboardAssistantPanel({ floating = false }: { floating?: boolean }) {
  const { state: businessState } = useBusinessContext();
  const dashboardManifest = useOptionalDashboardManifest();
  const [expanded, setExpanded] = useState(false);
  const [fullScreen, setFullScreen] = useState(false);
  const [conversationId, setConversationId] = useState(createConversationId);
  const [selectedModel, setSelectedModel] = useState(0);
  const [availableModels, setAvailableModels] = useState<ModelItem[]>([]);
  const [selectedModelId, setSelectedModelId] = useState<string | undefined>();
  const [savedModelsByProvider, setSavedModelsByProvider] = useState<Record<string, string>>({});
  const [aiThoughts, setAiThoughts] = useState<AIThought[]>(loadCachedAIThoughts);
  const [selectedTileIndex, setSelectedTileIndex] = useState<number | null>(null);
  const [message, setMessage] = useState("");
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [pendingAttachments, setPendingAttachments] = useState<ChatAttachment[]>([]);
  const [isGenerating, setIsGenerating] = useState(false);
  const [chatError, setChatError] = useState<string | null>(null);
  const [analysisStatus, setAnalysisStatus] = useState<"idle" | "running" | "completed" | "failed">("idle");
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const messageInputRef = useRef<HTMLInputElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const chatSurfaceRef = useRef<HTMLDivElement | null>(null);
  const assistantRootRef = useRef<HTMLDivElement | null>(null);
  const chatThreadRef = useRef<HTMLDivElement | null>(null);
  const modelScrollerRef = useRef<HTMLDivElement | null>(null);
  const modelDragRef = useRef({ active: false, moved: false, startX: 0, scrollLeft: 0, lastX: 0, velocity: 0 });
  const modelMomentumRef = useRef<number | null>(null);
  const chatStateHydrated = useRef(false);
  const analysisPollTimerRef = useRef<number | null>(null);

  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(CHAT_STATE_STORAGE_KEY);
      if (stored) {
        const parsed = JSON.parse(stored) as { conversationId?: string; messages?: ChatMessage[] };
        if (typeof parsed.conversationId === "string" && parsed.conversationId) setConversationId(parsed.conversationId);
        if (Array.isArray(parsed.messages)) setChatMessages(parsed.messages);
      }
    } catch {
      // Ignore corrupt local chat state and start a clean conversation.
    }
    chatStateHydrated.current = true;
  }, []);

  useEffect(() => {
    if (!chatStateHydrated.current) return;
    window.localStorage.setItem(CHAT_STATE_STORAGE_KEY, JSON.stringify({ conversationId, messages: chatMessages }));
  }, [conversationId, chatMessages]);

  const refreshInsights = useCallback(async () => {
    try {
      const payload = await getDashboardAIInsights();
        if (payload.status === "empty" || payload.status === "running" || payload.status === "error") {
          const nextThoughts = [{
            label: "Статус",
            title: payload.status === "empty" ? "ИИ-анализ ещё не выполнен" : payload.status === "running" ? "ИИ анализирует бизнес..." : "ИИ-анализ недоступен",
            text: payload.message ?? "Результат анализа пока недоступен.",
          }];
          setAiThoughts(nextThoughts);
          cacheAIThoughts(nextThoughts);
          return;
        }
        const summary = payload.summary
          ? [{ label: "AI Аналитик", title: "Краткая сводка", text: `${payload.summary}${payload.generated_at ? ` · ${new Date(payload.generated_at).toLocaleString("ru-RU")}` : ""}` }]
          : [];
        const items = (Array.isArray(payload.items) ? payload.items : []).map((item) => ({
          label: item.type === "recommendation" ? "Рекомендует" : item.priority === "critical" || item.priority === "high" ? "Требует внимания" : "Наблюдение",
          title: item.title,
          text: [item.description, item.affected_entity, item.affected_metric].filter(Boolean).join(" · "),
        }));
        const nextThoughts = [...summary, ...items];
        setAiThoughts(nextThoughts);
        cacheAIThoughts(nextThoughts);
    } catch {
      // Keep the last successful analysis visible during transient API failures.
    }
  }, []);

  const pollAnalysisStatus = useCallback(async (attempt: number) => {
    try {
      const payload = await getDashboardAIAnalysisStatus();
      if (payload.status === "analyzing") {
        setAnalysisStatus("running");
        if (attempt < 40) {
          analysisPollTimerRef.current = window.setTimeout(() => void pollAnalysisStatus(attempt + 1), 3_000);
        } else {
          setAnalysisStatus("failed");
          setAnalysisError("Анализ выполняется дольше обычного. Проверьте статус позже.");
        }
        return;
      }
      if (payload.status === "completed") {
        setAnalysisStatus("completed");
        setAnalysisError(null);
        await refreshInsights();
        if (dashboardManifest) await dashboardManifest.reload();
        return;
      }
      if (payload.status === "error" || payload.status === "retry_wait") {
        setAnalysisStatus("failed");
        setAnalysisError(payload.last_error ?? "Не удалось завершить AI-анализ.");
        return;
      }
      setAnalysisStatus("idle");
    } catch {
      setAnalysisStatus("failed");
      setAnalysisError("Не удалось получить статус AI-анализа.");
    }
  }, [dashboardManifest, refreshInsights]);

  useEffect(() => {
    let active = true;
    void getDashboardAIAnalysisStatus()
      .then((payload) => {
        if (!active) return;
        if (payload.status === "analyzing") {
          setAnalysisStatus("running");
          void pollAnalysisStatus(0);
        } else if (payload.status === "completed") {
          setAnalysisStatus("completed");
        }
      })
      .catch(() => undefined);
    const interval = window.setInterval(() => void refreshInsights(), 30_000);
    return () => {
      active = false;
      window.clearInterval(interval);
      if (analysisPollTimerRef.current !== null) window.clearTimeout(analysisPollTimerRef.current);
    };
  }, [pollAnalysisStatus, refreshInsights]);

  async function startDashboardAnalysis() {
    if (analysisStatus === "running") return;
    setAnalysisStatus("running");
    setAnalysisError(null);
    try {
      await runDashboardAIAnalysis();
      void pollAnalysisStatus(0);
    } catch (error) {
      setAnalysisStatus("failed");
      setAnalysisError(error instanceof Error ? error.message : "Не удалось запустить AI-анализ.");
    }
  }

  useEffect(() => {
    if (!expanded) return;
    void Promise.all([getAiProviders(), getAiRouting()])
      .then(([providers, routing]) => {
        const grouped = new Map<string, ModelItem>();
        providers
          .filter((provider) => provider.available && provider.status === "available")
          .forEach((provider) => {
            const providerId = canonicalProviderId(provider.provider, provider.id);
            const modelId = canonicalModelId(provider.model, providerId);
            if (!providerId || !modelId) return;
            const current = grouped.get(providerId);
            if (current) {
              if (!current.models.some((model) => model.id === modelId)) {
                current.models.push({ id: modelId, name: cleanModelLabel(provider.name, modelId), available: provider.available });
              }
              return;
            }
            grouped.set(providerId, {
              providerId,
              name: providerLabel(providerId),
              models: [{ id: modelId, name: cleanModelLabel(provider.name, modelId), available: provider.available }],
              icon: providerIconKey(providerId),
            });
          });
        const nextModels = Array.from(grouped.values());
        setAvailableModels(nextModels);
        const chatAssignment = routing.config.roles.ai_chat;
        const assignedProviderId = chatAssignment?.primary_provider_id
          ? canonicalProviderId(chatAssignment.primary_provider_id)
          : null;
        const assignedModelId = chatAssignment?.primary_model_id && assignedProviderId
          ? canonicalModelId(chatAssignment.primary_model_id, assignedProviderId)
          : null;
        const assignedIndex = assignedProviderId
          ? nextModels.findIndex((model) => model.providerId === assignedProviderId && model.models.some((item) => item.id === assignedModelId))
          : -1;
        const nextIndex = assignedIndex >= 0 ? assignedIndex : 0;
        const assignedModel = nextModels[nextIndex]?.models.find((item) => item.id === assignedModelId)
          ?? nextModels[nextIndex]?.models[0];
        setSelectedModel(nextIndex);
        setSelectedModelId(assignedModel?.id ?? nextModels[nextIndex]?.models[0]?.id);
        setSavedModelsByProvider(assignedProviderId && assignedModel
          ? { [assignedProviderId]: assignedModel.id }
          : {});
      })
      .catch(() => setAvailableModels([]));
  }, [expanded]);

  useEffect(() => {
    if (!expanded) return;

    const frame = window.requestAnimationFrame(() => {
      messageInputRef.current?.focus();
    });

    return () => window.cancelAnimationFrame(frame);
  }, [expanded]);

  useEffect(() => {
    if (!expanded) {
      return;
    }

    const handleOutsidePointerDown = (event: PointerEvent) => {
      const target = event.target;
      if (!(target instanceof Node)) return;
      if (assistantRootRef.current?.contains(target)) return;
      setExpanded(false);
      setFullScreen(false);
    };

    document.addEventListener("pointerdown", handleOutsidePointerDown);

    return () => {
      document.removeEventListener("pointerdown", handleOutsidePointerDown);
    };
  }, [expanded]);

  useEffect(() => {
    if (chatMessages.length === 0) {
      return;
    }

    const frame = window.requestAnimationFrame(() => {
      chatThreadRef.current?.scrollTo({
        top: chatThreadRef.current.scrollHeight,
        behavior: "smooth",
      });
    });

    return () => window.cancelAnimationFrame(frame);
  }, [chatMessages]);
  const tiles: ChatTile[] = [
    { title: "Обсудить продажи", icon: "chat" },
    { title: "Проверить склад", icon: "head" },
    { title: "Собрать сводку", icon: "chat" },
    { title: "Создать виджет через ИИ", icon: "head" },
  ];

  const thoughts = aiThoughts;

  const visibleThoughts = expanded ? thoughts.slice(0, 2) : thoughts;
  const smoothTransition = "transition-all duration-500 ease-[cubic-bezier(0.22,1,0.36,1)]";
  const hasConversation = chatMessages.length > 0;
  const activeModel = availableModels[selectedModel] ?? availableModels[0] ?? {
    providerId: "",
    name: "ИИ",
    models: [],
    icon: "generic" as const,
  };
  const chatTitle =
    chatMessages.find((item) => item.role === "user")?.text.trim() || "Новый чат";
  const pendingAttachmentChips = pendingAttachments.length ? (
    <div className="flex flex-wrap gap-2">
      {pendingAttachments.map((attachment) => (
        <span
          key={attachment.id}
          className="inline-flex items-center gap-2 rounded-full border border-[#4a4e56] bg-[#343840] px-3 py-1.5 text-[11px] text-slate-300"
        >
          {attachment.kind === "image" && attachment.dataUrl ? (
            <img
              src={attachment.dataUrl}
              alt=""
              width={20}
              height={20}
              className="h-5 w-5 rounded-full object-cover"
              aria-hidden="true"
            />
          ) : (
            <span className="flex h-5 w-5 items-center justify-center rounded-full bg-white/10 text-[10px] uppercase text-slate-200">
              {attachment.name.split(".").pop()?.slice(0, 3) || "file"}
            </span>
          )}
          <span className="max-w-[180px] truncate">{attachment.name}</span>
          <span className="opacity-60">{formatBytes(attachment.size)}</span>
          <button
            type="button"
            onClick={() => handleRemoveAttachment(attachment.id)}
            className="ml-1 inline-flex h-5 w-5 items-center justify-center rounded-full bg-white/10 text-[12px] leading-none text-slate-200 hover:bg-white/20"
            aria-label={`Удалить файл ${attachment.name}`}
          >
            ×
          </button>
        </span>
      ))}
    </div>
  ) : null;

  const handleAttachmentPick = async (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? []);
    event.target.value = "";
    if (!files.length) return;
    const drafts = await Promise.all(files.map((file) => buildAttachmentDraft(file)));
    setPendingAttachments((current) => [...current, ...drafts]);
    setExpanded(true);
    requestAnimationFrame(() => {
      messageInputRef.current?.focus();
    });
  };

  const handleRemoveAttachment = (attachmentId: string) => {
    setPendingAttachments((current) => current.filter((item) => item.id !== attachmentId));
  };

  const handleSendMessage = async (
    messageOverride?: string,
    attachmentsOverride?: ChatAttachment[],
    taskType: "business_analytics" | "system_action" | "communications" | "ai_chat" = "ai_chat",
  ) => {
    const text = (messageOverride ?? message).trim();
    const attachments = attachmentsOverride ?? pendingAttachments;
    if ((!text && attachments.length === 0) || isGenerating) return;

    setExpanded(true);
    setChatError(null);
    const userId = createId("user");
    const assistantId = createId("assistant");
    const userMessage: ChatMessage = {
      id: userId,
      role: "user",
      text,
      attachments,
    };
    const history = [...chatMessages, userMessage];
    setChatMessages((current) => [
      ...current,
      userMessage,
      { id: assistantId, role: "assistant", text: "", attachments: [] },
    ]);
    setMessage("");
    setPendingAttachments([]);
    setIsGenerating(true);
    try {
      await streamAiChat(
        history.map((item) => ({ role: item.role, content: buildMessageContent(item) })),
        (content) =>
          setChatMessages((current) =>
            current.map((item) => (item.id === assistantId ? { ...item, text: item.text + content } : item)),
          ),
        undefined,
        taskType,
        taskType === "ai_chat" ? activeModel.providerId || undefined : undefined,
        taskType === "ai_chat" ? selectedModelId : undefined,
        (meta) => {
          if (meta.provider_id) {
            const index = availableModels.findIndex((model) => model.providerId === meta.provider_id && model.models.some((item) => item.id === meta.model_id));
            if (index >= 0) setSelectedModel(index);
          }
          setChatMessages((current) =>
            current.map((item) =>
              item.id === assistantId
                ? { ...item, providerName: meta.provider_name, modelName: meta.model_id }
                : item,
            ),
          );
        },
        conversationId,
        businessState.selectedOrganizationIds[0] ?? null,
        businessState.period.preset,
      );
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : "Не удалось получить ответ AI.";
      setChatError(errorMessage);
      setChatMessages((current) =>
        current.map((item) =>
          item.id === assistantId && !item.text.trim()
            ? { ...item, text: errorMessage }
            : item,
        ),
      );
    } finally {
      setIsGenerating(false);
    }
  };

  const handleQuickAction = (tile: ChatTile, index: number) => {
    const prompt = QUICK_ACTION_PROMPTS[tile.title] ?? tile.title;
    const taskType = tile.title === "Создать виджет через ИИ" ? "system_action" : "business_analytics" as const;
    setSelectedTileIndex(index);
    if (tile.title === "Создать виджет через ИИ") {
      window.dispatchEvent(new CustomEvent("ai-business-os:open-ai-widget-builder"));
    }
    void handleSendMessage(prompt, [], taskType);
  };

  const handleEndConversation = () => {
    setChatMessages([]);
    setConversationId(createConversationId());
    setMessage("");
    setPendingAttachments([]);
    setExpanded(true);
    requestAnimationFrame(() => {
      messageInputRef.current?.focus();
    });
  };

  if (floating && !expanded) {
    return (
      <button
        type="button"
        onClick={() => setExpanded(true)}
        className="fixed bottom-6 right-6 z-50 flex h-14 w-14 items-center justify-center rounded-full border border-[#4a4e56] bg-[#FFF27A] text-[#1E1E21] shadow-[0_16px_40px_rgba(0,0,0,0.35)] transition hover:scale-105"
        aria-label="Открыть чат с ИИ"
        title="Открыть чат с ИИ"
      >
        <ChatTileIcon kind="chat" />
      </button>
    );
  }

  return (
    <>
      {fullScreen ? (
        <div className="fixed inset-0 z-[55] bg-[#17191d]/80 backdrop-blur-sm" aria-hidden="true" />
      ) : null}
      <div ref={assistantRootRef} className={fullScreen ? "fixed inset-3 z-[60] mx-auto flex w-[min(980px,calc(100vw-1.5rem))] flex-col gap-3 sm:inset-6" : floating ? "fixed bottom-6 right-6 z-50 flex w-[min(420px,calc(100vw-2rem))] flex-col gap-3" : "flex min-h-0 flex-col gap-3 xl:sticky xl:top-[6.5rem] xl:h-[calc(100dvh-8rem)]"}>
      <div id="ai-chat" ref={chatSurfaceRef}>
        <Surface
          className={cn(
            "relative flex min-h-0 shrink-0 flex-col overflow-hidden border-[#3c4048] bg-[radial-gradient(circle_at_78%_12%,rgba(255,255,255,0.05),transparent_32%),linear-gradient(180deg,#2E3137_0%,#2A2D33_100%)] px-4",
            smoothTransition,
            fullScreen ? "h-full min-h-0 pt-5 pb-4" : expanded ? "h-[699px] xl:!h-[calc(100dvh_-_23.625rem)] pt-5 pb-4" : "h-[165px] xl:h-[165px] py-3",
          )}
        >
          <button
            type="button"
            onClick={() => setExpanded((value) => !value)}
            className="pointer-events-none absolute inset-0 z-0"
            aria-hidden="true"
            tabIndex={-1}
          />
          <div className="pointer-events-none absolute inset-0 opacity-40 [background-image:repeating-linear-gradient(120deg,rgba(255,255,255,0.03)_0,rgba(255,255,255,0.03)_1px,transparent_1px,transparent_14px)]" />
          {chatError ? (
            <p className="relative z-10 rounded-full bg-[#565b63] px-3 py-1.5 text-[12px] text-[#f4f7fb]" role="alert">
              {chatError}
            </p>
          ) : null}
          <div className={cn("relative flex min-h-0 flex-col", smoothTransition, expanded ? "flex-1 gap-4" : "flex-1 justify-center gap-3")}>
            <input
              ref={fileInputRef}
              type="file"
              multiple
              className="hidden"
              onChange={(event) => {
                void handleAttachmentPick(event);
              }}
            />
            {expanded && hasConversation ? (
              <div className="flex items-center gap-4">
                <button
                  type="button"
                  onClick={() => setExpanded(false)}
                  className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full border border-[#4a4e56] bg-[#343840] text-xl text-[#f4f7fb] transition-all duration-500 ease-[cubic-bezier(0.22,1,0.36,1)] hover:border-[#FFF27A]/30 hover:text-[#FFF27A]"
                  aria-label="Назад"
                  title="Назад"
                >
                  <span aria-hidden>‹</span>
                </button>
                <div className="flex min-w-0 flex-1 items-center gap-3">
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center overflow-hidden rounded-full border border-[#4a4e56] bg-[#343840]">
                    <ModelIcon kind={activeModel.icon} selected />
                  </div>
                  <div className="min-w-0">
                    <p className="max-w-full truncate text-[18px] font-semibold leading-[1.1] tracking-[-0.05em] text-[#f4f7fb] xl:text-[20px]">
                      {chatTitle}
                    </p>
                    <p className="mt-0.5 text-[11px] uppercase tracking-[0.28em] text-slate-500">
                      {activeModel.name}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={handleEndConversation}
                    className="ml-auto shrink-0 rounded-full border border-[#4a4e56] px-3 py-2 text-[10px] uppercase tracking-[0.12em] text-slate-400 transition hover:border-[#FFF27A]/40 hover:text-[#FFF27A]"
                  >
                    Завершить диалог
                  </button>
                  <button
                    type="button"
                    onClick={() => setFullScreen((value) => !value)}
                    className="shrink-0 rounded-full border border-[#4a4e56] px-3 py-2 text-[10px] uppercase tracking-[0.12em] text-slate-400 transition hover:border-[#FFF27A]/40 hover:text-[#FFF27A]"
                    aria-label={fullScreen ? "Закрыть полный экран" : "Открыть чат в полный размер"}
                    title={fullScreen ? "Закрыть полный экран" : "Открыть чат в полный размер"}
                  >
                    {fullScreen ? "Свернуть" : "На весь экран"}
                  </button>
                </div>
              </div>
            ) : (
              <div className="flex items-start justify-between gap-4">
                <div className={cn("flex-1", !expanded ? "text-center" : "")}>
                  <p
                    className={cn(
                      "font-semibold tracking-[-0.08em] text-[#f4f7fb] leading-[1.05]",
                      smoothTransition,
                      expanded ? "text-[22px] xl:text-[26px]" : "text-[17px] xl:text-[19px]",
                    )}
                  >
                    Как я могу помочь сегодня?
                  </p>
                </div>
                <button
                  type="button"
                  className="inline-flex h-11 w-11 items-center justify-center rounded-full border border-[#4a4e56] bg-[#343840] text-xl text-[#f4f7fb] transition-all duration-500 ease-[cubic-bezier(0.22,1,0.36,1)] hover:border-[#FFF27A]/30 hover:text-[#FFF27A]"
                  aria-label={expanded ? "Свернуть чат" : "Открыть чат"}
                  onClick={() => setExpanded((value) => !value)}
                >
                  <span aria-hidden>{expanded ? "⌄" : "›"}</span>
                </button>
                {expanded ? (
                  <button
                    type="button"
                    onClick={() => setFullScreen(true)}
                    className="inline-flex h-11 items-center justify-center rounded-full border border-[#4a4e56] px-3 text-[10px] uppercase tracking-[0.12em] text-slate-400 transition hover:border-[#FFF27A]/40 hover:text-[#FFF27A]"
                    aria-label="Открыть чат в полный размер"
                  >
                    На весь экран
                  </button>
                ) : null}
              </div>
            )}

            {expanded ? pendingAttachmentChips : null}

            {!expanded ? (
              <form
                className="flex h-[58px] w-full items-center gap-3 rounded-[24px] border border-[#3a3d43] bg-[#343840] px-4 pr-2 text-left shadow-[0_18px_30px_rgba(0,0,0,0.16)] transition-all duration-500 ease-[cubic-bezier(0.22,1,0.36,1)]"
                onSubmit={(event) => {
                  event.preventDefault();
                  handleSendMessage();
                }}
              >
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-[#343840] text-[#f4f7fb] transition-all duration-500 ease-[cubic-bezier(0.22,1,0.36,1)] hover:bg-[#3d424a] hover:text-[#FFF27A]"
                  aria-label="Прикрепить файл"
                  title="Прикрепить файл"
                >
                  <img src="/attachmenticon.png" alt="" width={24} height={24} className="h-5 w-5 select-none object-contain" aria-hidden="true" />
                </button>
                <input
                  ref={messageInputRef}
                  value={message}
                  onChange={(event) => setMessage(event.target.value)}
                  onFocus={() => setExpanded(true)}
                  onClick={() => setExpanded(true)}
                  placeholder="Напишите сообщение..."
                  aria-label="Напишите сообщение"
                  className="min-w-0 flex-1 border-0 bg-transparent text-[15px] text-slate-300 outline-none placeholder:text-slate-400"
                />
                <button
                  type="submit"
                  disabled={isGenerating}
                  className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-[#FFF27A] text-[#1E1E21] transition-all duration-500 ease-[cubic-bezier(0.22,1,0.36,1)] hover:bg-[#fff6a6]"
                  aria-label="Отправить сообщение"
                >
                  <svg
                    viewBox="0 0 24 24"
                    className="h-[17px] w-[17px]"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.8"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    aria-hidden="true"
                  >
                    <path d="M22 2 11 13" />
                    <path d="M22 2 15 22l-4-9-9-4 20-7Z" />
                  </svg>
                </button>
              </form>
            ) : hasConversation ? (
              <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-hidden">
                <div ref={chatThreadRef} className="min-h-0 flex-1 overflow-y-auto pr-1">
                  <div className="flex flex-col gap-4 pb-3">
                    {chatMessages.map((item) => {
                      const parsed = item.role === "assistant" ? parseAssistantFiles(item.text) : null;
                      const visibleText = parsed ? parsed.text || item.text : item.text;
                      return item.role === "user" ? (
                        <div key={item.id} className="ml-auto max-w-[82%] rounded-[22px] bg-[#565b63] px-4 py-3 text-[#f4f7fb] shadow-[0_10px_22px_rgba(0,0,0,0.14)]">
                          <p className="whitespace-pre-wrap text-[15px] leading-6 text-[#f4f7fb]">{item.text}</p>
                          {item.attachments.length > 0 ? (
                            <div className="mt-3 flex flex-wrap gap-2">
                              {item.attachments.map((attachment) => (
                                <span
                                  key={attachment.id}
                                  className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/10 px-3 py-1.5 text-[11px] text-[#f4f7fb]"
                                >
                                  {attachment.kind === "image" && attachment.dataUrl ? (
                                    <img
                                      src={attachment.dataUrl}
                                      alt=""
                                      width={20}
                                      height={20}
                                      className="h-5 w-5 rounded-full object-cover"
                                      aria-hidden="true"
                                    />
                                  ) : (
                                    <span className="flex h-5 w-5 items-center justify-center rounded-full bg-white/10 text-[10px] uppercase text-[#f4f7fb]">
                                      {attachment.name.split(".").pop()?.slice(0, 3) || "file"}
                                    </span>
                                  )}
                                  <span className="max-w-[180px] truncate">{attachment.name}</span>
                                  <span className="opacity-60">{formatBytes(attachment.size)}</span>
                                </span>
                              ))}
                            </div>
                          ) : null}
                        </div>
                      ) : (
                        <div key={item.id} className="mr-auto max-w-[82%] rounded-[22px] bg-[#f4f7fb] px-4 py-3 text-[#1E1E21] shadow-[0_10px_22px_rgba(0,0,0,0.14)]">
                          {item.providerName ? <p className="mb-1 text-[10px] uppercase tracking-[0.2em] text-slate-500">{item.providerName}{item.modelName ? ` · ${item.modelName}` : ""}</p> : null}
                          <p className="whitespace-pre-wrap text-[15px] leading-6 text-[#1E1E21]">{visibleText || " "}</p>
                          {parsed?.attachments.length ? (
                            <div className="mt-3 flex flex-wrap gap-2">
                              {parsed.attachments.map((attachment) => (
                                <button
                                  key={attachment.id}
                                  type="button"
                                  onClick={() => {
                                    const blob = new Blob([attachment.content], { type: attachment.type });
                                    const url = URL.createObjectURL(blob);
                                    const anchor = document.createElement("a");
                                    anchor.href = url;
                                    anchor.download = attachment.name;
                                    anchor.click();
                                    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
                                  }}
                                  className="inline-flex items-center gap-2 rounded-full border border-[#d7dae3] bg-white px-3 py-1.5 text-[11px] text-[#1E1E21] transition hover:border-[#FFF27A]/40"
                                >
                                  <span className="max-w-[180px] truncate font-medium">{attachment.name}</span>
                                  <span className="opacity-60">{formatBytes(attachment.size)}</span>
                                  <span className="rounded-full bg-[#FFF27A] px-2 py-0.5 text-[10px] font-semibold text-[#1E1E21]">
                                    Скачать
                                  </span>
                                </button>
                              ))}
                            </div>
                          ) : null}
                        </div>
                      );
                    })}
                  </div>
                </div>

                <form
                  className="mt-1 flex h-[60px] items-center gap-3 rounded-[24px] border border-[#3a3d43] bg-[#343840] px-4 pr-2 text-left shadow-[0_18px_30px_rgba(0,0,0,0.16)] transition-all duration-500 ease-[cubic-bezier(0.22,1,0.36,1)]"
                  onSubmit={(event) => {
                    event.preventDefault();
                    handleSendMessage();
                  }}
                >
                  <button
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-[#343840] text-[#f4f7fb] transition-all duration-500 ease-[cubic-bezier(0.22,1,0.36,1)] hover:bg-[#3d424a] hover:text-[#FFF27A]"
                    aria-label="Прикрепить файл"
                    title="Прикрепить файл"
                  >
                    <img src="/attachmenticon.png" alt="" width={24} height={24} className="h-5 w-5 select-none object-contain" aria-hidden="true" />
                  </button>
                  <input
                    ref={messageInputRef}
                    value={message}
                    onChange={(event) => setMessage(event.target.value)}
                    placeholder="Напишите сообщение..."
                    aria-label="Напишите сообщение"
                    className="min-w-0 flex-1 border-0 bg-transparent text-[15px] text-slate-300 outline-none placeholder:text-slate-400"
                  />
                  <button
                    type="submit"
                    disabled={isGenerating}
                    className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-[#FFF27A] text-[#1E1E21] transition-all duration-500 ease-[cubic-bezier(0.22,1,0.36,1)] hover:bg-[#fff6a6]"
                    aria-label="Отправить сообщение"
                  >
                    <svg
                      viewBox="0 0 24 24"
                      className="h-[17px] w-[17px]"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.8"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      aria-hidden="true"
                    >
                      <path d="M22 2 11 13" />
                      <path d="M22 2 15 22l-4-9-9-4 20-7Z" />
                    </svg>
                  </button>
                </form>
              </div>
            ) : (
              <>
                <div className="grid grid-cols-2 gap-4 transition-all duration-500 ease-[cubic-bezier(0.22,1,0.36,1)]">
                  {tiles.map((tile, index) => {
                    const selected = index === selectedTileIndex;

                    return (
                    <button
                      key={`${tile.title}-${tile.icon}`}
                      type="button"
                      onClick={() => {
                        handleQuickAction(tile, index);
                      }}
                      className={cn(
                        "group relative flex min-h-[154px] flex-col justify-between overflow-hidden rounded-[24px] px-4 py-4 text-left transition-all duration-500 ease-[cubic-bezier(0.22,1,0.36,1)] hover:-translate-y-0.5",
                        selected
                          ? "bg-[#FFF27A] text-[#1E1E21] shadow-[0_16px_36px_rgba(255,242,122,0.18)]"
                          : "bg-[#4a4a4a] text-[#f4f7fb]",
                      )}
                    >
                      <div className="relative z-10 max-w-[150px] text-[21px] font-semibold leading-[1.14] tracking-[-0.03em]">
                        {tile.title}
                      </div>
                      <div className="relative z-10 flex items-end justify-between gap-3">
                        <div
                          className={cn(
                            "flex h-[52px] w-[52px] items-center justify-center rounded-full",
                            selected ? "bg-[#1E1E21]/10" : "bg-white/10",
                          )}
                        >
                          <ChatTileIcon kind={tile.icon} />
                        </div>
                        <span className="text-3xl font-light leading-none">↗</span>
                      </div>
                    </button>
                    );
                  })}
                </div>

                <div className="flex items-center justify-between gap-3 pt-2">
                  <p className="text-[22px] font-medium tracking-[-0.05em] text-[#cfd3dc]">Выбери ИИ</p>
                  <button type="button" className="text-sm text-slate-400 transition hover:text-[#f4f7fb]">
                    Все
                  </button>
                </div>

                <div className="min-h-0 flex-1 overflow-hidden">
                  <div
                    ref={modelScrollerRef}
                    className="flex cursor-grab select-none gap-4 overflow-x-auto scroll-smooth pb-2 snap-x snap-proximity [scrollbar-width:none] [&::-webkit-scrollbar]:hidden active:cursor-grabbing"
                    onMouseDown={(event) => {
                      const scroller = modelScrollerRef.current;
                      if (!scroller) return;
                      if (modelMomentumRef.current !== null) cancelAnimationFrame(modelMomentumRef.current);
                      modelDragRef.current = { active: true, moved: false, startX: event.clientX, scrollLeft: scroller.scrollLeft, lastX: event.clientX, velocity: 0 };
                    }}
                    onMouseMove={(event) => {
                      const scroller = modelScrollerRef.current;
                      const drag = modelDragRef.current;
                      if (!scroller || !drag.active) return;
                      if (Math.abs(event.clientX - drag.startX) > 5) drag.moved = true;
                      scroller.scrollLeft = drag.scrollLeft - (event.clientX - drag.startX);
                      drag.velocity = drag.lastX - event.clientX;
                      drag.lastX = event.clientX;
                    }}
                    onMouseUp={() => {
                      const scroller = modelScrollerRef.current;
                      const drag = modelDragRef.current;
                      drag.active = false;
                      if (!scroller || Math.abs(drag.velocity) < 0.5) return;
                      const glide = () => {
                        if (!modelScrollerRef.current || Math.abs(drag.velocity) < 0.2) {
                          modelMomentumRef.current = null;
                          return;
                        }
                        modelScrollerRef.current.scrollLeft += drag.velocity;
                        drag.velocity *= 0.92;
                        modelMomentumRef.current = requestAnimationFrame(glide);
                      };
                      modelMomentumRef.current = requestAnimationFrame(glide);
                    }}
                    onMouseLeave={() => {
                      modelDragRef.current.active = false;
                    }}
                  >
                    {availableModels.map((model, index) => {
                      const selected = index === selectedModel;

                      return (
                        <button
                          key={`${model.providerId}:${model.models[0]?.id ?? model.name}`}
                          type="button"
                          onClick={() => {
                            setSelectedModel(index);
                            const savedModel = savedModelsByProvider[model.providerId];
                            const nextModel = model.models.find((item) => item.id === savedModel) ?? model.models[0];
                            setSelectedModelId(nextModel?.id);
                          }}
                          className={cn(
                            "flex h-[112px] min-w-[118px] shrink-0 snap-start flex-col items-center justify-between rounded-[24px] border px-2 py-3 transition-all duration-500 ease-[cubic-bezier(0.22,1,0.36,1)] hover:-translate-y-0.5",
                            selected
                              ? "border-[#FFF27A] bg-[#FFF27A] text-[#1E1E21] shadow-[0_12px_28px_rgba(255,242,122,0.18)]"
                              : "border-[#3a3d43] bg-[#4b4f56] text-[#f4f7fb] hover:bg-[#52565d]",
                          )}
                          aria-label={model.name}
                          title={model.name}
                          draggable={false}
                        >
                          <span className="flex h-[58px] w-[58px] items-center justify-center overflow-hidden rounded-[18px]">
                            <ModelIcon kind={model.icon} selected={selected} />
                          </span>
                          <span
                            className={cn(
                              "text-center text-[11px] font-medium leading-[1.1] tracking-[-0.03em]",
                              selected ? "text-[#1E1E21]" : "text-[#f4f7fb]",
                            )}
                          >
                            {model.name}
                          </span>
                        </button>
                      );
                    })}
                  </div>
                </div>

                {activeModel.models.length > 0 ? (
                  <div className="flex flex-wrap gap-2 pt-1">
                    {activeModel.models.map((model) => {
                      const selected = model.id === selectedModelId;
                      return (
                        <button
                          key={`${activeModel.providerId}:${model.id}`}
                          type="button"
                          onClick={() => {
                            setSelectedModelId(model.id);
                            setSavedModelsByProvider((current) => ({ ...current, [activeModel.providerId]: model.id }));
                          }}
                          className={cn(
                            "rounded-full border px-3 py-1.5 text-xs transition",
                            selected
                              ? "border-[#FFF27A] bg-[#FFF27A] text-[#1E1E21]"
                              : "border-[#3a3d43] bg-[#343840] text-slate-300 hover:border-[#5a6270]",
                          )}
                        >
                          {model.name}
                        </button>
                      );
                    })}
                  </div>
                ) : null}

                <form
                  className="flex h-[58px] items-center gap-3 rounded-[24px] border border-[#3a3d43] bg-[#343840] px-4 pr-2 text-left shadow-[0_18px_30px_rgba(0,0,0,0.16)] transition-all duration-500 ease-[cubic-bezier(0.22,1,0.36,1)]"
                  onSubmit={(event) => {
                    event.preventDefault();
                    handleSendMessage();
                  }}
                >
                  <button
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-[#343840] text-[#f4f7fb] transition-all duration-500 ease-[cubic-bezier(0.22,1,0.36,1)] hover:bg-[#3d424a] hover:text-[#FFF27A]"
                    aria-label="Прикрепить файл"
                    title="Прикрепить файл"
                  >
                    <img src="/attachmenticon.png" alt="" width={24} height={24} className="h-5 w-5 select-none object-contain" aria-hidden="true" />
                  </button>
                  <input
                    ref={messageInputRef}
                    value={message}
                    onChange={(event) => setMessage(event.target.value)}
                    placeholder="Напишите сообщение..."
                    aria-label="Напишите сообщение"
                    className="min-w-0 flex-1 border-0 bg-transparent text-[15px] text-slate-300 outline-none placeholder:text-slate-400"
                  />
                  <button
                    type="submit"
                    disabled={isGenerating}
                    className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-[#FFF27A] text-[#1E1E21] transition-all duration-500 ease-[cubic-bezier(0.22,1,0.36,1)] hover:bg-[#fff6a6]"
                    aria-label="Отправить сообщение"
                  >
                    <svg
                      viewBox="0 0 24 24"
                      className="h-[17px] w-[17px]"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.8"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      aria-hidden="true"
                    >
                      <path d="M22 2 11 13" />
                      <path d="M22 2 15 22l-4-9-9-4 20-7Z" />
                    </svg>
                  </button>
                </form>
              </>
            )}
          </div>
        </Surface>
      </div>

      {!floating ? (
        <Surface
          className={cn(
            "relative flex min-h-0 flex-col overflow-hidden border-[#3c4048] bg-[linear-gradient(180deg,#2E3137_0%,#2A2D33_100%)] px-4 py-4 transition-all duration-500 ease-[cubic-bezier(0.22,1,0.36,1)]",
            expanded ? "flex-none" : "flex-1",
          )}
        >
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-[10px] uppercase tracking-[0.3em] text-slate-400">Мысли ИИ</p>
            <h3 className="mt-1.5 text-[24px] font-semibold tracking-[-0.06em] text-[#f4f7fb]">
              Что важно сейчас
            </h3>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant="accent">{thoughts.length}</Badge>
            <Button
              type="button"
              size="sm"
              variant="secondary"
              disabled={analysisStatus === "running"}
              onClick={() => void startDashboardAnalysis()}
              className="whitespace-nowrap text-[11px]"
            >
              {analysisStatus === "running" ? "Анализируется..." : analysisStatus === "completed" ? "Анализ завершён" : "Запустить анализ"}
            </Button>
          </div>
        </div>
        {analysisError ? <p className="mt-2 text-[11px] text-rose-200">{analysisError}</p> : null}
        <div
          className={cn(
            "mt-3 flex min-h-0 flex-col gap-2 transition-all duration-500 ease-[cubic-bezier(0.22,1,0.36,1)]",
            expanded ? "flex-none overflow-hidden" : "flex-1 overflow-y-auto pr-1",
          )}
        >
          {visibleThoughts.map((item) => (
            <div
              key={item.title}
              className="rounded-[22px] border border-[#3a3d43] bg-[#343840] p-2.5 transition-all duration-500 ease-[cubic-bezier(0.22,1,0.36,1)]"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <Badge variant={item.label === "Предупреждает" ? "dark" : "soft"}>{item.label}</Badge>
                  <p className="mt-2 text-[14px] font-semibold tracking-[-0.04em] text-[#f4f7fb]">{item.title}</p>
                  <p className="mt-1 text-[11px] leading-5 text-slate-300">{item.text}</p>
                </div>
                <span className="text-lg leading-none text-[#FFF27A]">›</span>
              </div>
            </div>
          ))}
        </div>
        </Surface>
      ) : null}
    </div>
    </>
  );
}

function ModelIcon({ kind, selected }: { kind: ModelItem["icon"]; selected: boolean }) {
  if (kind === "generic") {
    return <span className="flex h-[56px] w-[56px] items-center justify-center rounded-[18px] bg-[#343840] text-sm font-semibold text-slate-200">AI</span>;
  }
  const src =
    kind === "ollama"
      ? "/ai-model-icons/Ollama.png"
      : kind === "chatgpt"
      ? "/ai-model-icons/ChatGPT.png"
      : kind === "claude"
        ? "/ai-model-icons/Claude.png"
        : kind === "grok"
          ? "/ai-model-icons/Grok.png"
          : kind === "deepseek"
            ? "/ai-model-icons/DeepSeek.png"
            : "/ai-model-icons/Ollama.png";

  return (
    <img
      src={src}
      alt=""
      width={56}
      height={56}
      className={cn(
        "h-[56px] w-[56px] select-none rounded-[18px] object-cover transition-transform duration-500 ease-[cubic-bezier(0.22,1,0.36,1)]",
        selected ? "scale-100" : "scale-100",
      )}
      draggable={false}
      aria-hidden="true"
    />
  );
}

function providerIconKey(providerId: string): ModelItem["icon"] {
  const normalized = providerId.toLowerCase();
  if (normalized.includes("ollama")) return "ollama";
  if (normalized.includes("chatgpt") || normalized.includes("openai")) return "chatgpt";
  if (normalized.includes("claude") || normalized.includes("anthropic")) return "claude";
  if (normalized.includes("grok")) return "grok";
  if (normalized.includes("deepseek")) return "deepseek";
  return "generic";
}

function providerLabel(providerId: string): string {
  if (providerId === "openai-codex") return "OpenAI Codex";
  if (providerId === "custom") return "Local / Custom";
  if (providerId === "moa") return "MOA";
  return providerId
    .split(/[-_]/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function canonicalProviderId(providerId: string, targetId?: string): string {
  const provider = providerId.trim().toLowerCase();
  const target = (targetId ?? "").trim().toLowerCase();
  if (provider === "custom" || provider.startsWith("custom:") || target.startsWith("custom:")) return "custom";
  if (provider === "openai-codex" || provider.startsWith("openai-codex:") || target.startsWith("openai-codex:")) return "openai-codex";
  return provider;
}

function canonicalModelId(modelId: string, providerId: string): string {
  const value = modelId.trim();
  const prefix = `${providerId}:`;
  return value.toLowerCase().startsWith(prefix) ? value.slice(prefix.length) : value;
}

function cleanModelLabel(name: string, modelId: string): string {
  const label = name.trim();
  return label && !label.toLowerCase().startsWith("custom:") && !label.toLowerCase().startsWith("openai-codex:")
    ? label
    : modelId;
}

function ChatTileIcon({ kind }: { kind: ChatTile["icon"] }) {
  if (kind === "chat") {
    return (
      <svg viewBox="0 0 24 24" className="h-6 w-6 text-[#1E1E21]" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M8.5 17.5 5.5 20v-3.2C4.1 15.5 3 13.9 3 12c0-4.4 3.8-8 9-8s9 3.6 9 8-3.8 8-9 8c-1 0-1.9-.1-2.8-.3" />
        <path d="M8 10.5h8" />
        <path d="M8 13.5h4.5" />
      </svg>
    );
  }

  return (
    <svg viewBox="0 0 24 24" className="h-6 w-6 text-[#1E1E21]" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 13c2.2 0 4-1.8 4-4s-1.8-4-4-4-4 1.8-4 4 1.8 4 4 4Z" />
      <path d="M4.5 20c.8-3.1 3.1-5 7.5-5s6.7 1.9 7.5 5" />
      <path d="M17.5 9.5c1.7 0 3 1.3 3 3 0 1.5-1 2.7-2.4 3" />
    </svg>
  );
}

function severityLabel(severity?: string | null) {
  if (!severity) return null;
  const normalized = severity.trim().toLowerCase();
  if (!normalized) return null;
  if (normalized === "info") return "Норма";
  if (normalized === "warning") return "Внимание";
  if (normalized === "attention") return "Требует внимания";
  return businessCopy(severity) ?? severity;
}

function useMeasuredWidth<T extends HTMLElement>() {
  const [node, setNode] = useState<T | null>(null);
  const [width, setWidth] = useState(0);
  const ref = useCallback((element: T | null) => {
    setNode(element);
  }, []);

  useLayoutEffect(() => {
    if (!node) return;

    const updateWidth = () => {
      setWidth(node.getBoundingClientRect().width);
    };

    updateWidth();

    const observer = new ResizeObserver(() => {
      updateWidth();
    });
    observer.observe(node);

    return () => {
      observer.disconnect();
    };
  }, [node]);

  return [ref, width] as const;
}

function cloneResponsiveLayouts(layouts: ResponsiveLayouts) {
  return Object.fromEntries(
    Object.entries(layouts).map(([breakpoint, layout]) => [
      breakpoint,
      (layout ?? []).map((item) => ({ ...item })),
    ]),
  ) as ResponsiveLayouts;
}

function applyBoundsToResponsiveLayouts(
  layouts: ResponsiveLayouts,
  widgets: DashboardManifestWidget[],
  widgetContracts: Map<string, ReturnType<typeof getWidgetSizeContract>>,
  editMode: boolean,
  lockedWidgetIds: Set<string>,
) {
  return Object.fromEntries(
    Object.entries(layouts).map(([breakpoint, layout]) => {
      const columns = LAUNCHER_COLUMNS[breakpoint as keyof typeof LAUNCHER_COLUMNS] ?? LAUNCHER_COLUMNS.lg;
      const safeLayout = layout ?? [];
      return [
        breakpoint,
        safeLayout.map((item) => {
          const widget = widgets.find((entry) => entry.widget_id === item.i);
          const contract = widget ? widgetContracts.get(widget.widget_id) : null;
          if (!widget || !contract) {
            return item;
          }

          const min = clampSize(contract.minSize, columns);
          const max = clampSize(contract.maxSize, columns);
          const locked = widget.locked_position || lockedWidgetIds.has(widget.widget_id);
          const lockedSize = Boolean(widget.locked_size);
          const canResize = editMode && !locked && !lockedSize && widgetCanResize(widget);
          return {
            ...item,
            minW: min.w,
            minH: min.h,
            maxW: max.w,
            maxH: max.h,
            lockedPosition: locked,
            lockedSize,
            isResizable: canResize,
            resizeHandles: canResize ? ["se"] : undefined,
            isDraggable: editMode && !locked,
            static: locked,
          };
        }),
      ];
    }),
  ) as ResponsiveLayouts;
}

function parseNumber(value: string | number | null | undefined) {
  if (value === null || value === undefined || value === "") return null;
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  const normalized = String(value).replace(/\s+/g, "").replace(",", ".");
  const parsed = Number(normalized);
  return Number.isFinite(parsed) ? parsed : null;
}

function formatNumberString(value: number, maximumFractionDigits = 0) {
  const formatted = new Intl.NumberFormat("ru-RU", { maximumFractionDigits })
    .format(Math.abs(value))
    .replace(/\u00A0/g, " ");
  return value < 0 ? `−${formatted}` : formatted;
}

function formatPlainNumber(value: string | number | null | undefined) {
  const parsed = parseNumber(value);
  if (parsed === null) return "—";
  return formatNumberString(parsed, 0);
}

function formatMoney(value: string | number | null | undefined, currencyCode?: string | null) {
  const parsed = parseNumber(value);
  if (parsed === null) return "—";
  const formatted = formatNumberString(parsed, 0);
  return currencyCode ? `${formatted} ${currencyCode}` : formatted;
}

function formatPercent(value: string | number | null | undefined) {
  const parsed = parseNumber(value);
  if (parsed === null) return "—";
  return `${formatNumberString(parsed, 1)}%`;
}

export function formatPresentationValue(value: string | number | null | undefined) {
  if (value === null || value === undefined || value === "") {
    return "—";
  }
  const parsed = parseNumber(value);
  if (parsed === null) {
    return String(value).trim();
  }
  return formatPlainNumber(parsed);
}

export function presentationMetricLabel(key: string) {
  const normalized = key.trim();
  if (!normalized) return "Показатель";
  const normalizedKey = normalized.toLowerCase();
  if (METRIC_LABELS[normalizedKey]) return METRIC_LABELS[normalizedKey];
  const upper = normalized.toUpperCase();
  if (upper === "CUSTOMER_RETURN_VALUE") return "Сумма документов возврата";
  if (upper === "SALE_REVENUE") return "Выручка";
  if (upper === "PAYMENTS_RECEIVED") return "Поступления";
  if (upper === "CASH_OUT") return "Расходы";
  if (upper === "CASH_FLOW") return "Чистый денежный поток";
  if (upper === "ORDER_COUNT") return "Заказы";
  if (upper === "SOLD_UNITS") return "Продано единиц";
  if (upper === "AVERAGE_ORDER" || upper === "AVERAGE_ORDER_VALUE" || upper === "AVERAGE_CHECK") return "Средний заказ";
  if (upper === "CUSTOMERS" || upper === "CUSTOMERS_COUNT" || upper === "UNIQUE_CUSTOMERS") return "Клиенты";
  if (upper === "PRODUCTS" || upper === "PRODUCTS_COUNT" || upper === "UNIQUE_PRODUCTS") return "Товары";
  if (upper === "VISITS" || upper === "VISITS_COUNT") return "Визиты";
  return "Показатель";
}

function metricCurrency(metric?: SerializedMetricValue | null) {
  return metric?.currency || (metric?.unit === "currency" ? "UZS" : null);
}

function formatMetric(metric?: SerializedMetricValue | null) {
  if (!metric) return "—";
  if (metric.value === null || metric.value === undefined || metric.value === "") {
    return metric.data_status === "NO_VERIFIED_DATA" ? "Недостаточно данных" : "—";
  }
  if (metric.unit === "currency") {
    return formatMoney(metric.value, metricCurrency(metric));
  }
  if (metric.unit === "percent") {
    return formatPercent(metric.value);
  }
  if (metric.unit === "days") {
    const value = formatPlainNumber(metric.value);
    return value === "—" ? value : `${value} дн.`;
  }
  return formatPlainNumber(metric.value);
}

function metricDelta(metric?: SerializedMetricValue | null) {
  if (!metric || metric.delta === null || metric.delta === undefined || metric.delta === "") return null;
  const deltaValue = parseNumber(metric.delta);
  const percent = parseNumber(metric.percent_delta);
  const direction = deltaValue !== null && deltaValue > 0 ? "+" : "";
  if (metric.unit === "currency") {
    return `${direction}${formatMoney(metric.delta, metricCurrency(metric))}${percent !== null ? ` · ${direction}${formatPercent(percent)}` : ""}`;
  }
  if (percent !== null) {
    return `${direction}${formatPercent(percent)}`;
  }
  return `${direction}${formatPlainNumber(metric.delta)}`;
}

function widgetPayload<T>(widget: DashboardManifestWidget) {
  return (widget.payload ?? {}) as T;
}

function metricTone(metric?: SerializedMetricValue | null) {
  const status = metric?.data_status;
  if (status === "AVAILABLE") return "text-[#f4f7fb]";
  if (status === "PARTIAL" || status === "ANALYSIS_PENDING") return "text-[#FFF27A]";
  return "text-slate-400";
}

function businessCopy(text?: unknown) {
  if (typeof text !== "string" || !text) return null;
  const normalized = text.trim();
  if (!normalized) return null;

  const lower = normalized.toLowerCase();
  if (lower === "medium") return "Средний";
  if (lower === "low") return "Низкий";
  if (lower === "critical") return "Критично";
  if (lower === "all time") return "За весь период";
  if (/^\d+\s+canonical rows/i.test(normalized)) return null;
  if (/^(canonical|materialized|snapshot|verified|partial)$/i.test(normalized)) return null;
  if (/\bcanonical\b/i.test(normalized) && normalized.length < 80) return null;
  if (/\bmaterialized\b/i.test(normalized)) return null;
  return normalized;
}

function evidenceCopy(value: unknown) {
  if (typeof value === "string") return businessCopy(value) ?? value;
  if (value === null || value === undefined) return null;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (typeof value === "object") {
    const record = value as Record<string, unknown>;
    for (const key of ["label", "title", "name", "description", "value"]) {
      if (typeof record[key] === "string" && record[key]) return record[key] as string;
    }
    try {
      return JSON.stringify(value);
    } catch {
      return null;
    }
  }
  return null;
}

export function displayMetricLabel(label?: string | null) {
  if (!label) return null;
  const normalized = label.trim();
  if (!normalized) return null;

  const copy = businessCopy(normalized);
  if (copy && copy !== normalized) {
    return copy;
  }

  const metricLabel = presentationMetricLabel(normalized);
  if (metricLabel !== "Показатель") {
    return metricLabel;
  }

  return copy;
}

function widgetHeader(widget: DashboardManifestWidget, compact = false) {
  const subtitle = businessCopy(widget.subtitle);
  return (
    <div className="drag-handle flex items-start justify-between gap-3">
      <div className="min-w-0">
        <h3 className={cn("mt-1 line-clamp-2 font-semibold leading-[1.1] tracking-[-0.04em] text-[#f4f7fb]", compact ? "text-[16px]" : "text-[18px]")}>
          {widgetTitleFromName(widget.title)}
        </h3>
        {subtitle ? <p className={cn("mt-1 leading-6 text-slate-400", compact ? "text-xs" : "text-sm")}>{subtitle}</p> : null}
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <Badge
          variant={statusVariant(widget.data_status)}
          className={cn("px-2 py-0.5 text-[10px] leading-4", compact && "text-[9px]")}
        >
          {statusLabel(widget.data_status, compact)}
        </Badge>
      </div>
    </div>
  );
}

function widgetFooter(widget: DashboardManifestWidget, compact = false) {
  void widget;
  void compact;
  return null;
}

function semanticSizeLabel(size: LauncherSemanticSize) {
  switch (size) {
    case "small":
      return "Маленький";
    case "medium":
      return "Средний";
    case "large":
      return "Большой";
    default:
      return "Средний";
  }
}

function widgetSemanticSizeOptions(widget: DashboardManifestWidget) {
  const allowed = launcherSemanticSizeOptions(getWidgetSizeContract(widget).allowedSizes);
  return allowed.length > 0 ? allowed : ["small"];
}

function widgetSizeFromContract(widget: DashboardManifestWidget, size: LauncherSemanticSize) {
  const allowed = widgetSemanticSizeOptions(widget);
  if (allowed.includes(size)) return size;
  if (allowed.includes("medium")) return "medium";
  if (allowed.includes("small")) return "small";
  return allowed[0] ?? "small";
}

type WidgetEditMenuProps = {
  widget: DashboardManifestWidget;
  currentSize: LauncherSemanticSize;
  locked: boolean;
  onChangeSize: (size: LauncherSemanticSize) => void;
  onToggleLock: () => void;
  onHide: () => void;
};

function WidgetEditMenu({
  widget,
  currentSize,
  locked,
  onChangeSize,
  onToggleLock,
  onHide,
}: WidgetEditMenuProps) {
  const sizeOptions = widgetSemanticSizeOptions(widget);

  return (
    <Dropdown
      align="right"
      trigger={
        <button
          type="button"
          className="inline-flex h-9 w-9 items-center justify-center rounded-full border border-[#3a3d43] bg-[#2E3137] text-slate-400 shadow-[0_10px_24px_rgba(15,23,42,0.08)] transition hover:border-[#4a4e56] hover:text-[#f4f7fb]"
          aria-label="Редактировать виджет"
        >
          ⋯
        </button>
      }
      panelClassName="w-64 rounded-[22px] border border-[#3a3d43] bg-[#2E3137] p-3 shadow-[0_24px_60px_rgba(15,23,42,0.14)]"
    >
      {(close) => (
        <>
          <p className="text-[11px] uppercase tracking-[0.26em] text-slate-400">Размер</p>
          <div className="mt-2 grid gap-2">
            {sizeOptions.map((size) => (
              <button
                key={size}
                type="button"
                onClick={() => {
                  onChangeSize(size);
                  close();
                }}
                className={cn(
                  "rounded-[16px] border px-3 py-2 text-left text-sm font-medium transition",
                  currentSize === size
                    ? "border-[#FFF27A]/30 bg-[#FFF27A] text-[#1E1E21]"
                    : "border-[#3a3d43] bg-[#2E3137] text-slate-300 hover:border-[#4a4e56] hover:text-[#f4f7fb]",
                )}
              >
                {semanticSizeLabel(size)}
              </button>
            ))}
          </div>

          <div className="my-3 h-px bg-[#3a3d43]" />

          <div className="grid gap-2">
            <button
              type="button"
              onClick={() => {
                onToggleLock();
                close();
              }}
              className="rounded-[16px] border border-[#3a3d43] bg-[#2E3137] px-3 py-2 text-left text-sm font-medium text-slate-300 transition hover:border-[#4a4e56] hover:text-[#f4f7fb]"
            >
              {locked ? "Разблокировать" : "Закрепить"}
            </button>
            <button
              type="button"
              onClick={() => {
                onHide();
                close();
              }}
              className="rounded-[16px] border border-[#3a3d43] bg-[#2E3137] px-3 py-2 text-left text-sm font-medium text-slate-300 transition hover:border-[#4a4e56] hover:text-[#f4f7fb]"
            >
              Скрыть
            </button>
          </div>
        </>
      )}
    </Dropdown>
  );
}

function widgetVariantToCount(variant: LauncherWidgetVariant | undefined, dense = false) {
  switch (variant) {
    case "compact":
      return dense ? 1 : 2;
    case "regular":
      return dense ? 2 : 3;
    case "expanded":
      return dense ? 3 : 4;
    case "xl":
      return dense ? 4 : 6;
    default:
      return dense ? 2 : 3;
  }
}

function widgetListCount(widget: DashboardManifestWidget, variant?: LauncherWidgetVariant) {
  const family = getWidgetSizeContract(widget).family;
  switch (family) {
    case "kpi":
      return 0;
    case "chart":
      return variant === "compact" ? 2 : variant === "regular" ? 3 : variant === "expanded" ? 4 : 6;
    case "table":
      return variant === "compact" ? 4 : variant === "regular" ? 6 : variant === "expanded" ? 8 : 10;
    case "list":
      return variant === "compact" ? 3 : variant === "regular" ? 4 : variant === "expanded" ? 6 : 8;
    case "summary":
      return variant === "compact" ? 1 : variant === "regular" ? 2 : variant === "expanded" ? 3 : 4;
    case "detail":
      return variant === "compact" ? 1 : variant === "regular" ? 2 : variant === "expanded" ? 3 : 5;
    case "alert":
      return variant === "compact" ? 1 : variant === "regular" ? 2 : 3;
    default:
      return widgetVariantToCount(variant, true) + 1;
  }
}

function widgetSurfacePadding(widget: DashboardManifestWidget, variant?: LauncherWidgetVariant) {
  const group = widgetLayoutGroup(widget);
  if (widget.widget_id === "executive-brief" || widget.widget_type === "data_quality") {
    return variant === "compact" ? "p-4" : "p-4 sm:p-5";
  }
  if (variant === "compact") {
    return "p-4";
  }
  if (group === "table") return "p-4 sm:p-5";
  if (group === "kpi") return "p-5";
  if (group === "alert") return "p-5";
  return "p-5";
}

function widgetTitleFromName(title: string) {
  const metricLabel = displayMetricLabel(title);
  if (metricLabel && metricLabel !== "Показатель") return metricLabel;
  if (title === "Revenue" || title === "Revenue KPI") return "Выручка";
  if (title === "Orders" || title === "Orders KPI") return "Заказы";
  if (title === "Sold Units" || title === "Sold Units KPI") return "Продано единиц";
  if (title === "Average Order" || title === "Average Order Value") return "Средний заказ";
  if (title === "Customers" || title === "Customers KPI") return "Клиенты";
  if (title === "Products" || title === "Products KPI") return "Товары";
  if (title === "Visits" || title === "Visits KPI") return "Визиты";
  if (title === "Sales Summary") return "Сводка продаж";
  if (title === "Executive brief") return "Сводка руководителя";
  if (title === "Watchlist") return "На контроле";
  if (title === "Product Signals") return "Товарные сигналы";
  if (title === "Data Quality") return "Качество данных";
  if (title === "Inventory Risk") return "Риски запасов";
  if (title === "Visit Summary") return "Визиты";
  if (title === "Organization Comparison") return "Сравнение организаций";
  if (title === "Product Ranking") return "Топ товаров";
  if (title === "Customer Ranking") return "Клиенты";
  if (title === "Cash Flow") return "Денежный поток";
  if (title === "Payments Received") return "Поступления";
  if (title === "Returns") return "Возвраты";
  if (title === "Revenue Trend") return "Динамика выручки";
  if (title === "Ограничение качества данных") return "Качество данных";
  return title;
}

export function aggregateProductSignalWidgets(widgets: DashboardManifestWidget[]) {
  const normalized = widgets.filter(Boolean);
  const productSignals = normalized.filter((widget) => {
    const title = String(widget.title ?? "").toLowerCase();
    return widget.widget_type === "product_alert"
      || (widget.widget_type === "ai_insight" && widget.entity_type === "product")
      || (widget.widget_type === "watchlist" && widget.entity_type === "product")
      || title.includes("товар") || title.includes("product");
  });

  if (productSignals.length <= 1) return normalized;

  const remainder = normalized.filter((widget) => !productSignals.includes(widget));
  const first = productSignals[0];
  const mergedOrganizations = Array.from(new Set(productSignals.flatMap((widget) => widget.organization_ids ?? [])));
  const rows = productSignals.map((widget, index) => ({
    id: widget.widget_id,
    title: widget.title,
    summary: businessCopy(widget.summary) ?? businessCopy(widget.subtitle) ?? "Продуктовый сигнал требует внимания.",
    severity: widget.data_status === "AVAILABLE" ? "info" : widget.data_status === "PARTIAL" ? "warning" : "attention",
    recommendation: widget.payload && typeof widget.payload === "object" && "recommendation" in widget.payload
      ? String((widget.payload as Record<string, unknown>).recommendation ?? "")
      : null,
    evidence: widget.signal_ids ?? [],
    tags: [
      widget.entity_type ?? "product",
      widget.source_type ?? "AI_DYNAMIC",
      `#${index + 1}`,
    ],
  }));

  return [
    ...remainder,
    {
      ...first,
      widget_id: "product-signals",
      widget_type: "watchlist",
      title: "Товарные сигналы",
      subtitle: "Собранные товарные предупреждения в одной карточке",
      signal_ids: productSignals.flatMap((widget) => widget.signal_ids ?? []),
      entity_type: "product",
      entity_id: null,
      organization_ids: mergedOrganizations,
      semantic_size: first.semantic_size === "XL" ? "XL" : "L",
      priority: Math.min(...productSignals.map((widget) => widget.priority)) - 0.25,
      priority_reason: "Сгруппированы однотипные товарные сигналы",
      min_size: "L",
      preferred_size: "L",
      max_size: "XL",
      supports_horizontal_expand: true,
      supports_vertical_expand: true,
      supports_internal_scroll: false,
      flow: "vertical",
      preferred_aspect: "tall",
      content_density: "high",
      scroll_behavior: "none",
      removable_by_ai: true,
      movable_by_ai: true,
      resizable_by_ai: true,
      locked_position: false,
      locked_size: false,
      pinned: false,
      hidden: false,
      drilldown: first.drilldown,
      summary: "Товарные сигналы, которые требуют внимания.",
      data_status: productSignals.some((widget) => widget.data_status === "AVAILABLE") ? "AVAILABLE" : "PARTIAL",
      payload: {
        rows,
        source_widget_ids: productSignals.map((widget) => widget.widget_id),
        total_count: productSignals.length,
      },
    } as DashboardManifestWidget,
  ];
}

export function getExecutiveBriefVisibleInsightLimit(variant?: LauncherWidgetVariant) {
  switch (variant) {
    case "compact":
      return 1;
    case "regular":
      return 2;
    case "expanded":
      return 3;
    case "xl":
      return 3;
    default:
      return 3;
  }
}

const METRIC_LABELS: Record<string, string> = {
  low_stock: "Низкий остаток",
  overstock: "Избыток",
  stockout_risk: "Риск дефицита",
  cash_flow: "Денежный поток",
  payments_received: "Поступления",
  returns: "Возвраты",
  verified_cash_in: "Подтверждённый приток",
  verified_cash_out: "Подтверждённый отток",
  revenue: "Выручка",
  orders: "Заказы",
  sold_units: "Продано единиц",
  customers: "Клиенты",
  customers_count: "Клиенты",
  unique_customers: "Клиенты",
  products: "Товары",
  products_count: "Товары",
  unique_products: "Товары",
  visits: "Визиты",
  visits_count: "Визиты",
  orders_count: "Заказы",
  average_order: "Средний заказ",
  average_order_value: "Средний заказ",
  average_check: "Средний заказ",
  sales: "Продажи",
  sales_count: "Продажи",
  conversion_rate: "Конверсия",
  return_rate: "Доля возвратов",
  current_stock: "Остаток",
  days_of_stock: "Дней запаса",
  sales_velocity_30d: "Скорость 30д",
};

function humanizeMetricKey(key: string) {
  return presentationMetricLabel(key);
}

function SmallStat({ label, value, note, compact = false }: { label: string; value: string; note?: string | null; compact?: boolean }) {
  return (
    <div className={cn("rounded-[18px] border border-[#3a3d43] bg-[#343840]/80", compact ? "p-2.5" : "p-3")}>
      <p className={cn("uppercase tracking-[0.24em] text-slate-400", compact ? "text-[10px]" : "text-[11px]")}>{label}</p>
      <p className={cn("mt-2 font-semibold tracking-[-0.03em] text-[#f4f7fb]", compact ? "text-base" : "text-lg")}>{value}</p>
      {note ? <p className={cn("mt-1 text-slate-400", compact ? "text-[11px] leading-5" : "text-xs")}>{note}</p> : null}
    </div>
  );
}

function ListShell({ children, scroll }: { children: React.ReactNode; scroll?: boolean }) {
  return (
    <div className={cn("mt-4 min-h-0 flex-1", scroll ? "overflow-y-auto pr-1" : "overflow-hidden")}>{children}</div>
  );
}

function resolveVisibleMetricStatus(metric?: SerializedMetricValue | null, fallbackStatus?: AnalyticsDataStatus): AnalyticsDataStatus {
  const status = metric?.data_status ?? metric?.status ?? fallbackStatus ?? "NO_DATA";
  if (status === "AVAILABLE" || status === "PARTIAL" || status === "ANALYSIS_PENDING") {
    return status;
  }

  const hasVisibleData =
    metric !== null &&
    metric !== undefined &&
    [
      metric.value,
      metric.previous_value,
      metric.delta,
      metric.percent_delta,
      metric.coverage,
      metric.confidence,
      metric.record_count,
      metric.currency,
      metric.note,
    ].some((value) => value !== null && value !== undefined && value !== "");

  return hasVisibleData ? "AVAILABLE" : status;
}

function KpiWidget({ widget, variant }: { widget: DashboardManifestWidget; variant?: LauncherWidgetVariant }) {
  const payload = widgetPayload<{ metric?: SerializedMetricValue; metric_key?: string }>(widget);
  const metric = payload.metric;
  const compact = variant === "compact";
  return (
    <Surface className={cn("group relative flex h-full min-h-0 flex-col overflow-hidden", widgetSurfacePadding(widget, variant))}>
      {widgetHeader(widget, compact)}
      <div className={cn("mt-5 flex min-h-0 flex-1 items-center justify-center", compact && "mt-4")}>
        <div className="w-full text-center">
          <p className={cn(compact ? "text-[28px]" : "text-[40px]", "font-semibold tracking-[-0.08em]", metricTone(metric))}>{formatMetric(metric)}</p>
          {!compact && payload.metric_key ? (
            <p className="mt-2 text-sm leading-6 text-slate-400">
              {displayMetricLabel(payload.metric_key) ?? "Показатель"}
            </p>
          ) : null}
        </div>
      </div>
      {compact ? null : widgetFooter(widget, compact)}
    </Surface>
  );
}

function buildSparkPath(values: number[], width: number, height: number) {
  const max = Math.max(...values, 1);
  const min = Math.min(...values, 0);
  const range = Math.max(max - min, 1);
  const step = values.length > 1 ? width / (values.length - 1) : width;
  return values
    .map((value, index) => {
      const x = index * step;
      const y = height - ((value - min) / range) * height;
      return `${index === 0 ? "M" : "L"}${x},${y}`;
    })
    .join(" ");
}

function TrendWidget({ widget, variant }: { widget: DashboardManifestWidget; variant?: LauncherWidgetVariant }) {
  const payload = widgetPayload<{ metric?: SerializedMetricValue; series?: Array<{ organization_name?: string; value?: string | number | null; status?: AnalyticsDataStatus }>; period_label?: string }>(widget);
  const metric = payload.metric;
  const values = (payload.series ?? []).map((item) => parseNumber(item.value) ?? 0);
  const hasSeries = values.some((value) => value > 0);
  const seriesLimit = widgetListCount(widget, variant);
  const chartHeight = variant === "compact" ? 80 : variant === "regular" ? 108 : variant === "expanded" ? 128 : 140;
  const periodLabel = businessCopy(payload.period_label) ?? businessCopy(widget.summary) ?? "За выбранный период";
  return (
    <Surface className={cn("group relative flex h-full min-h-0 flex-col overflow-hidden", widgetSurfacePadding(widget, variant))}>
      {widgetHeader(widget, variant === "compact")}
      <div className={cn("mt-5 flex min-h-0 flex-1 flex-col gap-4", variant === "compact" && "gap-3")}>
        <div className="flex items-end justify-between gap-4">
          <div>
            <p className={cn(variant === "compact" ? "text-[28px]" : "text-[38px]", "font-semibold tracking-[-0.08em]", metricTone(metric))}>{formatMetric(metric)}</p>
            <p className={cn("mt-1 text-slate-400", variant === "compact" ? "text-xs" : "text-sm")}>{periodLabel}</p>
          </div>
          {metricDelta(metric) ? <Badge variant="accent">{metricDelta(metric)}</Badge> : null}
        </div>
        <div className="rounded-[24px] border border-[#3a3d43] bg-[linear-gradient(180deg,#2E3137_0%,#26292e_100%)] p-3">
          {hasSeries ? (
            <>
              <svg viewBox="0 0 520 180" className="w-full" style={{ height: `${chartHeight}px` }}>
                <g stroke="#e2e8f0" strokeDasharray="4 6">
                  {[0, 1, 2, 3].map((index) => {
                    const y = 12 + index * 48;
                    return <line key={index} x1="0" x2="520" y1={y} y2={y} />;
                  })}
                </g>
                <path d={buildSparkPath(values, 520, 152)} fill="none" stroke="#4f46e5" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              <div className={cn("mt-3 grid gap-2", variant === "compact" ? "sm:grid-cols-2" : "sm:grid-cols-2 xl:grid-cols-3")}>
                {(payload.series ?? []).slice(0, seriesLimit).map((row, index) => (
                  <div key={`${row.organization_name ?? "series"}-${index}`} className="rounded-2xl border border-[#3a3d43] bg-[#2E3137] px-3 py-2">
                    <p className="text-xs uppercase tracking-[0.22em] text-slate-400">{row.organization_name ?? `Сегмент ${index + 1}`}</p>
                    <p className="mt-1 text-sm font-semibold text-[#f4f7fb]">{formatMoney(row.value ?? null, metricCurrency(metric))}</p>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <div className={cn(
              "flex h-full items-center justify-center rounded-[20px] border border-dashed border-[#3a3d43] bg-[#2E3137]/60 px-6 text-center text-sm leading-6 text-slate-400",
              variant === "compact" ? "min-h-[148px]" : variant === "regular" ? "min-h-[180px]" : "min-h-[220px]",
            )}>
              Для этого виджета пока нет временного ряда в текущем контексте.
            </div>
          )}
        </div>
      </div>
      {variant === "compact" ? null : widgetFooter(widget, false)}
    </Surface>
  );
}

function ExecutiveBriefWidget({ widget, variant }: { widget: DashboardManifestWidget; variant?: LauncherWidgetVariant }) {
  const payload = widgetPayload<{
    headline?: string;
    business_status?: string;
    key_numbers?: ExecutiveNumber[];
    top_insights?: SerializedAIInsight[];
    risks?: SerializedAIInsight[];
    opportunities?: SerializedAIInsight[];
    data_warnings?: SerializedAIInsight[];
  }>(widget);
  const keyLimit = variant === "xl" ? 2 : 1;
  const visibleLimit = getExecutiveBriefVisibleInsightLimit(variant);
  const flattenedInsights = [
    { title: "Ключевые сигналы", rows: payload.top_insights },
    { title: "Риски", rows: payload.risks },
    { title: "Возможности", rows: payload.opportunities },
    { title: "Что влияет на точность", rows: payload.data_warnings },
  ].flatMap(({ title, rows }) => (rows ?? []).map((item) => ({ ...item, sectionTitle: title })));
  const visibleInsights = flattenedInsights.slice(0, visibleLimit);
  const hiddenInsights = Math.max(0, flattenedInsights.length - visibleInsights.length);
  const metricChipLimit = variant === "xl" ? 3 : variant === "expanded" ? 2 : 1;
  return (
    <Surface className={cn("group relative flex h-full min-h-0 flex-col overflow-hidden", widgetSurfacePadding(widget, variant))}>
      {widgetHeader(widget, variant === "compact")}
      <div className={cn("mt-4 min-h-0 flex-1 overflow-y-auto pr-1", variant === "compact" ? "space-y-3" : "space-y-4")}>
        <div className="space-y-3">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <p className={cn("font-semibold tracking-[-0.03em] text-[#f4f7fb]", variant === "compact" ? "text-base" : "text-lg")}>
                {businessCopy(payload.headline) ?? businessCopy(widget.summary) ?? "Краткая executive-сводка"}
              </p>
              {payload.business_status ? (
                <p className={cn("mt-1 text-slate-400", variant === "compact" ? "text-xs" : "text-sm")}>
                  {businessCopy(payload.business_status) ?? payload.business_status}
                </p>
              ) : null}
            </div>
            {payload.key_numbers?.length ? (
              <div className={cn("grid gap-2", variant === "compact" ? "grid-cols-1" : "grid-cols-2 sm:grid-cols-2 xl:grid-cols-4")}>
                {payload.key_numbers.slice(0, keyLimit).map((item, index) => (
                  <div key={`${item.label ?? "num"}-${index}`} className="rounded-[18px] border border-[#3a3d43] bg-[#2E3137] px-3 py-2">
                    <p className="text-[11px] uppercase tracking-[0.24em] text-slate-400">{displayMetricLabel(item.label) ?? businessCopy(item.label) ?? item.label ?? `Метрика ${index + 1}`}</p>
                    <p className={cn("mt-2 font-semibold tracking-[-0.03em] text-[#f4f7fb]", variant === "compact" ? "text-base" : "text-lg")}>{formatPresentationValue(item.current)}</p>
                    {item.delta !== null && item.delta !== undefined && item.delta !== "" ? (
                      <p className="mt-1 text-xs text-slate-400">Δ {formatPresentationValue(item.delta)}</p>
                    ) : null}
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        </div>

        {visibleInsights.length ? (
          <div className="space-y-3">
            {visibleInsights.map((item, index) => (
              <div
                key={`${item.id ?? item.title ?? "insight"}-${index}`}
                className={cn("rounded-[18px] border border-[#3a3d43] bg-[#2E3137] px-4 py-3 shadow-[0_8px_18px_rgba(15,23,42,0.03)]", variant === "compact" && "px-3 py-3")}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant="soft">{item.sectionTitle ?? "Сигнал"}</Badge>
                      {severityLabel(item.severity) ? <Badge variant="accent">{severityLabel(item.severity)}</Badge> : null}
                    </div>
                    <p className={cn("mt-2 font-semibold tracking-[-0.03em] text-[#f4f7fb]", variant === "compact" ? "text-sm" : "text-base")}>
                      {displayMetricLabel(item.title) ?? businessCopy(item.title) ?? item.title ?? "Сигнал"}
                    </p>
                    {item.summary ? (
                      <p className={cn("mt-1 leading-6 text-slate-300", variant === "compact" ? "text-xs leading-5" : "text-sm")}>
                        {businessCopy(item.summary) ?? item.summary}
                      </p>
                    ) : null}
                  </div>
                </div>
                {item.metrics?.length ? (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {item.metrics.slice(0, metricChipLimit).map((metric, metricIndex) => (
                      <div key={`${item.id ?? index}-metric-${metricIndex}`} className="rounded-full border border-[#3a3d43] bg-[#343840] px-3 py-1 text-xs text-slate-300">
                        {metric.label ? `${displayMetricLabel(metric.label) ?? metric.label}: ` : ""}
                        <span className="font-medium text-[#f4f7fb]">{formatPresentationValue(metric.current)}</span>
                      </div>
                    ))}
                  </div>
                ) : null}
                {item.recommendation ? (
                  <p className="mt-2 text-sm font-medium text-[#FFF27A]">{businessCopy(item.recommendation) ?? item.recommendation}</p>
                ) : null}
                {item.evidence?.length ? (
                  <div className="mt-2 flex flex-wrap gap-2">
                    {item.evidence.slice(0, 2).map((evidence, evidenceIndex) => (
                      <Badge key={`${item.id ?? index}-evidence-${evidenceIndex}`} variant="soft">
                        {evidenceCopy(evidence) ?? "Подтверждённые данные"}
                      </Badge>
                    ))}
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        ) : (
          <div className="rounded-[20px] border border-dashed border-[#3a3d43] bg-[#2E3137] px-5 py-6 text-sm text-slate-400">
            Пока нет подтверждённых executive-выводов для текущего контекста.
          </div>
        )}

        {hiddenInsights > 0 ? (
          <div className="inline-flex w-fit items-center rounded-full border border-[#3a3d43] bg-[#2E3137] px-4 py-2 text-xs font-medium text-slate-400">
            Ещё {hiddenInsights} выводов
          </div>
        ) : null}
      </div>
      {widgetFooter(widget, variant === "compact")}
    </Surface>
  );
}

function RankingWidget({ widget, rows, customerMode = false, variant }: { widget: DashboardManifestWidget; rows: SerializedProductRow[] | SerializedCustomerRow[]; customerMode?: boolean; variant?: LauncherWidgetVariant }) {
  return (
    <Surface className={cn("group relative flex h-full min-h-0 flex-col overflow-hidden", widgetSurfacePadding(widget, variant))}>
      {widgetHeader(widget, variant === "compact")}
      <ListShell scroll>
        <div className="space-y-3">
          {rows.length ? rows.map((row, index) => {
            const productRow = row as SerializedProductRow;
            const customerRow = row as SerializedCustomerRow;
            const name = customerMode ? customerRow.customer_name : productRow.product_name;
            const sublabel = customerMode
              ? `${formatMetric(customerRow.orders_count)} заказов · ${formatMetric(customerRow.sold_units)} ед.`
              : `${productRow.organization_name ?? "Организация"} · ${formatMetric(productRow.sold_units)} ед.`;
            const valueMetric = customerMode ? customerRow.revenue : productRow.revenue;
            const noteMetric = customerMode ? customerRow.days_since_last_order : productRow.current_stock;
            return (
              <div key={`${name ?? "row"}-${index}`} className={cn("rounded-[20px] border border-[#3a3d43] bg-[#343840]/80", variant === "compact" ? "p-3" : "p-4")}>
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-3">
                      <span className={cn("inline-flex shrink-0 items-center justify-center rounded-full bg-slate-900 font-semibold text-white", variant === "compact" ? "h-8 w-8 text-xs" : "h-9 w-9 text-sm")}>{index + 1}</span>
                      <div className="min-w-0">
                        <p className={cn("truncate font-semibold tracking-[-0.03em] text-[#f4f7fb]", variant === "compact" ? "text-sm" : "text-base")}>{name ?? "Без названия"}</p>
                        <p className={cn("mt-1 text-slate-400", variant === "compact" ? "text-xs" : "text-sm")}>{sublabel}</p>
                      </div>
                    </div>
                  </div>
                  <div className="text-right">
                    <p className={cn("font-semibold tracking-[-0.03em] text-[#f4f7fb]", variant === "compact" ? "text-base" : "text-lg")}>{formatMetric(valueMetric)}</p>
                    {noteMetric ? <p className="mt-1 text-xs text-slate-400">{customerMode ? `С последнего заказа: ${formatMetric(noteMetric)}` : `Остаток: ${formatMetric(noteMetric)}`}</p> : null}
                  </div>
                </div>
              </div>
            );
          }) : (
            <div className="rounded-[20px] border border-dashed border-[#3a3d43] bg-[#343840] px-5 py-10 text-center text-sm text-slate-400">
              Нет строк для текущего контекста.
            </div>
          )}
        </div>
      </ListShell>
      {widgetFooter(widget, variant === "compact")}
    </Surface>
  );
}

function OrganizationComparisonWidget({ widget, variant }: { widget: DashboardManifestWidget; variant?: LauncherWidgetVariant }) {
  const payload = widgetPayload<{ rows?: SerializedOrganizationRow[] }>(widget);
  const rows = payload.rows ?? [];
  return (
    <Surface className={cn("group relative flex h-full min-h-0 flex-col overflow-hidden", widgetSurfacePadding(widget, variant))}>
      {widgetHeader(widget, variant === "compact")}
      <div className={cn("mt-4 min-h-0 flex-1 overflow-hidden rounded-[22px] border border-[#3a3d43] bg-[#2E3137]", variant === "compact" && "text-xs")}>
        <div className="h-full overflow-auto">
          <table className={cn("min-w-full text-left", variant === "compact" ? "text-xs" : "text-sm")}>
            <thead className="sticky top-0 bg-[#343840] text-slate-400">
              <tr>
                <th className={cn("font-medium", variant === "compact" ? "px-3 py-2" : "px-4 py-3")}>Организация</th>
                <th className={cn("font-medium", variant === "compact" ? "px-3 py-2" : "px-4 py-3")}>Выручка</th>
                <th className={cn("font-medium", variant === "compact" ? "px-3 py-2" : "px-4 py-3")}>Заказы</th>
                <th className={cn("font-medium", variant === "compact" ? "px-3 py-2" : "px-4 py-3")}>Продано</th>
                <th className={cn("font-medium", variant === "compact" ? "px-3 py-2" : "px-4 py-3")}>Поступления</th>
                <th className={cn("font-medium", variant === "compact" ? "px-3 py-2" : "px-4 py-3")}>Клиенты</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.organization_id} className="border-t border-[#3a3d43] align-top">
                  <td className={cn("font-semibold text-[#f4f7fb]", variant === "compact" ? "px-3 py-3" : "px-4 py-4")}>{row.organization_name}</td>
                  <td className={cn("text-slate-200", variant === "compact" ? "px-3 py-3" : "px-4 py-4")}>{formatMetric(row.metrics.revenue)}</td>
                  <td className={cn("text-slate-200", variant === "compact" ? "px-3 py-3" : "px-4 py-4")}>{formatMetric(row.metrics.orders)}</td>
                  <td className={cn("text-slate-200", variant === "compact" ? "px-3 py-3" : "px-4 py-4")}>{formatMetric(row.metrics.sold_units)}</td>
                  <td className={cn("text-slate-200", variant === "compact" ? "px-3 py-3" : "px-4 py-4")}>{formatMetric(row.metrics.payments_received)}</td>
                  <td className={cn("text-slate-200", variant === "compact" ? "px-3 py-3" : "px-4 py-4")}>{formatMetric(row.metrics.customers)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      {widgetFooter(widget, variant === "compact")}
    </Surface>
  );
}

function InventoryRiskWidget({ widget, variant }: { widget: DashboardManifestWidget; variant?: LauncherWidgetVariant }) {
  const payload = widgetPayload<{
    low_stock?: SerializedProductRow[];
    overstock?: SerializedProductRow[];
    stockout_risk?: SerializedProductRow[];
    transfer_opportunities?: SerializedInventoryOpportunity[];
  }>(widget);

  const sections = [
    ["Низкий остаток", payload.low_stock ?? []],
    ["Избыток", payload.overstock ?? []],
    ["Риск дефицита", payload.stockout_risk ?? []],
  ] as const;
  const visibleCount = Math.max(1, Math.min(variant === "compact" ? 1 : 2, widgetListCount(widget, variant)));

  return (
    <Surface className={cn("group relative flex h-full min-h-0 flex-col overflow-hidden", widgetSurfacePadding(widget, variant))}>
      {widgetHeader(widget, variant === "compact")}
      <ListShell scroll>
        <div className="space-y-4">
          {sections.map(([title, rows]) =>
            rows.length ? (
              <section key={title}>
                <div className="mb-2 flex items-center justify-between gap-3">
                  <h4 className="text-sm font-semibold uppercase tracking-[0.24em] text-slate-400">{title}</h4>
                  <Badge variant="soft">{rows.length}</Badge>
                </div>
                <div className="space-y-3">
                  {rows.slice(0, visibleCount).map((row, index) => (
                    <div key={`${title}-${row.product_external_id ?? row.product_name ?? index}`} className={cn("rounded-[18px] border border-[#3a3d43] bg-[#343840]/80", variant === "compact" ? "p-3" : "p-4")}>
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <p className={cn("truncate font-semibold tracking-[-0.03em] text-[#f4f7fb]", variant === "compact" ? "text-sm" : "text-base")}>{row.product_name ?? "Товар без имени"}</p>
                          <p className={cn("mt-1 text-slate-400", variant === "compact" ? "text-xs" : "text-sm")}>{row.organization_name ?? "Организация"}</p>
                        </div>
                        <Badge variant="accent">{title}</Badge>
                      </div>
                      <div className={cn("mt-3 grid gap-3", variant === "compact" ? "sm:grid-cols-2" : "sm:grid-cols-3")}>
                        <SmallStat compact={variant === "compact"} label="Остаток" value={formatMetric(row.current_stock)} />
                        <SmallStat compact={variant === "compact"} label="Дней запаса" value={formatMetric(row.days_of_stock)} />
                        <SmallStat compact={variant === "compact"} label="Скорость 30д" value={formatMetric(row.sales_velocity_30d)} />
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            ) : null,
          )}

          {payload.transfer_opportunities?.length ? (
            <section>
              <div className="mb-2 flex items-center justify-between gap-3">
                <h4 className="text-sm font-semibold uppercase tracking-[0.24em] text-slate-400">Переброска запасов</h4>
                <Badge variant="soft">{payload.transfer_opportunities.length}</Badge>
              </div>
              <div className="space-y-3">
                {payload.transfer_opportunities.slice(0, visibleCount).map((item, index) => (
                  <div key={`${item.product_external_id ?? item.product_name ?? index}-transfer`} className={cn("rounded-[18px] border border-[#3a3d43] bg-[#343840]/80", variant === "compact" ? "p-3" : "p-4")}>
                    <p className={cn("font-semibold tracking-[-0.03em] text-[#f4f7fb]", variant === "compact" ? "text-sm" : "text-base")}>{item.product_name ?? "Товар"}</p>
                    <p className={cn("mt-1 text-slate-400", variant === "compact" ? "text-xs" : "text-sm")}>{item.from_organization_name} → {item.to_organization_name}</p>
                    <div className={cn("mt-3 grid gap-3", variant === "compact" ? "sm:grid-cols-1" : "sm:grid-cols-2")}>
                      <SmallStat compact={variant === "compact"} label="Источник" value={formatMetric(item.source_stock)} note={formatMetric(item.source_days)} />
                      <SmallStat compact={variant === "compact"} label="Назначение" value={formatMetric(item.destination_stock)} note={formatMetric(item.destination_days)} />
                    </div>
                    {item.reason ? <p className="mt-3 text-sm text-[#FFF27A]">{item.reason}</p> : null}
                  </div>
                ))}
              </div>
            </section>
          ) : null}
        </div>
      </ListShell>
      {widgetFooter(widget, variant === "compact")}
    </Surface>
  );
}

function VisitSummaryWidget({ widget, variant }: { widget: DashboardManifestWidget; variant?: LauncherWidgetVariant }) {
  const payload = widgetPayload<{ metric?: SerializedMetricValue; sales_reps?: SerializedSalesRepRow[] }>(widget);
  const reps = payload.sales_reps ?? [];
  const resolvedStatus = resolveVisibleMetricStatus(payload.metric, widget.data_status);
  const resolvedWidget = resolvedStatus !== widget.data_status ? { ...widget, data_status: resolvedStatus } : widget;
  return (
    <Surface className={cn("group relative flex h-full min-h-0 flex-col overflow-hidden", widgetSurfacePadding(widget, variant))}>
      {widgetHeader(resolvedWidget, variant === "compact")}
      <div className={cn("mt-5 grid gap-3", variant === "compact" ? "sm:grid-cols-2" : "sm:grid-cols-3")}>
        <SmallStat compact={variant === "compact"} label="Визиты" value={formatMetric(payload.metric)} note={payload.metric?.note ?? null} />
        <SmallStat compact={variant === "compact"} label="Покрытие" value={payload.metric?.coverage !== null && payload.metric?.coverage !== undefined ? formatPlainNumber(payload.metric.coverage) : "—"} />
        <SmallStat compact={variant === "compact"} label="Статус" value={statusLabel(resolvedStatus, variant === "compact")} />
      </div>
      <ListShell scroll>
        <div className="space-y-3">
          {reps.length ? reps.map((rep, index) => (
            <div key={`${rep.sales_rep_external_id ?? rep.sales_rep_name ?? index}`} className={cn("rounded-[18px] border border-[#3a3d43] bg-[#343840]/80", variant === "compact" ? "p-3" : "p-4")}>
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className={cn("font-semibold tracking-[-0.03em] text-[#f4f7fb]", variant === "compact" ? "text-sm" : "text-base")}>{rep.sales_rep_name ?? "Без имени"}</p>
                  <p className={cn("mt-1 text-slate-400", variant === "compact" ? "text-xs" : "text-sm")}>{rep.organization_name ?? "Организация"}</p>
                </div>
                <Badge variant="soft">{formatMetric(rep.conversion_rate)}</Badge>
              </div>
              <div className={cn("mt-3 grid gap-3", variant === "compact" ? "sm:grid-cols-2" : "sm:grid-cols-4")}>
                <SmallStat compact={variant === "compact"} label="Визиты" value={formatMetric(rep.visits_count)} />
                <SmallStat compact={variant === "compact"} label="Заказы" value={formatMetric(rep.orders_count)} />
                <SmallStat compact={variant === "compact"} label="Выручка" value={formatMetric(rep.revenue)} />
                <SmallStat compact={variant === "compact"} label="Продано" value={formatMetric(rep.sold_units)} />
              </div>
            </div>
          )) : (
            <div className="rounded-[18px] border border-dashed border-[#3a3d43] bg-[#343840] px-5 py-10 text-center text-sm text-slate-400">Нет данных по полевой команде.</div>
          )}
        </div>
      </ListShell>
      {widgetFooter(widget, variant === "compact")}
    </Surface>
  );
}

function DataQualityWidget({ widget, variant }: { widget: DashboardManifestWidget; variant?: LauncherWidgetVariant }) {
  const payload = widgetPayload<{ items?: Array<{ metric_key?: string; data_status?: AnalyticsDataStatus; coverage?: number | null; confidence?: number | null; message?: string | null; missing_fields?: string[] }>; notes?: string[] }>(widget);
  const items = payload.items ?? [];
  const visibleItems = items.slice(0, 2);
  const hiddenItems = Math.max(0, items.length - visibleItems.length);
  const primaryItem = visibleItems[0] ?? null;
  return (
    <Surface className={cn("group relative flex h-full min-h-0 flex-col overflow-hidden", widgetSurfacePadding(widget, variant))}>
      {widgetHeader(widget, variant === "compact")}
      <div className="mt-4 flex min-h-0 flex-col gap-3">
        <div className="rounded-[18px] border border-[#3a3d43] bg-[#2E3137] px-4 py-3">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="text-sm font-semibold tracking-[-0.03em] text-[#f4f7fb]">Качество данных</p>
              <p className="mt-1 text-xs leading-5 text-slate-400">
                {primaryItem ? businessCopy(primaryItem.message) ?? "Есть ограничения по точности некоторых показателей." : "Показатели пока можно использовать как общую сводку без детальной проверки."}
              </p>
            </div>
            <Badge variant={statusVariant(primaryItem?.data_status ?? "NO_DATA")}>{statusLabel(primaryItem?.data_status ?? "NO_DATA", variant === "compact")}</Badge>
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            {primaryItem?.coverage !== null && primaryItem?.coverage !== undefined ? <Badge variant="soft">Покрытие {formatPercent(primaryItem.coverage)}</Badge> : null}
            {primaryItem?.confidence !== null && primaryItem?.confidence !== undefined ? <Badge variant="soft">Надёжность {formatPercent(primaryItem.confidence)}</Badge> : null}
          </div>
        </div>
        <div className="space-y-2">
          {visibleItems.map((item, index) => (
            <div key={`${item.metric_key ?? "quality"}-${index}`} className={cn("rounded-[18px] border border-[#3a3d43] bg-[#343840]/80", variant === "compact" ? "p-3" : "p-4")}>
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className={cn("font-semibold tracking-[-0.03em] text-[#f4f7fb]", variant === "compact" ? "text-sm" : "text-base")}>{humanizeMetricKey(item.metric_key ?? "Показатель")}</p>
                  <p className={cn("mt-1 leading-6 text-slate-200", variant === "compact" ? "text-xs leading-5" : "text-sm")}>
                    {businessCopy(item.message) ?? "Требуется уточнение части данных."}
                  </p>
                </div>
                <Badge variant={statusVariant(item.data_status ?? "NO_DATA")}>{statusLabel(item.data_status ?? "NO_DATA", variant === "compact")}</Badge>
              </div>
              <div className="mt-2 flex flex-wrap gap-2">
                {item.coverage !== null && item.coverage !== undefined ? <Badge variant="soft">Покрытие {formatPercent(item.coverage)}</Badge> : null}
                {item.confidence !== null && item.confidence !== undefined ? <Badge variant="soft">Надёжность {formatPercent(item.confidence)}</Badge> : null}
                {(item.missing_fields ?? []).length ? <Badge variant="neutral">Нужно уточнить {(item.missing_fields ?? []).length} полей</Badge> : null}
              </div>
            </div>
          ))}
        </div>
        {(payload.notes ?? []).length ? (
          <div className="rounded-[18px] border border-[#3a3d43] bg-[#2E3137] px-4 py-3 text-sm text-slate-300">
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">Что влияет на точность</p>
            <ul className="mt-2 space-y-1.5">
              {(payload.notes ?? []).slice(0, 2).map((note, index) => (
                <li key={`${note}-${index}`}>• {businessCopy(note) ?? note}</li>
              ))}
            </ul>
          </div>
        ) : null}
        {hiddenItems > 0 ? <div className="inline-flex w-fit items-center rounded-full border border-[#3a3d43] bg-[#2E3137] px-4 py-2 text-xs font-medium text-slate-400">Ещё {hiddenItems} ограничений</div> : null}
      </div>
      {widgetFooter(widget, variant === "compact")}
    </Surface>
  );
}

function AlertWidget({ widget, variant }: { widget: DashboardManifestWidget; variant?: LauncherWidgetVariant }) {
  const payload = widgetPayload<SerializedAIInsight>(widget);
  return (
    <Surface className={cn("group relative flex h-full min-h-0 flex-col overflow-hidden", widgetSurfacePadding(widget, variant))}>
      {widgetHeader(widget, variant === "compact")}
      <div className={cn("mt-4 flex min-h-0 flex-1 flex-col gap-3", variant === "compact" && "gap-2")}>
        <div className="rounded-[18px] border border-yellow-100 bg-[linear-gradient(180deg,#2E3137_0%,#26292e_100%)] p-4">
          <p className={cn("font-semibold tracking-[-0.03em] text-[#f4f7fb]", variant === "compact" ? "text-base" : "text-lg")}>{displayMetricLabel(payload.title) ?? displayMetricLabel(widget.title) ?? "Сигнал"}</p>
          <p className={cn("mt-2 leading-6 text-slate-300", variant === "compact" ? "text-xs" : "text-sm")}>{businessCopy(payload.summary) ?? businessCopy(widget.summary) ?? "Сигнал требует внимания."}</p>
          {payload.recommendation ? <p className={cn("mt-3 font-medium text-[#FFF27A]", variant === "compact" ? "text-xs" : "text-sm")}>{businessCopy(payload.recommendation) ?? payload.recommendation}</p> : null}
        </div>
        {payload.metrics?.length ? (
          <div className={cn("grid gap-3", variant === "compact" ? "sm:grid-cols-1" : "sm:grid-cols-2")}>
            {payload.metrics.slice(0, widgetListCount(widget, variant)).map((metric, index) => (
              <SmallStat
                compact={variant === "compact"}
                key={`${metric.label ?? "metric"}-${index}`}
                label={metric.label ? displayMetricLabel(metric.label) ?? metric.label : `Метрика ${index + 1}`}
                value={formatPresentationValue(metric.current)}
                note={metric.delta ? `Δ ${formatPresentationValue(metric.delta)}` : null}
              />
            ))}
          </div>
        ) : null}
        {payload.evidence?.length ? (
          <div className="flex flex-wrap gap-2">
            {payload.evidence.slice(0, 4).map((evidence, index) => (
              <Badge key={`alert-evidence-${index}`} variant="soft">{evidenceCopy(evidence) ?? "Подтверждённые данные"}</Badge>
            ))}
          </div>
        ) : null}
      </div>
      {widgetFooter(widget, variant === "compact")}
    </Surface>
  );
}

function WatchlistWidget({ widget, variant }: { widget: DashboardManifestWidget; variant?: LauncherWidgetVariant }) {
  const payload = widgetPayload<{ rows?: SerializedAIInsight[] }>(widget);
  const rows = payload.rows ?? [];
  return (
    <Surface className={cn("group relative flex h-full min-h-0 flex-col overflow-hidden", widgetSurfacePadding(widget, variant))}>
      {widgetHeader(widget, variant === "compact")}
      <ListShell scroll>
        <div className="space-y-3">
          {rows.length ? rows.map((row, index) => (
            <div key={`${row.id ?? row.title ?? index}`} className={cn("rounded-[18px] border border-[#3a3d43] bg-[#343840]/80", variant === "compact" ? "p-3" : "p-4")}>
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className={cn("font-semibold tracking-[-0.03em] text-[#f4f7fb]", variant === "compact" ? "text-sm" : "text-base")}>{businessCopy(row.title) ?? row.title ?? "Сигнал"}</p>
                  <p className={cn("mt-1 text-slate-400", variant === "compact" ? "text-xs" : "text-sm")}>{businessCopy(row.summary) ?? "Без описания"}</p>
                </div>
                {severityLabel(row.severity) ? <Badge variant="accent">{severityLabel(row.severity)}</Badge> : null}
              </div>
            </div>
          )) : (
            <div className={cn("rounded-[18px] border border-dashed border-[#3a3d43] bg-[#343840] text-center text-sm text-slate-400", variant === "compact" ? "px-4 py-6" : "px-5 py-10")}>На контроле пока нет сигналов.</div>
          )}
        </div>
      </ListShell>
      {widgetFooter(widget, variant === "compact")}
    </Surface>
  );
}

function UnknownWidgetCard({ widget }: { widget: DashboardManifestWidget }) {
  return (
    <Surface className="group relative flex h-full flex-col justify-between p-5">
      <div>
        <p className="text-[11px] uppercase tracking-[0.28em] text-slate-400">Новый тип виджета</p>
        <h3 className="mt-2 text-[20px] font-semibold tracking-[-0.04em] text-[#f4f7fb]">{widgetTitleFromName(widget.title)}</h3>
        <p className="mt-3 text-sm leading-6 text-slate-400">
          Этот тип виджета пока не поддержан в текущем интерфейсе.
        </p>
      </div>
      <div className="mt-4">
        <Badge variant="neutral">резервный вариант</Badge>
      </div>
    </Surface>
  );
}

function renderWidget(widget: DashboardManifestWidget, variant?: LauncherWidgetVariant) {
  switch (widget.widget_type) {
    case "kpi":
      return <KpiWidget widget={widget} variant={variant} />;
    case "line_chart":
    case "trend":
    case "bar_chart":
      return <TrendWidget widget={widget} variant={variant} />;
    case "organization_comparison":
      return <OrganizationComparisonWidget widget={widget} variant={variant} />;
    case "product_ranking":
      return <RankingWidget widget={widget} rows={widgetPayload<{ rows?: SerializedProductRow[] }>(widget).rows ?? []} variant={variant} />;
    case "customer_ranking":
      return <RankingWidget widget={widget} rows={widgetPayload<{ rows?: SerializedCustomerRow[] }>(widget).rows ?? []} customerMode variant={variant} />;
    case "inventory_risk":
      return <InventoryRiskWidget widget={widget} variant={variant} />;
    case "visit_summary":
      return <VisitSummaryWidget widget={widget} variant={variant} />;
    case "data_quality":
      return <DataQualityWidget widget={widget} variant={variant} />;
    case "ai_insight":
    case "ai_recommendation":
      return widget.widget_id === "executive-brief" ? <ExecutiveBriefWidget widget={widget} variant={variant} /> : <AlertWidget widget={widget} variant={variant} />;
    case "watchlist":
      return <WatchlistWidget widget={widget} variant={variant} />;
    case "alert":
    case "product_alert":
    case "customer_alert":
    case "inventory_alert":
    case "photo_alert":
      return <AlertWidget widget={widget} variant={variant} />;
    default:
      return <UnknownWidgetCard widget={widget} />;
  }
}

export function DashboardGrid() {
  const { manifest, loading, error } = useDashboardManifest();
  const { state: businessState, availableOrganizations } = useBusinessContext();
  const [launcherState, setLauncherState] = useState<LauncherState | null>(null);
  const [editMode, setEditMode] = useState(false);
  const [interactionLayouts, setInteractionLayouts] = useState<ResponsiveLayouts | null>(null);
  const [widgetLibraryOpen, setWidgetLibraryOpen] = useState(false);
  const [aiWidgetBuilderOpen, setAiWidgetBuilderOpen] = useState(false);
  const [aiWidgetBuilderPrompt, setAiWidgetBuilderPrompt] = useState("");
  const [aiWidgetBuilderReply, setAiWidgetBuilderReply] = useState("");
  const [aiWidgetBuilderLoading, setAiWidgetBuilderLoading] = useState(false);
  const [customWidgets, setCustomWidgets] = useState<DashboardManifestWidget[]>(() => readStoredCustomWidgets());
  const [librarySelectedType, setLibrarySelectedType] = useState<DashboardWidgetType>("kpi");
  const [librarySelectedOrganizationId, setLibrarySelectedOrganizationId] = useState<string>("");
  const [libraryLoading, setLibraryLoading] = useState(false);
  const [libraryError, setLibraryError] = useState<string | null>(null);
  const [suggestionsDrawerOpen, setSuggestionsDrawerOpen] = useState(false);
  const [dismissedSuggestionIds, setDismissedSuggestionIds] = useState<string[]>([]);
  const [previewResult, setPreviewResult] = useState<LauncherSuggestionPreview | null>(null);
  const [selectedSuggestionId, setSelectedSuggestionId] = useState<string | null>(null);
  const [gridMounted, setGridMounted] = useState(false);
  const [widgetsColumnRef, containerWidth] = useMeasuredWidth<HTMLDivElement>();
  const launcherStateLoaded = useRef(false);

  useEffect(() => {
    const handleOpenWidgetBuilder = () => {
      setEditMode(true);
      setLibraryError(null);
      setLibrarySelectedType((current) => current ?? widgetCatalog[0]?.widget_type ?? "kpi");
      setLibrarySelectedOrganizationId(
        (current) => current || businessState.selectedOrganizationIds[0] || availableOrganizations[0]?.id || "",
      );
      setWidgetLibraryOpen(true);
    };

    const handleOpenAiWidgetBuilder = () => {
      setEditMode(true);
      setAiWidgetBuilderReply("");
      setAiWidgetBuilderOpen(true);
    };

    window.addEventListener("ai-business-os:open-widget-builder", handleOpenWidgetBuilder);
    window.addEventListener("ai-business-os:open-ai-widget-builder", handleOpenAiWidgetBuilder);
    return () => {
      window.removeEventListener("ai-business-os:open-widget-builder", handleOpenWidgetBuilder);
      window.removeEventListener("ai-business-os:open-ai-widget-builder", handleOpenAiWidgetBuilder);
    };
  }, [availableOrganizations, businessState.selectedOrganizationIds]);

  const manifestWidgets = useMemo(
    () => [...(manifest?.widgets.filter((widget) => !widget.hidden) ?? []), ...customWidgets],
    [customWidgets, manifest],
  );
  const allWidgets = useMemo(
    () => {
      const baseWidgets = manifestWidgets.length > 0 ? manifestWidgets : FALLBACK_DASHBOARD_WIDGETS;
      return aggregateProductSignalWidgets(dedupeWidgets(dedupeWidgetSignatures(baseWidgets)));
    },
    [manifestWidgets],
  );
  const defaultState = useMemo(() => createDefaultLauncherState(allWidgets) as LauncherState, [allWidgets]);
  const effectiveState = useMemo(
    () => normalizeLauncherState(launcherState ?? defaultState, allWidgets) as LauncherState,
    [allWidgets, defaultState, launcherState],
  );
  const activeState = previewResult?.previewState ?? effectiveState;
  const widgetContracts = useMemo(
    () => new Map(allWidgets.map((widget) => [widget.widget_id, getWidgetSizeContract(widget)])),
    [allWidgets],
  );
  const hiddenWidgetIds = useMemo(
    () => new Set(activeState.hidden ?? []),
    [activeState.hidden],
  );
  const visibleWidgets = useMemo(
    () => allWidgets.filter((widget) => !hiddenWidgetIds.has(widget.widget_id)),
    [allWidgets, hiddenWidgetIds],
  );
  const currentLayouts = useMemo(
    () => composeResponsiveLauncherLayouts(activeState, visibleWidgets) as ResponsiveLayouts,
    [activeState, visibleWidgets],
  );
  const activeBreakpoint = breakpointForWidth(containerWidth || 1024) as keyof typeof LAUNCHER_COLUMNS;
  const lockedWidgetIds = useMemo(
    () => new Set(effectiveState.locked ?? []),
    [effectiveState.locked],
  );
  const currentLayoutsWithBounds = useMemo(
    () => applyBoundsToResponsiveLayouts(currentLayouts, visibleWidgets, widgetContracts, editMode, lockedWidgetIds),
    [currentLayouts, editMode, lockedWidgetIds, visibleWidgets, widgetContracts],
  );
  const renderedLayouts = interactionLayouts ?? currentLayoutsWithBounds;
  const renderedLayoutsSignature = JSON.stringify(renderedLayouts);
  const stableRenderedLayoutsRef = useRef<{ signature: string; value: ResponsiveLayouts }>({
    signature: renderedLayoutsSignature,
    value: renderedLayouts,
  });
  if (stableRenderedLayoutsRef.current.signature !== renderedLayoutsSignature) {
    stableRenderedLayoutsRef.current = { signature: renderedLayoutsSignature, value: renderedLayouts };
  }
  const stableRenderedLayouts = stableRenderedLayoutsRef.current.value;
  const activeLayout = useMemo(
    () => (stableRenderedLayouts[activeBreakpoint] ?? []) as LayoutItem[],
    [activeBreakpoint, stableRenderedLayouts],
  );
  const widgetVariantMap = useMemo(() => {
    const map = new Map<string, "compact" | "regular" | "expanded" | "xl">();
    for (const item of activeLayout) {
      map.set(item.i, getLauncherVariantFromGrid(item.w, item.h));
    }
    return map;
  }, [activeLayout]);
  const hiddenWidgets = useMemo(
    () => allWidgets.filter((widget) => hiddenWidgetIds.has(widget.widget_id)),
    [allWidgets, hiddenWidgetIds],
  );
  const widgetCatalog = useMemo<WidgetCatalogItem[]>(() => {
    const registryMap = new Map((manifest?.widget_registry ?? []).map((entry) => [entry.widget_type, entry]));
    return ALL_WIDGET_TYPES.map((widget_type) => ({
      widget_type,
      title: widgetCatalogTitle(widget_type),
      description: registryMap.get(widget_type)?.description ?? widgetCatalogDescription(widget_type),
    }));
  }, [manifest]);
  const selectedCatalogItem = useMemo(
    () => widgetCatalog.find((item) => item.widget_type === librarySelectedType) ?? widgetCatalog[0] ?? null,
    [librarySelectedType, widgetCatalog],
  );
  const selectedOrganizationName = useMemo(
    () => availableOrganizations.find((item) => item.id === librarySelectedOrganizationId)?.name ?? null,
    [availableOrganizations, librarySelectedOrganizationId],
  );
  const previewWidget = useMemo(() => {
    if (!selectedCatalogItem) return null;
    const orgName = selectedOrganizationName ?? "Организация";
    return createFallbackWidget({
      widget_id: `preview-${selectedCatalogItem.widget_type}`,
      widget_type: selectedCatalogItem.widget_type,
      title: selectedCatalogItem.title,
      subtitle: orgName,
      semantic_size: "L",
      priority: 0,
      summary: selectedCatalogItem.description,
      payload: buildWidgetPreviewPayload(selectedCatalogItem.widget_type, orgName),
    });
  }, [selectedCatalogItem, selectedOrganizationName]);
  const launcherSuggestions = useMemo(
    () =>
      createDevelopmentLauncherSuggestions(allWidgets, effectiveState).filter(
        (suggestion) => !dismissedSuggestionIds.includes(suggestion.id),
      ),
    [allWidgets, dismissedSuggestionIds, effectiveState],
  );
  const highlightedWidgetIds = useMemo(
    () => new Set(previewResult?.suggestion.actions.map((action) => action.widgetId) ?? []),
    [previewResult],
  );

  useEffect(() => {
    setGridMounted(true);
  }, []);

  useEffect(() => {
    if (loading) return;
    if (!launcherStateLoaded.current) {
      launcherStateLoaded.current = true;
      const nextState = normalizeLauncherState(loadLauncherState() ?? defaultState, allWidgets) as LauncherState;
      setLauncherState(nextState);
      return;
    }
    setLauncherState((current) => {
      const nextState = normalizeLauncherState(current ?? defaultState, allWidgets) as LauncherState;
      return JSON.stringify(current) === JSON.stringify(nextState) ? current : nextState;
    });
  }, [allWidgets, defaultState, loading]);

  useEffect(() => {
    if (!launcherStateLoaded.current || !launcherState) return;
    saveLauncherState(launcherState);
  }, [launcherState]);

  useEffect(() => {
    if (process.env.NODE_ENV !== "development" || containerWidth <= 0) return;
    console.debug("[launcher]", {
      containerWidth,
      breakpoint: activeBreakpoint,
      columns: LAUNCHER_COLUMNS[activeBreakpoint],
      widgetCount: visibleWidgets.length,
      order: effectiveState.order,
      sizes: effectiveState.sizes,
      layout: activeLayout.map(({ i, x, y, w, h }) => ({ i, x, y, w, h })),
    });
  }, [activeBreakpoint, activeLayout, containerWidth, effectiveState.order, effectiveState.sizes, visibleWidgets.length]);

  const resetLayouts = () => {
    clearLauncherState();
    setLauncherState(defaultState);
    setInteractionLayouts(null);
    setWidgetLibraryOpen(false);
    setSuggestionsDrawerOpen(false);
    cancelPreview();
  };

  const updateSemanticState = useCallback((updater: (current: LauncherState) => LauncherState) => {
    setLauncherState((current) => {
      const next = normalizeLauncherState(updater(current ?? defaultState), allWidgets) as LauncherState;
      saveLauncherState(next);
      return next;
    });
  }, [allWidgets, defaultState]);

  const openSuggestionsDrawer = useCallback(() => {
    setSuggestionsDrawerOpen(true);
  }, []);

  const previewSuggestion = useCallback((suggestion: LauncherSuggestion) => {
    if (editMode) return;
    const preview = evaluateLauncherSuggestion(effectiveState, allWidgets, suggestion);
    setPreviewResult(preview);
    setSelectedSuggestionId(suggestion.id);
    setSuggestionsDrawerOpen(false);
  }, [allWidgets, editMode, effectiveState]);

  const applySuggestion = useCallback((suggestion: LauncherSuggestion) => {
    if (editMode) return;
    const applied = evaluateLauncherSuggestion(effectiveState, allWidgets, suggestion);
    if (applied.appliedActions > 0) {
      setLauncherState(applied.previewState);
      saveLauncherState(applied.previewState);
    }
    setPreviewResult(applied);
    setSelectedSuggestionId(suggestion.id);
    setSuggestionsDrawerOpen(false);
  }, [allWidgets, editMode, effectiveState]);

  const cancelPreview = useCallback(() => {
    setPreviewResult(null);
    setSelectedSuggestionId(null);
  }, []);

  const dismissSuggestion = useCallback((suggestionId: string) => {
    setDismissedSuggestionIds((current) => Array.from(new Set([...current, suggestionId])));
    setSuggestionsDrawerOpen(false);
    if (selectedSuggestionId === suggestionId) {
      cancelPreview();
    }
  }, [cancelPreview, selectedSuggestionId]);

  const commitWidgetSize = useCallback((widgetId: string, size: LauncherSemanticSize) => {
    setInteractionLayouts(null);
    updateSemanticState((current) => updateLauncherWidgetSize(current, allWidgets, widgetId, size) as LauncherState);
  }, [allWidgets, updateSemanticState]);

  const toggleWidgetLock = useCallback((widgetId: string) => {
    updateSemanticState((current) => {
      const locked = new Set(current.locked ?? []);
      if (locked.has(widgetId)) locked.delete(widgetId);
      else locked.add(widgetId);
      return {
        ...current,
        locked: Array.from(locked),
      };
    });
  }, [updateSemanticState]);

  const hideWidget = useCallback((widgetId: string) => {
    updateSemanticState((current) => {
      const hidden = new Set(current.hidden ?? []);
      const userHidden = new Set(current.userOverrides?.hidden ?? []);
      hidden.add(widgetId);
      userHidden.add(widgetId);
      return {
        ...current,
        hidden: Array.from(hidden),
        userOverrides: {
          size: current.userOverrides?.size ?? [],
          order: Boolean(current.userOverrides?.order),
          hidden: Array.from(userHidden),
        },
      };
    });
  }, [updateSemanticState]);

  const restoreWidget = useCallback((widgetId: string) => {
    updateSemanticState((current) => {
      const hidden = new Set(current.hidden ?? []);
      const userHidden = new Set(current.userOverrides?.hidden ?? []);
      hidden.delete(widgetId);
      userHidden.delete(widgetId);
      return {
        ...current,
        hidden: Array.from(hidden),
        userOverrides: {
          size: current.userOverrides?.size ?? [],
          order: Boolean(current.userOverrides?.order),
          hidden: Array.from(userHidden),
        },
      };
    });
  }, [updateSemanticState]);

  const handleDragStart = useCallback(() => {
    setInteractionLayouts(cloneResponsiveLayouts(currentLayoutsWithBounds));
  }, [currentLayoutsWithBounds]);

  const handleDrag = useCallback((currentLayout: ReadonlyArray<LayoutItem>) => {
    setInteractionLayouts((current) => {
      const next = cloneResponsiveLayouts(current ?? currentLayoutsWithBounds);
      next[activeBreakpoint] = currentLayout.map((item) => ({ ...item }));
      return next;
    });
  }, [activeBreakpoint, currentLayoutsWithBounds]);

  const handleDragStop = useCallback((currentLayout: ReadonlyArray<LayoutItem>) => {
    const order = deriveLauncherOrder(currentLayout, effectiveState.order);
    const nextState = normalizeLauncherState({
      ...effectiveState,
      order,
      userOverrides: {
        size: effectiveState.userOverrides?.size ?? [],
        order: true,
        hidden: effectiveState.userOverrides?.hidden ?? [],
      },
    }, allWidgets) as LauncherState;
    setInteractionLayouts(null);
    setLauncherState(nextState);
    saveLauncherState(nextState);
  }, [allWidgets, effectiveState]);

  const handleResizeStart = useCallback(() => {
    setInteractionLayouts(cloneResponsiveLayouts(currentLayoutsWithBounds));
  }, [currentLayoutsWithBounds]);

  const handleResize = useCallback((currentLayout: ReadonlyArray<LayoutItem>) => {
    setInteractionLayouts((current) => {
      const next = cloneResponsiveLayouts(current ?? currentLayoutsWithBounds);
      next[activeBreakpoint] = currentLayout.map((item) => ({ ...item }));
      return next;
    });
  }, [activeBreakpoint, currentLayoutsWithBounds]);

  const handleResizeStop = useCallback((
    currentLayout: ReadonlyArray<LayoutItem>,
    _oldItem?: LayoutItem | null,
    newItem?: LayoutItem | null,
  ) => {
    const resizedItem = newItem ?? currentLayout.find((item) => item.i === _oldItem?.i);
    if (!resizedItem) {
      setInteractionLayouts(null);
      return;
    }
    const widget = allWidgets.find((entry) => entry.widget_id === resizedItem.i);
    if (!widget) {
      setInteractionLayouts(null);
      return;
    }
    const semanticSize = snapWidgetSemanticSize(
      widget,
      resizedItem.w ?? 0,
      resizedItem.h ?? 0,
      LAUNCHER_COLUMNS[activeBreakpoint],
    );
    setInteractionLayouts(null);
    commitWidgetSize(widget.widget_id, semanticSize);
  }, [activeBreakpoint, allWidgets, commitWidgetSize]);

  const hiddenCount = hiddenWidgets.length;
  const activeSuggestion = previewResult?.suggestion ?? null;

  useEffect(() => {
    if (editMode && previewResult) {
      cancelPreview();
    }
  }, [cancelPreview, editMode, previewResult]);

  useEffect(() => {
    storeCustomWidgets(customWidgets);
  }, [customWidgets]);

  const addLibraryWidget = useCallback(async () => {
    if (!selectedCatalogItem) return;
    const organizationId = librarySelectedOrganizationId || businessState.selectedOrganizationIds[0] || availableOrganizations[0]?.id || "";
    if (!organizationId) {
      setLibraryError("Выберите организацию для этого виджета.");
      return;
    }

    const organizationName = availableOrganizations.find((item) => item.id === organizationId)?.name ?? "Организация";
    setLibraryLoading(true);
    setLibraryError(null);
    try {
      const manifestForOrganization = await getDashboardManifest({
        organizationId,
        period: businessState.period.preset,
        dateFrom: businessState.period.preset === "custom" ? businessState.period.dateFrom : null,
        dateTo: businessState.period.preset === "custom" ? businessState.period.dateTo : null,
        comparisonMode: "previous_period",
        language: "ru",
      });
      const sourceWidget =
        manifestForOrganization.widgets.find((widget) => widget.widget_type === selectedCatalogItem.widget_type)
        ?? allWidgets.find((widget) => widget.widget_type === selectedCatalogItem.widget_type)
        ?? null;

      const widgetId = createId(`custom-${selectedCatalogItem.widget_type}`);
      const templateWidget = sourceWidget
        ? {
            ...sourceWidget,
            widget_id: widgetId,
            source_type: "USER_PINNED" as const,
            organization_ids: [organizationId],
            hidden: false,
            pinned: true,
            movable_by_ai: true,
            resizable_by_ai: true,
            removable_by_ai: true,
            summary: sourceWidget.summary ?? `${selectedCatalogItem.title} для ${organizationName}`,
            subtitle: sourceWidget.subtitle ?? organizationName,
          }
        : createFallbackWidget({
            widget_id: widgetId,
            widget_type: selectedCatalogItem.widget_type,
            title: selectedCatalogItem.title,
            subtitle: organizationName,
            semantic_size: "L",
            priority: (allWidgets.reduce((max, widget) => Math.max(max, widget.priority ?? 0), 0) ?? 0) + 1,
            summary: `${selectedCatalogItem.title} для ${organizationName}`,
            payload: buildWidgetPreviewPayload(selectedCatalogItem.widget_type, organizationName),
          });

      if (!sourceWidget) {
        templateWidget.organization_ids = [organizationId];
        templateWidget.data_status = "AVAILABLE";
        templateWidget.hidden = false;
        templateWidget.pinned = true;
      } else {
        templateWidget.payload = {
          ...sourceWidget.payload,
          organization_name: organizationName,
        };
      }

      setCustomWidgets((current) => [...current, templateWidget]);
      updateSemanticState((current) => ({
        ...current,
        order: [...current.order, templateWidget.widget_id],
        sizes: {
          ...current.sizes,
          [templateWidget.widget_id]: semanticSizeToLauncherSize(templateWidget.semantic_size),
        },
        hidden: Array.from(new Set((current.hidden ?? []).filter((id) => id !== templateWidget.widget_id))),
        userOverrides: {
          size: Array.from(new Set([...(current.userOverrides?.size ?? []), templateWidget.widget_id])),
          order: true,
          hidden: Array.from(new Set(current.userOverrides?.hidden ?? [])),
        },
      }));
      setWidgetLibraryOpen(false);
    } catch (loadError) {
      setLibraryError(loadError instanceof Error ? loadError.message : "Не удалось добавить виджет.");
    } finally {
      setLibraryLoading(false);
    }
  }, [allWidgets, availableOrganizations, businessState.period.dateFrom, businessState.period.dateTo, businessState.period.preset, businessState.selectedOrganizationIds, librarySelectedOrganizationId, selectedCatalogItem, updateSemanticState]);

  return (
    <div ref={widgetsColumnRef} className="w-full min-w-0 space-y-4">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
          <div className="max-w-4xl">
            <p className="text-[11px] uppercase tracking-[0.32em] text-slate-400">Бизнес-обзор</p>
            <h2 className="mt-2 text-[32px] font-semibold tracking-[-0.06em] text-[#f4f7fb] sm:text-[36px]">
              Мой бизнес
            </h2>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant={editMode ? "secondary" : "ghost"}
              size="sm"
              onClick={() => {
                setEditMode((value) => {
                  const nextValue = !value;
                  if (!nextValue) {
                    setWidgetLibraryOpen(false);
                    setInteractionLayouts(null);
                  }
                  return nextValue;
                });
              }}
            >
              {editMode ? "Готово" : "Режим редактирования"}
            </Button>
            {editMode ? (
              <>
                <FilterChip active={visibleWidgets.length > 0}>{visibleWidgets.length} виджетов</FilterChip>
                <AiSuggestionsButton
                  count={launcherSuggestions.length}
                  open={suggestionsDrawerOpen}
                  onClick={openSuggestionsDrawer}
                />
                {hiddenCount > 0 ? (
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => {
                      setLibraryError(null);
                      setLibrarySelectedType((current) => current ?? widgetCatalog[0]?.widget_type ?? "kpi");
                      setLibrarySelectedOrganizationId((current) => current || businessState.selectedOrganizationIds[0] || availableOrganizations[0]?.id || "");
                      setWidgetLibraryOpen(true);
                    }}
                  >
                    Добавить виджеты
                  </Button>
                ) : null}
                <Button variant="secondary" size="sm" onClick={resetLayouts}>
                  Сбросить раскладку
                </Button>
              </>
            ) : null}
          </div>
        </div>

        {(loading || error) && (
          <Surface className="border border-white/5 bg-white/[0.02] px-4 py-3">
            <p className="text-xs uppercase tracking-[0.28em] text-slate-400">Статус данных</p>
            <p className="mt-2 text-sm leading-6 text-slate-300">
              {loading ? "Обновляю данные из backend, структура дашборда уже показана." : `Последний запрос не ответил: ${error}`}
            </p>
          </Surface>
        )}

        {previewResult && activeSuggestion ? (
          <AiPreviewBanner
            preview={previewResult}
            onApply={() => applySuggestion(activeSuggestion)}
            onCancel={cancelPreview}
            onOpenSuggestions={() => setSuggestionsDrawerOpen(true)}
          />
        ) : null}

        <div suppressHydrationWarning>
        {gridMounted ? (
        <Responsive
          className="layout w-full"
          width={containerWidth || 1024}
          layouts={stableRenderedLayouts}
          breakpoints={LAUNCHER_BREAKPOINTS}
          cols={LAUNCHER_COLUMNS}
          rowHeight={74}
          margin={[18, 18]}
          containerPadding={[0, 0]}
          draggableHandle=".drag-handle"
          resizeHandles={[]}
          compactType={null}
          preventCollision={false}
          isResizable={false}
          isDraggable={editMode}
          onDragStart={() => {
            if (!editMode) return;
            handleDragStart();
          }}
          onDrag={(currentLayout) => {
            if (!editMode) return;
            handleDrag(currentLayout);
          }}
          onDragStop={(currentLayout) => {
            if (!editMode) return;
            handleDragStop(currentLayout);
          }}
          onResizeStart={() => {
            if (!editMode) return;
            handleResizeStart();
          }}
          onResize={(currentLayout) => {
            if (!editMode) return;
            handleResize(currentLayout);
          }}
          onResizeStop={(currentLayout, oldItem, newItem) => {
            if (!editMode) return;
            handleResizeStop(currentLayout, oldItem, newItem);
          }}
        >
          {visibleWidgets.map((widget) => {
            const currentSize = activeState.sizes[widget.widget_id] ?? "medium";
            const locked = Boolean(widget.locked_position || (activeState.locked ?? []).includes(widget.widget_id));
            return (
              <div
                key={widget.widget_id}
                className={cn(
                  "relative min-h-0",
                  previewResult && highlightedWidgetIds.has(widget.widget_id) && "ring-2 ring-yellow-200 ring-offset-2 ring-offset-[#2E3137]",
                )}
              >
                {editMode ? (
                  <div className="absolute right-3 top-3 z-20">
                    <WidgetEditMenu
                      widget={widget}
                      currentSize={widgetSizeFromContract(widget, currentSize)}
                      locked={locked}
                      onChangeSize={(size) => commitWidgetSize(widget.widget_id, size)}
                      onToggleLock={() => toggleWidgetLock(widget.widget_id)}
                      onHide={() => hideWidget(widget.widget_id)}
                    />
                  </div>
                ) : null}
                {renderWidget(widget, widgetVariantMap.get(widget.widget_id))}
              </div>
            );
          })}
        </Responsive>
        ) : (
          <div className="min-h-[320px]" aria-hidden="true" />
        )}
        </div>
      <Drawer
        open={aiWidgetBuilderOpen}
        onClose={() => setAiWidgetBuilderOpen(false)}
        title="Создать виджет через ИИ"
        description="Опишите, какие данные должны быть на виджете. ИИ поможет собрать конфигурацию."
        badges={<Badge variant="neutral">AI-конструктор</Badge>}
        className="max-w-[min(52rem,calc(100vw-2rem))]"
      >
        <div className="grid gap-5">
          <div className="space-y-4 rounded-[28px] border border-[#3a3d43] bg-[#26292e] p-4">
            <div>
              <p className="text-[11px] uppercase tracking-[0.28em] text-slate-400">Конструктор</p>
              <h3 className="mt-2 text-xl font-semibold tracking-[-0.04em] text-[#f4f7fb]">Параметры виджета</h3>
            </div>
            <Input placeholder="Название виджета" aria-label="Название виджета" />
            <Select
              label="Тип виджета"
              value={librarySelectedType}
              options={widgetCatalog.map((item) => ({ value: item.widget_type, label: item.title }))}
              onChange={(value) => setLibrarySelectedType(value as DashboardWidgetType)}
              placeholder="Выберите тип"
            />
            <Select
              label="Организация"
              value={librarySelectedOrganizationId}
              options={availableOrganizations.map((item) => ({ value: item.id, label: item.name }))}
              onChange={setLibrarySelectedOrganizationId}
              placeholder="Выберите организацию"
            />
            <div className="rounded-2xl border border-dashed border-[#4a4e56] bg-[#2E3137] p-4 text-sm leading-6 text-slate-400">
              Период, метрика и фильтры будут определены по вашему описанию и текущему контексту бизнеса.
            </div>
          </div>

          <div className="flex min-h-[360px] flex-col rounded-[28px] border border-[#3a3d43] bg-[#26292e] p-4">
            <div>
              <p className="text-[11px] uppercase tracking-[0.28em] text-slate-400">ИИ</p>
              <h3 className="mt-2 text-xl font-semibold tracking-[-0.04em] text-[#f4f7fb]">Опишите нужный виджет</h3>
            </div>
            <div className="mt-4 min-h-0 flex-1 rounded-2xl border border-[#3a3d43] bg-[#2E3137] p-4 text-sm leading-6 text-slate-300">
              {aiWidgetBuilderReply || "Например: покажи продажи Бекзода за неделю простой цифрой."}
            </div>
            <div className="mt-4 space-y-3">
              <textarea
                value={aiWidgetBuilderPrompt}
                onChange={(event) => setAiWidgetBuilderPrompt(event.target.value)}
                placeholder="Что должен показывать виджет?"
                className="min-h-24 w-full resize-none rounded-2xl border border-[#3a3d43] bg-[#2E3137] px-4 py-3 text-sm text-[#f4f7fb] outline-none transition placeholder:text-slate-400 focus:border-[#6a6f79] focus:ring-4 focus:ring-white/10"
              />
              <Button
                className="w-full"
                disabled={aiWidgetBuilderLoading || !aiWidgetBuilderPrompt.trim()}
                onClick={() => {
                  const prompt = aiWidgetBuilderPrompt.trim();
                  if (!prompt) return;
                  setAiWidgetBuilderLoading(true);
                  setAiWidgetBuilderReply("");
                  void streamAiChat(
                    [{ role: "user", content: prompt }],
                    (content) => setAiWidgetBuilderReply((current) => current + content),
                    undefined,
                    "system_action",
                    undefined,
                    undefined,
                    undefined,
                    undefined,
                    businessState.selectedOrganizationIds[0] ?? null,
                    businessState.period.preset,
                  ).catch((error) => setAiWidgetBuilderReply(error instanceof Error ? error.message : "Не удалось получить ответ AI."))
                    .finally(() => setAiWidgetBuilderLoading(false));
                }}
              >
                {aiWidgetBuilderLoading ? "ИИ думает..." : "Отдать команду ИИ"}
              </Button>
            </div>
          </div>
        </div>
      </Drawer>
      {editMode ? (
        <Drawer
          open={widgetLibraryOpen}
          onClose={() => setWidgetLibraryOpen(false)}
          title="Каталог виджетов"
          description="Выберите тип виджета, посмотрите превью и укажите организацию для данных."
          badges={<Badge variant="neutral">{widgetCatalog.length} типов</Badge>}
          className="max-w-[min(92rem,calc(100vw-2rem))]"
        >
          <div className="grid gap-5 xl:grid-cols-[minmax(0,1.2fr)_minmax(360px,0.8fr)]">
            <div className="space-y-4">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-[11px] uppercase tracking-[0.28em] text-slate-400">Все типы</p>
                  <h3 className="mt-2 text-xl font-semibold tracking-[-0.04em] text-[#f4f7fb]">Выберите шаблон</h3>
                </div>
                <Badge variant="neutral">{widgetCatalog.length}</Badge>
              </div>

              <div className="grid gap-3 md:grid-cols-2 2xl:grid-cols-3">
                {widgetCatalog.map((item) => {
                  const selected = item.widget_type === librarySelectedType;
                  return (
                    <button
                      key={item.widget_type}
                      type="button"
                      onClick={() => {
                        setLibrarySelectedType(item.widget_type);
                        setLibraryError(null);
                      }}
                      className={cn(
                        "rounded-[24px] border p-4 text-left transition-all duration-300 ease-[cubic-bezier(0.22,1,0.36,1)]",
                        selected
                          ? "border-[#FFF27A]/40 bg-[#FFF27A]/10 shadow-[0_12px_30px_rgba(255,242,122,0.08)]"
                          : "border-[#3a3d43] bg-[#2E3137] hover:border-[#4a4e56]",
                      )}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <p className="text-base font-semibold tracking-[-0.04em] text-[#f4f7fb]">{item.title}</p>
                          <p className="mt-1 text-xs leading-5 text-slate-400">{item.description}</p>
                        </div>
                        <Badge variant={selected ? "accent" : "neutral"}>{item.widget_type}</Badge>
                      </div>
                      <div className="mt-4 flex items-center justify-between gap-3">
                        <span className="text-[11px] uppercase tracking-[0.22em] text-slate-500">Превью</span>
                        <span className="text-xs text-slate-400">{selected ? "Выбран" : "Нажмите для выбора"}</span>
                      </div>
                    </button>
                  );
                })}
              </div>

              {hiddenCount > 0 ? (
                <div className="rounded-[26px] border border-[#3a3d43] bg-[#26292e] p-4">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <p className="text-[11px] uppercase tracking-[0.28em] text-slate-400">Скрытые в раскладке</p>
                      <h3 className="mt-2 text-lg font-semibold tracking-[-0.04em] text-[#f4f7fb]">{hiddenCount} виджетов</h3>
                    </div>
                    <Badge variant="neutral">{hiddenCount}</Badge>
                  </div>
                  <div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                    {hiddenWidgets.map((widget) => (
                      <div key={widget.widget_id} className="rounded-[20px] border border-[#3a3d43] bg-[#2E3137] p-3">
                        <p className="text-sm font-semibold tracking-[-0.03em] text-[#f4f7fb]">{widgetTitleFromName(widget.title)}</p>
                        {widget.subtitle ? <p className="mt-1 text-xs leading-5 text-slate-400">{businessCopy(widget.subtitle)}</p> : null}
                        <Button
                          size="sm"
                          variant="soft"
                          className="mt-3 w-full"
                          onClick={() => restoreWidget(widget.widget_id)}
                        >
                          Показать
                        </Button>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>

            <div className="space-y-4">
              <div className="rounded-[28px] border border-[#3a3d43] bg-[#26292e] p-4">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-[11px] uppercase tracking-[0.28em] text-slate-400">Превью</p>
                    <h3 className="mt-2 text-xl font-semibold tracking-[-0.04em] text-[#f4f7fb]">{selectedCatalogItem?.title ?? "Виджет"}</h3>
                  </div>
                  <Badge variant="neutral">{selectedCatalogItem?.widget_type ?? "—"}</Badge>
                </div>
                <div className="mt-4 h-[360px] overflow-hidden rounded-[24px] border border-[#3a3d43] bg-[#2E3137] p-2">
                  {previewWidget ? renderWidget(previewWidget, "compact") : null}
                </div>
              </div>

              <div className="rounded-[28px] border border-[#3a3d43] bg-[#26292e] p-4">
                <p className="text-[11px] uppercase tracking-[0.28em] text-slate-400">Параметры</p>
                <div className="mt-3 space-y-3">
                  <Select
                    label="Тип виджета"
                    value={librarySelectedType}
                    options={widgetCatalog.map((item) => ({ value: item.widget_type, label: item.title }))}
                    onChange={(value) => setLibrarySelectedType(value as DashboardWidgetType)}
                    placeholder="Выберите тип"
                  />
                  <Select
                    label="Организация"
                    value={librarySelectedOrganizationId}
                    options={availableOrganizations.map((item) => ({ value: item.id, label: item.name }))}
                    onChange={setLibrarySelectedOrganizationId}
                    placeholder="Выберите организацию"
                  />
                  <p className="text-sm leading-6 text-slate-400">
                    {selectedCatalogItem?.description ?? "Выберите тип виджета и организацию."}
                  </p>
                  {libraryError ? <p className="text-sm text-rose-300">{libraryError}</p> : null}
                  <Button
                    className="w-full"
                    disabled={libraryLoading || !librarySelectedOrganizationId}
                    onClick={() => {
                      void addLibraryWidget();
                    }}
                  >
                    {libraryLoading ? "Добавляем..." : "Добавить виджет"}
                  </Button>
                </div>
              </div>
            </div>
          </div>
        </Drawer>
      ) : null}

      <AiSuggestionsDrawer
        open={suggestionsDrawerOpen}
        editMode={editMode}
        suggestions={launcherSuggestions}
        selectedSuggestionId={selectedSuggestionId}
        preview={previewResult}
        onClose={() => setSuggestionsDrawerOpen(false)}
        onSelectPreview={previewSuggestion}
        onApply={applySuggestion}
        onDismiss={dismissSuggestion}
      />
    </div>
  );
}
