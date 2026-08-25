import assert from "node:assert/strict";
import test from "node:test";

import {
  composeLauncherLayout,
  composeResponsiveLauncherLayouts,
  createDefaultLauncherState,
  breakpointForWidth,
  deriveLauncherOrder,
  launcherLayoutsOverlap,
  normalizeLauncherState,
} from "../lib/launcher/composer.js";
import { launcherSemanticSizeOptions } from "../lib/launcher/size-mapping.js";
import {
  LAUNCHER_STATE_STORAGE_KEY,
  loadLauncherState,
  saveLauncherState,
} from "../lib/launcher/state-persistence.js";
import { getWidgetSizeContract } from "../lib/launcher/widget-registry.js";

function widget(id: string, type = "kpi", priority = 1) {
  return {
    widget_id: id,
    widget_type: type,
    title: id,
    priority,
    pinned: false,
    locked_position: false,
  };
}

function compose(sizes: Record<string, "small" | "medium" | "large">) {
  const widgets = Object.keys(sizes).map((id, index) => widget(id, "kpi", index));
  const state = { order: Object.keys(sizes), sizes };
  return composeLauncherLayout({ state, widgets, columns: 12 });
}

function composeWidgets(items: Array<{ id: string; type: string; size: "small" | "medium" | "large"; priority?: number }>) {
  const widgets = items.map((item, index) => widget(item.id, item.type, item.priority ?? index));
  const state = {
    order: items.map((item) => item.id),
    sizes: Object.fromEntries(items.map((item) => [item.id, item.size])),
  };
  return composeLauncherLayout({ state, widgets, columns: 12 });
}

test("12 columns pack four small widgets into one complete row", () => {
  const layout = compose({ a: "small", b: "small", c: "small", d: "small" });
  assert.deepEqual(layout.map(({ x, y, w }) => ({ x, y, w })), [
    { x: 0, y: 0, w: 3 },
    { x: 3, y: 0, w: 3 },
    { x: 6, y: 0, w: 3 },
    { x: 9, y: 0, w: 3 },
  ]);
});

test("row normalization gives widgets in the same row the same y and row height", () => {
  const layout = composeWidgets([
    { id: "a", type: "alert", size: "medium", priority: 1 },
    { id: "b", type: "visit_summary", size: "medium", priority: 2 },
  ]);

  assert.deepEqual(
    layout.map(({ i, x, y, w, h }) => ({ i, x, y, w, h })),
    [
      { i: "a", x: 0, y: 0, w: 6, h: 4 },
      { i: "b", x: 6, y: 0, w: 6, h: 4 },
    ],
  );
});

test("next row starts only after the previous row height finishes", () => {
  const layout = composeWidgets([
    { id: "lead", type: "alert", size: "medium", priority: 1 },
    { id: "summary", type: "visit_summary", size: "medium", priority: 2 },
    { id: "revenue", type: "kpi", size: "small", priority: 3 },
  ]);

  const lead = layout.find((item) => item.i === "lead");
  const summary = layout.find((item) => item.i === "summary");
  const revenue = layout.find((item) => item.i === "revenue");

  assert.equal(lead?.h, 4);
  assert.equal(summary?.h, 4);
  assert.equal(lead?.y, 0);
  assert.equal(summary?.y, 0);
  assert.equal(revenue?.y, 4);
});

test("large widgets occupy a full row and push the next row downward", () => {
  const layout = composeWidgets([
    { id: "hero", type: "trend", size: "large", priority: 1 },
    { id: "a", type: "kpi", size: "small", priority: 2 },
    { id: "b", type: "kpi", size: "small", priority: 3 },
    { id: "c", type: "kpi", size: "small", priority: 4 },
    { id: "d", type: "kpi", size: "small", priority: 5 },
  ]);

  const hero = layout.find((item) => item.i === "hero");
  const smalls = ["a", "b", "c", "d"].map((id) => layout.find((item) => item.i === id));

  assert.deepEqual(
    smalls.map((item) => ({ x: item?.x, y: item?.y, w: item?.w, h: item?.h })),
    [
      { x: 0, y: hero?.h, w: 3, h: 2 },
      { x: 3, y: hero?.h, w: 3, h: 2 },
      { x: 6, y: hero?.h, w: 3, h: 2 },
      { x: 9, y: hero?.h, w: 3, h: 2 },
    ],
  );
  assert.equal(hero?.w, 12);
  assert.equal(hero?.y, 0);
});

test("composer is deterministic, overlap-free, and emits each widget once", () => {
  const widgets = [widget("a"), widget("b"), widget("c", "trend"), widget("d", "table")];
  const state = normalizeLauncherState({
    order: ["a", "b", "a", "missing"],
    sizes: { a: "small", b: "small", c: "medium", d: "large" },
  }, widgets);
  const first = composeLauncherLayout({ state, widgets, columns: 12 });
  const second = composeLauncherLayout({ state, widgets, columns: 12 });
  assert.deepEqual(first, second);
  assert.equal(launcherLayoutsOverlap(first), false);
  assert.deepEqual(new Set(first.map((item) => item.i)), new Set(["a", "b", "c", "d"]));
  assert.equal(first.length, 4);
});

test("drag result changes semantic order and recomposes predictably", () => {
  const previous = ["a", "b", "c", "d"];
  const dropped = [
    { i: "a", x: 0, y: 0, w: 3, h: 2 },
    { i: "d", x: 3, y: 0, w: 3, h: 2 },
    { i: "b", x: 6, y: 0, w: 3, h: 2 },
    { i: "c", x: 9, y: 0, w: 3, h: 2 },
  ];
  assert.deepEqual(deriveLauncherOrder(dropped, previous), ["a", "d", "b", "c"]);
});

test("responsive composition is regenerated independently for 12, 8, and 4 columns", () => {
  const widgets = [widget("a"), widget("b"), widget("c"), widget("d")];
  const state = createDefaultLauncherState(widgets);
  const layouts = composeResponsiveLauncherLayouts(state, widgets);
  assert.deepEqual(layouts.lg.map((item) => item.w), [3, 3, 3, 3]);
  assert.deepEqual(layouts.md.map((item) => item.w), [4, 4, 4, 4]);
  assert.deepEqual(layouts.sm.map((item) => item.w), [4, 4, 4, 4]);
  assert.equal(launcherLayoutsOverlap(layouts.lg), false);
  assert.equal(launcherLayoutsOverlap(layouts.md), false);
  assert.equal(launcherLayoutsOverlap(layouts.sm), false);
});

test("desktop breakpoint switches to lg at 1024px", () => {
  assert.equal(breakpointForWidth(1023), "md");
  assert.equal(breakpointForWidth(1024), "lg");
});

test("launcher persistence stores semantic state without generated geometry", () => {
  const storage: Record<string, string> = {};
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: {
      localStorage: {
        getItem: (key: string) => storage[key] ?? null,
        setItem: (key: string, value: string) => { storage[key] = value; },
        removeItem: (key: string) => { delete storage[key]; },
      },
    },
  });

  saveLauncherState({ order: ["a"], sizes: { a: "small" }, pinned: [], locked: [], hidden: ["b"] });
  const raw = storage[LAUNCHER_STATE_STORAGE_KEY];
  assert.ok(raw);
  assert.equal(/"[xywh]":/.test(raw), false);
  assert.deepEqual(loadLauncherState(), {
    version: "v1",
    order: ["a"],
    sizes: { a: "small" },
    pinned: [],
    locked: [],
    hidden: ["b"],
    userOverrides: {
      size: [],
      order: false,
      hidden: [],
    },
  });
  delete (globalThis as { window?: unknown }).window;
});

test("hidden widgets are excluded before composer rows are built", () => {
  const widgets = [widget("a"), widget("b"), widget("c")];
  const state = normalizeLauncherState({
    order: ["a", "b", "c"],
    sizes: { a: "small", b: "small", c: "small" },
    hidden: ["b"],
  }, widgets);

  const layout = composeLauncherLayout({ state, widgets, columns: 12 });
  assert.deepEqual(layout.map((item) => item.i), ["a", "c"]);
});

test("allowed semantic size options come from the widget contract", () => {
  const kpi = widget("kpi", "kpi");
  const table = widget("table", "organization_comparison");
  const alert = widget("alert", "inventory_risk");

  assert.deepEqual(launcherSemanticSizeOptions(["3x2"]), ["small"]);
  assert.deepEqual(launcherSemanticSizeOptions(["6x3", "12x4", "12x5"]), ["medium", "large"]);
  assert.deepEqual(launcherSemanticSizeOptions(["12x4"]), ["large"]);
  assert.deepEqual(launcherSemanticSizeOptions(getWidgetSizeContract(kpi).allowedSizes), ["small", "medium"]);
  assert.deepEqual(launcherSemanticSizeOptions(getWidgetSizeContract(table).allowedSizes), ["medium", "large"]);
  assert.deepEqual(launcherSemanticSizeOptions(getWidgetSizeContract(alert).allowedSizes), ["medium", "large"]);
});

test("new launcher restoration ignores obsolete physical layout keys", () => {
  const storage: Record<string, string> = {
    "ai-business-os:launcher-layout:v16": JSON.stringify({
      cols: 24,
      layout: [{ i: "a", x: 0, y: 0, w: 4, h: 2 }],
    }),
  };
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: {
      localStorage: {
        getItem: (key: string) => storage[key] ?? null,
        setItem: (key: string, value: string) => { storage[key] = value; },
        removeItem: (key: string) => { delete storage[key]; },
      },
    },
  });

  assert.equal(loadLauncherState(), null);
  delete (globalThis as { window?: unknown }).window;
});
