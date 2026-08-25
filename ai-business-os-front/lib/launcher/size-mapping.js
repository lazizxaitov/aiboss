export const LAUNCHER_SIZE_PRESETS = {
  "1x1": { w: 1, h: 1 },
  "2x1": { w: 2, h: 1 },
  "2x2": { w: 2, h: 2 },
  "3x2": { w: 3, h: 2 },
  "4x2": { w: 4, h: 2 },
  "5x2": { w: 5, h: 2 },
  "4x3": { w: 4, h: 3 },
  "5x3": { w: 5, h: 3 },
  "6x2": { w: 6, h: 2 },
  "6x3": { w: 6, h: 3 },
  "8x4": { w: 8, h: 4 },
  "12x4": { w: 12, h: 4 },
  "12x5": { w: 12, h: 5 },
  "16x5": { w: 16, h: 5 },
  "20x5": { w: 20, h: 5 },
  "24x5": { w: 24, h: 5 },
  "28x5": { w: 28, h: 5 },
  "32x5": { w: 32, h: 5 },
};

export const SEMANTIC_TO_LAUNCHER_SIZE = {
  XS: "2x2",
  S: "3x2",
  M: "4x2",
  L: "6x3",
  XL: "8x4",
};

export function clampSize(size, cols) {
  const preset = LAUNCHER_SIZE_PRESETS[size] ?? LAUNCHER_SIZE_PRESETS["2x2"];
  const width = Math.max(1, Math.min(preset.w, cols));
  const height = Math.max(1, preset.h);
  return { w: width, h: height };
}

export function normalizeLauncherSize(size) {
  return LAUNCHER_SIZE_PRESETS[size] ? size : "2x2";
}

export function semanticSizeToLauncherSize(semanticSize) {
  return SEMANTIC_TO_LAUNCHER_SIZE[semanticSize] ?? "3x2";
}

export function launcherSizeToSemanticSize(size) {
  const preset = LAUNCHER_SIZE_PRESETS[size] ?? LAUNCHER_SIZE_PRESETS["2x2"];
  if (preset.w <= 3) return "small";
  if (preset.w <= 6) return "medium";
  return "large";
}

export function launcherSemanticSizeOptions(allowedSizes) {
  return Array.from(
    new Set((allowedSizes ?? []).map((size) => launcherSizeToSemanticSize(size))),
  );
}

export function getLauncherVariantFromGrid(width, height) {
  if (width <= 2 && height <= 2) return "compact";
  if (width <= 4 && height <= 3) return "regular";
  if (width <= 6 && height <= 4) return "expanded";
  return "xl";
}
