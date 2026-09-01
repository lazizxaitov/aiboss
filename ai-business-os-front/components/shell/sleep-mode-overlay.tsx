"use client";

import { useEffect, useState } from "react";

import { getDashboardAIInsights } from "@/lib/core-api";

export function SleepModeOverlay({ onClose }: { onClose: () => void }) {
  const [now, setNow] = useState(() => new Date());
  const [thought, setThought] = useState("Мысли ИИ загружаются...");

  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 1000);
    void getDashboardAIInsights().then((payload) => {
      setThought(payload.summary || payload.message || "Новых мыслей ИИ пока нет.");
    }).catch(() => setThought("Мысли ИИ временно недоступны."));
    return () => window.clearInterval(timer);
  }, []);

  return (
    <div className="fixed inset-0 z-[110] flex items-center justify-center bg-[#101114]/95 px-6 text-[#f4f7fb]" onClick={onClose}>
      <div className="pointer-events-none text-center">
        <p className="text-[clamp(4rem,14vw,9rem)] font-light tracking-[-0.08em]">{now.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}</p>
        <p className="mt-2 text-lg text-slate-400">{now.toLocaleDateString("ru-RU", { weekday: "long", day: "numeric", month: "long" })}</p>
        <div className="mx-auto mt-12 max-w-xl rounded-3xl border border-white/10 bg-white/[0.04] px-6 py-5 text-left opacity-60 backdrop-blur-sm">
          <p className="text-[10px] uppercase tracking-[0.3em] text-slate-500">Мысли ИИ</p>
          <p className="mt-3 text-sm leading-6 text-slate-300">{thought}</p>
        </div>
        <p className="mt-10 text-xs text-slate-600">Нажмите в любом месте, чтобы вернуться</p>
      </div>
    </div>
  );
}
