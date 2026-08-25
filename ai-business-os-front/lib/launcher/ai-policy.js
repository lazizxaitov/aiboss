import { normalizeLauncherState } from "./composer";
import { launcherSemanticSizeOptions } from "./size-mapping";
import { getWidgetSizeContract } from "./widget-registry";

export const LAUNCHER_AI_PRIORITY = Object.freeze({
  NORMAL: 0,
  ELEVATED: 1,
  IMPORTANT: 2,
  CRITICAL: 3,
});

const VALID_SEMANTIC_SIZES = new Set(["small", "medium", "large"]);

function cloneState(state) {
  return {
    ...state,
    order: Array.isArray(state?.order) ? [...state.order] : [],
    sizes: state?.sizes && typeof state.sizes === "object" ? { ...state.sizes } : {},
    pinned: Array.isArray(state?.pinned) ? [...state.pinned] : [],
    locked: Array.isArray(state?.locked) ? [...state.locked] : [],
    hidden: Array.isArray(state?.hidden) ? [...state.hidden] : [],
    userOverrides: {
      size: Array.isArray(state?.userOverrides?.size) ? [...state.userOverrides.size] : [],
      order: Boolean(state?.userOverrides?.order),
      hidden: Array.isArray(state?.userOverrides?.hidden) ? [...state.userOverrides.hidden] : [],
    },
  };
}

function unique(values) {
  return Array.from(new Set(values));
}

export function normalizeLauncherAIPriority(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return LAUNCHER_AI_PRIORITY.NORMAL;
  if (numeric >= LAUNCHER_AI_PRIORITY.CRITICAL) return LAUNCHER_AI_PRIORITY.CRITICAL;
  if (numeric >= LAUNCHER_AI_PRIORITY.IMPORTANT) return LAUNCHER_AI_PRIORITY.IMPORTANT;
  if (numeric >= LAUNCHER_AI_PRIORITY.ELEVATED) return LAUNCHER_AI_PRIORITY.ELEVATED;
  return LAUNCHER_AI_PRIORITY.NORMAL;
}

export function normalizeLauncherAIAction(action) {
  if (!action || typeof action !== "object") return null;
  const type = typeof action.type === "string" ? action.type : null;
  const widgetId = typeof action.widgetId === "string" ? action.widgetId.trim() : "";
  const reason = typeof action.reason === "string" ? action.reason.trim() : "";
  const priority = "priority" in action ? normalizeLauncherAIPriority(action.priority) : undefined;
  if (!type || !widgetId || !reason) return null;
  if (!["promote", "demote", "resize", "show", "suggest_hide"].includes(type)) return null;
  const normalized = { type, widgetId, reason };
  if (priority !== undefined) normalized.priority = priority;
  if (type === "resize") {
    const size = typeof action.size === "string" ? action.size.trim() : "";
    if (!VALID_SEMANTIC_SIZES.has(size)) return null;
    normalized.size = size;
  }
  return normalized;
}

function movableOrder(state, lockedIds) {
  return (state.order ?? []).filter((id) => !lockedIds.has(id));
}

function rebuildOrder(state, widgets, nextMovableOrder) {
  const lockedIds = new Set(state.locked ?? []);
  const lockedPositions = new Map();
  for (const [index, id] of (state.order ?? []).entries()) {
    if (lockedIds.has(id)) lockedPositions.set(index, id);
  }

  const nextOrder = [];
  let movableIndex = 0;
  const orderedIds = unique((state.order ?? []).filter((id) => !lockedIds.has(id)));
  const movableSet = new Set(orderedIds);
  const filteredMovable = nextMovableOrder.filter((id) => movableSet.has(id));

  for (let index = 0; index < (state.order ?? []).length; index += 1) {
    if (lockedPositions.has(index)) {
      nextOrder.push(lockedPositions.get(index));
      continue;
    }
    nextOrder.push(filteredMovable[movableIndex] ?? orderedIds[movableIndex] ?? null);
    movableIndex += 1;
  }

  return normalizeLauncherState({
    ...state,
    order: nextOrder.filter((id) => typeof id === "string"),
  }, widgets);
}

function shiftOrder(state, widgets, widgetId, steps, direction) {
  const lockedIds = new Set(state.locked ?? []);
  if (lockedIds.has(widgetId)) {
    return { state, applied: false, reason: "locked_widget" };
  }

  const currentOrder = movableOrder(state, lockedIds);
  const currentIndex = currentOrder.indexOf(widgetId);
  if (currentIndex < 0) return { state, applied: false, reason: "widget_not_found" };

  const offset = Math.max(1, Math.min(3, steps));
  const targetIndex = direction === "promote"
    ? Math.max(0, currentIndex - offset)
    : Math.min(currentOrder.length - 1, currentIndex + offset);

  if (targetIndex === currentIndex) return { state, applied: false, reason: "no_change" };

  const nextMovable = [...currentOrder];
  nextMovable.splice(currentIndex, 1);
  nextMovable.splice(targetIndex, 0, widgetId);
  return {
    state: rebuildOrder(state, widgets, nextMovable),
    applied: true,
    reason: direction,
  };
}

export function promoteWidget(state, widgets, widgetId, priority = LAUNCHER_AI_PRIORITY.ELEVATED) {
  const normalized = normalizeLauncherAIPriority(priority);
  const steps = normalized === LAUNCHER_AI_PRIORITY.NORMAL ? 1 : normalized;
  return shiftOrder(cloneState(state), widgets, widgetId, steps, "promote");
}

export function demoteWidget(state, widgets, widgetId, priority = LAUNCHER_AI_PRIORITY.ELEVATED) {
  const lockedIds = new Set(state?.locked ?? []);
  if (lockedIds.has(widgetId) || (state?.pinned ?? []).includes(widgetId)) {
    return { state: cloneState(state), applied: false, reason: "protected_widget" };
  }
  const normalized = normalizeLauncherAIPriority(priority);
  const steps = normalized === LAUNCHER_AI_PRIORITY.NORMAL ? 1 : normalized;
  return shiftOrder(cloneState(state), widgets, widgetId, steps, "demote");
}

export function applyPriority(state, widgets, widgetId, priority, direction = "promote") {
  return direction === "demote"
    ? demoteWidget(state, widgets, widgetId, priority)
    : promoteWidget(state, widgets, widgetId, priority);
}

function findWidgetContract(widget) {
  const contract = getWidgetSizeContract(widget);
  return {
    ...contract,
    allowedSizes: launcherSemanticSizeOptions(contract.allowedSizes),
  };
}

export function applyLauncherAIAction(state, widgets, action) {
  const normalizedAction = normalizeLauncherAIAction(action);
  if (!normalizedAction) {
    return { state: cloneState(state), applied: false, reason: "invalid_action" };
  }

  const widget = widgets.find((item) => item.widget_id === normalizedAction.widgetId);
  if (!widget) {
    return { state: cloneState(state), applied: false, reason: "widget_not_found" };
  }

  const userOverrides = cloneState(state).userOverrides ?? { size: [], order: false, hidden: [] };
  const hiddenSet = new Set(state?.hidden ?? []);
  const userHiddenSet = new Set(userOverrides.hidden ?? []);
  const sizeOverrides = new Set(userOverrides.size ?? []);
  const lockedSet = new Set(state?.locked ?? []);

  switch (normalizedAction.type) {
    case "promote":
      return promoteWidget(state, widgets, normalizedAction.widgetId, normalizedAction.priority);
    case "demote":
      return demoteWidget(state, widgets, normalizedAction.widgetId, normalizedAction.priority);
    case "resize": {
      if (lockedSet.has(normalizedAction.widgetId)) {
        return { state: cloneState(state), applied: false, reason: "protected_widget" };
      }
      if (sizeOverrides.has(normalizedAction.widgetId)) {
        return { state: cloneState(state), applied: false, reason: "user_size_override" };
      }
      const contract = findWidgetContract(widget);
      if (!contract.allowedSizes.includes(normalizedAction.size)) {
        return { state: cloneState(state), applied: false, reason: "unsupported_size" };
      }
      return {
        state: normalizeLauncherState({
          ...cloneState(state),
          sizes: {
            ...(state?.sizes ?? {}),
            [normalizedAction.widgetId]: normalizedAction.size,
          },
        }, widgets),
        applied: true,
        reason: "resize",
      };
    }
    case "show":
      if (userHiddenSet.has(normalizedAction.widgetId)) {
        return { state: cloneState(state), applied: false, reason: "user_hidden" };
      }
      if (!hiddenSet.has(normalizedAction.widgetId)) {
        return { state: cloneState(state), applied: false, reason: "already_visible" };
      }
      hiddenSet.delete(normalizedAction.widgetId);
      return {
        state: normalizeLauncherState({
          ...cloneState(state),
          hidden: Array.from(hiddenSet),
        }, widgets),
        applied: true,
        reason: "show",
      };
    case "suggest_hide":
      return {
        state: cloneState(state),
        applied: false,
        reason: "suggest_hide",
        suggestion: {
          type: "suggest_hide",
          widgetId: normalizedAction.widgetId,
          reason: normalizedAction.reason,
        },
      };
    default:
      return { state: cloneState(state), applied: false, reason: "unsupported_action" };
  }
}
