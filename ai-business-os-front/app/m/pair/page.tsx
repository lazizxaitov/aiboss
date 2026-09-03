"use client";

import { useEffect, useMemo, useState, type FormEvent } from "react";

type Stage = "form" | "pairing" | "installPrompt" | "error";

type InstallEvent = Event & { prompt: () => Promise<void> };

function detectPlatform(): "ios" | "android" | "other" {
  if (typeof navigator === "undefined") return "other";
  const ua = navigator.userAgent;
  if (/iPhone|iPad|iPod/.test(ua)) return "ios";
  if (/Android/.test(ua)) return "android";
  return "other";
}

function deviceLabel(): string {
  const platform = detectPlatform();
  const ua = typeof navigator !== "undefined" ? navigator.userAgent : "";
  const browser = /CriOS|Chrome/.test(ua) ? "Chrome" : /Safari/.test(ua) ? "Safari" : /Firefox/.test(ua) ? "Firefox" : "Браузер";
  const platformLabel = platform === "ios" ? "iPhone/iPad" : platform === "android" ? "Android" : "Устройство";
  return `${platformLabel} · ${browser}`;
}

const DEVICE_ID_STORAGE_KEY = "aibos_device_id";

// A stable id this browser/PWA keeps across re-pairing (session expired,
// cookies cleared, PWA reinstalled) so the Settings device list updates the
// existing entry for this phone instead of growing a new "ghost" device
// every time it re-scans a QR code.
function clientDeviceId(): string {
  if (typeof window === "undefined") return "";
  try {
    const existing = window.localStorage.getItem(DEVICE_ID_STORAGE_KEY);
    if (existing) return existing;
    const created = typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;
    window.localStorage.setItem(DEVICE_ID_STORAGE_KEY, created);
    return created;
  } catch {
    return "";
  }
}

export default function MobilePairPage() {
  // Read the token straight from the URL instead of Next's useSearchParams —
  // this page is fully client-rendered anyway, and this avoids having to
  // wrap the whole page in a <Suspense> boundary just for one query param.
  const [token] = useState(() => (typeof window === "undefined" ? "" : new URLSearchParams(window.location.search).get("token") ?? ""));
  const platform = useMemo(detectPlatform, []);

  const [stage, setStage] = useState<Stage>(token ? "form" : "error");
  const [login, setLogin] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(token ? null : "В ссылке нет кода подключения. Отсканируйте QR-код заново в системе.");
  const [installEvent, setInstallEvent] = useState<InstallEvent | null>(null);

  useEffect(() => {
    const handler = (event: Event) => {
      event.preventDefault();
      setInstallEvent(event as InstallEvent);
    };
    window.addEventListener("beforeinstallprompt", handler);
    return () => window.removeEventListener("beforeinstallprompt", handler);
  }, []);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setStage("pairing");
    setError(null);
    try {
      const response = await fetch("/api/v1/device/pair", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, login, password, device_label: deviceLabel(), device_id: clientDeviceId() || undefined }),
      });
      const payload = (await response.json().catch(() => ({}))) as { access_token?: string; detail?: string };
      if (!response.ok || typeof payload.access_token !== "string") {
        throw new Error(payload.detail ?? "Не удалось подключить устройство.");
      }
      document.cookie = `aibos_owner_session=${encodeURIComponent(payload.access_token)}; Path=/; Max-Age=2592000; SameSite=Lax`;
      setStage("installPrompt");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Не удалось подключить устройство.");
      setStage("form");
    }
  };

  const openApp = () => {
    window.location.assign("/m");
  };

  if (stage === "error") {
    return (
      <main className="flex min-h-dvh flex-col items-center justify-center gap-4 px-6 text-center">
        <p className="text-lg font-semibold">Не удалось подключиться</p>
        <p className="max-w-sm text-sm text-slate-400">{error}</p>
      </main>
    );
  }

  if (stage === "installPrompt") {
    return (
      <main className="flex min-h-dvh flex-col items-center justify-center gap-6 px-6 py-10 text-center">
        <div className="space-y-2">
          <p className="text-xs uppercase tracking-[0.32em] text-slate-400">Готово</p>
          <h1 className="text-2xl font-semibold tracking-[-0.03em]">Устройство подключено</h1>
          <p className="max-w-sm text-sm leading-6 text-slate-400">
            Добавьте AI BOS на главный экран, чтобы открывать его как обычное приложение.
          </p>
        </div>

        {installEvent ? (
          <button
            type="button"
            onClick={() => void installEvent.prompt().then(openApp)}
            className="inline-flex h-12 items-center justify-center gap-2 rounded-full border border-[#FFF27A]/30 bg-[#FFF27A] px-6 text-sm font-medium text-[#1E1E21]"
          >
            Добавить на главный экран
          </button>
        ) : platform === "ios" ? (
          <div className="max-w-xs space-y-2 rounded-2xl border border-[#3a3d43] bg-[#2E3137] px-5 py-4 text-left text-sm text-slate-300">
            <p>1. Нажмите кнопку «Поделиться» ⬆️ внизу экрана Safari.</p>
            <p>2. Выберите «На экран „Домой“».</p>
            <p>3. Нажмите «Добавить».</p>
          </div>
        ) : (
          <p className="max-w-sm text-sm text-slate-400">
            Откройте меню браузера и выберите «Добавить на главный экран» / «Установить приложение».
          </p>
        )}

        <button type="button" onClick={openApp} className="text-sm text-[#FFF27A] underline">
          Продолжить без установки
        </button>
      </main>
    );
  }

  return (
    <main className="flex min-h-dvh flex-col items-center justify-center gap-6 px-6 py-10 text-center">
      <div className="space-y-2">
        <p className="text-xs uppercase tracking-[0.32em] text-slate-400">AI Business OS</p>
        <h1 className="text-2xl font-semibold tracking-[-0.03em]">Подключить устройство</h1>
        <p className="max-w-sm text-sm leading-6 text-slate-400">
          Введите логин и пароль от системы, чтобы дать этому телефону доступ к мобильной версии.
        </p>
      </div>

      <form onSubmit={submit} className="flex w-full max-w-xs flex-col gap-3">
        <input
          type="text"
          autoComplete="username"
          placeholder="Логин"
          value={login}
          onChange={(event) => setLogin(event.target.value)}
          required
          disabled={stage === "pairing"}
          className="h-12 rounded-full border border-[#3a3d43] bg-[#2E3137] px-4 text-sm text-[#f4f7fb] outline-none placeholder:text-slate-500 focus:border-[#FFF27A]/40"
        />
        <input
          type="password"
          autoComplete="current-password"
          placeholder="Пароль"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          required
          disabled={stage === "pairing"}
          className="h-12 rounded-full border border-[#3a3d43] bg-[#2E3137] px-4 text-sm text-[#f4f7fb] outline-none placeholder:text-slate-500 focus:border-[#FFF27A]/40"
        />
        {error ? <p className="text-sm text-rose-300">{error}</p> : null}
        <button
          type="submit"
          disabled={stage === "pairing"}
          className="h-12 rounded-full bg-[#FFF27A] text-sm font-medium text-[#1E1E21] transition disabled:cursor-wait disabled:opacity-60"
        >
          {stage === "pairing" ? "Подключаем..." : "Войти"}
        </button>
      </form>
    </main>
  );
}
