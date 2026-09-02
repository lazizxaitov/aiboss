"use client";

import { type ReactNode, useEffect, useState } from "react";

const coreApiUrl = "";

function StartupScreen({ failed, onRetry }: { failed: boolean; onRetry: () => void }) {
  return (
    <main className="flex min-h-screen items-center justify-center bg-[#1E1E21] px-6 text-[#f4f7fb]">
      <section className="w-full max-w-[360px] rounded-[26px] border border-[#3a3d43] bg-[#2E3137] px-8 py-9 text-center shadow-[0_22px_70px_rgba(0,0,0,0.3)]">
        <h1 className="text-xl font-medium tracking-[-0.04em]">AI Business OS запускается...</h1>
        <p className="mt-3 text-sm text-slate-400">
          {failed ? "Backend не запустился. Проверьте сервис и повторите попытку." : "Подключаем рабочие сервисы"}
        </p>
        {failed ? (
          <button type="button" onClick={onRetry} className="mt-6 h-11 w-full rounded-full bg-[#FFF27A] text-sm font-medium text-[#1E1E21]">
            Повторить подключение
          </button>
        ) : (
          <div className="mx-auto mt-6 h-[3px] w-8 overflow-hidden rounded-full bg-[#454952]">
            <div className="h-full w-2/5 animate-pulse rounded-full bg-[#FFF27A]" />
          </div>
        )}
      </section>
    </main>
  );
}

export function BackendStartupGate({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);
  const [retryKey, setRetryKey] = useState(0);

  useEffect(() => {
    let active = true;
    let timer: number | undefined;
    const deadline = Date.now() + 45_000;

    const check = async () => {
      try {
        const controller = new AbortController();
        const timeout = window.setTimeout(() => controller.abort(), 2500);
        const response = await fetch(`${coreApiUrl}/api/v1/health`, {
          cache: "no-store",
          signal: controller.signal,
        });
        window.clearTimeout(timeout);
        if (active && response.ok) {
          setReady(true);
          return;
        }
      } catch {
        // Backend can be unavailable while launchd is restarting it.
      }
      if (active && Date.now() >= deadline) {
        setFailed(true);
        return;
      }
      if (active) timer = window.setTimeout(() => void check(), 1000);
    };

    void check();
    return () => {
      active = false;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [retryKey]);

  return ready ? children : <StartupScreen failed={failed} onRetry={() => { setFailed(false); setReady(false); setRetryKey((value) => value + 1); }} />;
}
