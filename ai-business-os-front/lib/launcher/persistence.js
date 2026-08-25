import {
  GRID_COLUMNS,
  LAUNCHER_STORAGE_KEY,
  LEGACY_STORAGE_KEYS,
  LAUNCHER_LAYOUT_VERSION,
  buildLayoutForCols,
  normalizeLayoutForBreakpoint,
} from "./layout-engine";

function isUserLayoutSnapshot(snapshot) {
  return (
    snapshot?.version === LAUNCHER_LAYOUT_VERSION &&
    snapshot?.kind === "user" &&
    Array.isArray(snapshot?.layout)
  );
}

export function readStoredLayouts() {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(LAUNCHER_STORAGE_KEY);
  if (raw) return { key: LAUNCHER_STORAGE_KEY, value: raw };
  for (const legacyKey of LEGACY_STORAGE_KEYS) {
    const legacy = window.localStorage.getItem(legacyKey);
    if (legacy) return { key: legacyKey, value: legacy };
  }
  return null;
}

export function loadLauncherLayouts(widgets) {
  if (typeof window === "undefined") return null;
  const stored = readStoredLayouts();
  if (!stored) return null;
  try {
    const parsed = JSON.parse(stored.value);
    let cols = Number(parsed?.cols ?? GRID_COLUMNS.lg);
    let layout = Array.isArray(parsed?.layout) ? parsed.layout : null;
    const isUserLayout = isUserLayoutSnapshot(parsed);

    if (!layout) {
      const responsiveLayouts = Array.isArray(parsed?.lg) || Array.isArray(parsed?.md) ? parsed : null;
      if (!responsiveLayouts) return null;
      const preferredLayout = Array.isArray(responsiveLayouts.lg)
        ? responsiveLayouts.lg
        : Object.values(responsiveLayouts).find((value) => Array.isArray(value) && value.length > 0) ?? [];
      layout = preferredLayout;
      cols = GRID_COLUMNS.lg;
    }

    if (!isUserLayout) {
      clearLauncherLayouts();
      return null;
    }

    const normalized = normalizeLayoutForBreakpoint(layout, widgets, Math.max(1, cols));
    const snapshot = {
      version: LAUNCHER_LAYOUT_VERSION,
      kind: "user",
      cols: Math.max(1, cols),
      layout: normalized,
    };

    if (stored.key !== LAUNCHER_STORAGE_KEY || parsed?.version !== LAUNCHER_LAYOUT_VERSION) {
      window.localStorage.setItem(LAUNCHER_STORAGE_KEY, JSON.stringify(snapshot));
    }
    return {
      version: LAUNCHER_LAYOUT_VERSION,
      kind: "user",
      cols: snapshot.cols,
      layout: snapshot.layout,
    };
  } catch {
    return null;
  }
}

export function saveLauncherLayouts(snapshot, options = {}) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(LAUNCHER_STORAGE_KEY, JSON.stringify({
    version: LAUNCHER_LAYOUT_VERSION,
    kind: options.kind ?? "user",
    cols: snapshot?.cols ?? GRID_COLUMNS.lg,
    layout: Array.isArray(snapshot?.layout) ? snapshot.layout : [],
  }));
}

export function clearLauncherLayouts() {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(LAUNCHER_STORAGE_KEY);
  for (const legacyKey of LEGACY_STORAGE_KEYS) {
    window.localStorage.removeItem(legacyKey);
  }
}

export function restoreDefaultLauncherLayouts(widgets, cols = GRID_COLUMNS.lg) {
  clearLauncherLayouts();
  return {
    version: LAUNCHER_LAYOUT_VERSION,
    kind: "system-default",
    cols,
    layout: buildLayoutForCols(widgets, cols),
  };
}
