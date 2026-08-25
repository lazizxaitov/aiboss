export const LAUNCHER_STATE_STORAGE_KEY = "ai-business-os:launcher-state:v1";

function serializedState(state) {
  const userOverrides = state?.userOverrides && typeof state.userOverrides === "object"
    ? state.userOverrides
    : { size: [], order: false, hidden: [] };
  return {
    version: "v1",
    order: Array.isArray(state?.order) ? state.order : [],
    sizes: state?.sizes && typeof state.sizes === "object" ? state.sizes : {},
    pinned: Array.isArray(state?.pinned) ? state.pinned : [],
    locked: Array.isArray(state?.locked) ? state.locked : [],
    hidden: Array.isArray(state?.hidden) ? state.hidden : [],
    userOverrides: {
      size: Array.isArray(userOverrides.size) ? userOverrides.size : [],
      order: Boolean(userOverrides.order),
      hidden: Array.isArray(userOverrides.hidden) ? userOverrides.hidden : [],
    },
  };
}

export function loadLauncherState() {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(LAUNCHER_STATE_STORAGE_KEY);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw);
    if (parsed?.version !== "v1") return null;
    return serializedState(parsed);
  } catch {
    return null;
  }
}

export function saveLauncherState(state) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(LAUNCHER_STATE_STORAGE_KEY, JSON.stringify(serializedState(state)));
}

export function clearLauncherState() {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(LAUNCHER_STATE_STORAGE_KEY);
}
