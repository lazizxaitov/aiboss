"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { Drawer } from "@/components/ui/drawer";
import { MobileActionButton } from "@/components/mobile/mobile-action-button";
// MobileComposerProvider now lives in the parent app/m/layout.tsx, shared
// with the sibling /m/chat route — see the comment there for why.

type MenuItem = { href: string; label: string; icon: string };

// Same destinations as the desktop sidebar (components/shell/app-sidebar.tsx).
// They open the existing, already-responsive desktop pages for now — giving
// each one its own purpose-built /m/... screen is a natural next step, one
// page at a time, once this shell and the reduced /m dashboard are in place.
const MENU_ITEMS: MenuItem[] = [
  { href: "/m", label: "Главная", icon: "/dashboard.png" },
  { href: "/m/chat", label: "Чат с ИИ", icon: "/ceo.png" },
  { href: "/ceo", label: "Аналитика", icon: "/ceo.png" },
  { href: "/sales", label: "Продажи", icon: "/sales.png" },
  { href: "/visits", label: "Визиты", icon: "/visits.png" },
  { href: "/products", label: "Товары", icon: "/products.png" },
  { href: "/inventory", label: "Склад", icon: "/inventory.png" },
  { href: "/customers", label: "Клиенты", icon: "/customers.png" },
  { href: "/finance", label: "Финансы", icon: "/finance.png" },
  { href: "/profile", label: "Профиль", icon: "/customers.png" },
  { href: "/settings", label: "Настройки", icon: "/settings.png" },
  { href: "/alerts", label: "Уведомления", icon: "/notifications.png" },
];

function hasSession(): boolean {
  if (typeof document === "undefined") return false;
  return document.cookie.split(";").some((item) => item.trim().startsWith("aibos_owner_session="));
}

export default function MobileShellLayout({ children }: Readonly<{ children: ReactNode }>) {
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);
  const [checked, setChecked] = useState(false);
  const [authorized, setAuthorized] = useState(false);

  useEffect(() => {
    if (hasSession()) {
      setAuthorized(true);
    } else {
      window.location.replace("/login");
    }
    setChecked(true);
  }, []);

  if (!checked || !authorized) {
    return <div className="flex min-h-dvh items-center justify-center text-sm text-slate-400">Загрузка...</div>;
  }

  return (
    <div className="flex min-h-dvh flex-col">
      <header className="sticky top-0 z-40 flex h-14 shrink-0 items-center justify-center border-b border-[#3a3d43] bg-[#1E1E21]/95 backdrop-blur">
        <span className="text-sm font-semibold tracking-[-0.02em] text-[#f4f7fb]">AI Business OS</span>
      </header>

      <main className="min-h-0 w-full flex-1 overflow-x-hidden px-4 pb-28 pt-4">{children}</main>

      <nav className="fixed inset-x-3 bottom-3 z-40 grid grid-cols-3 rounded-[24px] border border-[#3a3d43] bg-[#2E3137]/95 p-2 shadow-[0_18px_50px_rgba(0,0,0,0.35)] backdrop-blur">
        <button
          type="button"
          onClick={() => setMenuOpen(true)}
          className="flex min-h-14 flex-col items-center justify-center gap-1 rounded-2xl text-[11px] text-slate-300"
        >
          <span aria-hidden="true" className="text-xl leading-none">
            ☰
          </span>
          <span>Меню</span>
        </button>

        <MobileActionButton />

        <button
          type="button"
          disabled
          title="Скоро"
          className="flex min-h-14 flex-col items-center justify-center gap-1 rounded-2xl text-[11px] text-slate-500 opacity-50"
        >
          <span aria-hidden="true" className="text-xl leading-none">
            ⚙
          </span>
          <span>Режим</span>
        </button>
      </nav>

      <Drawer open={menuOpen} onClose={() => setMenuOpen(false)} title="Меню" className="max-w-sm">
        <nav className="flex flex-col gap-1">
          {MENU_ITEMS.map((item) => {
            const active = item.href === "/m" ? pathname === "/m" : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setMenuOpen(false)}
                className={`flex items-center gap-3 rounded-2xl px-3 py-3 text-sm transition ${
                  active ? "bg-[#3a3d43] text-[#f4f7fb]" : "text-slate-300 hover:bg-[#343840]"
                }`}
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={item.icon} alt="" className="h-5 w-5 object-contain" />
                {item.label}
              </Link>
            );
          })}
        </nav>
      </Drawer>
    </div>
  );
}
