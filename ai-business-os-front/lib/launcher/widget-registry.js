import {
  normalizeLauncherSize,
} from "./size-mapping";

export const WIDGET_FAMILIES = {
  KPI: "kpi",
  CHART: "chart",
  TABLE: "table",
  LIST: "list",
  SUMMARY: "summary",
  ALERT: "alert",
  DETAIL: "detail",
};

export const FAMILY_CONTRACTS = {
  kpi: {
    allowedSizes: ["3x2"],
    defaultSize: "3x2",
    minSize: "3x2",
    maxSize: "3x2",
    overflowStrategy: "none",
    previewContentLimit: 0,
    contentVariants: ["compact"],
  },
  chart: {
    allowedSizes: ["6x3"],
    defaultSize: "6x3",
    minSize: "6x3",
    maxSize: "6x3",
    overflowStrategy: "body",
    previewContentLimit: 0,
    contentVariants: ["regular", "expanded"],
  },
  table: {
    allowedSizes: ["12x4"],
    defaultSize: "12x4",
    minSize: "12x4",
    maxSize: "12x4",
    overflowStrategy: "table-scroll",
    previewContentLimit: 0,
    contentVariants: ["expanded", "xl"],
  },
  list: {
    allowedSizes: ["12x5"],
    defaultSize: "12x5",
    minSize: "12x5",
    maxSize: "12x5",
    overflowStrategy: "list-scroll",
    previewContentLimit: 8,
    contentVariants: ["expanded", "xl"],
  },
  summary: {
    allowedSizes: ["6x3"],
    defaultSize: "6x3",
    minSize: "6x3",
    maxSize: "6x3",
    overflowStrategy: "summary-preview",
    previewContentLimit: 3,
    contentVariants: ["regular", "expanded"],
  },
  alert: {
    allowedSizes: ["6x3"],
    defaultSize: "6x3",
    minSize: "6x3",
    maxSize: "6x3",
    overflowStrategy: "list-scroll",
    previewContentLimit: 3,
    contentVariants: ["regular", "expanded"],
  },
  detail: {
    allowedSizes: ["12x5"],
    defaultSize: "12x5",
    minSize: "12x5",
    maxSize: "12x5",
    overflowStrategy: "summary-preview",
    previewContentLimit: 3,
    contentVariants: ["expanded", "xl"],
  },
  default: {
    allowedSizes: ["6x3"],
    defaultSize: "6x3",
    minSize: "6x3",
    maxSize: "6x3",
    overflowStrategy: "body",
    previewContentLimit: 0,
    contentVariants: ["regular", "expanded"],
  },
};

export const WIDGET_FAMILY_BY_TYPE = {
  kpi: WIDGET_FAMILIES.KPI,
  trend: WIDGET_FAMILIES.CHART,
  line_chart: WIDGET_FAMILIES.CHART,
  bar_chart: WIDGET_FAMILIES.CHART,
  organization_comparison: WIDGET_FAMILIES.TABLE,
  table: WIDGET_FAMILIES.TABLE,
  product_ranking: WIDGET_FAMILIES.LIST,
  customer_ranking: WIDGET_FAMILIES.LIST,
  inventory_risk: WIDGET_FAMILIES.ALERT,
  visit_summary: WIDGET_FAMILIES.SUMMARY,
  sales_rep_performance: WIDGET_FAMILIES.SUMMARY,
  data_quality: WIDGET_FAMILIES.SUMMARY,
  ai_insight: WIDGET_FAMILIES.DETAIL,
  ai_recommendation: WIDGET_FAMILIES.DETAIL,
  watchlist: WIDGET_FAMILIES.LIST,
  alert: WIDGET_FAMILIES.ALERT,
  product_alert: WIDGET_FAMILIES.ALERT,
  customer_alert: WIDGET_FAMILIES.ALERT,
  inventory_alert: WIDGET_FAMILIES.ALERT,
  photo_alert: WIDGET_FAMILIES.ALERT,
};

function resolveFamily(widget) {
  if (widget.widget_type === "ai_insight" && widget.widget_id === "executive-brief") {
    return WIDGET_FAMILIES.DETAIL;
  }
  return WIDGET_FAMILY_BY_TYPE[widget.widget_type] ?? WIDGET_FAMILIES.SUMMARY;
}

function resolveRule(widget) {
  if (widget.widget_type === "inventory_risk") {
    return {
      ...FAMILY_CONTRACTS.alert,
      allowedSizes: ["4x3", "6x3", "12x5"],
      defaultSize: "4x3",
      minSize: "4x3",
      maxSize: "12x5",
      previewContentLimit: 2,
    };
  }
  if (widget.widget_type === "data_quality") {
    return {
      ...FAMILY_CONTRACTS.summary,
      allowedSizes: ["3x2", "6x3"],
      defaultSize: "3x2",
      minSize: "3x2",
      maxSize: "6x3",
      overflowStrategy: "summary-preview",
      previewContentLimit: 2,
    };
  }
  const family = resolveFamily(widget);
  if (widget.widget_type === "ai_insight" && widget.widget_id === "executive-brief") {
    return {
      ...FAMILY_CONTRACTS.detail,
      overflowStrategy: "summary-preview",
      previewContentLimit: 3,
    };
  }
  return FAMILY_CONTRACTS[family] ?? FAMILY_CONTRACTS.default;
}

function uniqueSizes(sizes) {
  return Array.from(new Set(sizes.map(normalizeLauncherSize)));
}

export function buildWidgetDefinition(widget) {
  const rule = resolveRule(widget);
  const family = resolveFamily(widget);
  const allowedSizes = uniqueSizes(rule.allowedSizes);
  const defaultSize = allowedSizes.includes(rule.defaultSize) ? rule.defaultSize : allowedSizes[0];
  const minSize = allowedSizes.includes(rule.minSize) ? rule.minSize : allowedSizes[0];
  const maxSize = allowedSizes.includes(rule.maxSize) ? rule.maxSize : allowedSizes[allowedSizes.length - 1];
  return {
    widget_id: widget.widget_id,
    widget_type: widget.widget_type,
    family,
    title: widget.title,
    source_type: widget.source_type,
    allowedSizes,
    defaultSize,
    minSize,
    maxSize,
    contentVariants: rule.contentVariants,
    overflowStrategy: rule.overflowStrategy,
    previewContentLimit: rule.previewContentLimit,
    priority: widget.priority,
    lockedPosition: widget.locked_position,
    lockedSize: widget.locked_size,
    contentDensity: widget.content_density,
    scrollBehavior: widget.scroll_behavior,
    semanticSize: widget.semantic_size,
    drilldown: widget.drilldown,
    supportsAIPlacement: widget.movable_by_ai || widget.resizable_by_ai || widget.removable_by_ai,
  };
}

export function buildWidgetRegistry(widgets) {
  return widgets.map(buildWidgetDefinition);
}

export function getWidgetDefinition(widget) {
  return buildWidgetDefinition(widget);
}

export function getRegistryEntryById(registry, widgetId) {
  return registry.find((item) => item.widget_id === widgetId) ?? null;
}

export function getWidgetFamily(widget) {
  return resolveFamily(widget);
}

export function getWidgetSizeContract(widget) {
  const rule = resolveRule(widget);
  const allowedSizes = uniqueSizes(rule.allowedSizes);
  const defaultSize = allowedSizes.includes(rule.defaultSize) ? rule.defaultSize : allowedSizes[0];
  const minSize = allowedSizes.includes(rule.minSize) ? rule.minSize : allowedSizes[0];
  const maxSize = allowedSizes.includes(rule.maxSize) ? rule.maxSize : allowedSizes[allowedSizes.length - 1];
  return {
    family: resolveFamily(widget),
    allowedSizes,
    defaultSize,
    minSize,
    maxSize,
    contentVariants: rule.contentVariants,
    overflowStrategy: rule.overflowStrategy,
    previewContentLimit: rule.previewContentLimit,
  };
}
