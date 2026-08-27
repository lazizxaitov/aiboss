"use client";

import { useEffect, useRef, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Drawer } from "@/components/ui/drawer";
import { Select } from "@/components/ui/select";
import { Surface } from "@/components/ui/surface";
import { useOwnerSessionState } from "@/components/auth/session-lock-guard";
import { getAiRouting, saveAiRouting, type AiRoutingConfig } from "@/lib/core-api";
import { useUnsavedChangesGuard } from "@/lib/use-unsaved-changes";

type Provider = {
  id: string;
  provider: string;
  model: string;
  name: string;
  status: "available" | "unavailable" | "not_configured";
  available: boolean;
};

type Assignment = AiRoutingConfig["roles"][string];
type RoutingConfig = AiRoutingConfig;
const roles = [
  {
    id: "business_analytics",
    title: "Аналитика бизнеса",
    description: "Продажи, товары, клиенты, сравнения периодов, аномалии и управленческие сводки.",
  },
  {
    id: "system_action",
    title: "Работа с системой",
    description: "AI Chat, Widget Builder, изменения виджетов и разрешённые действия в Dashboard.",
  },
  {
    id: "communications",
    title: "Данные и коммуникации",
    description: "Telegram, сообщения продавцов, анализ переписок и подготовка сводок.",
  },
  {
    id: "ai_chat",
    title: "AI Chat",
    description: "Общение пользователя с AI Business OS и ответы в чате.",
  },
] as const;

const emptyAssignment = (): Assignment => ({
  primary_provider_id: null,
  primary_model_id: null,
  fallback_provider_id: null,
  fallback_model_id: null,
});

export function AiRoutingSettings() {
  const session = useOwnerSessionState();
  const [providers, setProviders] = useState<Provider[]>([]);
  const [config, setConfig] = useState<RoutingConfig>({ roles: {} });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [selectedRoleId, setSelectedRoleId] = useState<string | null>(null);
  const [providersOpen, setProvidersOpen] = useState(false);
  const routingLoadedRef = useRef(false);
  const routingDirtyRef = useRef(false);

  useUnsavedChangesGuard(routingDirtyRef.current);

  useEffect(() => {
    if (!session.hydrated || !session.authenticated || session.locked) return;
    void getAiRouting()
      .then((payload) => {
        setProviders(Array.isArray(payload.providers) ? payload.providers : []);
        setConfig(payload.config);
        routingLoadedRef.current = true;
        routingDirtyRef.current = false;
        if (payload.malformed) setNotice("Не удалось загрузить настройки ИИ");
      })
      .catch((error) => {
        const message = error instanceof Error ? error.message : "";
        setNotice(message.includes(" 401") ? "Ожидается восстановление авторизации." : message.includes(" 423") ? "Сессия заблокирована. Разблокируйте её, чтобы загрузить настройки ИИ." : message || "Не удалось загрузить настройки ИИ.");
      })
      .finally(() => setLoading(false));
  }, [session.hydrated, session.authenticated, session.locked]);

  useEffect(() => {
    if (!routingLoadedRef.current || !routingDirtyRef.current) return;
    const timer = window.setTimeout(() => {
      void saveAiRouting(config)
        .then((payload) => {
          routingDirtyRef.current = false;
          setProviders(Array.isArray(payload.providers) ? payload.providers : []);
          setConfig(payload.config);
        })
        .catch(() => setNotice("Не удалось сохранить настройки ИИ."));
    }, 400);
    return () => window.clearTimeout(timer);
  }, [config]);

  const updateAssignment = (roleId: string, patch: Partial<Assignment>) => {
    routingDirtyRef.current = true;
    setConfig((current) => ({
      ...current,
      roles: { ...current.roles, [roleId]: { ...emptyAssignment(), ...current.roles[roleId], ...patch } },
    }));
    setNotice(null);
  };

  const statusLabel = (provider: Provider) => provider.status === "available" ? "Доступен" : provider.status === "unavailable" ? "Недоступен" : "Не настроен";
  const providerLabel = (providerId: string) => {
    if (providerId === "openai-codex") return "OpenAI Codex";
    if (providerId === "custom") return "Local / Custom";
    return providerId;
  };
  const providerOptions = Array.from(new Map(providers.filter((provider) => provider.available).map((provider) => [provider.provider, provider])).values())
    .map((provider) => ({ value: provider.provider, label: providerLabel(provider.provider) }));
  const modelsFor = (providerId: string | null) => providers.filter((provider) => provider.provider === providerId && provider.available);
  const selectedRole = roles.find((role) => role.id === selectedRoleId) ?? null;
  const selectedAssignment = selectedRole ? config.roles[selectedRole.id] ?? emptyAssignment() : emptyAssignment();

  const save = async () => {
    setSaving(true);
    setNotice(null);
    try {
      const payload = await saveAiRouting(config);
      routingDirtyRef.current = false;
      setProviders(Array.isArray(payload.providers) ? payload.providers : []);
      setConfig(payload.config);
      setNotice("Настройки сохранены");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Не удалось сохранить настройки.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Surface>
      <div className="rounded-[28px] bg-[#2E3137] p-6 sm:p-7">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="space-y-2">
            <p className="text-xs uppercase tracking-[0.32em] text-slate-400">Искусственный интеллект</p>
            <h2 className="text-2xl font-semibold tracking-[-0.04em] text-[#f4f7fb]">ИИ и распределение ролей</h2>
            <p className="max-w-2xl text-sm leading-6 text-slate-400">Выберите, какой подключенный агент отвечает за каждый тип задач. Выбор выполняется на backend.</p>
          </div>
          <Button variant="primary" onClick={() => void save()} disabled={loading || saving}>{saving ? "Сохраняем..." : "Сохранить"}</Button>
        </div>

        <div className="mt-6 flex items-center justify-between gap-4 rounded-2xl border border-[#3a3d43] bg-[#343840] px-4 py-3">
          <div>
            <p className="text-sm font-medium text-slate-200">Доступные ИИ</p>
            <p className="mt-1 text-xs text-slate-400">Провайдеры и модели из текущего registry.</p>
          </div>
          <Button variant="secondary" size="sm" onClick={() => setProvidersOpen(true)}>
            Открыть список{providers.length ? ` · ${providers.length}` : ""}
          </Button>
        </div>

        <div className="mt-6 grid gap-4 md:grid-cols-2">
          {roles.map((role) => {
            const assignment = config.roles[role.id] ?? emptyAssignment();
            return (
              <div
                key={role.id}
                role="button"
                tabIndex={0}
                onClick={() => setSelectedRoleId(role.id)}
                onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") setSelectedRoleId(role.id); }}
                className="rounded-2xl border border-[#3a3d43] bg-[#343840] p-5 text-left transition hover:border-[#5a6270]"
              >
                <h3 className="text-lg font-semibold text-[#f4f7fb]">{role.title}</h3>
                <p className="mt-1 max-w-3xl text-sm leading-6 text-slate-400">{role.description}</p>
                <div className="mt-4 flex items-center justify-between gap-3 rounded-2xl border border-[#3a3d43] bg-[#2E3137] px-4 py-3">
                  <span className="text-sm text-slate-300">{assignment.primary_provider_id && assignment.primary_provider_id !== "hermes" ? providerLabel(assignment.primary_provider_id) : "Агент не выбран"}</span>
                  <span className="text-xs text-slate-400">{assignment.primary_model_id && assignment.primary_model_id !== "default" ? assignment.primary_model_id : "Настроить"}</span>
                </div>
                {role.id === "business_analytics" ? (
                  <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-slate-300">
                    <button
                      type="button"
                      onClick={() => {
                        routingDirtyRef.current = true;
                        setConfig((current) => ({ ...current, business_analytics_auto_enabled: !current.business_analytics_auto_enabled }));
                      }}
                      className={`rounded-full border px-3 py-1.5 ${config.business_analytics_auto_enabled ? "border-[#FFF27A] bg-[#FFF27A] text-[#1E1E21]" : "border-[#4a4e56] bg-[#2E3137]"}`}
                    >
                      Автоаналитика: {config.business_analytics_auto_enabled ? "включена" : "выключена"}
                    </button>
                    {["after_sync", "daily", "weekly"].map((trigger) => {
                      const active = config.business_analytics_triggers?.includes(trigger);
                      return (
                        <button
                          key={trigger}
                          type="button"
                          onClick={() => {
                            routingDirtyRef.current = true;
                            setConfig((current) => ({ ...current, business_analytics_triggers: active ? (current.business_analytics_triggers ?? []).filter((item) => item !== trigger) : [...(current.business_analytics_triggers ?? []), trigger] }));
                          }}
                          className={`rounded-full border px-3 py-1.5 ${active ? "border-[#FFF27A] text-[#FFF27A]" : "border-[#4a4e56] text-slate-400"}`}
                        >
                          {trigger === "after_sync" ? "После синхронизации" : trigger === "daily" ? "Ежедневно" : "Еженедельно"}
                        </button>
                      );
                    })}
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
        {notice ? <p className="mt-4 text-sm text-slate-300">{notice}</p> : null}
      </div>
      <Drawer
        open={Boolean(selectedRole)}
        onClose={() => setSelectedRoleId(null)}
        title={selectedRole?.title ?? "Выбор агента"}
        description={selectedRole?.description}
        badges={<Badge variant="neutral">Выбор агента</Badge>}
        className="!max-w-[min(34rem,calc(100vw-2rem))]"
      >
        <div className="space-y-3">
          <Select
            label="Тип ИИ"
            value={selectedAssignment.primary_provider_id ?? ""}
            options={providerOptions}
            onChange={(value) => {
              if (!selectedRole) return;
              updateAssignment(selectedRole.id, { primary_provider_id: value, primary_model_id: modelsFor(value)[0]?.model ?? null });
            }}
            placeholder="Выберите агента"
          />
          <Select
            label="Модель"
            value={selectedAssignment.primary_model_id ?? ""}
            options={modelsFor(selectedAssignment.primary_provider_id).map((target) => ({ value: target.model, label: target.name }))}
            onChange={(value) => selectedRole && updateAssignment(selectedRole.id, { primary_model_id: value })}
            placeholder="Выберите модель"
          />
          <Button className="w-full" onClick={() => setSelectedRoleId(null)}>Готово</Button>
        </div>
      </Drawer>
      <Drawer
        open={providersOpen}
        onClose={() => setProvidersOpen(false)}
        title="Доступные ИИ"
        description="Провайдеры и модели, доступные для выбора в AI Business OS."
        badges={<Badge variant="neutral">{providers.length}</Badge>}
        className="!max-w-[min(48rem,calc(100vw-2rem))]"
      >
        {providers.length > 0 ? (
          <div className="grid gap-3 sm:grid-cols-2">
            {providers.map((provider) => (
              <div key={provider.id} className="rounded-2xl border border-[#3a3d43] bg-[#343840] px-4 py-4">
                <div className="flex items-center justify-between gap-3">
                  <p className="min-w-0 truncate text-sm font-medium text-slate-200">{provider.name}</p>
                  <Badge variant="neutral"><span className={`mr-1.5 inline-block h-2 w-2 rounded-full ${provider.status === "available" ? "bg-emerald-400" : "bg-slate-500"}`} />{statusLabel(provider)}</Badge>
                </div>
                <p className="mt-2 truncate text-xs text-slate-400">{provider.available ? provider.model : "Модель недоступна"}</p>
              </div>
            ))}
          </div>
        ) : (
          <p className="rounded-2xl border border-[#3a3d43] bg-[#343840] p-4 text-sm text-slate-400">Доступные модели не найдены.</p>
        )}
      </Drawer>
    </Surface>
  );
}
