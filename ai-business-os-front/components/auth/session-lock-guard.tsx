"use client";

import { type FormEvent, type ReactNode, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

const apiUrl = process.env.NEXT_PUBLIC_CORE_API_URL ?? "http://127.0.0.1:8000";
const lockAfterMs = 5 * 60 * 1000;

function token() {
  return document.cookie.split(";").map((item) => item.trim()).find((item) => item.startsWith("aibos_owner_session="))?.split("=").slice(1).join("=") ?? "";
}

function authHeaders() {
  return { "Content-Type": "application/json", Authorization: `Bearer ${decodeURIComponent(token())}` };
}

export function SessionLockGuard({ children }: { children: ReactNode }) {
  const router = useRouter();
  const timer = useRef<number | null>(null);
  const [locked, setLocked] = useState(false);
  const [login, setLogin] = useState("Пользователь");
  const [pin, setPin] = useState("");
  const [error, setError] = useState<string | null>(null);

  const resetTimer = () => {
    if (locked) return;
    if (timer.current !== null) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => {
      void fetch(`${apiUrl}/api/v1/auth/lock`, { method: "POST", headers: authHeaders() }).then(() => setLocked(true)).catch(() => undefined);
    }, lockAfterMs);
  };

  useEffect(() => {
    let active = true;
    void fetch(`${apiUrl}/api/v1/auth/me`, { headers: authHeaders(), cache: "no-store" })
      .then((response) => response.json())
      .then((payload) => {
        if (!active) return;
        setLocked(payload.locked === true);
        setLogin(payload.user?.login ?? "Пользователь");
      })
      .catch(() => undefined);

    const events = ["pointerdown", "keydown", "touchstart", "scroll"];
    events.forEach((event) => window.addEventListener(event, resetTimer, { passive: true }));
    resetTimer();
    return () => {
      active = false;
      events.forEach((event) => window.removeEventListener(event, resetTimer));
      if (timer.current !== null) window.clearTimeout(timer.current);
    };
  }, []);

  async function unlock(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    const response = await fetch(`${apiUrl}/api/v1/auth/unlock`, { method: "POST", headers: authHeaders(), body: JSON.stringify({ pin }) });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      setError(payload.detail ?? "Неверный PIN");
      return;
    }
    setPin("");
    setLocked(false);
    resetTimer();
  }

  function logout() {
    void fetch(`${apiUrl}/api/v1/auth/logout`, { method: "POST", headers: authHeaders() }).finally(() => {
      document.cookie = "aibos_owner_session=; Path=/; Max-Age=0; SameSite=Lax";
      router.replace("/login");
    });
  }

  return (
    <>
      <div className={locked ? "pointer-events-none select-none brightness-50" : ""}>{children}</div>
      {locked ? (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-[#0d0e10]/55 p-4">
          <form onSubmit={unlock} className="pointer-events-auto w-full max-w-[360px] rounded-[28px] border border-[#454952] bg-[#2E3137] p-7 shadow-[0_28px_90px_rgba(0,0,0,0.5)]">
            <p className="text-xs uppercase tracking-[0.3em] text-slate-400">AI БОС</p>
            <h2 className="mt-3 text-2xl font-semibold text-[#f4f7fb]">Система заблокирована</h2>
            <p className="mt-2 text-sm text-slate-400">{login}</p>
            <input autoFocus type="password" inputMode="numeric" maxLength={4} pattern="[0-9]{4}" value={pin} onChange={(event) => setPin(event.target.value.replace(/\D/g, "").slice(0, 4))} placeholder="PIN из 4 цифр" className="mt-6 h-12 w-full rounded-full border border-[#5b5f67] bg-transparent px-5 text-[#f4f7fb] outline-none placeholder:text-slate-400 focus:border-[#FFF27A]" />
            {error ? <p className="mt-2 text-sm text-rose-300">{error}</p> : null}
            <button type="submit" className="mt-5 h-12 w-full rounded-full bg-[#FFF27A] font-medium text-[#1E1E21]">Разблокировать</button>
            <button type="button" onClick={logout} className="mt-3 h-10 w-full rounded-full border border-[#454952] text-sm text-slate-300">Выйти</button>
          </form>
        </div>
      ) : null}
    </>
  );
}
