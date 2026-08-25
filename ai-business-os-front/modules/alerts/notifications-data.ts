export type NotificationTab = "All" | "Transactions" | "Payouts" | "Invoices" | "System" | "AI Alerts";

export type NotificationTone = "ai" | "success" | "danger" | "info";

export const NOTIFICATION_TAB_LABELS: Record<NotificationTab, string> = {
  All: "Все",
  Transactions: "Транзакции",
  Payouts: "Выплаты",
  Invoices: "Счета",
  System: "Система",
  "AI Alerts": "ИИ-сигналы",
};

export const NOTIFICATION_TONE_LABELS: Record<NotificationTone, string> = {
  ai: "ИИ",
  success: "Успех",
  danger: "Ошибка",
  info: "Инфо",
};

export type NotificationItem = {
  id: string;
  title: string;
  message: string;
  time: string;
  tag: Exclude<NotificationTab, "All">;
  tone: NotificationTone;
  unread: boolean;
  read: boolean;
  actionLabel: string;
  detailsHref: string;
};

export const NOTIFICATION_TABS: NotificationTab[] = ["All", "Transactions", "Payouts", "Invoices", "System", "AI Alerts"];

export function getNotificationTabLabel(tab: NotificationTab) {
  return NOTIFICATION_TAB_LABELS[tab];
}

export function getNotificationToneLabel(tone: NotificationTone) {
  return NOTIFICATION_TONE_LABELS[tone];
}

export function filterNotifications(tab: NotificationTab, notifications: NotificationItem[]) {
  if (tab === "All") return notifications;
  return notifications.filter((item) => item.tag === tab || (tab === "AI Alerts" && item.tone === "ai"));
}

export function getUnreadCount(tab: NotificationTab, notifications: NotificationItem[]) {
  return filterNotifications(tab, notifications).filter((item) => item.unread).length;
}
