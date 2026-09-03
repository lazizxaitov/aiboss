"use client";

import Script from "next/script";
import { useEffect, useState } from "react";

// Telegram's Mini App SDK (loaded from telegram.org below) attaches itself
// to window.Telegram.WebApp. This page is only ever meant to be opened
// through the bot's menu button inside the Telegram client, so it lives
// outside the app/(dashboard) route group on purpose — it must render with
// no login/session guard and no dashboard chrome around it.
interface TelegramWebApp {
  ready: () => void;
  expand: () => void;
  initData: string;
  showScanQrPopup: (params: { text?: string }, callback: (text: string) => boolean | void) => void;
  closeScanQrPopup: () => void;
}

declare global {
  interface Window {
    Telegram?: { WebApp?: TelegramWebApp };
  }
}

type LinkStage = "idle" | "scanning" | "linking" | "success" | "error";

export default function TelegramMiniAppPage() {
  const [sdkReady, setSdkReady] = useState(false);
  const [stage, setStage] = useState<LinkStage>("idle");
  const [message, setMessage] = useState<string | null>(null);
  const [login, setLogin] = useState("");
  const [password, setPassword] = useState("");

  useEffect(() => {
    if (!sdkReady) return;
    const webApp = window.Telegram?.WebApp;
    webApp?.ready();
    webApp?.expand();
  }, [sdkReady]);

  const completeLink = async (token: string, initData: string) => {
    setStage("linking");
    try {
      const response = await fetch("/api/v1/telegram/webapp/link", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token: token.trim(), init_data: initData, login, password }),
      });
      const data = (await response.json().catch(() => null)) as
        | { connected?: boolean; message?: string; detail?: string }
        | null;
      if (!response.ok || !data?.connected) {
        setStage("error");
        setMessage(data?.detail || data?.message || "Не удалось подключиться. Обновите QR-код в системе и попробуйте снова.");
        return;
      }
      setStage("success");
      setMessage(data.message || "Telegram успешно подключён к AI Business OS.");
    } catch {
      setStage("error");
      setMessage("Не удалось связаться с сервером. Проверьте подключение и попробуйте снова.");
    }
  };

  const scanQr = () => {
    const webApp = window.Telegram?.WebApp;
    if (!webApp) {
      setStage("error");
      setMessage("Откройте эту страницу через кнопку меню бота в Telegram.");
      return;
    }
    if (!login.trim() || !password) {
      setStage("error");
      setMessage("Сначала введите логин и пароль от системы.");
      return;
    }
    setStage("scanning");
    setMessage(null);
    webApp.showScanQrPopup(
      { text: "Наведите камеру на QR-код в системе AI Business OS" },
      (scannedText: string) => {
        webApp.closeScanQrPopup();
        void completeLink(scannedText, webApp.initData);
        return true;
      },
    );
  };

  const canScan = sdkReady && login.trim().length > 0 && password.length > 0;

  return (
    <>
      <Script src="https://telegram.org/js/telegram-web-app.js" strategy="afterInteractive" onLoad={() => setSdkReady(true)} />
      <main className="flex min-h-screen flex-col items-center justify-center gap-6 bg-[#1E1E21] px-6 py-10 text-center text-[#f4f7fb]">
        <div className="space-y-2">
          <p className="text-xs uppercase tracking-[0.32em] text-slate-400">AI Business OS</p>
          <h1 className="text-2xl font-semibold tracking-[-0.03em]">Панель бота</h1>
          <p className="max-w-sm text-sm leading-6 text-slate-400">
            Введите логин и пароль от системы, затем отсканируйте QR-код, показанный в системе
            (кнопка «Подключить Telegram»), чтобы дать этому Telegram-аккаунту доступ к AI Business OS.
          </p>
        </div>

        {stage === "success" ? (
          <div className="max-w-sm space-y-2 rounded-2xl border border-emerald-500/30 bg-emerald-500/10 px-5 py-4 text-emerald-200">
            <p className="text-sm">{message}</p>
          </div>
        ) : (
          <>
            <div className="flex w-full max-w-xs flex-col gap-3">
              <input
                type="text"
                autoComplete="username"
                placeholder="Логин"
                value={login}
                onChange={(event) => setLogin(event.target.value)}
                disabled={stage === "scanning" || stage === "linking"}
                className="h-11 rounded-full border border-[#3a3d43] bg-[#2E3137] px-4 text-sm text-[#f4f7fb] outline-none placeholder:text-slate-500 focus:border-[#FFF27A]/40"
              />
              <input
                type="password"
                autoComplete="current-password"
                placeholder="Пароль"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                disabled={stage === "scanning" || stage === "linking"}
                className="h-11 rounded-full border border-[#3a3d43] bg-[#2E3137] px-4 text-sm text-[#f4f7fb] outline-none placeholder:text-slate-500 focus:border-[#FFF27A]/40"
              />
            </div>
            <button
              type="button"
              onClick={scanQr}
              disabled={!canScan || stage === "scanning" || stage === "linking"}
              className="inline-flex h-12 items-center justify-center gap-2 rounded-full border border-[#FFF27A]/30 bg-[#FFF27A] px-6 text-sm font-medium text-[#1E1E21] transition disabled:cursor-not-allowed disabled:opacity-50"
            >
              {stage === "linking" ? "Подключаем..." : "Сканировать QR"}
            </button>
          </>
        )}

        {stage === "error" && message ? <p className="max-w-sm text-sm text-rose-300">{message}</p> : null}
        {!sdkReady ? <p className="text-xs text-slate-500">Загрузка панели Telegram...</p> : null}
      </main>
    </>
  );
}
