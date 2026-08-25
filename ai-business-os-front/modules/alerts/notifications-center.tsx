"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { SectionHeading } from "@/components/ui/section-heading";
import { Surface } from "@/components/ui/surface";
import { cn } from "@/lib/cn";
import { getNotifications, markAllNotificationsRead } from "@/lib/core-api";
import { emitNotificationsChanged } from "@/lib/notifications-events";
import {
  NOTIFICATION_TABS,
  getNotificationTabLabel,
  type NotificationItem,
  type NotificationTab,
  filterNotifications,
  getUnreadCount,
} from "@/modules/alerts/notifications-data";

export function NotificationsCenter({ selectedId }: { selectedId?: string }) {
  const [activeTab, setActiveTab] = useState<NotificationTab>("All");
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [isSyncing, setIsSyncing] = useState(false);

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

  useEffect(() => {
    if (!selectedId) return;
    const timer = window.setTimeout(() => {
      document.getElementById(`notification-${selectedId}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
    }, 0);
    return () => window.clearTimeout(timer);
  }, [selectedId]);

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
    <section className="space-y-6">
      <SectionHeading
        eyebrow="Центр уведомлений"
        title="Уведомления"
        description="Все бизнес-события, транзакции и системные сигналы собраны в одном месте."
      />

      <Surface className="overflow-hidden px-5 py-5 sm:px-6 sm:py-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="accent">{unreadCount} непрочитанных</Badge>
              <Badge variant="soft">{notifications.length} всего</Badge>
              <Badge variant="soft">ИИ-сигналы</Badge>
            </div>
            <p className="mt-4 max-w-2xl text-sm leading-7 text-slate-400">
              Здесь видно, что требует внимания прямо сейчас. Карточки можно открыть из верхнего колокольчика или отсюда.
            </p>
          </div>

          <button
            type="button"
            onClick={() => void handleMarkAllRead()}
            disabled={isSyncing}
            className="inline-flex h-11 items-center justify-center rounded-full border border-[#3a3d43] bg-[#2E3137] px-4 text-sm font-medium text-slate-300 transition hover:border-[#4a4e56] hover:text-[#f4f7fb] disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isSyncing ? "Обновляем..." : "Отметить все как прочитанные"}
          </button>
        </div>

        <div className="mt-6 flex gap-3 overflow-x-auto border-b border-[#3a3d43] pb-4">
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
                  active ? "border border-[#FFF27A]/30 bg-[#FFF27A] text-[#1E1E21]" : "text-slate-400 hover:bg-[#343840] hover:text-[#f4f7fb]",
                )}
              >
                <span>{getNotificationTabLabel(tab)}</span>
                {active ? <span className="inline-flex h-6 min-w-6 items-center justify-center rounded-full bg-[#f4f7fb]/10 px-2 text-xs font-semibold text-[#f4f7fb]">{count}</span> : null}
              </button>
            );
          })}
        </div>

        <div className="mt-2 space-y-4">
          {visibleNotifications.length > 0 ? (
            visibleNotifications.map((item) => <NotificationRow key={item.id} item={item} highlighted={item.id === selectedId} />)
          ) : (
            <div className="rounded-[24px] border border-dashed border-[#3a3d43] px-6 py-12 text-center">
              <p className="text-lg font-semibold text-[#f4f7fb]">Уведомлений пока нет</p>
              <p className="mt-2 text-sm leading-6 text-slate-400">
                После обновления данных здесь появятся реальные события бизнеса.
              </p>
            </div>
          )}
        </div>
      </Surface>
    </section>
  );
}

function NotificationRow({ item, highlighted }: { item: NotificationItem; highlighted?: boolean }) {
  return (
    <article
      id={`notification-${item.id}`}
      className={cn(
        "rounded-[28px] border px-5 py-5 transition",
        highlighted ? "border-[#FFF27A]/30 bg-[#323043] shadow-[0_16px_50px_rgba(255,242,122,0.12)]" : "border-[#3a3d43] bg-[#2E3137]",
        item.read ? "opacity-90" : "opacity-100",
      )}
    >
      <div className="flex items-start gap-4">
        <NotificationGlyph tone={item.tone} />
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-3">
                <h3 className="truncate text-[20px] font-semibold tracking-[-0.03em] text-[#f4f7fb]">{item.title}</h3>
                <NotificationTag tone={item.tone}>{item.tag}</NotificationTag>
              </div>
            <p className="mt-2 max-w-4xl text-[15px] leading-7 text-slate-300">{item.message}</p>
          </div>
          {item.unread ? <span className="mt-2 h-3 w-3 shrink-0 rounded-full bg-[#FFF27A]" /> : null}
        </div>

        <div className="mt-4 flex items-center justify-between gap-4">
            <p className="text-sm font-medium text-slate-400">{item.time}</p>
            <Link
              href={item.detailsHref}
              className="inline-flex items-center gap-2 text-[16px] font-medium text-[#FFF27A] transition hover:text-[#f4f7fb]"
            >
              {item.actionLabel}
              <span className="text-[18px] leading-none">›</span>
            </Link>
          </div>
        </div>
      </div>
    </article>
  );
}

function NotificationGlyph({ tone }: { tone: NotificationItem["tone"] }) {
  const toneClasses: Record<NotificationItem["tone"], string> = {
    ai: "bg-[#FFF27A] text-[#1E1E21]",
    success: "bg-[#32443d] text-[#f4f7fb]",
    danger: "bg-[#4a3540] text-[#f4f7fb]",
    info: "bg-[#2f4050] text-[#f4f7fb]",
  };

  const icon = tone === "success" ? "✓" : tone === "danger" ? "✕" : tone === "info" ? "i" : "✦";
  return (
    <div className={cn("flex h-16 w-16 shrink-0 items-center justify-center rounded-2xl text-[28px]", toneClasses[tone])}>
      {icon}
    </div>
  );
}

function NotificationTag({ tone, children }: { tone: NotificationItem["tone"]; children: string }) {
  const toneClasses: Record<NotificationItem["tone"], string> = {
    ai: "bg-[#FFF27A] text-[#1E1E21]",
    success: "bg-[#32443d] text-[#d9f2e3]",
    danger: "bg-[#4a3540] text-[#ffd8e1]",
    info: "bg-[#2f4050] text-[#d9e8ff]",
  };

  return <span className={cn("inline-flex rounded-full px-3 py-1 text-xs font-semibold", toneClasses[tone])}>{children}</span>;
}
