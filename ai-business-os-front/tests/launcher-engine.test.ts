import assert from "node:assert/strict";
import test from "node:test";

import {
  GRID_COLUMNS,
  buildDefaultLayouts,
  buildLauncherGridSpec,
  buildLauncherLayoutsFromCanonical,
  computeLauncherColumnCount,
  dedupeWidgets,
  dedupeWidgetSignatures,
  buildLayoutForCols,
  normalizeLauncherLayouts,
  snapWidgetSemanticSize,
  widgetCanResize,
  widgetLayoutGroup,
} from "../lib/launcher/layout-engine.js";
import {
  applyLauncherCommand,
  moveWidget,
  resizeWidget,
} from "../lib/launcher/commands.js";
import {
  clearLauncherLayouts,
  loadLauncherLayouts,
  restoreDefaultLauncherLayouts,
} from "../lib/launcher/persistence.js";
import { buildWidgetRegistry, getWidgetSizeContract } from "../lib/launcher/widget-registry.js";
import {
  aggregateProductSignalWidgets,
  getExecutiveBriefVisibleInsightLimit,
  displayMetricLabel,
  formatPresentationValue,
  presentationMetricLabel,
} from "../components/dashboard/dashboard-grid.tsx";
import { composeLauncherLayout, createDefaultLauncherState, updateLauncherWidgetSize } from "../lib/launcher/composer.js";

function widget(overrides = {}) {
  return {
    widget_id: "revenue",
    widget_type: "kpi",
    source_type: "PERMANENT",
    title: "Выручка",
    subtitle: null,
    metric_keys: [],
    signal_ids: [],
    entity_type: null,
    entity_id: null,
    organization_ids: [],
    semantic_size: "S",
    priority: 1,
    priority_reason: "priority",
    min_size: "S",
    preferred_size: "S",
    max_size: "M",
    supports_horizontal_expand: true,
    supports_vertical_expand: true,
    supports_internal_scroll: false,
    flow: "horizontal",
    preferred_aspect: "compact",
    content_density: "medium",
    scroll_behavior: "none",
    removable_by_ai: true,
    movable_by_ai: true,
    resizable_by_ai: true,
    locked_position: false,
    locked_size: false,
    pinned: false,
    hidden: false,
    drilldown: null,
    summary: null,
    data_status: "AVAILABLE",
    payload: {},
    ...overrides,
  };
}

const sampleWidgets = [
  widget({ widget_id: "revenue", title: "Выручка", semantic_size: "S", priority: 1 }),
  widget({ widget_id: "orders", title: "Заказы", semantic_size: "S", priority: 2 }),
  widget({ widget_id: "trend", widget_type: "trend", title: "Динамика", semantic_size: "XL", priority: 3 }),
  widget({ widget_id: "products", widget_type: "product_ranking", title: "Топ товаров", semantic_size: "L", priority: 4 }),
  widget({ widget_id: "quality", widget_type: "data_quality", title: "Качество", semantic_size: "M", priority: 5 }),
  widget({ widget_id: "comparison", widget_type: "organization_comparison", title: "Сравнение организаций", semantic_size: "XL", priority: 6 }),
  widget({ widget_id: "executive-brief", widget_type: "ai_insight", title: "Executive brief", semantic_size: "XL", priority: 6.5 }),
  widget({ widget_id: "watchlist", widget_type: "watchlist", title: "Watchlist", semantic_size: "S", priority: 7 }),
];

test("launcher column count grows with the available width", () => {
  assert.equal(buildLauncherGridSpec(1920).columns, 24);
  assert.equal(computeLauncherColumnCount(1024), 12);
  assert.equal(computeLauncherColumnCount(1280), 16);
  assert.equal(computeLauncherColumnCount(1440), 16);
  assert.equal(computeLauncherColumnCount(1920), 24);
  assert.equal(computeLauncherColumnCount(2125), 24);
  assert.equal(computeLauncherColumnCount(2560), 32);
});

test("default launcher layout keeps semantic widget widths instead of stretching", () => {
  const layouts = buildDefaultLayouts(sampleWidgets, { lg: 16 });
  assert.ok(Array.isArray(layouts.lg));
  const firstRow = layouts.lg.filter((item) => item.y === 0);
  assert.equal(firstRow[0].x, 0);
  assert.ok(firstRow.reduce((sum, item) => sum + item.w, 0) >= 16);
  assert.ok(firstRow.length >= 3);
  assert.ok(layouts.lg.some((item) => item.w >= 8));
});

test("layout normalization snaps unsupported sizes to allowed launcher sizes", () => {
  const layouts = normalizeLauncherLayouts(
    {
      lg: [{ i: "revenue", x: -5, y: 0, w: 9, h: 7 }],
      md: [{ i: "revenue", x: 99, y: 3, w: 1, h: 1 }],
      sm: [],
      xs: [],
      xxs: [],
    },
    [sampleWidgets[0]],
  );

  assert.equal(layouts.lg[0].x, 0);
  assert.ok(layouts.lg[0].w <= GRID_COLUMNS.lg);
  assert.ok(layouts.lg[0].h >= 2);
  assert.ok(layouts.md[0].w >= 2);
});

test("launcher commands move and resize widgets immutably", () => {
  const layouts = buildDefaultLayouts(sampleWidgets);
  const moved = moveWidget(layouts, "revenue", { x: 4, y: 2 });
  assert.equal(moved.lg.find((item) => item.i === "revenue").x, 4);
  assert.equal(moved.lg.find((item) => item.i === "revenue").y, 2);

  const resized = resizeWidget(layouts, "trend", "4x2");
  const trend = resized.lg.find((item) => item.i === "trend");
  assert.equal(trend.w, 4);
  assert.equal(trend.h, 2);

  const commandApplied = applyLauncherCommand(layouts, { type: "minimizeWidget", widgetId: "trend" }, sampleWidgets);
  assert.equal(commandApplied.lg.find((item) => item.i === "trend").w, 2);
  assert.equal(commandApplied.lg.find((item) => item.i === "trend").h, 2);
});

test("widget registry exposes family-aware size contracts", () => {
  const registry = buildWidgetRegistry(sampleWidgets);
  const comparison = registry.find((item) => item.widget_id === "comparison");
  const executiveBrief = registry.find((item) => item.widget_id === "executive-brief");
  const watchlist = registry.find((item) => item.widget_id === "watchlist");
  const dataQuality = buildWidgetRegistry([
    widget({ widget_id: "quality", widget_type: "data_quality", title: "Качество данных", semantic_size: "M", priority: 5 }),
  ])[0];
  const inventoryRisk = buildWidgetRegistry([
    widget({ widget_id: "inventory-risk", widget_type: "inventory_risk", title: "Риски запасов", semantic_size: "L", priority: 8 }),
  ])[0];

  assert.equal(registry.find((item) => item.widget_id === "revenue")?.allowedSizes.join(","), "3x2,6x3");
  assert.equal(registry.find((item) => item.widget_id === "revenue")?.family, "kpi");
  assert.equal(registry.find((item) => item.widget_id === "revenue")?.overflowStrategy, "none");
  assert.equal(registry.find((item) => item.widget_id === "revenue")?.previewContentLimit, 0);
  assert.equal(comparison?.family, "table");
  assert.equal(comparison?.defaultSize, "6x3");
  assert.ok(comparison?.allowedSizes.includes("6x3"));
  assert.ok(comparison?.allowedSizes.includes("12x4"));
  assert.equal(comparison?.overflowStrategy, "table-scroll");
  assert.equal(comparison?.previewContentLimit, 0);
  assert.equal(executiveBrief?.family, "detail");
  assert.deepEqual(executiveBrief?.allowedSizes, ["12x5"]);
  assert.equal(executiveBrief?.defaultSize, "12x5");
  assert.equal(executiveBrief?.overflowStrategy, "summary-preview");
  assert.equal(executiveBrief?.previewContentLimit, 3);
  assert.equal(watchlist?.family, "list");
  assert.ok(watchlist?.allowedSizes.includes("6x3"));
  assert.ok(watchlist?.allowedSizes.includes("12x4"));
  assert.equal(watchlist?.overflowStrategy, "list-scroll");
  assert.ok((watchlist?.contentVariants ?? []).length > 0);
  assert.equal(inventoryRisk?.family, "alert");
  assert.equal(inventoryRisk?.defaultSize, "4x3");
  assert.ok(inventoryRisk?.allowedSizes.includes("4x3"));
  assert.equal(inventoryRisk?.overflowStrategy, "list-scroll");
  assert.deepEqual(dataQuality?.allowedSizes, ["3x2", "6x3"]);
  assert.equal(dataQuality?.defaultSize, "3x2");
  assert.equal(dataQuality?.overflowStrategy, "summary-preview");
  assert.equal(dataQuality?.previewContentLimit, 2);

  const contract = getWidgetSizeContract(sampleWidgets[0]);
  assert.ok(contract.allowedSizes.includes(contract.defaultSize));
  assert.ok(contract.allowedSizes.includes(contract.minSize));
  assert.ok(contract.allowedSizes.includes(contract.maxSize));
});

test("launcher edit mode only enables resize for widgets with multiple allowed semantic sizes", () => {
  const kpiWidget = widget({ widget_id: "kpi-only", widget_type: "kpi", title: "Выручка", semantic_size: "S", priority: 1 });
  const detailWidget = widget({ widget_id: "executive-brief", widget_type: "ai_insight", title: "Сводка", semantic_size: "XL", priority: 2 });
  const alertWidget = widget({ widget_id: "risk", widget_type: "inventory_risk", title: "Риски", semantic_size: "L", priority: 2 });

  assert.equal(widgetCanResize(kpiWidget), true);
  assert.equal(widgetCanResize(detailWidget), false);
  assert.equal(widgetCanResize(alertWidget), true);
});

test("semantic resize snaps to the nearest allowed SmartUp launcher size", () => {
  const alertWidget = widget({ widget_id: "risk", widget_type: "inventory_risk", title: "Риски", semantic_size: "L", priority: 2 });

  assert.equal(snapWidgetSemanticSize(alertWidget, 4, 3, 12), "medium");
  assert.equal(snapWidgetSemanticSize(alertWidget, 12, 5, 12), "large");
});

test("semantic size updates are stored without physical geometry and recompose the launcher", () => {
  const widgets = [
    widget({ widget_id: "risk", widget_type: "inventory_risk", title: "Риски", semantic_size: "L", priority: 1 }),
    widget({ widget_id: "orders", widget_type: "kpi", title: "Заказы", semantic_size: "S", priority: 2 }),
    widget({ widget_id: "revenue", widget_type: "kpi", title: "Выручка", semantic_size: "S", priority: 3 }),
  ];
  const baseState = createDefaultLauncherState(widgets);
  const updatedState = updateLauncherWidgetSize({
    ...baseState,
    sizes: {
      ...baseState.sizes,
      risk: "medium",
    },
  }, widgets, "risk", "large");

  assert.deepEqual(updatedState.userOverrides?.size, ["risk"]);
  assert.equal(Object.keys(updatedState).some((key) => ["x", "y", "w", "h"].includes(key)), false);

  const before = composeLauncherLayout({ state: baseState, widgets, columns: 12 });
  const after = composeLauncherLayout({ state: updatedState, widgets, columns: 12 });

  assert.equal(before.find((item) => item.i === "risk")?.w, 3);
  assert.equal(after.find((item) => item.i === "risk")?.w, 12);
  assert.equal(after.find((item) => item.i === "orders")?.y, 3);
  assert.equal(after.find((item) => item.i === "revenue")?.y, 3);
});

test("launcher resize controls remain semantic and respect size locks", () => {
  const resized = resizeWidget(
    {
      lg: [
        { i: "kpi", x: 0, y: 0, w: 3, h: 2, lockedPosition: false, lockedSize: false, isResizable: false },
        { i: "alert", x: 3, y: 0, w: 6, h: 3, lockedPosition: false, lockedSize: false, isResizable: true },
      ],
    },
    "alert",
    "4x3",
  );

  assert.equal(resized.lg.find((item) => item.i === "kpi")?.isResizable, false);
  assert.equal(resized.lg.find((item) => item.i === "alert")?.isResizable, true);
  assert.equal(resized.lg.find((item) => item.i === "alert")?.w, 4);
  assert.equal(resized.lg.find((item) => item.i === "alert")?.h, 3);
});

test("launcher layout deduplicates widget ids deterministically", () => {
  const duplicated = [
    sampleWidgets[0],
    sampleWidgets[0],
    sampleWidgets[1],
    sampleWidgets[1],
  ];
  assert.equal(dedupeWidgets(duplicated).length, 2);

  const layouts = buildDefaultLayouts(duplicated);
  const ids = layouts.lg.map((item) => item.i);
  assert.equal(new Set(ids).size, ids.length);
});

test("launcher layout deduplicates semantic widget duplicates", () => {
  const duplicateBySignature = [
    widget({ widget_id: "revenue-a", title: "Выручка", semantic_size: "S", priority: 1 }),
    widget({ widget_id: "revenue-b", title: "Выручка", semantic_size: "S", priority: 2 }),
    widget({ widget_id: "orders", title: "Заказы", semantic_size: "S", priority: 3 }),
  ];

  assert.equal(dedupeWidgetSignatures(duplicateBySignature).length, 2);
});

test("canonical launcher layout repacks across wider wide-screen columns", () => {
  const canonical = buildLayoutForCols(sampleWidgets, 6);
  const derived = buildLauncherLayoutsFromCanonical(canonical, sampleWidgets, { lg: 16 }, 6);
  const firstRow = derived.lg.filter((item) => item.y === 0);
  assert.ok(firstRow.length >= 2);
  assert.ok(firstRow.reduce((sum, item) => sum + item.w, 0) <= 16);
});

test("launcher widget families drive layout grouping", () => {
  assert.equal(widgetLayoutGroup(sampleWidgets[0]), "kpi");
  assert.equal(widgetLayoutGroup(sampleWidgets[2]), "chart");
  assert.equal(widgetLayoutGroup(sampleWidgets[3]), "list");
  assert.equal(widgetLayoutGroup(sampleWidgets[5]), "table");
  assert.equal(widgetLayoutGroup(sampleWidgets[6]), "wide");
  assert.equal(widgetLayoutGroup(sampleWidgets[7]), "list");
});

test("legacy narrow layouts migrate to the new full-width defaults", () => {
  const legacyKey = "ai-business-os:launcher-layout:v5";
  const stored = {
    [legacyKey]: JSON.stringify({
      lg: [{ i: "revenue", x: 0, y: 0, w: 3, h: 2 }],
      md: [],
      sm: [],
      xs: [],
      xxs: [],
    }),
  } as Record<string, string>;

  const localStorage = {
    getItem(key: string) {
      return stored[key] ?? null;
    },
    setItem(key: string, value: string) {
      stored[key] = value;
    },
    removeItem(key: string) {
      delete stored[key];
    },
  };

  (globalThis as typeof globalThis & { window?: { localStorage: typeof localStorage } }).window = {
    localStorage,
  };

  const layouts = loadLauncherLayouts(sampleWidgets);
  assert.equal(layouts, null);
  assert.equal(stored[legacyKey], undefined);

  const restored = restoreDefaultLauncherLayouts(sampleWidgets, 16);
  assert.equal(restored.kind, "system-default");
  assert.equal(restored.cols, 16);
  assert.equal(restored.layout[0].x, 0);

  clearLauncherLayouts();
  delete (globalThis as typeof globalThis & { window?: unknown }).window;
});

test("obsolete user layouts are discarded so the fluid default can use the full width", () => {
  const userLayout = {
    "ai-business-os:launcher-layout:v15": JSON.stringify({
      version: "v15",
      kind: "user",
      cols: 16,
      layout: [
        { i: "revenue", x: 0, y: 0, w: 4, h: 2 },
        { i: "orders", x: 4, y: 0, w: 4, h: 2 },
      ],
    }),
  } as Record<string, string>;

  const localStorage = {
    getItem(key: string) {
      return userLayout[key] ?? null;
    },
    setItem(key: string, value: string) {
      userLayout[key] = value;
    },
    removeItem(key: string) {
      delete userLayout[key];
    },
  };

  (globalThis as typeof globalThis & { window?: { localStorage: typeof localStorage } }).window = {
    localStorage,
  };

  const layouts = loadLauncherLayouts(sampleWidgets);
  assert.equal(layouts, null);
  assert.equal(userLayout["ai-business-os:launcher-layout:v15"], undefined);

  const reset = restoreDefaultLauncherLayouts(sampleWidgets, 24);
  assert.equal(reset.kind, "system-default");
  assert.equal(reset.cols, 24);
  assert.ok(reset.layout.every((item) => item.x + item.w <= 24));

  clearLauncherLayouts();
  delete (globalThis as typeof globalThis & { window?: unknown }).window;
});

test("24-column desktop layout places large analytical widgets side by side", () => {
  const wideWidgets = [
    widget({ widget_id: "trend-a", widget_type: "trend", priority: 1 }),
    widget({ widget_id: "trend-b", widget_type: "trend", priority: 2 }),
  ];
  const layout = buildLayoutForCols(wideWidgets, 24);
  assert.deepEqual(
    layout.map(({ x, y, w }) => ({ x, y, w })),
    [
      { x: 0, y: 0, w: 12 },
      { x: 12, y: 0, w: 12 },
    ],
  );
});

test("24-column desktop layout balances five KPI widgets across the available row", () => {
  const kpis = Array.from({ length: 5 }, (_, index) =>
    widget({ widget_id: `kpi-${index}`, priority: index + 1 }),
  );
  const layout = buildLayoutForCols(kpis, 24);
  assert.deepEqual(
    layout.map(({ x, y, w }) => ({ x, y, w })),
    [
      { x: 0, y: 0, w: 6 },
      { x: 6, y: 0, w: 6 },
      { x: 12, y: 0, w: 4 },
      { x: 16, y: 0, w: 4 },
      { x: 20, y: 0, w: 4 },
    ],
  );
});

test("a final long-form list uses the complete wide-screen row", () => {
  const layout = buildLayoutForCols([
    widget({ widget_id: "list-a", widget_type: "watchlist", priority: 1 }),
    widget({ widget_id: "list-b", widget_type: "watchlist", priority: 2 }),
    widget({ widget_id: "list-c", widget_type: "watchlist", priority: 3 }),
  ], 24);
  const finalItem = layout.find((item) => item.i === "list-c");
  assert.equal(finalItem?.x, 0);
  assert.equal(finalItem?.w, 24);
});

test("content contracts keep list, KPI, table, and quality widgets in their intended density bands", () => {
  const registry = buildWidgetRegistry([
    widget({ widget_id: "kpi-revenue", widget_type: "kpi", title: "Выручка", priority: 1 }),
    widget({ widget_id: "client-list", widget_type: "watchlist", title: "На контроле", priority: 2 }),
    widget({ widget_id: "org-table", widget_type: "organization_comparison", title: "Сравнение организаций", priority: 3 }),
    widget({ widget_id: "quality", widget_type: "data_quality", title: "Качество данных", priority: 4 }),
  ]);

  const kpi = registry.find((item) => item.widget_id === "kpi-revenue");
  const list = registry.find((item) => item.widget_id === "client-list");
  const table = registry.find((item) => item.widget_id === "org-table");
  const quality = registry.find((item) => item.widget_id === "quality");

  assert.equal(kpi?.overflowStrategy, "none");
  assert.equal(kpi?.allowedSizes.join(","), "3x2,6x3");
  assert.equal(kpi?.previewContentLimit, 0);
  assert.equal(list?.overflowStrategy, "list-scroll");
  assert.ok((list?.allowedSizes ?? []).includes("6x3"));
  assert.ok((list?.allowedSizes ?? []).includes("12x5"));
  assert.equal(table?.allowedSizes[0], "6x3");
  assert.equal(table?.allowedSizes.at(-1), "12x5");
  assert.equal(table?.overflowStrategy, "table-scroll");
  assert.equal(quality?.defaultSize, "3x2");
  assert.equal(quality?.overflowStrategy, "summary-preview");
  assert.equal(quality?.previewContentLimit, 2);
});

test("executive brief insight visibility scales by variant", () => {
  assert.equal(getExecutiveBriefVisibleInsightLimit("compact"), 1);
  assert.equal(getExecutiveBriefVisibleInsightLimit("regular"), 2);
  assert.equal(getExecutiveBriefVisibleInsightLimit("expanded"), 3);
  assert.equal(getExecutiveBriefVisibleInsightLimit("xl"), 3);
});

test("presentation formatting removes raw backend numeric forms and technical labels", () => {
  assert.equal(formatPresentationValue("317488070.0000"), "317 488 070");
  assert.equal(formatPresentationValue(-12692000), "−12 692 000");
  assert.equal(formatPresentationValue("text"), "text");
  assert.equal(displayMetricLabel("CUSTOMER_RETURN_VALUE"), "Сумма документов возврата");
  assert.equal(displayMetricLabel("low_stock"), "Низкий остаток");
  assert.equal(presentationMetricLabel("CUSTOMER_RETURN_VALUE"), "Сумма документов возврата");
  assert.equal(presentationMetricLabel("medium"), "Показатель");
});

test("product signals are aggregated into a single launcher widget", () => {
  const widgets = [
    widget({ widget_id: "product-signal-a", widget_type: "product_alert", title: "Product signal A", entity_type: "product", priority: 1 }),
    widget({ widget_id: "product-signal-b", widget_type: "watchlist", title: "Product signal B", entity_type: "product", priority: 2 }),
    widget({ widget_id: "revenue", widget_type: "kpi", title: "Выручка", priority: 3 }),
  ];

  const aggregated = aggregateProductSignalWidgets(widgets);
  assert.equal(aggregated.length, 2);
  const productSignals = aggregated.find((item) => item.widget_id === "product-signals");
  assert.ok(productSignals);
  assert.equal(productSignals?.title, "Товарные сигналы");
  assert.equal(productSignals?.payload && typeof productSignals.payload === "object" ? (productSignals.payload as { total_count?: number }).total_count : 0, 2);
});
