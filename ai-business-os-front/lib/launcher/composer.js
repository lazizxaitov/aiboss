import { getWidgetFamily } from "./widget-registry";

// Two extra breakpoints for large/ultra-wide monitors. Without them, a
// screen wider than "lg" (1024px) still only had 12 columns, so each column
// grew huge as the viewport widened — the grid either looked stretched out
// (full width) or had to be artificially capped (looked small/letterboxed).
// More columns at wider breakpoints keeps each column a sane physical size
// while the grid still fills the full available width.
export const LAUNCHER_BREAKPOINTS = Object.freeze({
  xxl: 2200, xl: 1600, lg: 1024, md: 768, sm: 0,
});
export const LAUNCHER_COLUMNS = Object.freeze({
  xxl: 20, xl: 16, lg: 12, md: 8, sm: 4,
});

const VALID_SIZES = new Set(["small", "medium", "large"]);

// Height now varies by the widget's chosen semantic size, not just its family.
// A "small" chart/table/list needs meaningfully less vertical room than a
// "large" one, otherwise content is forced to cram into (or spill out of) a
// box sized for a different density.
const FAMILY_HEIGHTS = Object.freeze({
  kpi: { small: 2, medium: 2, large: 2 },
  alert: { small: 2, medium: 3, large: 4 },
  wide: { small: 4, medium: 5, large: 6 },
  detail: { small: 3, medium: 4, large: 6 },
  summary: { small: 2, medium: 4, large: 5 },
  chart: { small: 3, medium: 5, large: 7 },
  list: { small: 3, medium: 5, large: 7 },
  table: { small: 4, medium: 5, large: 7 },
});

const DEFAULT_FAMILY_HEIGHTS = { small: 3, medium: 4, large: 5 };

const FAMILY_DEFAULT_SIZES = Object.freeze({
  kpi: "small",
  alert: "medium",
  wide: "large",
  detail: "large",
  summary: "medium",
  chart: "medium",
  list: "large",
  table: "large",
});

function unique(values) {
  return Array.from(new Set(values));
}

function orderedWidgets(widgets) {
  return [...widgets].sort((left, right) => {
    const priority = Number(left.priority ?? 0) - Number(right.priority ?? 0);
    return priority || String(left.widget_id).localeCompare(String(right.widget_id));
  });
}

function defaultSizeForWidget(widget) {
  const family = getWidgetFamily(widget);
  return FAMILY_DEFAULT_SIZES[family] ?? "medium";
}

function widthForSize(size, columns) {
  if (columns <= 4) {
    // At the narrowest breakpoint everything is effectively full-width, but
    // "small" still gets a visibly smaller footprint than "large" so users
    // can tell the sizes apart instead of everything collapsing to columns.
    if (size === "small") return Math.max(2, Math.round(columns / 2));
    if (size === "medium") return columns;
    return columns;
  }
  if (columns <= 8) {
    // Previously "small" and "medium" both returned 4 here, making the two
    // sizes visually identical. Give medium real extra width.
    if (size === "small") return 4;
    if (size === "medium") return Math.min(columns, 6);
    return columns;
  }
  if (columns <= 12) {
    if (size === "small") return 3;
    if (size === "medium") return 6;
    return columns;
  }
  // Wider grids (xl/xxl breakpoints, 16-20 columns): keep "small"/"medium"
  // widgets at a sane absolute width instead of shrinking them further, so
  // more widgets fit side by side and fill the extra screen width rather
  // than a handful of boxes stretching to cover it.
  if (size === "small") return 4;
  if (size === "medium") return 8;
  return columns;
}

function heightForWidget(widget, size) {
  const family = getWidgetFamily(widget);
  const heightsForFamily = FAMILY_HEIGHTS[family] ?? DEFAULT_FAMILY_HEIGHTS;
  return heightsForFamily[size] ?? heightsForFamily.medium ?? DEFAULT_FAMILY_HEIGHTS.medium;
}

export function createDefaultLauncherState(widgets) {
  const ordered = orderedWidgets(widgets);
  return {
    order: ordered.map((widget) => widget.widget_id),
    sizes: Object.fromEntries(
      ordered.map((widget) => [widget.widget_id, defaultSizeForWidget(widget)]),
    ),
    pinned: ordered.filter((widget) => widget.pinned).map((widget) => widget.widget_id),
    locked: ordered.filter((widget) => widget.locked_position).map((widget) => widget.widget_id),
    hidden: [],
    userOverrides: {
      size: [],
      order: false,
      hidden: [],
    },
  };
}

export function normalizeLauncherState(state, widgets) {
  const defaults = createDefaultLauncherState(widgets);
  const validIds = new Set(defaults.order);
  const storedOrder = Array.isArray(state?.order)
    ? unique(state.order.filter((id) => typeof id === "string" && validIds.has(id)))
    : [];
  const order = [...storedOrder, ...defaults.order.filter((id) => !storedOrder.includes(id))];
  const sizes = Object.fromEntries(order.map((id) => {
    const stored = state?.sizes?.[id];
    return [id, VALID_SIZES.has(stored) ? stored : defaults.sizes[id]];
  }));
  const filterIds = (values) => Array.isArray(values)
    ? unique(values.filter((id) => typeof id === "string" && validIds.has(id)))
    : [];

  return {
    order,
    sizes,
    pinned: filterIds(state?.pinned ?? defaults.pinned),
    locked: filterIds(state?.locked ?? defaults.locked),
    hidden: filterIds(state?.hidden ?? []),
    userOverrides: {
      size: filterIds(state?.userOverrides?.size ?? []),
      order: Boolean(state?.userOverrides?.order),
      hidden: filterIds(state?.userOverrides?.hidden ?? []),
    },
  };
}

export function updateLauncherWidgetSize(state, widgets, widgetId, size) {
  return normalizeLauncherState({
    ...state,
    sizes: {
      ...(state?.sizes ?? {}),
      [widgetId]: VALID_SIZES.has(size) ? size : "medium",
    },
    userOverrides: {
      size: Array.from(new Set([...(state?.userOverrides?.size ?? []), widgetId])),
      order: Boolean(state?.userOverrides?.order),
      hidden: state?.userOverrides?.hidden ?? [],
    },
  }, widgets);
}

export function composeLauncherLayout({ state, widgets, columns }) {
  const normalized = normalizeLauncherState(state, widgets);
  const byId = new Map(widgets.map((widget) => [widget.widget_id, widget]));
  const hidden = new Set(normalized.hidden);
  const orderedIds = normalized.order.filter((id) => byId.has(id) && !hidden.has(id));
  const locked = new Set(normalized.locked);
  const layout = [];
  let y = 0;
  let currentRow = [];
  let currentWidth = 0;
  let currentRowHeight = 0;

  const flushRow = () => {
    if (currentRow.length === 0) return;
    // If a row doesn't reach the full column count (the last widget in a row
    // is "medium" on a wide screen, or a row simply has too few widgets to
    // fill it), grow its widgets — each up to its own family's "large" width
    // — instead of leaving a dead gap on the right. This is what made the
    // dashboard look "not full-width" / "black bars" on large and ultra-wide
    // screens, independent of the xl/xxl breakpoint columns fix.
    let remainder = columns - currentWidth;
    if (remainder > 0) {
      const growable = currentRow.map((entry) => ({
        entry,
        room: Math.max(0, Math.min(entry.maxW, columns) - entry.w),
      }));
      while (remainder > 0 && growable.some((item) => item.room > 0)) {
        for (const item of growable) {
          if (remainder <= 0) break;
          if (item.room <= 0) continue;
          item.entry.w += 1;
          item.room -= 1;
          remainder -= 1;
        }
      }
    }
    let x = 0;
    for (const entry of currentRow) {
      const isLocked = locked.has(entry.id);
      // Real (non-degenerate) resize bounds: the widget can be dragged
      // between the widths/heights of its own allowed sizes, clamped to the
      // available columns, instead of being pinned to its current w/h.
      const minW = Math.min(entry.minW, columns);
      const maxW = Math.min(Math.max(entry.maxW, minW), columns);
      const minH = Math.min(entry.minH, entry.maxH);
      const maxH = Math.max(entry.maxH, minH);
      layout.push({
        i: entry.id,
        x,
        y,
        w: entry.w,
        h: entry.preferredHeight,
        minW,
        maxW,
        minH,
        maxH,
        static: isLocked,
        isDraggable: !isLocked,
        isResizable: !isLocked && entry.canResize,
      });
      x += entry.w;
    }
    y += currentRowHeight;
    currentRow = [];
    currentWidth = 0;
    currentRowHeight = 0;
  };

  for (const id of orderedIds) {
    const widget = byId.get(id);
    if (!widget) continue;
    const size = normalized.sizes[id] ?? "medium";
    const w = Math.min(widthForSize(size, columns), columns);
    const preferredHeight = heightForWidget(widget, size);
    const widthsForSizes = ["small", "medium", "large"].map((candidate) => (
      Math.min(widthForSize(candidate, columns), columns)
    ));
    const heightsForSizes = ["small", "medium", "large"].map((candidate) => (
      heightForWidget(widget, candidate)
    ));
    const minW = Math.min(...widthsForSizes);
    const maxW = Math.max(...widthsForSizes);
    const minH = Math.min(...heightsForSizes);
    const maxH = Math.max(...heightsForSizes);
    const canResize = minW !== maxW || minH !== maxH;

    if (currentRow.length > 0 && currentWidth + w > columns) {
      flushRow();
    }

    currentRow.push({ id, w, preferredHeight, minW, maxW, minH, maxH, canResize });
    currentWidth += w;
    currentRowHeight = Math.max(currentRowHeight, preferredHeight);

    if (currentWidth >= columns) {
      flushRow();
    }
  }

  flushRow();

  return layout;
}

export function composeResponsiveLauncherLayouts(state, widgets) {
  return Object.fromEntries(Object.entries(LAUNCHER_COLUMNS).map(([breakpoint, columns]) => [
    breakpoint,
    composeLauncherLayout({ state, widgets, columns }),
  ]));
}

export function breakpointForWidth(width) {
  if (width >= LAUNCHER_BREAKPOINTS.xxl) return "xxl";
  if (width >= LAUNCHER_BREAKPOINTS.xl) return "xl";
  if (width >= LAUNCHER_BREAKPOINTS.lg) return "lg";
  if (width >= LAUNCHER_BREAKPOINTS.md) return "md";
  return "sm";
}

export function deriveLauncherOrder(layout, previousOrder) {
  const visibleOrder = [...layout]
    .sort((left, right) => left.y - right.y || left.x - right.x || left.i.localeCompare(right.i))
    .map((item) => item.i);
  return unique([
    ...visibleOrder,
    ...previousOrder.filter((id) => !visibleOrder.includes(id)),
  ]);
}

function overlapArea(left, right) {
  const width = Math.max(0, Math.min(left.x + left.w, right.x + right.w) - Math.max(left.x, right.x));
  const height = Math.max(0, Math.min(left.y + left.h, right.y + right.h) - Math.max(left.y, right.y));
  return width * height;
}

function layoutDistance(left, right) {
  const leftCenterX = left.x + left.w / 2;
  const leftCenterY = left.y + left.h / 2;
  const rightCenterX = right.x + right.w / 2;
  const rightCenterY = right.y + right.h / 2;
  return Math.hypot(leftCenterX - rightCenterX, leftCenterY - rightCenterY);
}

export function swapLauncherOrder(layout, previousOrder, draggedId) {
  const dragged = layout.find((item) => item.i === draggedId);
  if (!dragged) return deriveLauncherOrder(layout, previousOrder);

  const target = layout
    .filter((item) => item.i !== draggedId && !item.static)
    .sort((left, right) => {
      const overlapDiff = overlapArea(right, dragged) - overlapArea(left, dragged);
      return overlapDiff || layoutDistance(dragged, left) - layoutDistance(dragged, right);
    })[0];
  if (!target) return previousOrder;

  const nextOrder = [...previousOrder];
  const draggedIndex = nextOrder.indexOf(draggedId);
  const targetIndex = nextOrder.indexOf(target.i);
  if (draggedIndex < 0 || targetIndex < 0 || draggedIndex === targetIndex) return nextOrder;
  [nextOrder[draggedIndex], nextOrder[targetIndex]] = [nextOrder[targetIndex], nextOrder[draggedIndex]];
  return nextOrder;
}

export function launcherLayoutsOverlap(layout) {
  return layout.some((item, index) => layout.slice(index + 1).some((other) => (
    item.x < other.x + other.w
    && item.x + item.w > other.x
    && item.y < other.y + other.h
    && item.y + item.h > other.y
  )));
}
