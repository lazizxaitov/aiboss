"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Surface } from "@/components/ui/surface";
import { cn } from "@/lib/cn";
import {
  getCachedSmartUpOrganizations,
  getSmartUpMigrationCompleteness,
  getSmartUpMigrationJob,
  getSmartUpOrganizations,
  resetSmartUpImportedData,
  startSmartUpMigrationJob,
  testSmartUpOrganizationConnection,
  type SmartUpAccessPayload,
  type SmartUpCompletenessReport,
  type SmartUpMigrationJobResponse,
  type SmartUpMigrationMode,
  type SmartUpOrganization,
  type SmartUpConnectionCheckResponse,
  type SmartUpResetResponse,
} from "@/lib/core-api";

const DEFAULT_BASE_URL = "https://smartup.online";

type RequestState = {
  status: "idle" | "loading" | "success" | "error";
  message: string;
  response?:
    | SmartUpConnectionCheckResponse
    | SmartUpMigrationJobResponse
    | SmartUpCompletenessReport
    | SmartUpResetResponse
    | null;
};

type FormState = {
  baseUrl: string;
  username: string;
  password: string;
  timeoutSeconds: string;
};

function formatTashkentDateTime(value: string | null | undefined) {
  if (!value) return "—";
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

function redactMessage(message: string) {
  return message.replaceAll(/\b(password|authorization|cookie|jsessionid|token)\b/gi, "•••");
}

export function SmartUpIntegrationPage() {
  const cachedOrganizations = getCachedSmartUpOrganizations();
  const [organizations, setOrganizations] = useState<SmartUpOrganization[]>(() => cachedOrganizations ?? []);
  const [selectedOrganizationId, setSelectedOrganizationId] = useState<string>(() => {
    const initialOrganization = cachedOrganizations?.find((item) => item.is_active) ?? cachedOrganizations?.[0] ?? null;
    return initialOrganization?.id ?? "";
  });
  const [form, setForm] = useState<FormState>({
    baseUrl: DEFAULT_BASE_URL,
    username: "",
    password: "",
    timeoutSeconds: "30",
  });
  const [connectionState, setConnectionState] = useState<RequestState>({ status: "idle", message: "" });
  const [syncState, setSyncState] = useState<RequestState>({ status: "idle", message: "" });
  const [completeness, setCompleteness] = useState<SmartUpCompletenessReport | null>(null);
  const [job, setJob] = useState<SmartUpMigrationJobResponse | null>(null);
  const [loadingOrganizations, setLoadingOrganizations] = useState<boolean>(() => cachedOrganizations === null);
  const [organizationsError, setOrganizationsError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    const load = async () => {
      try {
        const [items, report] = await Promise.all([
          getSmartUpOrganizations(),
          getSmartUpMigrationCompleteness().catch(() => null),
        ]);
        if (!active) return;
        setOrganizations(items);
        setCompleteness(report);
        setOrganizationsError(null);
        setSelectedOrganizationId((current) => current || items.find((item) => item.is_active)?.id || items[0]?.id || "");
      } catch (error) {
        if (!active) return;
        setCompleteness(null);
        setOrganizationsError(
          error instanceof Error ? redactMessage(error.message) : "Не удалось загрузить организации SmartUp.",
        );
        setConnectionState({
          status: "error",
          message:
            error instanceof Error
              ? `Не удалось загрузить организации SmartUp: ${redactMessage(error.message)}`
              : "Не удалось загрузить организации SmartUp.",
        });
      } finally {
        if (active) setLoadingOrganizations(false);
      }
    };

    void load();

    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!job || !["pending", "running"].includes(job.status)) return;

    let active = true;
    const interval = window.setInterval(() => {
      void getSmartUpMigrationJob(job.job_id)
        .then((response) => {
          if (!active) return;
          setJob(response);
        })
        .catch(() => {
          // Keep last known job state if polling fails.
        });
    }, 2500);

    return () => {
      active = false;
      window.clearInterval(interval);
    };
  }, [job]);

  const selectedOrganization = useMemo(
    () => organizations.find((item) => item.id === selectedOrganizationId) ?? organizations[0] ?? null,
    [organizations, selectedOrganizationId],
  );

  const activeCount = organizations.filter((item) => item.is_active).length;
  const inactiveCount = organizations.length - activeCount;
  const latestSync = useMemo(() => {
    const timestamps = organizations
      .map((item) => item.last_sync_at)
      .filter((value): value is string => Boolean(value));
    if (!timestamps.length) return null;
    return timestamps.sort((a, b) => Date.parse(b) - Date.parse(a))[0];
  }, [organizations]);

  const makePayload = (): SmartUpAccessPayload => ({
    base_url: form.baseUrl.trim() || DEFAULT_BASE_URL,
    username: form.username,
    password: form.password,
    timeout_seconds: Number.isFinite(Number(form.timeoutSeconds)) ? Number(form.timeoutSeconds) : 30,
  });

  const refreshStatus = async () => {
    try {
      const report = await getSmartUpMigrationCompleteness().catch(() => null);
      setCompleteness(report);
      const updatedOrganizations = await getSmartUpOrganizations({ forceRefresh: true });
      setOrganizations(updatedOrganizations);
      setOrganizationsError(null);
      if (selectedOrganizationId && !updatedOrganizations.some((item) => item.id === selectedOrganizationId)) {
        setSelectedOrganizationId(updatedOrganizations.find((item) => item.is_active)?.id || updatedOrganizations[0]?.id || "");
      }
    } catch (error) {
      setOrganizationsError(
        error instanceof Error ? redactMessage(error.message) : "Не удалось обновить организации SmartUp.",
      );
    }
  };

  const runConnectionTest = async () => {
    if (!selectedOrganization) {
      setConnectionState({
        status: "error",
        message: "Сначала выберите организацию SmartUp.",
      });
      return;
    }

    setConnectionState({
      status: "loading",
      message: `Проверяем подключение для ${selectedOrganization.name}...`,
    });

    try {
      const response = await testSmartUpOrganizationConnection(selectedOrganization.id, makePayload());
      setConnectionState({
        status: response.connected ? "success" : "error",
        message: response.connected
          ? "Подключение успешно проверено и сохранено."
          : redactMessage(response.message),
        response,
      });
      await refreshStatus();
    } catch (error) {
      setConnectionState({
        status: "error",
        message: error instanceof Error ? redactMessage(error.message) : "Не удалось проверить подключение.",
      });
    }
  };

  const runMigration = async (migrationMode: SmartUpMigrationMode) => {
    setSyncState({
      status: "loading",
      message:
        migrationMode === "weekly_reconciliation"
          ? "Запускаем недельную синхронизацию всех активных организаций..."
          : "Запускаем полную синхронизацию всех активных организаций...",
    });

    try {
      const response = await startSmartUpMigrationJob({
        ...makePayload(),
        migration_mode: migrationMode,
      });
      setJob(response);
      setSyncState({
        status: "success",
        message: response.message,
        response,
      });
      await refreshStatus();
    } catch (error) {
      setSyncState({
        status: "error",
        message: error instanceof Error ? redactMessage(error.message) : "Не удалось запустить синхронизацию.",
      });
    }
  };

  const resetImportedData = async () => {
    const confirmed = window.confirm(
      "Удалить все загруженные SmartUp данные? Организации и настройки подключения останутся.",
    );
    if (!confirmed) return;

    setSyncState({
      status: "loading",
      message: "Удаляем все загруженные данные SmartUp...",
    });

    try {
      const response = await resetSmartUpImportedData();
      setSyncState({
        status: "success",
        message: response.message,
        response,
      });
      await refreshStatus();
    } catch (error) {
      setSyncState({
        status: "error",
        message: error instanceof Error ? redactMessage(error.message) : "Не удалось удалить данные.",
      });
    }
  };

  return (
    <section className="space-y-6">
      <Surface>
        <div className="min-h-0 rounded-[28px] bg-[#2E3137] p-6 sm:p-7 lg:p-8">
          <div className="flex flex-col gap-6 xl:flex-row xl:items-end xl:justify-between">
            <div className="max-w-3xl space-y-3">
              <p className="text-xs uppercase tracking-[0.32em] text-slate-400">Интеграции</p>
              <h1 className="text-3xl font-semibold tracking-[-0.04em] text-[#f4f7fb] sm:text-[34px]">
                SmartUp
              </h1>
              <p className="max-w-2xl text-sm leading-6 text-slate-400 sm:text-[15px]">
                Подключение организаций, проверка доступа и запуск синхронизации выполняются
                здесь. Данные сохраняются по организациям и не смешиваются между филиалами.
              </p>
            </div>

            <div className="flex flex-wrap gap-3">
              <Link
                href="/settings"
                className="inline-flex h-11 items-center justify-center rounded-full border border-[#3a3d43] bg-[#2E3137] px-4 text-sm font-medium text-slate-200 transition hover:border-[#4a4e56] hover:text-[#f4f7fb]"
              >
                К общим настройкам
              </Link>
              <Button variant="soft" size="md" onClick={() => void refreshStatus()} disabled={loadingOrganizations}>
                Обновить статус
              </Button>
            </div>
          </div>
        </div>
      </Surface>

      <div className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <Surface>
          <div className="min-h-0 rounded-[28px] bg-[#2E3137] p-6 sm:p-7">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
              <div className="space-y-2">
                <p className="text-xs uppercase tracking-[0.32em] text-slate-400">Подключение</p>
                <h2 className="text-2xl font-semibold tracking-[-0.04em] text-[#f4f7fb]">
                  Логин и пароль SmartUp
                </h2>
                <p className="max-w-2xl text-sm leading-6 text-slate-400">
                  Сохранение выполняется после успешной проверки. Настройки закрепляются за
                  выбранной организацией.
                </p>
              </div>

              <Badge variant="soft">
                {selectedOrganization ? selectedOrganization.name : "Организация не выбрана"}
              </Badge>
            </div>

            <div className="mt-6 grid gap-4 md:grid-cols-2">
              <label className="space-y-2 md:col-span-2">
                <span className="text-sm font-medium text-slate-200">Организация</span>
              <select
                value={selectedOrganizationId}
                onChange={(event) => setSelectedOrganizationId(event.target.value)}
                className="h-11 w-full rounded-2xl border border-[#3a3d43] bg-[#2E3137] px-4 text-sm text-[#f4f7fb] outline-none transition focus:border-yellow-300 focus:ring-4 focus:ring-yellow-100"
              >
                {loadingOrganizations ? (
                  <option value="">Загрузка организаций...</option>
                ) : organizationsError && organizations.length === 0 ? (
                  <option value="">Не удалось загрузить организации</option>
                ) : null}
                {organizations.map((organization) => (
                  <option key={organization.id} value={organization.id}>
                    {organization.name} · {organization.filial_id}
                  </option>
                  ))}
                </select>
              </label>
              <label className="space-y-2 md:col-span-2">
                <span className="text-sm font-medium text-slate-200">Base URL</span>
                <Input
                  value={form.baseUrl}
                  onChange={(event) =>
                    setForm((current) => ({ ...current, baseUrl: event.target.value }))
                  }
                  placeholder="https://smartup.online"
                />
              </label>
              <label className="space-y-2">
                <span className="text-sm font-medium text-slate-200">Login</span>
                <Input
                  value={form.username}
                  onChange={(event) =>
                    setForm((current) => ({ ...current, username: event.target.value }))
                  }
                  placeholder="username"
                />
              </label>
              <label className="space-y-2">
                <span className="text-sm font-medium text-slate-200">Password</span>
                <Input
                  type="password"
                  value={form.password}
                  onChange={(event) =>
                    setForm((current) => ({ ...current, password: event.target.value }))
                  }
                  placeholder="password"
                />
              </label>
            </div>

            <div className="mt-6 flex flex-wrap gap-3">
              <Button variant="primary" onClick={() => void runConnectionTest()} disabled={!selectedOrganization || loadingOrganizations}>
                Сохранить
              </Button>
              <Button variant="secondary" onClick={() => void runConnectionTest()} disabled={!selectedOrganization || loadingOrganizations}>
                Проверить подключение
              </Button>
              <Button variant="ghost" onClick={() => setForm({ baseUrl: DEFAULT_BASE_URL, username: "", password: "", timeoutSeconds: "30" })}>
                Очистить форму
              </Button>
            </div>

            {connectionState.status !== "idle" ? (
              <div
                className={cn(
                  "mt-6 rounded-[24px] border px-4 py-4",
                  connectionState.status === "success"
                    ? "border-[#244037] bg-[#244037]"
                    : connectionState.status === "error"
                      ? "border-[#40272c] bg-[#40272c]"
                      : "border-[#3a3d43] bg-[#343840]",
                )}
              >
                <p className="text-sm font-medium text-[#f4f7fb]">{connectionState.message}</p>
                {connectionState.response ? (
                  <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                    {[
                      ["connected", String((connectionState.response as SmartUpConnectionCheckResponse).connected)],
                      ["code", (connectionState.response as SmartUpConnectionCheckResponse).code ?? "—"],
                      ["status", String((connectionState.response as SmartUpConnectionCheckResponse).upstream_status ?? "—")],
                      ["organization", (connectionState.response as SmartUpConnectionCheckResponse).organization_name ?? "—"],
                      ["filial_id", (connectionState.response as SmartUpConnectionCheckResponse).filial_id ?? "—"],
                      ["project_code", (connectionState.response as SmartUpConnectionCheckResponse).project_code ?? "—"],
                    ].map(([label, value]) => (
                      <div key={label} className="rounded-2xl border border-[#3a3d43]/70 bg-[#2E3137] px-4 py-3 shadow-sm">
                        <p className="text-xs uppercase tracking-[0.24em] text-slate-400">{label}</p>
                        <p className="mt-1 text-sm font-medium text-slate-200">{value}</p>
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>
        </Surface>

        <Surface>
          <div className="min-h-0 rounded-[28px] bg-[#2E3137] p-6 sm:p-7">
            <div className="flex items-start justify-between gap-4">
              <div className="space-y-2">
                <p className="text-xs uppercase tracking-[0.32em] text-slate-400">Live Sync</p>
                <h2 className="text-2xl font-semibold tracking-[-0.04em] text-[#f4f7fb]">
                  Статус синхронизации
                </h2>
              </div>
              <Badge variant={job?.status === "running" ? "accent" : job?.status === "failed" ? "dark" : "soft"}>
                {job?.status ?? "готово"}
              </Badge>
            </div>

            <div className="mt-5 grid gap-3 sm:grid-cols-2">
              <InfoPanel title="Активных организаций" value={String(activeCount)} note={`${inactiveCount} отключено`} />
              <InfoPanel title="Последняя синхронизация" value={formatTashkentDateTime(latestSync)} note="по организациям SmartUp" />
              <InfoPanel
                title="Последний запуск"
                value={job ? job.message : "Нет активного задания"}
                note={job ? `job ${job.job_id.slice(0, 8)} · ${job.migration_mode}` : "Недельная и полная синхронизация запускаются вручную"}
                className="sm:col-span-2"
              />
            </div>

            <div className="mt-6 grid gap-3 sm:grid-cols-2">
              <Button variant="soft" onClick={() => void runMigration("weekly_reconciliation")} disabled={loadingOrganizations || organizations.length === 0}>
                Недельная синхронизация
              </Button>
              <Button variant="secondary" onClick={() => void runMigration("full_backfill")} disabled={loadingOrganizations || organizations.length === 0}>
                Синхронизация всей базы
              </Button>
              <Button
                variant="danger"
                onClick={() => void resetImportedData()}
                disabled={loadingOrganizations}
                className="sm:col-span-2"
              >
                Удалить все загруженные данные
              </Button>
            </div>

            <p className="mt-4 text-sm leading-6 text-slate-400">
              Запуск обрабатывает все активные организации. Если у одной организации нет доступа,
              это не останавливает остальные.
            </p>

            {syncState.status !== "idle" ? (
              <div
                className={cn(
                  "mt-6 rounded-[24px] border px-4 py-4",
                  syncState.status === "success"
                    ? "border-[#244037] bg-[#244037]"
                    : syncState.status === "error"
                      ? "border-[#40272c] bg-[#40272c]"
                      : "border-[#3a3d43] bg-[#343840]",
                )}
              >
                <p className="text-sm font-medium text-[#f4f7fb]">{syncState.message}</p>
                {job ? (
                  <div className="mt-3 grid gap-3 sm:grid-cols-2">
                    <MiniStat title="Job" value={job.job_id.slice(0, 12)} />
                    <MiniStat title="Старт" value={formatTashkentDateTime(job.started_at)} />
                    <MiniStat title="Завершение" value={formatTashkentDateTime(job.completed_at)} />
                    <MiniStat title="Организаций" value={`${job.progress_organizations}/${job.total_organizations}`} />
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>
        </Surface>
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
        <Surface>
          <div className="min-h-0 rounded-[28px] bg-[#2E3137] p-6 sm:p-7">
            <div className="flex items-start justify-between gap-4">
              <div className="space-y-2">
                <p className="text-xs uppercase tracking-[0.32em] text-slate-400">Организации</p>
                <h2 className="text-2xl font-semibold tracking-[-0.04em] text-[#f4f7fb]">
                  SMARTUP_ORGANIZATIONS
                </h2>
              </div>
              <Badge variant="soft">{organizations.length}</Badge>
            </div>

            <div className="mt-5 grid gap-3">
              {organizations.length > 0 ? (
                organizations.map((organization) => {
                  const active = organization.id === selectedOrganizationId;
                  return (
                    <button
                      key={organization.id}
                      type="button"
                      onClick={() => setSelectedOrganizationId(organization.id)}
                      className={cn(
                        "rounded-[24px] border p-4 text-left transition",
                        active
                          ? "border-[#FFF27A]/30 bg-[#343840] shadow-[0_14px_40px_rgba(0,0,0,0.18)]"
                          : "border-[#3a3d43] bg-[#2E3137] hover:border-[#4a4e56]",
                      )}
                    >
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <div>
                          <p className="text-base font-semibold tracking-[-0.02em] text-[#f4f7fb]">
                            {organization.name}
                          </p>
                          <p className="mt-1 text-sm text-slate-400">
                            filial_id {organization.filial_id} · company_id {organization.company_id}
                          </p>
                        </div>
                        <div className="flex items-center gap-2">
                          <Badge variant={organization.is_active ? "accent" : "soft"}>
                            {organization.is_active ? "Активна" : "Неактивна"}
                          </Badge>
                          <Badge variant="neutral">{organization.project_code}</Badge>
                        </div>
                      </div>

                      <div className="mt-4 grid gap-3 sm:grid-cols-3">
                        <InfoPanel
                          title="Последний запуск"
                          value={formatTashkentDateTime(organization.last_sync_at)}
                          note="по SmartUp"
                          compact
                        />
                        <InfoPanel
                          title="Integration"
                          value={organization.integration_id.slice(0, 8)}
                          note="связка с ядром"
                          compact
                        />
                        <InfoPanel
                          title="Режим"
                          value={organization.is_active ? "Активна" : "Пауза"}
                          note="участвует в синхронизации"
                          compact
                        />
                      </div>
                    </button>
                  );
                })
              ) : loadingOrganizations ? (
                <div className="rounded-[24px] border border-dashed border-[#3a3d43] bg-[#343840] px-5 py-8 text-center">
                  <p className="text-sm font-medium text-slate-200">Загрузка организаций...</p>
                  <p className="mt-2 text-sm leading-6 text-slate-400">
                    Запрашиваем список SMARTUP_ORGANIZATIONS у backend.
                  </p>
                </div>
              ) : organizationsError ? (
                <div className="rounded-[24px] border border-dashed border-[#40272c] bg-[#343840] px-5 py-8 text-center">
                  <p className="text-sm font-medium text-slate-200">Не удалось загрузить организации</p>
                  <p className="mt-2 text-sm leading-6 text-slate-400">{organizationsError}</p>
                  <div className="mt-4 flex justify-center">
                    <Button variant="secondary" onClick={() => void refreshStatus()}>
                      Повторить попытку
                    </Button>
                  </div>
                </div>
              ) : (
                <div className="rounded-[24px] border border-dashed border-[#3a3d43] bg-[#343840] px-5 py-8 text-center">
                  <p className="text-sm font-medium text-slate-200">Организации не найдены</p>
                  <p className="mt-2 text-sm leading-6 text-slate-400">
                    Проверьте переменные SMARTUP_ORGANIZATIONS и затем обновите страницу.
                  </p>
                </div>
              )}
            </div>
          </div>
        </Surface>

        <Surface>
          <div className="min-h-0 rounded-[28px] bg-[#2E3137] p-6 sm:p-7">
            <div className="space-y-2">
              <p className="text-xs uppercase tracking-[0.32em] text-slate-400">Краткий итог</p>
              <h2 className="text-2xl font-semibold tracking-[-0.04em] text-[#f4f7fb]">
                Что важно для SmartUp
              </h2>
            </div>

            <div className="mt-5 space-y-3">
              <SummaryLine label="Подключение" value={connectionState.status === "success" ? "Проверено" : "Требует проверки"} />
              <SummaryLine
                label="Синхронизация"
                value={job?.status === "running" ? "Выполняется" : job?.status === "failed" ? "Есть ошибки" : "Доступна"}
              />
              <SummaryLine
                label="Данные"
                value={completeness ? `${completeness.completed_entities}/${completeness.total_entities}` : "—"}
              />
              <SummaryLine label="Организации" value={`${activeCount} активных`} />
            </div>

            <div className="mt-6 rounded-[24px] border border-[#3a3d43] bg-[#343840] p-4">
              <p className="text-sm font-medium text-slate-200">Пояснение</p>
              <p className="mt-2 text-sm leading-6 text-slate-400">
                Здесь нет ручного управления cron или интервалами. Управление сводится к проверке
                подключения, выбору организации и запуску недельной либо полной синхронизации.
              </p>
            </div>
          </div>
        </Surface>
      </div>
    </section>
  );
}

function InfoPanel({
  title,
  value,
  note,
  compact = false,
  className,
}: {
  title: string;
  value: string;
  note: string;
  compact?: boolean;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "rounded-2xl border border-[#3a3d43] bg-[#343840] px-4 py-3",
        compact ? "px-3 py-3" : "px-4 py-4",
        className,
      )}
    >
      <p className="text-xs uppercase tracking-[0.24em] text-slate-400">{title}</p>
      <p className={cn("mt-2 font-semibold tracking-[-0.03em] text-[#f4f7fb]", compact ? "text-sm" : "text-[15px]")}>
        {value}
      </p>
      <p className={cn("mt-1 text-slate-400", compact ? "text-xs" : "text-sm")}>{note}</p>
    </div>
  );
}

function MiniStat({ title, value }: { title: string; value: string }) {
  return (
    <div className="rounded-2xl border border-[#3a3d43]/70 bg-[#2E3137] px-4 py-3 shadow-sm">
      <p className="text-xs uppercase tracking-[0.24em] text-slate-400">{title}</p>
      <p className="mt-1 text-sm font-medium text-slate-200">{value}</p>
    </div>
  );
}

function SummaryLine({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between rounded-2xl border border-[#3a3d43] bg-[#2E3137] px-4 py-4">
      <p className="text-sm font-medium text-slate-200">{label}</p>
      <p className="text-sm font-semibold text-[#f4f7fb]">{value}</p>
    </div>
  );
}
