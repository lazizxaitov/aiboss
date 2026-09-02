import { getWidgetFamily } from "./widget-registry";

export const LAUNCHER_BREAKPOINTS = Object.freeze({ lg: 1024, md: 768, sm: 0 });
export const LAUNCHER_COLUMNS = Object.freeze({ lg: 12, md: 8, sm: 4 });

const VALID_SIZES = new Set(["small", "medium", "large"]);

const FAMILY_HEIGHTS = Object.freeze({
  kpi: 2,
  alert: 3,
  wide: 5,
  detail: 5,
  summary: 4,
  chart: 5,
  list: 5,
  table: 5,
});

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
  if (columns <= 4) return columns;
  if (columns <= 8) return size === "large" ? columns : 4;
  if (size === "small") return 3;
  if (size === "medium") return 6;
  return columns;
}

function heightForWidget(widget) {
  return FAMILY_HEIGHTS[getWidgetFamily(widget)] ?? 4;
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
    let x = 0;
    for (const entry of currentRow) {
      layout.push({
        i: entry.id,
        x,
        y,
        w: entry.w,
        h: entry.preferredHeight,
        minW: entry.w,
        maxW: entry.w,
        minH: entry.preferredHeight,
        maxH: entry.preferredHeight,
        static: locked.has(entry.id),
        isDraggable: !locked.has(entry.id),
        isResizable: false,
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
    const w = Math.min(widthForSize(normalized.sizes[id] ?? "medium", columns), columns);
    const preferredHeight = heightForWidget(widget);

    if (currentRow.length > 0 && currentWidth + w > columns) {
      flushRow();
    }

    currentRow.push({ id, w, preferredHeight });
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
