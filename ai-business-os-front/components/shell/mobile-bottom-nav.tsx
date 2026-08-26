"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/cn";

const items = [
  { href: "/", label: "Главная", icon: "/dashboard.png" },
  { href: "/#ai-chat", label: "ИИ", icon: "/ceo.png" },
  { href: "/alerts", label: "Уведомления", icon: "/notifications.png" },
  { href: "/settings", label: "Ещё", icon: "/settings.png" },
];

export function MobileBottomNav() {
  const pathname = usePathname();
  return (
    <nav className="fixed inset-x-3 bottom-3 z-50 grid grid-cols-4 rounded-[24px] border border-[#3a3d43] bg-[#2E3137]/95 p-2 shadow-[0_18px_50px_rgba(0,0,0,0.35)] backdrop-blur lg:hidden">
      {items.map((item) => {
        const targetPath = item.href.split("#")[0] || "/";
        const active = item.href === "/" || item.href === "/#ai-chat" ? pathname === "/" : pathname.startsWith(targetPath);
        return <Link key={item.label} href={item.href} className={cn("flex min-h-14 flex-col items-center justify-center gap-1 rounded-2xl text-[10px] text-slate-400", active && "bg-[#FFF27A] text-[#1E1E21]")}><img src={item.icon} alt="" className={cn("h-5 w-5 object-contain", !active && "opacity-75")} /><span>{item.label}</span></Link>;
      })}
    </nav>
  );
}
