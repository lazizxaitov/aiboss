"use client";

import { useEffect, useState } from "react";
import { getMarketingAttributionStatus, type MarketingAttributionStatus } from "@/lib/core-api";

export function MarketingMeasurementCard() {
  const [status, setStatus] = useState<MarketingAttributionStatus | null>(null);
  useEffect(() => { void getMarketingAttributionStatus().then(setStatus).catch(() => undefined); }, []);
  return <div className="rounded-[28px] bg-[#2E3137] p-6 sm:p-7"><p className="text-xs uppercase tracking-[0.32em] text-slate-400">Маркетинговые измерения</p><h2 className="mt-2 text-2xl font-semibold text-[#f4f7fb]">Атрибуция</h2><p className="mt-3 text-sm text-slate-300">{status?.message ?? "Проверка tracking evidence..."}</p>{status?.confirmed_attribution_available ? <p className="mt-2 text-xs text-slate-400">Подтверждённых результатов: {status.attributed_outcome_count}</p> : null}</div>;
}
