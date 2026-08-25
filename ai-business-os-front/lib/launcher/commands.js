import { GRID_COLUMNS, normalizeLauncherLayouts, buildDefaultLayouts } from "./layout-engine";
import { LAUNCHER_SIZE_PRESETS, normalizeLauncherSize } from "./size-mapping";

function withBreakpoint(layouts, breakpoint, updater) {
  const next = { ...layouts };
  next[breakpoint] = updater([...(layouts?.[breakpoint] ?? [])]);
  return next;
}

export function findItem(items, widgetId) {
  return items.find((item) => item.i === widgetId) ?? null;
}

function updateItemSize(item, size) {
  const normalized = normalizeLauncherSize(size);
  const preset = LAUNCHER_SIZE_PRESETS[normalized] ?? LAUNCHER_SIZE_PRESETS["2x2"];
  return {
    ...item,
    w: preset.w,
    h: preset.h,
    launcherSize: normalized,
  };
}

export function moveWidget(layouts, widgetId, targetPosition, breakpoint = "lg") {
  return withBreakpoint(layouts, breakpoint, (items) =>
    items.map((item) => (item.i === widgetId ? { ...item, x: targetPosition.x, y: targetPosition.y } : item)),
  );
}

export function resizeWidget(layouts, widgetId, size, breakpoint = "lg") {
  return withBreakpoint(layouts, breakpoint, (items) =>
    items.map((item) => (item.i === widgetId ? updateItemSize(item, size) : item)),
  );
}

export function promoteWidget(layouts, widgetId) {
  const next = {};
  for (const [breakpoint, items] of Object.entries(layouts)) {
    next[breakpoint] = [...items].map((item) => (item.i === widgetId ? { ...item, y: 0 } : item));
  }
  return next;
}

export function minimizeWidget(layouts, widgetId) {
  return resizeWidget(layouts, widgetId, "2x2");
}

export function restoreWidget(layouts, widgetId, fallbackSize = "3x2") {
  return resizeWidget(layouts, widgetId, fallbackSize);
}

export function lockPosition(layouts, widgetId) {
  const next = {};
  for (const [breakpoint, items] of Object.entries(layouts)) {
    next[breakpoint] = items.map((item) => (item.i === widgetId ? { ...item, lockedPosition: true, isDraggable: false, static: item.lockedSize === true } : item));
  }
  return next;
}

export function unlockPosition(layouts, widgetId) {
  const next = {};
  for (const [breakpoint, items] of Object.entries(layouts)) {
    next[breakpoint] = items.map((item) => (item.i === widgetId ? { ...item, lockedPosition: false, isDraggable: true, static: item.lockedSize === true && item.static === true ? false : item.static } : item));
  }
  return next;
}

export function lockSize(layouts, widgetId) {
  const next = {};
  for (const [breakpoint, items] of Object.entries(layouts)) {
    next[breakpoint] = items.map((item) => (item.i === widgetId ? { ...item, lockedSize: true, isResizable: false, static: item.lockedPosition === true } : item));
  }
  return next;
}

export function unlockSize(layouts, widgetId) {
  const next = {};
  for (const [breakpoint, items] of Object.entries(layouts)) {
    next[breakpoint] = items.map((item) => (item.i === widgetId ? { ...item, lockedSize: false, isResizable: true, static: item.lockedPosition === true && item.static === true ? false : item.static } : item));
  }
  return next;
}

export function resetLayout(widgets) {
  return buildDefaultLayouts(widgets);
}

export function applyLayout(layout) {
  return layout;
}

export function normalizeLayout(layouts, widgets) {
  return normalizeLauncherLayouts(layouts, widgets, GRID_COLUMNS);
}

export function applyLauncherCommand(layouts, command, widgets = []) {
  switch (command.type) {
    case "moveWidget":
      return moveWidget(layouts, command.widgetId, { x: command.x, y: command.y }, command.breakpoint);
    case "resizeWidget":
      return resizeWidget(layouts, command.widgetId, command.size, command.breakpoint);
    case "promoteWidget":
      return promoteWidget(layouts, command.widgetId);
    case "minimizeWidget":
      return minimizeWidget(layouts, command.widgetId);
    case "restoreWidget":
      return restoreWidget(layouts, command.widgetId);
    case "lockPosition":
      return lockPosition(layouts, command.widgetId);
    case "unlockPosition":
      return unlockPosition(layouts, command.widgetId);
    case "lockSize":
      return lockSize(layouts, command.widgetId);
    case "unlockSize":
      return unlockSize(layouts, command.widgetId);
    case "resetLayout":
      return resetLayout(widgets);
    case "applyLayout":
      return applyLayout(command.layout);
    case "normalizeLayout":
      return normalizeLayout(command.layout, widgets);
    default:
      return layouts;
  }
}
