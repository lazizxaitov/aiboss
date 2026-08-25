import type { LauncherAIAction } from "./types";

const REJECTION_LABELS: Record<string, string> = {
  locked_widget: "Виджет закреплён вами.",
  protected_widget: "Виджет закреплён или размер выбран вами вручную.",
  pinned_widget: "Положение виджета закреплено вами.",
  hidden_widget: "Этот виджет скрыт вами.",
  user_hidden: "Этот виджет скрыт вами.",
  user_size_override: "Размер виджета выбран вами вручную.",
  unsupported_size: "Этот размер недоступен для виджета.",
  invalid_size: "Этот размер недоступен для виджета.",
  invalid_widget: "Виджет больше недоступен.",
  widget_not_found: "Виджет больше недоступен.",
  already_visible: "Виджет уже виден.",
  no_change: "Изменение не требуется.",
  suggest_hide: "ИИ предлагает скрыть этот виджет без немедленных изменений.",
  unsupported_action: "Это изменение сейчас недоступно.",
  invalid_action: "Это изменение сейчас недоступно.",
  policy_conflict: "Изменение конфликтует с текущими настройками.",
  LOCKED_BY_USER: "Виджет закреплён вами.",
  PINNED_BY_USER: "Положение виджета закреплено вами.",
  HIDDEN_BY_USER: "Этот виджет скрыт вами.",
  USER_SIZE_OVERRIDE: "Размер виджета выбран вами вручную.",
  INVALID_SIZE: "Этот размер недоступен для виджета.",
  INVALID_WIDGET: "Виджет больше недоступен.",
  POLICY_CONFLICT: "Изменение конфликтует с текущими настройками.",
};

const PRIORITY_LABELS: Record<0 | 1 | 2 | 3, string> = {
  0: "Низкий",
  1: "Средний",
  2: "Высокий",
  3: "Критический",
};

export function getLauncherAIActionLabel(action: LauncherAIAction) {
  switch (action.type) {
    case "promote":
      return "Поднять выше";
    case "demote":
      return "Переместить ниже";
    case "resize":
      return action.size === "small"
        ? "Сделать маленьким"
        : action.size === "medium"
          ? "Сделать средним"
          : "Сделать большим";
    case "show":
      return "Показать виджет";
    case "suggest_hide":
      return "Предложить скрыть";
    default:
      return "Изменить виджет";
  }
}

export function getLauncherAIRejectionMessage(reason: string) {
  return REJECTION_LABELS[reason] ?? "Изменение не удалось применить.";
}

export function getLauncherAISuggestionStatusMessage(appliedCount: number, rejectedCount: number) {
  if (appliedCount > 0 && rejectedCount > 0) return "Часть изменений применена.";
  if (appliedCount > 0) return "Изменения применены.";
  return "Изменения не были применены.";
}

export function getLauncherAIPreviewBadge(appliedCount: number, rejectedCount: number) {
  if (appliedCount > 0 && rejectedCount > 0) return "Частично применено";
  if (appliedCount > 0) return "Применено";
  return "Без изменений";
}

export function getLauncherAIPriorityLabel(priority: 0 | 1 | 2 | 3) {
  return PRIORITY_LABELS[priority];
}
