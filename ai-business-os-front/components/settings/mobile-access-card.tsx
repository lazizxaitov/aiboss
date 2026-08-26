"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Surface } from "@/components/ui/surface";

export function MobileAccessCard() {
  const [qr, setQr] = useState<string | null>(null);
  const publicUrl = process.env.NEXT_PUBLIC_AIBOSS_PUBLIC_URL?.trim().replace(/\/$/, "") ?? "";

  useEffect(() => {
    if (!publicUrl) return;
    setQr(`https://api.qrserver.com/v1/create-qr-code/?size=180x180&data=${encodeURIComponent(publicUrl)}`);
  }, [publicUrl]);

  return <Surface><div className="rounded-[28px] bg-[#2E3137] p-6 sm:p-7"><div className="flex flex-col gap-5 md:flex-row md:items-center md:justify-between"><div className="max-w-xl space-y-2"><p className="text-xs uppercase tracking-[0.32em] text-slate-400">Доступ</p><h2 className="text-2xl font-semibold tracking-[-0.04em] text-[#f4f7fb]">Мобильный доступ</h2><p className="text-sm leading-6 text-slate-400">Отсканируйте QR-код камерой телефона, чтобы открыть AI Business OS. Авторизация на телефоне создаст отдельную сессию.</p>{publicUrl ? <p className="break-all text-xs text-slate-500">{publicUrl}</p> : <p className="text-sm text-yellow-200">Настройте NEXT_PUBLIC_AIBOSS_PUBLIC_URL, чтобы создать QR-код.</p>}<Button type="button" variant="secondary" size="sm" disabled={!publicUrl} onClick={() => void navigator.clipboard?.writeText(publicUrl)}>Скопировать ссылку</Button></div><div className="flex min-h-[196px] min-w-[196px] items-center justify-center rounded-2xl bg-[#f4f7fb] p-2">{qr ? <img src={qr} alt="QR-код мобильного доступа" className="h-[180px] w-[180px]" /> : <span className="px-5 text-center text-xs text-[#5d626b]">QR-код недоступен</span>}</div></div></div></Surface>;
}
