"use client";
/* eslint-disable @next/next/no-img-element */

import { type FormEvent, useState } from "react";

const coreApiUrl = "";

export default function LoginPage() {
  const [login, setLogin] = useState("");
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${coreApiUrl}/api/v1/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ login, password }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || typeof payload.access_token !== "string") {
        throw new Error(payload.detail ?? "Не удалось выполнить вход.");
      }
      document.cookie = `aibos_owner_session=${encodeURIComponent(payload.access_token)}; Path=/; ${remember ? "Max-Age=2592000; " : ""}SameSite=Lax`;
      window.location.assign("/");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Не удалось выполнить вход.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="relative flex min-h-screen items-center justify-center overflow-hidden bg-[#1E1E21] px-4 py-8 text-[#f4f7fb]">
      <img src="/login_background.png" alt="" className="absolute inset-0 h-full w-full object-cover" />
      <section className="relative z-10 w-full max-w-[608px] rounded-[28px] bg-[#2E3137] px-6 py-10 shadow-[0_28px_80px_rgba(0,0,0,0.35)] sm:px-12 sm:py-12">
        <div className="mx-auto max-w-[512px]">
          <h1 className="text-center text-4xl font-medium tracking-[-0.04em]">Добро пожаловать!</h1>
          <form className="mt-10 space-y-5" onSubmit={submit}>
            <input
              value={login}
              onChange={(event) => setLogin(event.target.value)}
              placeholder="Логин"
              autoComplete="username"
              required
              className="h-16 w-full rounded-full border border-[#5b5f67] bg-transparent px-8 text-lg text-[#f4f7fb] outline-none placeholder:text-slate-400 focus:border-[#FFF27A]"
            />
            <input
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="Пароль"
              type="password"
              autoComplete="current-password"
              required
              className="h-16 w-full rounded-full border border-[#5b5f67] bg-transparent px-8 text-lg text-[#f4f7fb] outline-none placeholder:text-slate-400 focus:border-[#FFF27A]"
            />
            <label className="flex cursor-pointer items-center justify-end gap-3 text-base text-slate-200">
              <input type="checkbox" checked={remember} onChange={(event) => setRemember(event.target.checked)} className="h-5 w-5 accent-[#FFF27A]" />
              Запомнить меня
            </label>
            {error ? <p className="text-center text-sm text-rose-300">{error}</p> : null}
            <button type="submit" disabled={loading} className="h-16 w-full rounded-full bg-[#FFF27A] text-lg font-medium text-[#1E1E21] transition hover:bg-[#fff59b] disabled:cursor-wait disabled:opacity-60">
              {loading ? "Входим..." : "Войти"}
            </button>
          </form>
        </div>
      </section>
    </main>
  );
}
