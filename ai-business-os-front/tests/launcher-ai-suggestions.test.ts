import assert from "node:assert/strict";
import test from "node:test";

import { createDefaultLauncherState } from "../lib/launcher/composer.js";
import {
  applyLauncherSuggestion,
  createDevelopmentLauncherSuggestions,
  dismissLauncherSuggestion,
  evaluateLauncherSuggestion,
} from "../lib/launcher/ai-suggestions.ts";
import {
  getLauncherAIActionLabel,
  getLauncherAIRejectionMessage,
  getLauncherAIPriorityLabel,
  getLauncherAISuggestionStatusMessage,
} from "../lib/launcher/ai-presentation.ts";
import type { LauncherSuggestion } from "../lib/launcher/types.ts";

function widget(id: string, type = "kpi", priority = 1, overrides = {}) {
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
  widget("inventory-risk", "inventory_risk", 2),
  widget("executive-brief", "ai_insight", 3),
  widget("comparison", "organization_comparison", 4),
  widget("quality", "data_quality", 5),
  widget("watchlist", "watchlist", 6, { hidden: true }),
];

function baseState() {
  const state = createDefaultLauncherState(widgets);
  return {
    ...state,
    hidden: ["watchlist"],
    userOverrides: {
      size: [],
      order: false,
      hidden: ["watchlist"],
    },
  };
}

test("suggestion presentation maps action and rejection labels to Russian", () => {
  assert.equal(getLauncherAIActionLabel({ type: "promote", widgetId: "revenue", reason: "важно" }), "Поднять выше");
  assert.equal(getLauncherAIActionLabel({ type: "suggest_hide", widgetId: "watchlist", reason: "проверка" }), "Предложить скрыть");
  assert.equal(getLauncherAIPriorityLabel(3), "Критический");
  assert.equal(getLauncherAIRejectionMessage("locked_widget"), "Виджет закреплён вами.");
  assert.equal(getLauncherAIPriorityLabel(1), "Средний");
  assert.equal(getLauncherAISuggestionStatusMessage(1, 1), "Часть изменений применена.");
});

test("development suggestions are disabled in production", () => {
  const previous = process.env.NODE_ENV;
  try {
    process.env.NODE_ENV = "production";
    assert.deepEqual(createDevelopmentLauncherSuggestions(widgets, baseState()), []);
  } finally {
    process.env.NODE_ENV = previous;
  }
});

test("development suggestions are available outside production", () => {
  const previous = process.env.NODE_ENV;
  let suggestions: LauncherSuggestion[] = [];
  try {
    process.env.NODE_ENV = "test";
    suggestions = createDevelopmentLauncherSuggestions(widgets, baseState());
  } finally {
    process.env.NODE_ENV = previous;
  }

  assert.ok(suggestions);
  assert.ok(suggestions.length > 0);
  assert.ok(suggestions.every((suggestion) => !("x" in suggestion) && !("y" in suggestion) && !("w" in suggestion) && !("h" in suggestion)));
});

test("preview uses dry-run and does not mutate launcher state", () => {
  const state = baseState();
  const suggestion = createDevelopmentLauncherSuggestions(widgets, state).find((item) =>
    item.actions.some((action) => action.type === "resize" || action.type === "promote"),
  );
  assert.ok(suggestion);

  const before = JSON.parse(JSON.stringify(state));
  const preview = evaluateLauncherSuggestion(state, widgets, suggestion);

  assert.deepEqual(state, before);
  assert.ok(preview.previewState.order.length > 0);
  assert.equal(Object.keys(preview.previewState).some((key) => ["x", "y", "w", "h"].includes(key)), false);
});

test("apply revalidates against the current state and preserves preview isolation", () => {
  const state = baseState();
  const suggestion = {
    id: "manual-inventory-risk",
    title: "Риски склада требуют внимания",
    summary: "Демо-подсказка для проверки частичного применения.",
    reason: "10 товаров требуют внимания",
    priority: 3 as const,
    actions: [
      { type: "resize", widgetId: "inventory-risk", size: "large" as const, reason: "Показать блок рисков крупнее" },
      { type: "suggest_hide", widgetId: "inventory-risk", reason: "Проверка скрытия" },
    ],
  };

  const initialPreview = evaluateLauncherSuggestion(state, widgets, suggestion);
  assert.ok(initialPreview.appliedActions >= 1);
  assert.ok(initialPreview.rejectedActions >= 1);

  const overriddenState = {
    ...state,
    userOverrides: {
      size: ["inventory-risk"],
      order: false,
      hidden: ["watchlist"],
    },
  };

  const reapplied = applyLauncherSuggestion(overriddenState, widgets, suggestion);
  assert.equal(reapplied.appliedActions, 0);
  assert.equal(reapplied.rejectedActions, 2);
  assert.equal(reapplied.actions[0].message, "Размер виджета выбран вами вручную.");
  assert.equal(reapplied.actions[1].message, "ИИ предлагает скрыть этот виджет без немедленных изменений.");
  assert.deepEqual(overriddenState, {
    ...state,
    userOverrides: {
      size: ["inventory-risk"],
      order: false,
      hidden: ["watchlist"],
    },
  });
});

test("dismiss only filters suggestion queue and leaves launcher state untouched", () => {
  const state = baseState();
  const suggestions = createDevelopmentLauncherSuggestions(widgets, state);
  const dismissed = dismissLauncherSuggestion(suggestions, suggestions[0].id);

  assert.equal(dismissed.length, suggestions.length - 1);
  assert.deepEqual(state.hidden, ["watchlist"]);
});
