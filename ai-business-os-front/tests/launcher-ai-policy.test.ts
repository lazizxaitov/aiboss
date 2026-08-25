import assert from "node:assert/strict";
import test from "node:test";

import { createDefaultLauncherState } from "../lib/launcher/composer.js";
import {
  LAUNCHER_AI_PRIORITY,
  applyLauncherAIAction,
  applyPriority,
  normalizeLauncherAIAction,
  normalizeLauncherAIPriority,
  promoteWidget,
  demoteWidget,
} from "../lib/launcher/ai-policy.js";

function widget(id, type = "kpi", priority = 1, overrides = {}) {
  return {
    widget_id: id,
    widget_type: type,
    source_type: "PERMANENT",
    title: id,
    priority,
    pinned: false,
    locked_position: false,
    locked_size: false,
    hidden: false,
    semantic_size: "S",
    min_size: "S",
    preferred_size: "S",
    max_size: "M",
    content_density: "medium",
    scroll_behavior: "none",
    removable_by_ai: true,
    movable_by_ai: true,
    resizable_by_ai: true,
    drilldown: null,
    payload: {},
    ...overrides,
  };
}

const widgets = [
  widget("revenue", "kpi", 1),
  widget("orders", "kpi", 2),
  widget("trend", "trend", 3),
  widget("locked", "kpi", 4, { locked_position: true }),
  widget("pinned", "kpi", 5, { pinned: true }),
  widget("watchlist", "watchlist", 6),
];

function state(overrides = {}) {
  return {
    ...createDefaultLauncherState(widgets),
    ...overrides,
  };
}

test("AI action normalization strips physical geometry", () => {
  const action = normalizeLauncherAIAction({
    type: "resize",
    widgetId: "revenue",
    size: "medium",
    reason: "raise density",
    x: 99,
    y: 12,
    w: 20,
    h: 8,
  });

  assert.deepEqual(action, {
    type: "resize",
    widgetId: "revenue",
    size: "medium",
    reason: "raise density",
  });
});

test("AI priority normalizes to bounded semantic levels", () => {
  assert.equal(normalizeLauncherAIPriority(-1), LAUNCHER_AI_PRIORITY.NORMAL);
  assert.equal(normalizeLauncherAIPriority(0), LAUNCHER_AI_PRIORITY.NORMAL);
  assert.equal(normalizeLauncherAIPriority(1), LAUNCHER_AI_PRIORITY.ELEVATED);
  assert.equal(normalizeLauncherAIPriority(2), LAUNCHER_AI_PRIORITY.IMPORTANT);
  assert.equal(normalizeLauncherAIPriority(3), LAUNCHER_AI_PRIORITY.CRITICAL);
  assert.equal(normalizeLauncherAIPriority(10), LAUNCHER_AI_PRIORITY.CRITICAL);
});

test("promoteWidget moves a widget earlier without moving locked widgets", () => {
  const result = promoteWidget(state(), widgets, "watchlist", LAUNCHER_AI_PRIORITY.IMPORTANT);
  assert.equal(result.applied, true);
  assert.ok(result.state.order.indexOf("watchlist") < state().order.indexOf("watchlist"));
  assert.ok(result.state.order.includes("locked"));
});

test("demoteWidget respects pinned and locked widgets", () => {
  const pinnedResult = demoteWidget(state(), widgets, "pinned", LAUNCHER_AI_PRIORITY.CRITICAL);
  assert.equal(pinnedResult.applied, false);
  assert.deepEqual(pinnedResult.state.order, state().order);

  const lockedResult = demoteWidget(state(), widgets, "locked", LAUNCHER_AI_PRIORITY.IMPORTANT);
  assert.equal(lockedResult.applied, false);
  assert.deepEqual(lockedResult.state.order, state().order);
});

test("resize AI action respects contracts and user overrides", () => {
  const base = state({
    sizes: { revenue: "small", orders: "small", trend: "medium", locked: "small", pinned: "small", watchlist: "medium" },
    userOverrides: { size: ["watchlist"], order: false, hidden: [] },
  });

  const rejected = applyLauncherAIAction(base, widgets, {
    type: "resize",
    widgetId: "watchlist",
    size: "large",
    reason: "increase coverage",
  });
  assert.equal(rejected.applied, false);

  const limited = applyLauncherAIAction(base, widgets, {
    type: "resize",
    widgetId: "revenue",
    size: "medium",
    reason: "not allowed for KPI",
  });
  assert.equal(limited.applied, true);
  assert.equal(limited.state.sizes.revenue, "medium");

  const applied = applyLauncherAIAction(base, widgets, {
    type: "resize",
    widgetId: "trend",
    size: "large",
    reason: "expand chart",
  });
  assert.equal(applied.applied, true);
  assert.equal(applied.state.sizes.trend, "large");
  assert.deepEqual(applied.state.userOverrides.size, ["watchlist"]);
});

test("show does not override user-hidden widgets but may restore system-hidden ones", () => {
  const userHidden = state({
    hidden: ["watchlist"],
    userOverrides: { size: [], order: false, hidden: ["watchlist"] },
  });
  const blocked = applyLauncherAIAction(userHidden, widgets, {
    type: "show",
    widgetId: "watchlist",
    reason: "restore",
  });
  assert.equal(blocked.applied, false);
  assert.deepEqual(blocked.state.hidden, ["watchlist"]);

  const systemHidden = state({
    hidden: ["watchlist"],
    userOverrides: { size: [], order: false, hidden: [] },
  });
  const restored = applyLauncherAIAction(systemHidden, widgets, {
    type: "show",
    widgetId: "watchlist",
    reason: "restore",
  });
  assert.equal(restored.applied, true);
  assert.deepEqual(restored.state.hidden, []);
});

test("suggest_hide only produces a suggestion and keeps state intact", () => {
  const current = state();
  const result = applyLauncherAIAction(current, widgets, {
    type: "suggest_hide",
    widgetId: "trend",
    reason: "low engagement",
  });
  assert.equal(result.applied, false);
  assert.deepEqual(result.state.order, current.order);
  assert.deepEqual(result.suggestion, {
    type: "suggest_hide",
    widgetId: "trend",
    reason: "low engagement",
  });
});

test("applyPriority is a deterministic semantic helper", () => {
  const promoted = applyPriority(state(), widgets, "orders", LAUNCHER_AI_PRIORITY.ELEVATED, "promote");
  const demoted = applyPriority(state(), widgets, "orders", LAUNCHER_AI_PRIORITY.ELEVATED, "demote");
  assert.notDeepEqual(promoted.state.order, demoted.state.order);
  assert.ok(promoted.applied);
  assert.ok(demoted.applied);
});
