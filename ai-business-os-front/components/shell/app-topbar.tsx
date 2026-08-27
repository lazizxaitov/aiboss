"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { cn } from "@/lib/cn";
import { getNotifications, markAllNotificationsRead } from "@/lib/core-api";
import { emitNotificationsChanged } from "@/lib/notifications-events";
import { Dropdown } from "@/components/ui/dropdown";
import {
  NOTIFICATION_TABS,
  getNotificationTabLabel,
  type NotificationItem,
  type NotificationTab,
  filterNotifications,
  getUnreadCount,
} from "@/modules/alerts/notifications-data";

export function AppTopbar() {
  const router = useRouter();
  const [profilePhoto, setProfilePhoto] = useState<string | null>(null);
  const [profileName, setProfileName] = useState("А");
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<NotificationTab>("All");
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [isSyncing, setIsSyncing] = useState(false);

  useEffect(() => {
    const loadProfile = () => {
      setProfilePhoto(localStorage.getItem("aibos_profile_photo"));
      setProfileName(localStorage.getItem("aibos_profile_name") || "А");
    };
    loadProfile();
    window.addEventListener("aibos-profile-updated", loadProfile);
    return () => window.removeEventListener("aibos-profile-updated", loadProfile);
  }, []);

  useEffect(() => {
    let active = true;

    void getNotifications()
      .then((feed) => {
        if (active) setNotifications(feed.items);
      })
      .catch(() => {
        if (active) setNotifications([]);
      });

    return () => {
      active = false;
    };
  }, []);

  const visibleNotifications = useMemo(() => filterNotifications(activeTab, notifications), [activeTab, notifications]);
  const unreadCount = useMemo(() => getUnreadCount("All", notifications), [notifications]);

  const handleMarkAllRead = async () => {
    try {
      setIsSyncing(true);
      await markAllNotificationsRead();
      const feed = await getNotifications();
      setNotifications(feed.items);
      emitNotificationsChanged();
    } finally {
      setIsSyncing(false);
    }
  };

  return (
    <header className="relative flex items-center justify-between gap-4 rounded-[32px] bg-[#2E3137] px-5 py-4 shadow-[0_18px_50px_rgba(0,0,0,0.22)] lg:sticky lg:top-4 lg:z-40">
      <Link href="/" className="flex items-center gap-3">
        <img
          src="/main%20icon.png"
          alt="AI Business OS"
          width={48}
          height={48}
          className="h-12 w-12 rounded-full object-cover"
        />
        <div className="text-[20px] font-semibold tracking-[-0.04em] text-[#f4f7fb]">AI БОС</div>
      </Link>

      <div className="flex min-w-0 flex-1 items-center justify-end gap-3">
        <label className="hidden w-full max-w-[240px] items-center gap-3 rounded-full border border-[#3a3d43] bg-[#343840] px-4 py-3 text-slate-400 md:flex">
          <span className="text-lg leading-none">⌕</span>
          <input
            type="search"
            placeholder="Поиск"
            className="w-full bg-transparent text-sm text-[#f4f7fb] outline-none placeholder:text-slate-400"
          />
        </label>

        <div className="hidden items-center gap-3 lg:flex">
          <div className="rounded-full border border-[#3a3d43] bg-[#343840] px-5 py-3 text-sm font-medium text-slate-200">
            20 августа в 23:46
          </div>
        </div>

        <Dropdown
          align="right"
          className="h-12 w-12 shrink-0"
          open={notificationsOpen}
          onOpenChange={setNotificationsOpen}
          trigger={
            <button
              type="button"
              className="relative flex h-12 w-12 items-center justify-center rounded-full border border-[#3a3d43] bg-[#2E3137] text-slate-300 transition hover:border-[#4a4e56] hover:text-white"
              aria-label="Уведомления"
            >
              <img src="/notifications.png" alt="" width={24} height={24} className="h-6 w-6 select-none object-contain" />
              {unreadCount > 0 ? <span className="absolute right-2 top-2 h-2.5 w-2.5 rounded-full bg-rose-500 ring-2 ring-white" /> : null}
            </button>
          }
          panelClassName="w-[min(92vw,720px)] overflow-hidden rounded-[28px] border border-[#3a3d43] bg-[#2E3137] shadow-[0_28px_70px_rgba(0,0,0,0.28)]"
        >
          {(close) => (
            <div>
              <div className="flex items-start justify-between gap-4 border-b border-[#3a3d43] px-6 py-5">
                <div>
                  <h2 className="text-[26px] font-semibold tracking-[-0.04em] text-[#f4f7fb]">Уведомления</h2>
                  <p className="mt-2 text-sm font-medium text-slate-400">{unreadCount} непрочитанных</p>
                </div>
                <div className="flex items-center gap-3">
                  <button
                    type="button"
                    className="inline-flex items-center gap-2 rounded-full border border-[#3a3d43] px-4 py-2 text-sm font-medium text-slate-200 transition hover:bg-[#2E3137]/5 hover:text-white"
                    onClick={() => void handleMarkAllRead()}
                    disabled={isSyncing}
                  >
                    <span className="text-lg leading-none">✓✓</span>
                    {isSyncing ? "Обновляем..." : "Отметить все как прочитанные"}
                  </button>
                  <button
                    type="button"
                    className="flex h-10 w-10 items-center justify-center rounded-full border border-[#3a3d43] text-slate-300 transition hover:bg-[#2E3137]/5 hover:text-white"
                    aria-label="Настройки"
                  >
                    ⚙
                  </button>
                </div>
              </div>

              <div className="flex gap-3 overflow-x-auto border-b border-[#3a3d43] px-6 py-4">
                {NOTIFICATION_TABS.map((tab) => {
                  const active = activeTab === tab;
                  const count = getUnreadCount(tab, notifications);
                  return (
                    <button
                      key={tab}
                      type="button"
                      onClick={() => setActiveTab(tab)}
                      className={cn(
                        "inline-flex shrink-0 items-center gap-2 rounded-full px-3 py-2 text-sm font-medium transition",
                        active ? "border border-[#FFF27A]/30 bg-[#FFF27A] text-[#1E1E21]" : "text-slate-300 hover:bg-[#343840] hover:text-[#f4f7fb]",
                      )}
                    >
                      <span>{getNotificationTabLabel(tab)}</span>
                      {active ? <span className="inline-flex h-6 min-w-6 items-center justify-center rounded-full bg-[#f4f7fb]/10 px-2 text-xs font-semibold text-[#f4f7fb]">{count}</span> : null}
                    </button>
                  );
                })}
              </div>

              <div className="max-h-[520px] overflow-y-auto">
                {visibleNotifications.length > 0 ? (
                  visibleNotifications.map((item) => (
                    <article
                      key={item.id}
                      className={cn(
                        "border-b border-[#3a3d43] px-6 py-5 last:border-b-0",
                        item.read ? "bg-[#26292e]" : "bg-[#2E3137]",
                      )}
                    >
                      <div className="flex items-start gap-4">
                        <NotificationGlyph tone={item.tone} />
                        <div className="min-w-0 flex-1">
                          <div className="flex items-start justify-between gap-4">
                            <div className="min-w-0">
                              <div className="flex items-center gap-3">
                                <h3 className="truncate text-[18px] font-semibold tracking-[-0.03em] text-[#f4f7fb]">{item.title}</h3>
                                <NotificationTag tone={item.tone}>{getNotificationTabLabel(item.tag)}</NotificationTag>
                              </div>
                              <p className="mt-2 max-w-3xl text-[15px] leading-7 text-slate-400">{item.message}</p>
                            </div>
                            {item.unread ? <span className="mt-2 h-3 w-3 shrink-0 rounded-full bg-rose-400" /> : null}
                          </div>

                          <div className="mt-4 flex items-center justify-between gap-4">
                            <p className="text-sm font-medium text-slate-400">{item.time}</p>
                            <Link
                              href={item.detailsHref}
                              onClick={() => setNotificationsOpen(false)}
                              className="inline-flex items-center gap-2 text-[16px] font-medium text-[#FFF27A] transition hover:text-[#f4f7fb]"
                            >
                              {item.actionLabel}
                              <span className="text-[18px] leading-none">›</span>
                            </Link>
                          </div>
                        </div>
                      </div>
                    </article>
                  ))
                ) : (
                  <div className="px-6 py-12 text-center">
                    <p className="text-[17px] font-medium text-[#f4f7fb]">Уведомлений пока нет</p>
                    <p className="mt-2 text-sm leading-6 text-slate-400">
                      Новые события появятся здесь сразу после обновления данных.
                    </p>
                  </div>
                )}
              </div>

              <div className="border-t border-[#3a3d43] px-6 py-5">
                <Link
                  href="/alerts"
                  className="inline-flex w-full items-center justify-center gap-2 rounded-full border border-[#3a3d43] py-3 text-[16px] font-semibold text-slate-200 transition hover:bg-[#2E3137]/5 hover:text-white"
                  onClick={close}
                >
                  Все уведомления
                  <span className="text-[20px] leading-none">›</span>
                </Link>
              </div>
            </div>
          )}
        </Dropdown>

        <Dropdown
          align="right"
          className="h-12 w-12 shrink-0"
          panelClassName="w-[220px] overflow-hidden rounded-[20px]"
          trigger={(
            <button
              type="button"
              className="flex h-12 w-12 items-center justify-center overflow-hidden rounded-full bg-[#f3d5b4] text-sm font-semibold text-[#1E1E21] shadow-[0_8px_22px_rgba(15,23,42,0.08)]"
              aria-label="Профиль"
            >
              {profilePhoto ? (
                <span className="h-full w-full bg-cover bg-center" style={{ backgroundImage: `url(${profilePhoto})` }} />
              ) : (
                <span className="text-[12px]">{profileName.slice(0, 3).toUpperCase()}</span>
              )}
            </button>
          )}
        >
          {(close) => (
            <nav className="p-2" aria-label="Меню профиля">
              <Link href="/profile" onClick={close} className="block rounded-2xl px-4 py-3 text-sm text-slate-200 transition hover:bg-[#343840]">
                Профиль
              </Link>
              <Link href="/settings" onClick={close} className="block rounded-2xl px-4 py-3 text-sm text-slate-200 transition hover:bg-[#343840]">
                Настройки
              </Link>
              <button
                type="button"
                onClick={() => {
                  close();
                  document.cookie = "aibos_owner_session=; Path=/; Max-Age=0; SameSite=Lax";
                  router.replace("/login");
                }}
                className="block w-full rounded-2xl px-4 py-3 text-left text-sm text-rose-300 transition hover:bg-[#343840]"
              >
                Выйти
              </button>
            </nav>
          )}
        </Dropdown>
      </div>
    </header>
  );
}

function NotificationGlyph({ tone }: { tone: NotificationItem["tone"] }) {
  const toneClasses: Record<NotificationItem["tone"], string> = {
    ai: "bg-[#FFF27A] text-[#1E1E21]",
    success: "bg-[#244037] text-[#c7f4de]",
    danger: "bg-[#40272c] text-[#ffd3db]",
    info: "bg-[#20374a] text-[#d2ecff]",
  };

  const icon = tone === "success" ? "✓" : tone === "danger" ? "✕" : tone === "info" ? "i" : "✦";
  return (
    <div className={cn("flex h-12 w-12 items-center justify-center rounded-2xl text-[17px] font-semibold", toneClasses[tone])}>
      {icon}
    </div>
  );
}

function NotificationTag({
  tone,
  children,
}: {
  tone: NotificationItem["tone"];
  children: string;
}) {
  const toneClasses: Record<NotificationItem["tone"], string> = {
    ai: "bg-[#FFF27A] text-[#1E1E21]",
    success: "bg-[#244037] text-[#f4f7fb]",
    danger: "bg-[#40272c] text-[#f4f7fb]",
    info: "bg-[#20374a] text-[#f4f7fb]",
  };

  return (
    <span className={cn("inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold", toneClasses[tone])}>
      {children}
    </span>
  );
}
