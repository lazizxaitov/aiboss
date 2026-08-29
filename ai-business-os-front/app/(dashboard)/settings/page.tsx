"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { Component, type ErrorInfo, type ReactNode, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Surface } from "@/components/ui/surface";
import { AiRoutingSettings } from "@/components/settings/ai-routing-settings";
import { MobileAccessCard } from "@/components/settings/mobile-access-card";
import { useOwnerSessionState } from "@/components/auth/session-lock-guard";
import {
  getSmartUpLiveSyncStatus,
  getSessionLockSettings,
  saveSessionLockSettings,
  getSystemUpdateJob,
  getSystemUpdateStatus,
  installSystemUpdate,
  type SmartUpLiveSyncStatus,
  type SystemUpdateJob,
  type SystemUpdateStatus,
} from "@/lib/core-api";

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
  const session = useOwnerSessionState();
  const [liveSync, setLiveSync] = useState<SmartUpLiveSyncStatus | null>(null);

  useEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: "auto" });
  }, []);

  useEffect(() => {
    if (!session.hydrated || !session.authenticated || session.locked) return;
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
  }, [session.hydrated, session.authenticated, session.locked]);

  const logout = () => {
    const cookie = document.cookie.split(";").map((item) => item.trim()).find((item) => item.startsWith("aibos_owner_session="));
    const token = cookie?.slice("aibos_owner_session=".length) ?? "";
    void fetch(`${process.env.NEXT_PUBLIC_CORE_API_URL ?? "http://127.0.0.1:8000"}/api/v1/auth/logout`, {
      method: "POST",
      headers: { Authorization: `Bearer ${decodeURIComponent(token)}` },
    }).finally(() => {
      document.cookie = "aibos_owner_session=; Path=/; Max-Age=0; SameSite=Lax";
      router.replace("/login");
    });
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

      <SettingsBlockBoundary fallback="Не удалось загрузить мобильный доступ.">
        <MobileAccessCard />
      </SettingsBlockBoundary>

      <SettingsBlockBoundary fallback="Не удалось загрузить обновление системы.">
        <SystemUpdateCard />
      </SettingsBlockBoundary>


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
              <AutoLockSetting />
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
                  <span className={`h-2.5 w-2.5 rounded-full ${liveSync?.status === "initial_sync_required" || liveSync?.status === "initial_sync_running" || liveSync?.status === "live_sync_running" || liveSync?.status === "running" || liveSync?.status === "retry_wait" ? "bg-yellow-300" : liveSync?.status === "ready" || liveSync?.status === "success" ? "bg-emerald-400" : liveSync?.status === "error" ? "bg-rose-400" : "bg-slate-500"}`} />
                  <p className="text-sm font-medium text-slate-200">
                    {liveSync?.status === "not_configured" ? "SmartUp не настроен" : liveSync?.status === "initial_sync_required" || liveSync?.status === "initial_sync_running" ? "Первичная синхронизация SmartUp" : liveSync?.status === "live_sync_running" || liveSync?.status === "running" ? "Обновление данных SmartUp" : liveSync?.status === "retry_wait" ? "Временно нет связи со SmartUp" : liveSync?.status === "ready" || liveSync?.status === "success" ? "SmartUp подключён" : liveSync?.status === "error" ? "Ошибка подключения SmartUp" : "Статус SmartUp загружается"}
                  </p>
                </div>
                <p className="mt-1 text-xs text-slate-400">
                  {liveSync?.status === "initial_sync_required" || liveSync?.status === "initial_sync_running" ? "Загружаем данные..." : liveSync?.status === "retry_wait" ? "Используются последние сохранённые данные. Повторное подключение выполняется автоматически." : liveSync?.last_success_at ? `Последний успех: ${formatDateTime(liveSync.last_success_at)}` : liveSync?.status === "ready" || liveSync?.status === "success" ? "Данные готовы, синхронизация запланирована" : liveSync?.status === "not_configured" ? "Сохраните credentials и организации SmartUp" : "Сервис запускается автоматически"}
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

      <SettingsBlockBoundary fallback="Не удалось загрузить настройки ИИ">
        <AiRoutingSettings />
      </SettingsBlockBoundary>
    </section>
  );
}

type SettingsBlockBoundaryProps = { children: ReactNode; fallback: string };
type SettingsBlockBoundaryState = { hasError: boolean };

class SettingsBlockBoundary extends Component<SettingsBlockBoundaryProps, SettingsBlockBoundaryState> {
  state: SettingsBlockBoundaryState = { hasError: false };

  static getDerivedStateFromError(): SettingsBlockBoundaryState {
    return { hasError: true };
  }

  componentDidCatch(_error: Error, _info: ErrorInfo) {
    // Keep a malformed optional Settings block from taking down the page.
  }

  render() {
    return this.state.hasError ? <p className="rounded-[28px] bg-[#2E3137] p-6 text-sm text-slate-300">{this.props.fallback}</p> : this.props.children;
  }
}

function AutoLockSetting() {
  const session = useOwnerSessionState();
  const [minutes, setMinutes] = useState(5);
  const [notice, setNotice] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!session.hydrated || !session.authenticated || session.locked) return;
    void getSessionLockSettings()
      .then((settings) => setMinutes(settings.timeout_minutes))
      .catch(() => undefined);
  }, [session.hydrated, session.authenticated, session.locked]);

  const save = async () => {
    setSaving(true);
    setNotice(null);
    try {
      const settings = await saveSessionLockSettings(minutes);
      setMinutes(settings.timeout_minutes);
      setNotice("Сохранено");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Не удалось сохранить");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="rounded-2xl border border-[#3a3d43] bg-[#2E3137] px-4 py-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-slate-200">Автоблокировка</p>
          <p className="mt-1 text-sm text-slate-400">Заблокировать сессию после периода бездействия</p>
        </div>
        <div className="flex items-center gap-2">
          <input
            type="number"
            min={1}
            max={1440}
            value={minutes}
            onChange={(event) => setMinutes(Math.max(1, Math.min(1440, Number(event.target.value) || 1)))}
            className="h-10 w-20 rounded-xl border border-[#3a3d43] bg-[#343840] px-3 text-center text-sm text-slate-200 outline-none focus:border-[#FFF27A]"
          />
          <span className="text-sm text-slate-400">мин.</span>
          <Button variant="secondary" size="sm" onClick={save} disabled={saving}>
            {saving ? "Сохранение..." : "Сохранить"}
          </Button>
        </div>
      </div>
      {notice ? <p className="mt-2 text-xs text-slate-400">{notice}</p> : null}
    </div>
  );
}

const updateStageLabels: Record<string, string> = {
  checking: "Проверка",
  downloading: "Загрузка из GitHub",
  backend_dependencies: "Зависимости backend",
  frontend_dependencies: "Зависимости приложения",
  app_build: "Сборка приложения",
  install: "Установка приложения",
  restarting: "Перезапуск сервисов",
  completed: "Завершено",
  rollback: "Откат версии",
  failed: "Ошибка",
};

function SystemUpdateCard() {
  const session = useOwnerSessionState();
  const [systemStatus, setSystemStatus] = useState<SystemUpdateStatus | null>(null);
  const [job, setJob] = useState<SystemUpdateJob | null>(null);
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const pollTimerRef = useRef<number | null>(null);

  const checkForUpdates = async () => {
    if (!session.hydrated || !session.authenticated || session.locked) return;
    setLoading(true);
    setNotice(null);
    try {
      setSystemStatus(await getSystemUpdateStatus());
    } catch (error) {
      const message = error instanceof Error ? error.message : "";
      setNotice(message.includes(" 401") ? "Ожидается восстановление авторизации." : message.includes(" 423") ? "Сессия заблокирована. Разблокируйте её, чтобы проверить обновления." : message || "Не удалось проверить обновления.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!session.hydrated || !session.authenticated || session.locked) return;
    void checkForUpdates();
  }, [session.hydrated, session.authenticated, session.locked]);

  useEffect(() => {
    if (!job || job.status !== "running" || !session.hydrated || !session.authenticated || session.locked) return;
    let active = true;
    const poll = async () => {
      try {
        const next = await getSystemUpdateJob(job.job_id);
        if (!active) return;
        setJob(next);
        if (next.status === "running") pollTimerRef.current = window.setTimeout(poll, 4000);
        else if (next.status === "success") setNotice("Обновление установлено");
      } catch {
        if (active) pollTimerRef.current = window.setTimeout(poll, 5000);
      }
    };
    pollTimerRef.current = window.setTimeout(poll, 1500);
    return () => {
      active = false;
      if (pollTimerRef.current !== null) window.clearTimeout(pollTimerRef.current);
      pollTimerRef.current = null;
    };
  }, [job, session.hydrated, session.authenticated, session.locked]);

  const install = async () => {
    if (!session.hydrated || !session.authenticated || session.locked) return;
    setLoading(true);
    setNotice(null);
    try {
      setJob(await installSystemUpdate());
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Не удалось запустить обновление.");
    } finally {
      setLoading(false);
    }
  };

  const running = job?.status === "running";
  return (
    <Surface>
      <div className="rounded-[28px] bg-[#2E3137] p-6 sm:p-7">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="space-y-2">
            <p className="text-xs uppercase tracking-[0.32em] text-slate-400">Система</p>
            <h2 className="text-2xl font-semibold tracking-[-0.04em] text-[#f4f7fb]">Обновление системы</h2>
            <p className="text-sm text-slate-400">
              {job ? `${updateStageLabels[job.stage] ?? job.stage}: ${job.message}` : notice ?? (!session.hydrated ? "Проверяем авторизацию..." : session.locked ? "Сессия заблокирована. Разблокируйте её для доступа к обновлениям." : !session.authenticated ? "Требуется авторизация владельца." : "Проверяйте и устанавливайте обновления из GitHub.")}
            </p>
          </div>
          <div className="flex flex-wrap gap-3">
            <Button variant="secondary" size="sm" onClick={() => void checkForUpdates()} disabled={loading || running}>
              {loading ? "Проверяем..." : "Проверить обновления"}
            </Button>
            <Button variant="primary" size="sm" onClick={() => void install()} disabled={loading || running || !systemStatus?.update_available}>
              {running ? "Обновление выполняется..." : "Обновить систему"}
            </Button>
          </div>
        </div>
        <div className="mt-5 grid gap-3 sm:grid-cols-3">
          <UpdateValue title="Текущая версия" value={systemStatus?.current_version ?? "—"} />
          <UpdateValue title="Последняя версия" value={systemStatus?.latest_version ?? "—"} />
          <UpdateValue title="Статус" value={systemStatus ? (systemStatus.update_available ? "Доступно обновление" : "Версия актуальна") : "Проверяется"} />
        </div>
        {job?.previous_commit || job?.target_commit ? (
          <p className="mt-3 text-xs text-slate-400">
            Commit: текущий {job.current_version ?? "—"} · целевой {job.target_version ?? "—"}
          </p>
        ) : null}
        {systemStatus?.last_successful_update_at ? (
          <p className="mt-4 text-xs text-slate-400">Последнее успешное обновление: {formatDateTime(systemStatus.last_successful_update_at)}</p>
        ) : null}
        {job?.status === "failed" ? <p className="mt-3 text-sm text-rose-200">{job.error ?? job.message}</p> : null}
      </div>
    </Surface>
  );
}

function UpdateValue({ title, value }: { title: string; value: string }) {
  return (
    <div className="rounded-2xl border border-[#3a3d43] bg-[#343840] px-4 py-3">
      <p className="text-xs uppercase tracking-[0.2em] text-slate-400">{title}</p>
      <p className="mt-1 truncate text-sm font-medium text-slate-200">{value}</p>
    </div>
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
