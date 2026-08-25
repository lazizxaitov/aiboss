"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { SectionHeading } from "@/components/ui/section-heading";
import { Surface } from "@/components/ui/surface";
import { cn } from "@/lib/cn";
import { getNotification, getNotifications, markNotificationRead } from "@/lib/core-api";
import { emitNotificationsChanged } from "@/lib/notifications-events";
import {
  getNotificationTabLabel,
  getNotificationToneLabel,
  type NotificationItem,
} from "@/modules/alerts/notifications-data";

type NotificationDetailsProps = {
  notificationId: string;
};

export function NotificationDetails({ notificationId }: NotificationDetailsProps) {
  const [notification, setNotification] = useState<NotificationItem | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isMarkingRead, setIsMarkingRead] = useState(false);
  const [relatedNotifications, setRelatedNotifications] = useState<NotificationItem[]>([]);

  useEffect(() => {
    let active = true;

    void getNotification(notificationId)
      .then((item) => {
        if (!active) return;
        setNotification(item);
        setError(null);
      })
      .catch((fetchError) => {
        if (!active) return;
        setNotification(null);
        setError(fetchError instanceof Error ? fetchError.message : "Не удалось загрузить уведомление");
      });

    return () => {
      active = false;
    };
  }, [notificationId]);

  useEffect(() => {
    if (!notification || notification.read) return;

    let active = true;
    void (async () => {
      try {
        setIsMarkingRead(true);
        await markNotificationRead(notification.id);
        if (!active) return;
        setNotification((current) => (current ? { ...current, unread: false, read: true } : current));
        emitNotificationsChanged();
      } finally {
        if (active) setIsMarkingRead(false);
      }
    })();

    return () => {
      active = false;
    };
  }, [notification]);

  useEffect(() => {
    if (!notification) return;

    let active = true;

    void getNotifications()
      .then((feed) => {
        if (!active) return;
        setRelatedNotifications(
          feed.items.filter((item) => item.id !== notification.id && item.tag === notification.tag).slice(0, 3),
        );
      })
      .catch(() => {
        if (active) setRelatedNotifications([]);
      });

    return () => {
      active = false;
    };
  }, [notification]);

  return (
    <section className="space-y-6">
      <SectionHeading
        eyebrow="Уведомления"
        title={notification ? notification.title : "Детали уведомления"}
        description="Карточка отражает текущее событие, его статус и связанные действия."
        actions={
          <Link
            href="/alerts"
            className="inline-flex h-11 items-center justify-center rounded-full border border-[#3a3d43] bg-[#2E3137] px-4 text-sm font-medium text-slate-300 transition hover:border-[#4a4e56] hover:text-[#f4f7fb]"
          >
            Назад к уведомлениям
          </Link>
        }
      />

      <Surface className="overflow-hidden px-6 py-6 sm:px-8 sm:py-8">
        {error ? (
          <div className="rounded-[24px] border border-rose-500/20 bg-[#4a3540] px-5 py-4 text-rose-200">
            {error}
          </div>
        ) : null}

        {notification ? (
          <div className="space-y-6">
            <div className="flex flex-wrap items-center gap-3">
              <Badge variant={notification.unread ? "accent" : "soft"}>{notification.unread ? "Непрочитано" : "Прочитано"}</Badge>
              <Badge variant="soft">{getNotificationTabLabel(notification.tag)}</Badge>
              <Badge variant="soft">{getNotificationToneLabel(notification.tone)}</Badge>
            </div>

            <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
              <article className="rounded-[28px] border border-[#3a3d43] bg-[#2E3137] px-6 py-6">
                <div className="flex items-start gap-4">
                  <NotificationGlyph tone={notification.tone} />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-start justify-between gap-4">
                      <div className="min-w-0">
                        <h3 className="text-[24px] font-semibold tracking-[-0.04em] text-[#f4f7fb]">{notification.title}</h3>
                        <p className="mt-3 text-[16px] leading-8 text-slate-300">{notification.message}</p>
                      </div>
                      {notification.unread ? <span className="mt-2 h-3 w-3 shrink-0 rounded-full bg-yellow-300" /> : null}
                    </div>

                    <div className="mt-6 flex flex-wrap items-center gap-3 text-sm text-slate-400">
                      <span>Время: {notification.time}</span>
                      <span>•</span>
                      <span>Статус: {notification.read ? "прочитано" : "непрочитано"}</span>
                      <span>•</span>
                      <span>Действие: {notification.actionLabel}</span>
                      {isMarkingRead ? <span>• обновляется...</span> : null}
                    </div>
                  </div>
                </div>
              </article>

              <aside className="rounded-[28px] border border-[#3a3d43] bg-[#343840] px-5 py-5">
                <p className="text-xs uppercase tracking-[0.34em] text-slate-400">Действия</p>
                <div className="mt-4 space-y-3">
                  <div className="rounded-2xl border border-[#3a3d43] bg-[#343840] px-4 py-4 text-sm text-slate-300">
                    <p className="text-xs uppercase tracking-[0.28em] text-slate-400">Маршрут</p>
                    <p className="mt-2 break-all font-medium text-[#f4f7fb]">{notification.detailsHref}</p>
                  </div>
                  <div className="rounded-2xl border border-[#3a3d43] bg-[#343840] px-4 py-4 text-sm text-slate-300">
                    <p className="text-xs uppercase tracking-[0.28em] text-slate-400">ID события</p>
                    <p className="mt-2 break-all font-medium text-[#f4f7fb]">{notification.id}</p>
                  </div>
                  <Link
                    href="/alerts"
                    className="flex w-full items-center justify-between rounded-2xl border border-[#3a3d43] bg-[#2E3137] px-4 py-4 text-left text-sm font-medium text-slate-200 transition hover:border-[#4a4e56]"
                  >
                    <span>Открыть список уведомлений</span>
                    <span aria-hidden="true">›</span>
                  </Link>
                </div>
              </aside>
            </div>

            <div className="rounded-[28px] border border-[#3a3d43] bg-[#2E3137] px-6 py-6">
              <div className="flex items-center justify-between gap-4">
                <div>
                    <p className="text-xs uppercase tracking-[0.34em] text-slate-400">Связанные события</p>
                  <h4 className="mt-2 text-[18px] font-semibold tracking-[-0.03em] text-[#f4f7fb]">
                    Другие уведомления того же типа
                  </h4>
                </div>
                <Badge variant="soft">{relatedNotifications.length}</Badge>
              </div>

              <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                {relatedNotifications.length > 0 ? (
                  relatedNotifications.map((item) => (
                    <Link
                      key={item.id}
                      href={item.detailsHref}
                      className="rounded-[22px] border border-[#3a3d43] bg-[#343840] px-4 py-4 transition hover:border-[#FFF27A]/30 hover:bg-[#323043]"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <p className="truncate text-sm font-semibold text-[#f4f7fb]">{item.title}</p>
                          <p className="mt-1 line-clamp-2 text-sm leading-6 text-slate-300">{item.message}</p>
                        </div>
                        <span className="mt-1 h-2.5 w-2.5 shrink-0 rounded-full bg-yellow-300" />
                      </div>
                    </Link>
                  ))
                ) : (
                  <div className="rounded-[22px] border border-dashed border-[#3a3d43] px-4 py-6 text-sm text-slate-400">
                    Пока нет связанных событий для этой карточки.
                  </div>
                )}
              </div>
            </div>
          </div>
        ) : (
          <div className="rounded-[24px] border border-dashed border-[#3a3d43] px-6 py-12 text-center">
            <p className="text-lg font-semibold text-[#f4f7fb]">Уведомление не найдено</p>
            <p className="mt-2 text-sm leading-6 text-slate-400">
              Проверьте ссылку или вернитесь к списку уведомлений, чтобы выбрать другой элемент.
            </p>
          </div>
        )}
      </Surface>
    </section>
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
