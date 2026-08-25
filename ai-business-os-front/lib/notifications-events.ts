export const NOTIFICATIONS_CHANGED_EVENT = "ai-bos:notifications-changed";

export function emitNotificationsChanged() {
  window.dispatchEvent(new Event(NOTIFICATIONS_CHANGED_EVENT));
}
