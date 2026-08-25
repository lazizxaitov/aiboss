import { applyLauncherAIAction } from "./ai-policy";
import { getLauncherAIRejectionMessage, getLauncherAISuggestionStatusMessage } from "./ai-presentation";
import type {
  LauncherAIAction,
  LauncherAIPriority,
  LauncherState,
  LauncherSuggestion,
  LauncherSuggestionActionResult,
  LauncherSuggestionPreview,
} from "./types";
import type { DashboardManifestWidget } from "@/lib/core-api";

function cloneState(state: LauncherState): LauncherState {
  return {
    ...state,
    order: Array.isArray(state.order) ? [...state.order] : [],
    sizes: state.sizes ? { ...state.sizes } : {},
    pinned: Array.isArray(state.pinned) ? [...state.pinned] : [],
    locked: Array.isArray(state.locked) ? [...state.locked] : [],
    hidden: Array.isArray(state.hidden) ? [...state.hidden] : [],
    userOverrides: {
      size: Array.isArray(state.userOverrides?.size) ? [...state.userOverrides!.size] : [],
      order: Boolean(state.userOverrides?.order),
      hidden: Array.isArray(state.userOverrides?.hidden) ? [...state.userOverrides!.hidden] : [],
    },
  };
}

function buildSuggestion(
  id: string,
  title: string,
  summary: string,
  reason: string,
  priority: LauncherAIPriority,
  actions: LauncherAIAction[],
  createdAt?: string,
): LauncherSuggestion {
  return {
    id,
    title,
    summary,
    reason,
    priority,
    actions,
    createdAt,
  };
}

function firstHiddenWidget(state: LauncherState, widgets: DashboardManifestWidget[]) {
  const hidden = new Set(state.hidden ?? []);
  return widgets.find((widget) => hidden.has(widget.widget_id)) ?? null;
}

export function evaluateLauncherSuggestion(
  state: LauncherState,
  widgets: DashboardManifestWidget[],
  suggestion: LauncherSuggestion,
): LauncherSuggestionPreview {
  const initialState = cloneState(state);
  let current = cloneState(state);
  const actions: LauncherSuggestionActionResult[] = [];

  for (const action of suggestion.actions) {
    const result = applyLauncherAIAction(current, widgets, action);
    actions.push({
      action,
      applied: result.applied,
      reason: result.reason,
      message: getLauncherAIRejectionMessage(result.reason),
    });
    current = cloneState(result.state as LauncherState);
  }

  const appliedActions = actions.filter((item) => item.applied).length;
  const rejectedActions = actions.length - appliedActions;

  return {
    suggestion,
    initialState,
    previewState: current,
    appliedActions,
    rejectedActions,
    actions,
    message: getLauncherAISuggestionStatusMessage(appliedActions, rejectedActions),
  };
}

export function applyLauncherSuggestion(
  currentState: LauncherState,
  widgets: DashboardManifestWidget[],
  suggestion: LauncherSuggestion,
) {
  return evaluateLauncherSuggestion(currentState, widgets, suggestion);
}

export function dismissLauncherSuggestion(
  suggestions: LauncherSuggestion[],
  suggestionId: string,
) {
  return suggestions.filter((suggestion) => suggestion.id !== suggestionId);
}

export function createDevelopmentLauncherSuggestions(
  widgets: DashboardManifestWidget[],
  state: LauncherState,
): LauncherSuggestion[] {
  if (process.env.NODE_ENV === "production") return [];

  const suggestions: LauncherSuggestion[] = [];
  const now = new Date().toISOString();
  const hiddenWidget = firstHiddenWidget(state, widgets);
  const inventoryRisk = widgets.find((widget) => widget.widget_type === "inventory_risk");
  const executiveBrief = widgets.find((widget) => widget.widget_id === "executive-brief" || widget.widget_type === "ai_insight");
  const comparison = widgets.find((widget) => widget.widget_type === "organization_comparison");
  const dataQuality = widgets.find((widget) => widget.widget_type === "data_quality");
  const alert = widgets.find((widget) => widget.widget_type === "alert" || widget.widget_type === "product_alert" || widget.widget_type === "inventory_alert");

  if (inventoryRisk) {
    suggestions.push(
      buildSuggestion(
        `dev-${inventoryRisk.widget_id}-priority`,
        "Риски склада требуют внимания",
        `Виджет «${inventoryRisk.title}» можно поднять выше и показать в более крупном размере.`,
        "10 товаров требуют внимания, поэтому сигнал должен быть заметнее.",
        3,
        [
          { type: "promote", widgetId: inventoryRisk.widget_id, reason: "10 товаров требуют внимания", priority: 2 },
          { type: "resize", widgetId: inventoryRisk.widget_id, size: "large", reason: "Показать блок рисков крупнее" },
        ],
        now,
      ),
    );
  } else if (executiveBrief) {
    suggestions.push(
      buildSuggestion(
        `dev-${executiveBrief.widget_id}-brief`,
        "Управленческий обзор стоит видеть раньше",
        `Виджет «${executiveBrief.title}» можно сделать более заметным для быстрого просмотра.`,
        "Краткий управленческий обзор ускоряет контроль ключевых изменений.",
        2,
        [
          { type: "promote", widgetId: executiveBrief.widget_id, reason: "Краткий управленческий обзор важен для руководителя", priority: 1 },
          { type: "resize", widgetId: executiveBrief.widget_id, size: "large", reason: "Показать обзор шире" },
        ],
        now,
      ),
    );
  }

  if (hiddenWidget) {
    suggestions.push(
      buildSuggestion(
        `dev-${hiddenWidget.widget_id}-restore`,
        "Скрытый виджет можно вернуть",
        `Виджет «${hiddenWidget.title}» уже скрыт и может быть снова показан.`,
        "Полезный виджет был скрыт вручную и доступен для восстановления.",
        1,
        [
          { type: "show", widgetId: hiddenWidget.widget_id, reason: "Виджет скрыт и может быть восстановлен" },
        ],
        now,
      ),
    );
  } else if (comparison) {
    suggestions.push(
      buildSuggestion(
        `dev-${comparison.widget_id}-focus`,
        "Сравнение организаций можно отвести ниже",
        `Виджет «${comparison.title}» можно оставить в очереди, если требуется больше внимания другим блокам.`,
        "Это демонстрационная подсказка для проверки частичного применения.",
        1,
        [
          { type: "demote", widgetId: comparison.widget_id, reason: "Есть более важные виджеты для первого экрана", priority: 1 },
          { type: "suggest_hide", widgetId: comparison.widget_id, reason: "Проверка сценария предложения скрытия" },
        ],
        now,
      ),
    );
  }

  if (dataQuality) {
    suggestions.push(
      buildSuggestion(
        `dev-${dataQuality.widget_id}-size`,
        "Качество данных можно показать компактнее",
        `Виджет «${dataQuality.title}» обычно достаточно видеть в более компактном виде.`,
        "Бизнесу важен краткий статус, а не лишний объём карточки.",
        0,
        [
          { type: "resize", widgetId: dataQuality.widget_id, size: "medium", reason: "Компактный статус качества" },
        ],
        now,
      ),
    );
  }

  if (suggestions.length === 0 && alert) {
    suggestions.push(
      buildSuggestion(
        `dev-${alert.widget_id}-alert`,
        "Сигнал можно поднять выше",
        `Виджет «${alert.title}» можно сделать заметнее на главном экране.`,
        "Демонстрационный сигнал нужен для проверки подсказок ИИ без LLM.",
        1,
        [
          { type: "promote", widgetId: alert.widget_id, reason: "Сигнал важен для текущего экрана", priority: 1 },
        ],
        now,
      ),
    );
  }

  return suggestions.slice(0, 4);
}
