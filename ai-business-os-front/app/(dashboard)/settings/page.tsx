"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Surface } from "@/components/ui/surface";
import { AiRoutingSettings } from "@/components/settings/ai-routing-settings";
import { MobileAccessCard } from "@/components/settings/mobile-access-card";
import { getSmartUpLiveSyncStatus, type SmartUpLiveSyncStatus } from "@/lib/core-api";

export const dynamic = "force-dynamic";

const notificationRows = [
  { title: "Ежедневные сводки", description: "Короткий обзор по ключевым событиям за день" },
  { title: "Системные уведомления", description: "Сообщения о статусе синхронизации и доступе" },
  { title: "Напоминания", description: "Напоминания о задачах и важных действиях" },
];

const appearanceRows = [
  { title: "Тема", value: "Светлая" },
  { title: "Плотность интерфейса", value: "Стандартная" },
  { title: "Язык", value: "Русский" },
  { title: "Часовой пояс", value: "Asia/Tashkent" },
];

const securityRows = [
  { title: "Двухфакторная аутентификация", value: "Включить" },
  { title: "Активные сессии", value: "3 устройства" },
  { title: "Смена пароля", value: "Доступно" },
];

export default function Page() {
  const router = useRouter();
  const [liveSync, setLiveSync] = useState<SmartUpLiveSyncStatus | null>(null);

  useEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: "auto" });
  }, []);

  useEffect(() => {
    let active = true;
    const refresh = () => {
      void getSmartUpLiveSyncStatus()
        .then((status) => {
          if (active) setLiveSync(status);
        })
        .catch(() => undefined);
    };
    refresh();
    const interval = window.setInterval(refresh, 30_000);
    return () => {
      active = false;
      window.clearInterval(interval);
    };
  }, []);

  const logout = () => {
    document.cookie = "aibos_owner_session=; Path=/; Max-Age=0; SameSite=Lax";
    router.replace("/login");
  };

  return (
    <section className="space-y-6">
      <Surface className="overflow-hidden">
        <div className="min-h-0 rounded-[28px] bg-[#2E3137] p-6 sm:p-7 lg:p-8">
          <div className="flex flex-col gap-6 xl:flex-row xl:items-end xl:justify-between">
            <div className="max-w-3xl space-y-3">
              <p className="text-xs uppercase tracking-[0.32em] text-slate-400">Настройки</p>
              <h1 className="text-3xl font-semibold tracking-[-0.04em] text-[#f4f7fb] sm:text-[34px]">
                Общие параметры профиля и интерфейса
              </h1>
              <p className="max-w-2xl text-sm leading-6 text-slate-400 sm:text-[15px]">
                Здесь настраиваются базовые параметры работы платформы: профиль, уведомления,
                внешний вид и безопасность. Все блоки адаптируются под ширину экрана и не
                оставляют пустых областей справа.
              </p>
            </div>

            <div className="flex flex-wrap gap-3">
              <Button variant="secondary">Сбросить изменения</Button>
              <Button variant="primary">Сохранить настройки</Button>
              <Button variant="ghost" onClick={logout}>Выйти</Button>
            </div>
          </div>
        </div>
      </Surface>

      <MobileAccessCard />


      <div className="grid gap-6">
        <div className="grid gap-6">
          <Surface>
            <div className="min-h-0 rounded-[28px] bg-[#2E3137] p-6 sm:p-7">
              <div className="flex items-start justify-between gap-4">
                <div className="space-y-2">
                  <p className="text-xs uppercase tracking-[0.32em] text-slate-400">Уведомления</p>
                  <h2 className="text-2xl font-semibold tracking-[-0.04em] text-[#f4f7fb]">
                    Что показывать
                  </h2>
                </div>
                <Button variant="soft" size="sm">
                  Настроить
                </Button>
              </div>

              <div className="mt-5 space-y-3">
                {notificationRows.map((row) => (
                  <SettingRow key={row.title} title={row.title} description={row.description} />
                ))}
              </div>
            </div>
          </Surface>

          <Surface>
            <div className="min-h-0 rounded-[28px] bg-[#2E3137] p-6 sm:p-7">
              <div className="space-y-2">
                <p className="text-xs uppercase tracking-[0.32em] text-slate-400">Интерфейс</p>
                <h2 className="text-2xl font-semibold tracking-[-0.04em] text-[#f4f7fb]">
                  Внешний вид
                </h2>
              </div>

              <div className="mt-5 grid gap-3 sm:grid-cols-2">
                {appearanceRows.map((row) => (
                  <div key={row.title} className="rounded-2xl border border-[#3a3d43] bg-[#343840] px-4 py-4">
                    <p className="text-xs uppercase tracking-[0.24em] text-slate-400">{row.title}</p>
                    <p className="mt-2 text-sm font-medium text-slate-200">{row.value}</p>
                  </div>
                ))}
              </div>
            </div>
          </Surface>
        </div>
      </div>

      <div className="grid gap-6 xl:grid-cols-[0.95fr_1.05fr]">
        <Surface>
          <div className="min-h-0 rounded-[28px] bg-[#2E3137] p-6 sm:p-7">
            <div className="space-y-2">
              <p className="text-xs uppercase tracking-[0.32em] text-slate-400">Безопасность</p>
              <h2 className="text-2xl font-semibold tracking-[-0.04em] text-[#f4f7fb]">
                Доступ и защита
              </h2>
            </div>

            <div className="mt-5 space-y-3">
              {securityRows.map((row) => (
                <div
                  key={row.title}
                  className="flex items-center justify-between rounded-2xl border border-[#3a3d43] bg-[#2E3137] px-4 py-4"
                >
                  <div>
                    <p className="text-sm font-medium text-slate-200">{row.title}</p>
                    <p className="mt-1 text-sm text-slate-400">{row.value}</p>
                  </div>
                  <span className="h-3 w-3 rounded-full bg-emerald-500" />
                </div>
              ))}
            </div>
          </div>
        </Surface>

        <Surface>
          <div className="min-h-0 rounded-[28px] bg-[#2E3137] p-6 sm:p-7">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
              <div className="space-y-2">
                <p className="text-xs uppercase tracking-[0.32em] text-slate-400">Рабочие параметры</p>
                <h2 className="text-2xl font-semibold tracking-[-0.04em] text-[#f4f7fb]">
                  Автосохранение и поведение
                </h2>
              </div>
              <Button variant="secondary" size="sm">
                Проверить соединение
              </Button>
            </div>

            <div className="mt-5 grid gap-3 md:grid-cols-2">
              <CompactPanel title="Автосохранение" value="Включено" note="Настройки сохраняются автоматически" />
              <CompactPanel title="Окружение" value="Рабочее" note="Основная рабочая среда" />
              <CompactPanel title="Обновления" value="Авто" note="Интерфейс обновляется в фоне" />
              <CompactPanel title="Сессия" value="12 ч" note="Срок активности пользователя" />
            </div>
          </div>
        </Surface>
      </div>

      <Surface>
        <div className="min-h-0 rounded-[28px] bg-[#2E3137] p-6 sm:p-7">
          <div className="flex flex-col gap-5 lg:flex-row lg:items-center lg:justify-between">
            <div className="space-y-2">
              <p className="text-xs uppercase tracking-[0.32em] text-slate-400">Интеграции</p>
              <h2 className="text-2xl font-semibold tracking-[-0.04em] text-[#f4f7fb]">SmartUp</h2>
              <p className="max-w-2xl text-sm leading-6 text-slate-400">
                Отдельная страница для подключения SmartUp, проверки доступа и запуска
                синхронизации по организациям.
              </p>
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <div className="rounded-2xl border border-[#3a3d43] bg-[#343840] px-4 py-3">
                <div className="flex items-center gap-2">
                  <span className={`h-2.5 w-2.5 rounded-full ${liveSync?.status === "running" ? "bg-yellow-300" : liveSync?.status === "success" ? "bg-emerald-400" : liveSync?.status === "error" ? "bg-rose-400" : "bg-slate-500"}`} />
                  <p className="text-sm font-medium text-slate-200">
                    {liveSync?.status === "running" ? "Live-синхронизация выполняется" : liveSync?.status === "success" ? "Live-синхронизация активна" : liveSync?.status === "error" ? "Ошибка live-синхронизации" : "Статус live-синхронизации загружается"}
                  </p>
                </div>
                <p className="mt-1 text-xs text-slate-400">
                  {liveSync?.last_success_at ? `Последний успех: ${formatDateTime(liveSync.last_success_at)}` : "Ожидание первого успешного запуска"}
                </p>
              </div>
              <Link
                href="/settings/integrations/smartup"
                className="inline-flex h-11 items-center justify-center rounded-full bg-slate-950 px-4 text-sm font-medium text-white transition hover:bg-slate-800"
              >
                Открыть SmartUp
              </Link>
            </div>
          </div>
        </div>
      </Surface>

      <AiRoutingSettings />
    </section>
  );
}

function formatDateTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("ru-RU", {
    timeZone: "Asia/Tashkent",
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function SettingRow({ title, description }: { title: string; description: string }) {
  return (
    <div className="flex items-center justify-between gap-4 rounded-2xl border border-[#3a3d43] bg-[#343840] px-4 py-4">
      <div className="min-w-0">
        <p className="text-sm font-medium text-slate-200">{title}</p>
        <p className="mt-1 text-sm leading-6 text-slate-400">{description}</p>
      </div>
      <button
        type="button"
        className="flex h-6 w-11 items-center rounded-full bg-[#1E1E21] p-0.5 transition hover:bg-[#3a3d43]"
        aria-label={title}
      >
        <span className="h-5 w-5 rounded-full bg-[#2E3137] shadow-sm" />
      </button>
    </div>
  );
}

function CompactPanel({
  title,
  value,
  note,
}: {
  title: string;
  value: string;
  note: string;
}) {
  return (
    <div className="rounded-2xl border border-[#3a3d43] bg-[#343840] px-4 py-4">
      <p className="text-xs uppercase tracking-[0.24em] text-slate-400">{title}</p>
      <p className="mt-2 text-lg font-semibold tracking-[-0.03em] text-[#f4f7fb]">{value}</p>
      <p className="mt-1 text-sm leading-6 text-slate-400">{note}</p>
    </div>
  );
}
