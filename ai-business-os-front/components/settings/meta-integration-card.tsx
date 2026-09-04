"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  getMetaStatus,
  connectMeta,
  syncMeta,
  mapMetaResource,
  saveMetaCredentials,
  type MetaStatus,
  type MetaCredentialsInput,
} from "@/lib/core-api";

// A credential field the owner can type in. `secret` picks a password-style
// input (App Secret, Access Token) so the value isn't shown in plain text on
// screen; `savedLabel` mirrors the pattern below of never echoing back the
// actual stored value — only whether one exists — so a field that already
// has a token saved shows a placeholder like "сохранён" instead of the token.
const META_CREDENTIAL_FIELDS: Array<{ key: keyof MetaCredentialsInput; label: string; secret?: boolean; hint?: string }> = [
  { key: "access_token", label: "Access Token", secret: true, hint: "Достаточно одного System User токена из Meta Business Manager." },
  { key: "app_id", label: "App ID" },
  { key: "app_secret", label: "App Secret", secret: true },
  { key: "redirect_uri", label: "Redirect URI", hint: "Нужен только для OAuth-подключения через App ID/App Secret." },
];

export function MetaIntegrationCard() {
  const [data, setData] = useState<MetaStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [organizationId, setOrganizationId] = useState("");
  const [notice, setNotice] = useState<string | null>(null);

  const [credentialsOpen, setCredentialsOpen] = useState(false);
  const [credentialDrafts, setCredentialDrafts] = useState<MetaCredentialsInput>({});
  const [savingCredentials, setSavingCredentials] = useState(false);
  const [credentialsNotice, setCredentialsNotice] = useState<string | null>(null);

  const refresh = () =>
    getMetaStatus()
      .then(setData)
      .catch((error) => setNotice(error instanceof Error ? error.message : "Не удалось загрузить Meta"));
  useEffect(() => {
    void refresh();
  }, []);

  const run = async (action: () => Promise<MetaStatus | unknown>) => {
    setBusy(true);
    setNotice(null);
    try {
      const result = await action();
      if (result && typeof result === "object" && "resources" in result) setData(result as MetaStatus);
      else await refresh();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Операция Meta не выполнена");
    } finally {
      setBusy(false);
    }
  };

  const saveCredentials = async () => {
    setSavingCredentials(true);
    setCredentialsNotice(null);
    try {
      await saveMetaCredentials(credentialDrafts);
      setCredentialDrafts({});
      await refresh();
      setCredentialsNotice("Сохранено");
    } catch (error) {
      setCredentialsNotice(error instanceof Error ? error.message : "Не удалось сохранить данные Meta");
    } finally {
      setSavingCredentials(false);
    }
  };

  return (
    <div className="rounded-[28px] bg-[#2E3137] p-6 sm:p-7">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.32em] text-slate-400">Интеграции</p>
          <h2 className="mt-2 text-2xl font-semibold text-[#f4f7fb]">Meta и Instagram</h2>
          <p className="mt-2 text-sm text-slate-400">Реклама, страницы и органический контент для AI-аналитики.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" size="sm" onClick={() => setCredentialsOpen((open) => !open)}>
            {credentialsOpen ? "Скрыть данные для входа" : "Данные для входа"}
          </Button>
          <Button variant="secondary" size="sm" onClick={() => void run(connectMeta)} disabled={busy || !data?.configured}>
            {busy ? "Подключение..." : "Подключить Meta"}
          </Button>
          <Button variant="ghost" size="sm" onClick={() => void run(() => syncMeta("incremental"))} disabled={busy || data?.status !== "connected"}>
            Синхронизировать
          </Button>
          <Button variant="ghost" size="sm" onClick={() => void run(() => syncMeta("backfill", 30))} disabled={busy || data?.status !== "connected"}>
            Backfill 30 дн.
          </Button>
        </div>
      </div>

      <p className="mt-4 text-sm text-slate-300">
        Статус: {data?.status ?? "загрузка"}
        {data?.last_success_at ? ` · последний успех ${new Date(data.last_success_at).toLocaleString()}` : ""}
        {data && !data.configured ? " · нет сохранённых данных для входа" : ""}
      </p>

      {credentialsOpen ? (
        <div className="mt-4 space-y-3 rounded-2xl border border-[#3a3d43] bg-[#343840] p-4">
          <p className="text-sm text-slate-300">
            Введите данные из{" "}
            <a href="https://developers.facebook.com/apps" target="_blank" rel="noreferrer" className="text-[#FFF27A] underline">
              Meta for Developers
            </a>
            . Значения хранятся только на сервере и не показываются повторно — поле с уже сохранённым значением отмечено ниже.
          </p>
          <div className="grid gap-3 sm:grid-cols-2">
            {META_CREDENTIAL_FIELDS.map((field) => {
              const isSet = data?.credentials?.[field.key as keyof typeof data.credentials] ?? false;
              return (
                <label key={field.key} className="block text-xs text-slate-400">
                  <span>
                    {field.label}
                    {isSet ? <span className="ml-2 text-emerald-400">сохранено</span> : null}
                  </span>
                  <input
                    type={field.secret ? "password" : "text"}
                    value={credentialDrafts[field.key] ?? ""}
                    onChange={(event) => setCredentialDrafts((current) => ({ ...current, [field.key]: event.target.value }))}
                    placeholder={isSet ? "•••••••• (оставьте пустым, чтобы не менять)" : "Не задано"}
                    className="mt-1 h-10 w-full rounded-xl border border-[#3a3d43] bg-[#2E3137] px-3 text-sm text-slate-200 outline-none focus:border-[#FFF27A]/40"
                  />
                  {field.hint ? <span className="mt-1 block text-[11px] text-slate-500">{field.hint}</span> : null}
                </label>
              );
            })}
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <Button variant="primary" size="sm" onClick={() => void saveCredentials()} disabled={savingCredentials}>
              {savingCredentials ? "Сохранение..." : "Сохранить"}
            </Button>
            {credentialsNotice ? <span className="text-sm text-slate-300">{credentialsNotice}</span> : null}
          </div>
        </div>
      ) : null}

      {data?.resources?.length ? (
        <div className="mt-4 space-y-2">
          {data.resources.map((resource) => (
            <div
              key={`${resource.resource_type}:${resource.external_id}`}
              className="flex flex-wrap items-center justify-between gap-2 rounded-2xl border border-[#3a3d43] bg-[#343840] px-4 py-3"
            >
              <span className="text-sm text-slate-200">
                {resource.name || resource.username || resource.external_id} <span className="text-slate-500">({resource.resource_type})</span>
              </span>
              <div className="flex gap-2">
                <input
                  value={organizationId}
                  onChange={(event) => setOrganizationId(event.target.value)}
                  placeholder="ID организации"
                  className="h-9 w-40 rounded-xl border border-[#3a3d43] bg-[#2E3137] px-3 text-xs text-slate-200"
                />
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={!organizationId || busy}
                  onClick={() =>
                    void run(() =>
                      mapMetaResource({ organization_id: organizationId, resource_type: resource.resource_type, external_id: resource.external_id }),
                    )
                  }
                >
                  Связать
                </Button>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <p className="mt-4 text-sm text-slate-400">После подключения доступные рекламные аккаунты, страницы и Instagram-профили появятся здесь.</p>
      )}

      {data?.last_error || notice ? <p className="mt-3 text-sm text-rose-300">{notice || data?.last_error}</p> : null}
    </div>
  );
}
