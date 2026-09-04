"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  connectYouTube,
  getYouTubeStatus,
  mapYouTubeChannel,
  syncYouTube,
  saveYouTubeCredentials,
  type YouTubeStatus,
  type YouTubeCredentialsInput,
} from "@/lib/core-api";

// A credential field the owner can type in. `secret` picks a password-style
// input so the value isn't shown in plain text; a field that already has a
// value saved shows "сохранено" instead of ever echoing the value back.
const YOUTUBE_CREDENTIAL_FIELDS: Array<{ key: keyof YouTubeCredentialsInput; label: string; secret?: boolean; hint?: string }> = [
  { key: "refresh_token", label: "Refresh Token", secret: true, hint: "Долгоживущий — предпочтительный способ, не истекает через час, как Access Token." },
  { key: "access_token", label: "Access Token", secret: true },
  { key: "client_id", label: "OAuth Client ID" },
  { key: "client_secret", label: "OAuth Client Secret", secret: true },
  { key: "redirect_uri", label: "Redirect URI" },
];

export function YouTubeIntegrationCard() {
  const [data, setData] = useState<YouTubeStatus | null>(null);
  const [organizationId, setOrganizationId] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const [credentialsOpen, setCredentialsOpen] = useState(false);
  const [credentialDrafts, setCredentialDrafts] = useState<YouTubeCredentialsInput>({});
  const [savingCredentials, setSavingCredentials] = useState(false);
  const [credentialsNotice, setCredentialsNotice] = useState<string | null>(null);

  const refresh = () =>
    getYouTubeStatus()
      .then(setData)
      .catch((error) => setNotice(error instanceof Error ? error.message : "Не удалось загрузить YouTube"));
  useEffect(() => {
    void refresh();
  }, []);

  const run = async (action: () => Promise<YouTubeStatus | unknown>) => {
    setBusy(true);
    setNotice(null);
    try {
      const value = await action();
      if (value && typeof value === "object" && "channels" in value) setData(value as YouTubeStatus);
      else await refresh();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Операция YouTube не выполнена");
    } finally {
      setBusy(false);
    }
  };

  const saveCredentials = async () => {
    setSavingCredentials(true);
    setCredentialsNotice(null);
    try {
      await saveYouTubeCredentials(credentialDrafts);
      setCredentialDrafts({});
      await refresh();
      setCredentialsNotice("Сохранено");
    } catch (error) {
      setCredentialsNotice(error instanceof Error ? error.message : "Не удалось сохранить данные YouTube");
    } finally {
      setSavingCredentials(false);
    }
  };

  return (
    <div className="rounded-[28px] bg-[#2E3137] p-6 sm:p-7">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.32em] text-slate-400">Интеграции</p>
          <h2 className="mt-2 text-2xl font-semibold text-[#f4f7fb]">YouTube</h2>
          <p className="mt-2 text-sm text-slate-400">Каналы, видео и официальная daily-аналитика.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" size="sm" onClick={() => setCredentialsOpen((open) => !open)}>
            {credentialsOpen ? "Скрыть данные для входа" : "Данные для входа"}
          </Button>
          <Button variant="secondary" size="sm" onClick={() => void run(connectYouTube)} disabled={busy || !data?.configured}>
            {busy ? "Подключение..." : "Подключить YouTube"}
          </Button>
          <Button variant="ghost" size="sm" onClick={() => void run(() => syncYouTube())} disabled={busy || data?.status !== "connected"}>
            Синхронизировать
          </Button>
          <Button variant="ghost" size="sm" onClick={() => void run(() => syncYouTube("backfill", 30))} disabled={busy || data?.status !== "connected"}>
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
            Данные из{" "}
            <a href="https://console.cloud.google.com/apis/credentials" target="_blank" rel="noreferrer" className="text-[#FFF27A] underline">
              Google Cloud Console
            </a>{" "}
            (проект с включённым YouTube Data API). Значения хранятся только на сервере и не показываются повторно.
          </p>
          <div className="grid gap-3 sm:grid-cols-2">
            {YOUTUBE_CREDENTIAL_FIELDS.map((field) => {
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

      {data?.channels?.length ? (
        <div className="mt-4 space-y-2">
          {data.channels.map((channel) => (
            <div key={channel.external_id} className="flex flex-wrap items-center justify-between gap-2 rounded-2xl border border-[#3a3d43] bg-[#343840] px-4 py-3">
              <span className="text-sm text-slate-200">{channel.title || channel.external_id}</span>
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
                  onClick={() => void run(() => mapYouTubeChannel({ organization_id: organizationId, channel_id: channel.external_id }))}
                >
                  Связать
                </Button>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <p className="mt-4 text-sm text-slate-400">После подключения доступные каналы появятся здесь.</p>
      )}

      {data?.last_error || notice ? <p className="mt-3 text-sm text-rose-300">{notice || data?.last_error}</p> : null}
    </div>
  );
}
