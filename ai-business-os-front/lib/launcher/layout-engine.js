import { getWidgetDefinition, buildWidgetRegistry, getWidgetFamily } from "./widget-registry";
import {
  LAUNCHER_SIZE_PRESETS,
  clampSize,
  getLauncherVariantFromGrid,
  launcherSizeToSemanticSize,
  normalizeLauncherSize,
} from "./size-mapping";

export const LAUNCHER_LAYOUT_VERSION = "v16";
export const LAUNCHER_STORAGE_KEY = "ai-business-os:launcher-layout:v16";
export const LEGACY_STORAGE_KEYS = [
  "ai-business-os:launcher-layout:v12",
  "ai-business-os:launcher-layout:v11",
  "ai-business-os:launcher-layout:v10",
  "ai-business-os:launcher-layout:v8",
  "ai-business-os:launcher-layout:v7",
  "ai-business-os:launcher-layout:v6",
  "ai-business-os:launcher-layout:v5",
  "ai-business-os:launcher-layout:v4",
  "ai-business-os:launcher-layout:v13",
  "ai-business-os:launcher-layout:v14",
  "ai-business-os:launcher-layout:v15",
  "ai-business-os:dashboard-manifest-layout:v2",
  "ai-business-os:dashboard-manifest-layout:v3",
];

export const GRID_COLUMNS = {
  lg: 16,
  md: 12,
  sm: 8,
  xs: 6,
  xxs: 4,
};

export const LAUNCHER_LAYOUT_TARGET_CELL_WIDTH = 80;
export const LAUNCHER_LAYOUT_MIN_COLUMNS = 4;
export const LAUNCHER_LAYOUT_MAX_COLUMNS = 32;
export const LAUNCHER_LAYOUT_COLUMN_STEP = 4;

export function computeLauncherColumnCount(width) {
  const measuredWidth = Number.isFinite(width) ? Math.max(0, width) : 0;
  if (measuredWidth <= 0) return GRID_COLUMNS.lg;
  const idealColumns = Math.floor(measuredWidth / LAUNCHER_LAYOUT_TARGET_CELL_WIDTH);
  const steppedColumns = Math.floor(idealColumns / LAUNCHER_LAYOUT_COLUMN_STEP) * LAUNCHER_LAYOUT_COLUMN_STEP;
  return Math.max(LAUNCHER_LAYOUT_MIN_COLUMNS, Math.min(LAUNCHER_LAYOUT_MAX_COLUMNS, steppedColumns));
}

export function buildLauncherGridSpec(width) {
  const columns = computeLauncherColumnCount(width);
  const breakpoints = {};
  const cols = {};

  for (let count = LAUNCHER_LAYOUT_MIN_COLUMNS; count <= columns; count += LAUNCHER_LAYOUT_COLUMN_STEP) {
    const key = `c${count}`;
    breakpoints[key] = Math.max(0, Math.round(count * LAUNCHER_LAYOUT_TARGET_CELL_WIDTH));
    cols[key] = count;
  }

  return {
    columns,
    breakpoint: `c${columns}`,
    breakpoints,
    cols,
  };
}

export function dedupeWidgets(widgets) {
  const seen = new Set();
  const deduped = [];
  for (const widget of widgets) {
    if (!widget?.widget_id || seen.has(widget.widget_id)) continue;
    seen.add(widget.widget_id);
    deduped.push(widget);
  }
  return deduped;
}

export function dedupeWidgetSignatures(widgets) {
  const seen = new Set();
  const deduped = [];
  for (const widget of widgets) {
    if (!widget) continue;
    const signature = [
      widget.widget_type,
      String(widget.title ?? "").trim().toLowerCase(),
      widget.source_type,
      widget.entity_type ?? "",
      widget.entity_id ?? "",
      [...(widget.organization_ids ?? [])].sort().join(","),
      [...(widget.metric_keys ?? [])].sort().join(","),
      [...(widget.signal_ids ?? [])].sort().join(","),
    ].join("|");
    if (seen.has(signature)) continue;
    seen.add(signature);
    deduped.push(widget);
  }
  return deduped;
}

export function widgetLayoutGroup(widget) {
  if (widget.widget_type === "ai_insight" && widget.widget_id === "executive-brief") {
    return "wide";
  }
  if (widget.widget_id === "product-signals") {
    return "list";
  }
  return getWidgetFamily(widget);
}

export function widgetGroupRank(widget) {
  const group = widgetLayoutGroup(widget);
  switch (group) {
    case "kpi":
      return 0;
    case "summary":
      return 1;
    case "alert":
      return 2;
    case "wide":
      return 3;
    case "chart":
      return 4;
    case "table":
      return 5;
    case "list":
      return 6;
    default:
      return 7;
  }
}

export function rowCapacityForGroup(group) {
  switch (group) {
    case "kpi":
      return 4;
    case "chart":
      return 2;
    case "table":
      return 1;
    case "list":
      return 2;
    case "summary":
      return 3;
    case "alert":
      return 4;
    case "wide":
      return 2;
    case "compact":
      return 2;
    default:
      return 2;
  }
}

export function rowWidthsForGroup(group, count, cols) {
  const normalizedCount = Math.max(1, Math.min(count, rowCapacityForGroup(group)));
  const base = Math.floor(cols / normalizedCount);
  let remainder = cols % normalizedCount;
  return Array.from({ length: normalizedCount }, () => base + (remainder-- > 0 ? 1 : 0));
}

function adaptiveDefaultSizeName(widget, cols) {
  const group = widgetLayoutGroup(widget);
  switch (group) {
    case "kpi":
      if (cols >= 16) return "4x2";
      if (cols >= 12) return "3x2";
      return "2x2";
    case "chart":
      return cols >= 16 ? "12x5" : cols >= 12 ? "8x4" : "6x3";
    case "wide":
      return cols >= 16 ? "12x5" : cols >= 12 ? "8x4" : "6x3";
    case "table":
      return cols >= 16 ? "12x5" : "8x4";
    case "list":
      if (cols >= 16) return "12x5";
      if (cols >= 12) return "8x4";
      return "4x3";
    case "summary":
      if (cols >= 24) return "12x5";
      if (cols >= 20) return "8x4";
      if (cols >= 16) return "8x4";
      if (cols >= 12) return "6x3";
      return "3x2";
    case "alert":
      if (cols >= 16) return "4x3";
      if (cols >= 12) return "3x2";
      return "2x2";
    default:
      return getWidgetDefinition(widget).defaultSize;
  }
}

export function rowHeightForWidget(widget) {
  const def = getWidgetDefinition(widget);
  return LAUNCHER_SIZE_PRESETS[def.defaultSize].h;
}

function allowedSizesForWidget(widget) {
  return getWidgetDefinition(widget).allowedSizes;
}

export function widgetCanResize(widget) {
  return allowedSizesForWidget(widget).length > 1;
}

export function snapToAllowedSize(widget, width, height, cols) {
  const allowedSizes = allowedSizesForWidget(widget);
  const currentArea = Math.max(1, width * height);
  let bestSize = allowedSizes[0] ?? "2x2";
  let bestScore = Number.POSITIVE_INFINITY;

  for (const size of allowedSizes) {
    const clamped = clampSize(size, cols);
    const area = clamped.w * clamped.h;
    const widthDistance = Math.abs(clamped.w - width);
    const heightDistance = Math.abs(clamped.h - height);
    const areaDistance = Math.abs(area - currentArea);
    const score = widthDistance * 2 + heightDistance * 2 + areaDistance * 0.05;
    if (score < bestScore) {
      bestScore = score;
      bestSize = size;
    }
  }

  return normalizeLauncherSize(bestSize);
}

export function snapWidgetSemanticSize(widget, width, height, cols) {
  return launcherSizeToSemanticSize(snapToAllowedSize(widget, width, height, cols));
}

function layoutSortValue(item) {
  return [
    Math.max(0, item.y ?? 0),
    Math.max(0, item.x ?? 0),
    Math.max(0, item.priority ?? 0),
    item.i ?? "",
  ];
}

function compareLayoutItems(left, right) {
  const [leftY, leftX, leftPriority, leftId] = layoutSortValue(left);
  const [rightY, rightX, rightPriority, rightId] = layoutSortValue(right);
  if (leftY !== rightY) return leftY - rightY;
  if (leftX !== rightX) return leftX - rightX;
  if (leftPriority !== rightPriority) return leftPriority - rightPriority;
  return String(leftId).localeCompare(String(rightId));
}

function packWidgetEntries(entries, cols) {
  const packed = [];
  const remaining = [...entries];
  let cursorY = 0;

  const toLayoutItem = (entry, x, y) => ({
    i: entry.widget.widget_id,
    x,
    y,
    w: entry.size.w,
    h: entry.size.h,
    minW: Math.min(LAUNCHER_SIZE_PRESETS[entry.contract.minSize].w, cols),
    minH: LAUNCHER_SIZE_PRESETS[entry.contract.minSize].h,
    maxW: Math.min(LAUNCHER_SIZE_PRESETS[entry.contract.maxSize].w, cols),
    maxH: LAUNCHER_SIZE_PRESETS[entry.contract.maxSize].h,
    static: entry.widget.locked_position && entry.widget.locked_size,
    isDraggable: !entry.widget.locked_position,
    isResizable: !entry.widget.locked_size,
    lockedPosition: entry.widget.locked_position,
    lockedSize: entry.widget.locked_size,
    launcherSize: entry.sizeName,
    launcherVariant: getLauncherVariantFromGrid(entry.size.w, entry.size.h),
    priority: entry.widget.priority,
    widgetType: entry.widget.widget_type,
  });

  const compareCandidates = (left, right, remainingWidth) => {
    const leftRank = widgetGroupRank(left.widget);
    const rightRank = widgetGroupRank(right.widget);
    if (leftRank !== rightRank) return leftRank - rightRank;

    const leftPriority = left.widget.priority ?? 0;
    const rightPriority = right.widget.priority ?? 0;
    if (leftPriority !== rightPriority) return leftPriority - rightPriority;

    const leftGap = remainingWidth - left.size.w;
    const rightGap = remainingWidth - right.size.w;
    if (leftGap !== rightGap) return leftGap - rightGap;

    if (left.size.w !== right.size.w) return right.size.w - left.size.w;
    if (left.size.h !== right.size.h) return right.size.h - left.size.h;
    return left.widget.widget_id.localeCompare(right.widget.widget_id);
  };

  while (remaining.length > 0) {
    const row = [];
    let remainingWidth = cols;
    let rowHeight = 0;

    while (true) {
      let bestIndex = -1;
      let bestEntry = null;

      for (let index = 0; index < remaining.length; index += 1) {
        const entry = remaining[index];
        if (entry.size.w > remainingWidth) continue;
        if (!bestEntry || compareCandidates(entry, bestEntry, remainingWidth) < 0) {
          bestEntry = entry;
          bestIndex = index;
        }
      }

      if (bestIndex < 0 || !bestEntry) break;

      remaining.splice(bestIndex, 1);
      row.push(bestEntry);
      remainingWidth -= bestEntry.size.w;
      rowHeight = Math.max(rowHeight, bestEntry.size.h);
      if (remainingWidth <= 0) break;
    }

    if (row.length === 0) {
      const entry = remaining.shift();
      if (!entry) break;
      row.push(entry);
      rowHeight = entry.size.h;
    }

    const rowGroups = new Set(row.map((entry) => widgetLayoutGroup(entry.widget)));
    if (
      remaining.length === 0 &&
      row.length === 1 &&
      rowGroups.has("list") &&
      LAUNCHER_SIZE_PRESETS[`${cols}x5`]
    ) {
      row[0].size = { w: cols, h: 5 };
      row[0].sizeName = `${cols}x5`;
      remainingWidth = 0;
      rowHeight = Math.max(rowHeight, 5);
    } else if (remainingWidth > 0 && rowGroups.size === 1 && rowGroups.has("kpi")) {
      for (const entry of row) {
        if (remainingWidth <= 0) break;
        const maxWidth = Math.min(LAUNCHER_SIZE_PRESETS[entry.contract.maxSize].w, cols);
        const expandableBy = Math.min(remainingWidth, Math.max(0, maxWidth - entry.size.w));
        if (expandableBy <= 0) continue;
        entry.size = { ...entry.size, w: entry.size.w + expandableBy };
        entry.sizeName = `${entry.size.w}x${entry.size.h}`;
        remainingWidth -= expandableBy;
      }
    }

    let cursorX = 0;
    for (const entry of row) {
      packed.push(toLayoutItem(entry, cursorX, cursorY));
      cursorX += entry.size.w;
    }

    cursorY += Math.max(rowHeight, ...row.map((entry) => entry.size.h));
  }

  return packed;
}

function buildLayoutEntriesFromWidgets(widgets, cols) {
  return dedupeWidgets([...widgets]).sort((left, right) => {
    const groupDiff = widgetGroupRank(left) - widgetGroupRank(right);
    if (groupDiff !== 0) return groupDiff;
    const priorityDiff = left.priority - right.priority;
    if (priorityDiff !== 0) return priorityDiff;
    return left.widget_id.localeCompare(right.widget_id);
  }).map((widget) => {
    const contract = getWidgetDefinition(widget);
    const sizeName = normalizeLauncherSize(adaptiveDefaultSizeName(widget, cols));
    const size = clampSize(sizeName, cols);
    return {
      widget,
      contract,
      sizeName,
      size,
    };
  });
}

export function buildLayoutForCols(widgets, cols) {
  return packWidgetEntries(buildLayoutEntriesFromWidgets(widgets, cols), cols);
}

export function repackLayoutForCols(layout, widgets, cols) {
  const widgetMap = new Map(dedupeWidgets(widgets).map((widget) => [widget.widget_id, widget]));
  const orderedLayoutItems = dedupeLayoutItems(layout ?? [])
    .filter((item) => widgetMap.has(item.i))
    .sort(compareLayoutItems);

  const entries = orderedLayoutItems.map((item) => {
    const widget = widgetMap.get(item.i);
    const contract = getWidgetDefinition(widget);
    const sizeName = snapToAllowedSize(widget, item.w ?? LAUNCHER_SIZE_PRESETS[contract.defaultSize].w, item.h ?? LAUNCHER_SIZE_PRESETS[contract.defaultSize].h, cols);
    const size = clampSize(sizeName, cols);
    return {
      widget,
      contract,
      sizeName,
      size,
    };
  });

  if (entries.length === 0) {
    return buildLayoutForCols(widgets, cols);
  }

  return packWidgetEntries(entries, cols);
}

export function buildLauncherLayoutsFromCanonical(layout, widgets, columnsMap, sourceCols) {
  const layouts = {};
  const uniqueWidgets = dedupeWidgets(widgets);
  const canonical = Array.isArray(layout) ? layout : [];

  for (const [breakpoint, cols] of Object.entries(columnsMap)) {
    if (sourceCols && cols === sourceCols) {
      layouts[breakpoint] = normalizeLayoutForBreakpoint(canonical, uniqueWidgets, cols);
      continue;
    }
    layouts[breakpoint] = repackLayoutForCols(canonical, uniqueWidgets, cols);
  }

  return layouts;
}

export function buildDefaultLayouts(widgets, columnsMap = GRID_COLUMNS) {
  const uniqueWidgets = dedupeWidgets(widgets);
  const layouts = {};
  for (const [breakpoint, cols] of Object.entries(columnsMap)) {
    layouts[breakpoint] = buildLayoutForCols(uniqueWidgets, cols);
  }
  return layouts;
}

export function normalizeLayoutItem(widget, item, cols) {
  const def = getWidgetDefinition(widget);
  const preferredSize = adaptiveDefaultSizeName(widget, cols);
  const defaultPreset = LAUNCHER_SIZE_PRESETS[preferredSize] ?? LAUNCHER_SIZE_PRESETS[def.defaultSize];
  const safeSize = snapToAllowedSize(widget, item.w ?? defaultPreset.w, item.h ?? defaultPreset.h, cols);
  const clamped = clampSize(safeSize, cols);
  return {
    ...item,
    i: widget.widget_id,
    x: Math.max(0, Math.min(item.x ?? 0, Math.max(0, cols - clamped.w))),
    y: Math.max(0, item.y ?? 0),
    w: clamped.w,
    h: clamped.h,
    minW: Math.min(LAUNCHER_SIZE_PRESETS[def.minSize].w, cols),
    minH: LAUNCHER_SIZE_PRESETS[def.minSize].h,
    maxW: Math.min(LAUNCHER_SIZE_PRESETS[def.maxSize].w, cols),
    maxH: LAUNCHER_SIZE_PRESETS[def.maxSize].h,
    static: widget.locked_position && widget.locked_size,
    isDraggable: !widget.locked_position,
    isResizable: !widget.locked_size,
    lockedPosition: widget.locked_position,
    lockedSize: widget.locked_size,
    launcherSize: safeSize,
    launcherVariant: getLauncherVariantFromGrid(clamped.w, clamped.h),
    priority: widget.priority,
    widgetType: widget.widget_type,
  };
}

function dedupeLayoutItems(items) {
  const seen = new Set();
  return items.filter((item) => {
    if (seen.has(item.i)) return false;
    seen.add(item.i);
    return true;
  });
}

export function normalizeLayoutForBreakpoint(layout, widgets, cols) {
  if (!layout) return [];
  const widgetMap = new Map(dedupeWidgets(widgets).map((widget) => [widget.widget_id, widget]));
  const merged = [];
  for (const item of layout) {
    const widget = widgetMap.get(item.i);
    if (!widget) continue;
    merged.push(normalizeLayoutItem(widget, item, cols));
  }
  const unique = dedupeLayoutItems(merged);
  unique.sort((left, right) => {
    if (left.y !== right.y) return left.y - right.y;
    if (left.x !== right.x) return left.x - right.x;
    const leftPriority = left.priority ?? 0;
    const rightPriority = right.priority ?? 0;
    if (leftPriority !== rightPriority) return leftPriority - rightPriority;
    return left.i.localeCompare(right.i);
  });
  return unique;
}

export function normalizeLauncherLayouts(layouts, widgets, breakpoints = GRID_COLUMNS) {
  const normalized = {};
  const uniqueWidgets = dedupeWidgets(widgets);
  for (const [breakpoint, cols] of Object.entries(breakpoints)) {
    normalized[breakpoint] = normalizeLayoutForBreakpoint(layouts?.[breakpoint] ?? [], uniqueWidgets, cols);
  }
  return normalized;
}

export function migrateLauncherLayouts(layouts, widgets) {
  return normalizeLauncherLayouts(layouts, dedupeWidgets(widgets));
}

export function getLayoutForBreakpoint(layouts, breakpoint) {
  return layouts?.[breakpoint] ?? [];
}

export function createNormalizedLayoutSnapshot(layouts, widgets) {
  const dedupedWidgets = dedupeWidgets(widgets);
  const registry = buildWidgetRegistry(dedupedWidgets);
  return {
    version: LAUNCHER_LAYOUT_VERSION,
    registry,
    layouts: normalizeLauncherLayouts(layouts, dedupedWidgets),
  };
}
