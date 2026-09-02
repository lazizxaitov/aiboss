"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Surface } from "@/components/ui/surface";
import { createTelegramLink, disconnectTelegram, getTelegramLinkStatus, type TelegramLinkStatus } from "@/lib/core-api";

export function TelegramLinkCard() {
  const [status, setStatus] = useState<TelegramLinkStatus | null>(null);
  const [link, setLink] = useState<TelegramLinkStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void getTelegramLinkStatus().then(setStatus).catch((reason) => setError(reason instanceof Error ? reason.message : "Не удалось получить статус Telegram"));
  }, []);

  const connect = async () => {
    setBusy(true);
    setError(null);
    try {
      setLink(await createTelegramLink());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось создать ссылку подключения");
    } finally {
      setBusy(false);
    }
  };

  const disconnect = async () => {
    if (!window.confirm("Отключить Telegram от AI Business OS?")) return;
    setBusy(true);
    setError(null);
    try {
      setStatus(await disconnectTelegram());
      setLink(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось отключить Telegram");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Surface>
      <div className="rounded-[28px] bg-[#2E3137] p-6 sm:p-7">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
          <div className="max-w-2xl space-y-2">
            <p className="text-xs uppercase tracking-[0.32em] text-slate-400">Интеграции</p>
            <h2 className="text-2xl font-semibold tracking-[-0.04em] text-[#f4f7fb]">Telegram</h2>
            <p className="text-sm leading-6 text-slate-400">Подключите свой Telegram-чат к AI Business OS. После подключения бот будет использовать тот же AI-диалог, бизнес-данные и выбранную модель.</p>
            <p className="text-sm font-medium text-slate-200">{status?.connected ? "Подключён" : "Не подключён"}</p>
            {status?.chats.length ? <p className="text-xs text-slate-500">Подключённых чатов: {status.chats.length}</p> : null}
          </div>
          <Button variant={status?.connected ? "secondary" : "primary"} onClick={status?.connected ? disconnect : connect} disabled={busy || status === null}>
            {busy ? "Обработка..." : status?.connected ? "Отключить Telegram" : "Подключить Telegram"}
          </Button>
        </div>
        {link ? (
          <div className="mt-5 space-y-3 rounded-2xl border border-[#555961] bg-[#343840] p-4">
            <p className="text-sm font-medium text-slate-200">Откройте Telegram и отправьте боту команду:</p>
            <code className="block break-all rounded-xl bg-[#25282d] px-3 py-3 text-sm text-[#FFF27A]">{link.instructions}</code>
            {link.deep_link ? <a className="inline-flex text-sm text-[#FFF27A] underline" href={link.deep_link} target="_blank" rel="noreferrer">Открыть Telegram</a> : null}
            <p className="text-xs text-slate-500">Ссылка одноразовая и действует 10 минут.</p>
          </div>
        ) : null}
        {error ? <p className="mt-3 text-sm text-rose-300">{error}</p> : null}
      </div>
    </Surface>
  );
}
