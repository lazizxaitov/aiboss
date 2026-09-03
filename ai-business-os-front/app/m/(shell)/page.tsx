"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { getDashboardOverview, type DashboardCard, type DashboardOverviewResponse } from "@/lib/core-api";

const QUICK_LINKS: { href: string; label: string; icon: string }[] = [
  { href: "/sales", label: "Продажи", icon: "/sales.png" },
  { href: "/finance", label: "Финансы", icon: "/finance.png" },
  { href: "/customers", label: "Клиенты", icon: "/customers.png" },
  { href: "/inventory", label: "Склад", icon: "/inventory.png" },
];

function MetricTile({ card }: { card: DashboardCard }) {
  return (
    <div className="rounded-2xl border border-[#3a3d43] bg-[#2E3137] p-4">
      <p className="text-xs text-slate-400">{card.label}</p>
      <p className="mt-1 truncate text-xl font-semibold text-[#f4f7fb]">{card.value}</p>
      {card.change ? <p className="mt-1 text-xs text-emerald-300">{card.change}</p> : card.note ? <p className="mt-1 truncate text-xs text-slate-500">{card.note}</p> : null}
    </div>
  );
}

export default function MobileHomePage() {
  const [overview, setOverview] = useState<DashboardOverviewResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void getDashboardOverview()
      .then((data) => {
        if (!cancelled) setOverview(data);
      })
      .catch((reason) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "Не удалось загрузить данные");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const metrics = (overview?.business_metrics ?? []).slice(0, 4);
  const insights = (overview?.ai_insights ?? []).slice(0, 3);

  return (
    <div className="flex w-full min-w-0 flex-col gap-6">
      <div>
        <p className="text-xs uppercase tracking-[0.28em] text-slate-400">Обзор</p>
        <h1 className="mt-1 text-xl font-semibold tracking-[-0.02em] text-[#f4f7fb]">Ключевые показатели</h1>
      </div>

      {error ? (
        <p className="text-sm text-rose-300">{error}</p>
      ) : metrics.length ? (
        <div className="grid min-w-0 grid-cols-2 gap-3">
          {metrics.map((card) => (
            <MetricTile key={card.label} card={card} />
          ))}
        </div>
      ) : (
        <p className="text-sm text-slate-400">Загрузка показателей...</p>
      )}

      {insights.length ? (
        <div className="min-w-0 space-y-2 rounded-2xl border border-[#3a3d43] bg-[#2E3137] p-4">
          <p className="text-xs uppercase tracking-[0.28em] text-slate-400">Заметки ИИ</p>
          <ul className="space-y-2 text-sm leading-6 text-slate-300">
            {insights.map((insight, index) => (
              <li key={index} className="break-words">
                {insight}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <div>
        <p className="mb-3 text-xs uppercase tracking-[0.28em] text-slate-400">Разделы</p>
        <div className="grid min-w-0 grid-cols-4 gap-3">
          {QUICK_LINKS.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="flex flex-col items-center gap-2 rounded-2xl border border-[#3a3d43] bg-[#2E3137] p-3 text-center"
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={item.icon} alt="" className="h-6 w-6 object-contain opacity-90" />
              <span className="text-[11px] leading-tight text-slate-300">{item.label}</span>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
