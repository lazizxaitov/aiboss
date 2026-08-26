"use client";

import { useEffect, useState } from "react";

type InstallEvent = Event & { prompt: () => Promise<void> };

export function MobileInstallPrompt() {
  const [installEvent, setInstallEvent] = useState<InstallEvent | null>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const handler = (event: Event) => {
      event.preventDefault();
      setInstallEvent(event as InstallEvent);
      setVisible(true);
    };
    window.addEventListener("beforeinstallprompt", handler);
    return () => window.removeEventListener("beforeinstallprompt", handler);
  }, []);

  if (!visible || !installEvent) return null;
  return (
    <div className="fixed inset-x-4 bottom-24 z-50 rounded-2xl border border-[#3a3d43] bg-[#2E3137] p-4 shadow-[0_18px_50px_rgba(0,0,0,0.35)] lg:hidden">
      <p className="text-sm font-medium text-[#f4f7fb]">Добавить AI Business OS на экран телефона?</p>
      <div className="mt-3 flex gap-2">
        <button type="button" className="rounded-full bg-[#FFF27A] px-4 py-2 text-sm text-[#1E1E21]" onClick={() => void installEvent.prompt().then(() => setVisible(false))}>Установить</button>
        <button type="button" className="rounded-full border border-[#3a3d43] px-4 py-2 text-sm text-slate-300" onClick={() => setVisible(false)}>Позже</button>
      </div>
    </div>
  );
}
