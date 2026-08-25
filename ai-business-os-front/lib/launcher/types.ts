import type {
  DashboardContentDensity,
  DashboardDrilldown,
  DashboardManifestWidget,
  DashboardScrollBehavior,
  DashboardSemanticSize,
  DashboardWidgetSourceType,
  DashboardWidgetType,
} from "@/lib/core-api";

export type LauncherLayoutMode = "manual" | "assisted" | "ai";

export type LauncherBreakpoint = "lg" | "md" | "sm" | "xs" | "xxs";

export type LauncherSize = "1x1" | "2x1" | "2x2" | "3x2" | "4x2" | "4x3" | "6x2" | "6x3" | "8x4" | "12x4";

export type LauncherWidgetVariant = "compact" | "regular" | "expanded" | "xl";

export type LauncherSemanticSize = "small" | "medium" | "large";

export type LauncherUserOverrides = {
  size: string[];
  order: boolean;
  hidden: string[];
};

export type LauncherState = {
  order: string[];
  sizes: Record<string, LauncherSemanticSize>;
  pinned?: string[];
  locked?: string[];
  hidden?: string[];
  userOverrides?: LauncherUserOverrides;
};

export type LauncherWidgetDefinition = {
  widget_id: string;
  widget_type: DashboardWidgetType;
  title: string;
  source_type: DashboardWidgetSourceType;
  allowedSizes: LauncherSize[];
  defaultSize: LauncherSize;
  minSize: LauncherSize;
  maxSize: LauncherSize;
  priority: number;
  lockedPosition: boolean;
  lockedSize: boolean;
  contentDensity: DashboardContentDensity;
  scrollBehavior: DashboardScrollBehavior;
  semanticSize: DashboardSemanticSize;
  drilldown: DashboardDrilldown | null;
  supportsAIPlacement: boolean;
};

export type LauncherLayoutItem = {
  i: string;
  x: number;
  y: number;
  w: number;
  h: number;
  minW?: number;
  minH?: number;
  maxW?: number;
  maxH?: number;
  static?: boolean;
  isDraggable?: boolean;
  isResizable?: boolean;
  lockedPosition?: boolean;
  lockedSize?: boolean;
  launcherSize?: LauncherSize;
  launcherVariant?: LauncherWidgetVariant;
  priority?: number;
  widgetType?: DashboardWidgetType;
};

export type LauncherLayout = Record<LauncherBreakpoint, LauncherLayoutItem[]>;

export type LauncherCommand =
  | { type: "moveWidget"; widgetId: string; x: number; y: number; breakpoint?: LauncherBreakpoint }
  | { type: "resizeWidget"; widgetId: string; size: LauncherSize; breakpoint?: LauncherBreakpoint }
  | { type: "promoteWidget"; widgetId: string }
  | { type: "minimizeWidget"; widgetId: string }
  | { type: "restoreWidget"; widgetId: string }
  | { type: "lockPosition"; widgetId: string }
  | { type: "unlockPosition"; widgetId: string }
  | { type: "lockSize"; widgetId: string }
  | { type: "unlockSize"; widgetId: string }
  | { type: "resetLayout" }
  | { type: "applyLayout"; layout: LauncherLayout }
  | { type: "normalizeLayout"; layout: LauncherLayout };

export type LauncherAIPriority = 0 | 1 | 2 | 3;

export type LauncherAIAction =
  | {
      type: "promote";
      widgetId: string;
      reason: string;
      priority?: LauncherAIPriority;
    }
  | {
      type: "demote";
      widgetId: string;
      reason: string;
      priority?: LauncherAIPriority;
    }
  | {
      type: "resize";
      widgetId: string;
      size: LauncherSemanticSize;
      reason: string;
    }
  | {
      type: "show";
      widgetId: string;
      reason: string;
    }
  | {
    type: "suggest_hide";
    widgetId: string;
    reason: string;
  };

export type LauncherSuggestion = {
  id: string;
  actions: LauncherAIAction[];
  title: string;
  summary: string;
  reason: string;
  priority: LauncherAIPriority;
  createdAt?: string;
};

export type LauncherSuggestionActionResult = {
  action: LauncherAIAction;
  applied: boolean;
  reason: string;
  message: string;
};

export type LauncherSuggestionPreview = {
  suggestion: LauncherSuggestion;
  initialState: LauncherState;
  previewState: LauncherState;
  appliedActions: number;
  rejectedActions: number;
  actions: LauncherSuggestionActionResult[];
  message: string;
};

export type LauncherWidgetSnapshot = DashboardManifestWidget & {
  launcher_definition?: LauncherWidgetDefinition;
};
