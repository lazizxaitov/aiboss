"use client";
/* eslint-disable @next/next/no-img-element */

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";

import { cn } from "@/lib/cn";

type SidebarItem = {
  href: string;
  label: string;
  icon:
    | "dashboard"
    | "analytics"
    | "sales"
    | "visits"
    | "product"
    | "inventory"
    | "customer"
    | "payout"
    | "profile"
    | "inbox"
    | "settings";
  badge?: number;
};

const mainItems: SidebarItem[] = [
  { href: "/", icon: "dashboard", label: "Бизнес-обзор" },
  { href: "/ceo", icon: "analytics", label: "Аналитика" },
  { href: "/sales", icon: "sales", label: "Продажи" },
  { href: "/visits", icon: "visits", label: "Визиты" },
  { href: "/products", icon: "product", label: "Товары" },
  { href: "/inventory", icon: "inventory", label: "Склад" },
  { href: "/customers", icon: "customer", label: "Клиенты" },
  { href: "/finance", icon: "payout", label: "Финансы" },
];

const settingsItems: SidebarItem[] = [
  { href: "/profile", icon: "profile", label: "Профиль" },
  { href: "/settings", icon: "settings", label: "Настройки" },
  { href: "/alerts", icon: "inbox", label: "Уведомления" },
];

function isActive(pathname: string, searchParams: { toString(): string }, href: string) {
  const [path, query] = href.split("?");
  if (path === "/") {
    return pathname === "/";
  }

  if (pathname !== path && !pathname.startsWith(`${path}/`)) return false;
  if (!query) return true;
  return new URLSearchParams(query).toString() === searchParams.toString();
}

function SidebarIcon({ name, active }: { name: SidebarItem["icon"]; active?: boolean }) {
  const src =
    name === "dashboard"
      ? "/dashboard.png"
      : name === "analytics"
        ? "/ceo.png"
        : name === "sales"
          ? "/sales.png"
          : name === "visits"
            ? "/visits.png"
            : name === "product"
              ? "/products.png"
              : name === "inventory"
                ? "/inventory.png"
                : name === "customer"
                  ? "/customers.png"
                  : name === "payout"
                    ? "/finance.png"
                    : name === "profile"
                      ? "/customers.png"
                      : name === "inbox"
                        ? "/notifications.png"
                        : "/settings.png";

  return (
    <img
      src={src}
      alt=""
      className={cn(
        "h-6 w-6 select-none object-contain transition duration-200",
        active ? "opacity-100" : "opacity-80",
      )}
      draggable={false}
      aria-hidden="true"
    />
  );
}

function SidebarLink({ item, active }: { item: SidebarItem; active: boolean }) {
  return (
    <Link
      href={item.href}
      title={item.label}
      className={cn(
        "group relative flex h-12 w-12 items-center justify-center rounded-full transition duration-200",
        active
          ? "bg-[#50545c] text-[#f4f7fb] shadow-[0_10px_24px_rgba(0,0,0,0.18)]"
          : "text-slate-300 hover:text-[#f4f7fb]",
      )}
    >
      <span className={cn("flex h-6 w-6 items-center justify-center", active ? "text-[#f4f7fb]" : "text-slate-400")}>
        <SidebarIcon name={item.icon} active={active} />
      </span>
      <span className="pointer-events-none absolute left-full top-1/2 z-50 ml-3 -translate-y-1/2 whitespace-nowrap rounded-xl border border-[#3a3d43] bg-[#2E3137] px-3 py-2 text-xs font-medium text-[#f4f7fb] opacity-0 shadow-[0_12px_28px_rgba(0,0,0,0.22)] transition-opacity duration-150 group-hover:opacity-100 group-focus-visible:opacity-100">
        {item.label}
      </span>
    </Link>
  );
}

export function AppSidebar() {
  const pathname = usePathname();
  const searchParams = useSearchParams();

  return (
    <aside className="hidden shrink-0 lg:flex lg:h-[calc(100dvh-8rem)] lg:w-[88px] lg:self-start lg:sticky lg:top-[6.5rem] lg:z-30">
      <div className="flex h-full w-[88px] flex-col items-center overflow-visible rounded-[20px] bg-[#2E3137] px-0 py-[16px] shadow-[0_18px_50px_rgba(0,0,0,0.22)]">
        <nav className="flex w-full flex-1 flex-col items-center gap-[22px]">
          {mainItems.map((item) => (
            <SidebarLink key={item.href} item={item} active={isActive(pathname, searchParams, item.href)} />
          ))}
        </nav>

        <div className="flex-1" />

        <nav className="flex w-full flex-col items-center gap-[22px] pb-[24px]">
          {settingsItems.map((item) => (
            <SidebarLink key={item.href} item={item} active={isActive(pathname, searchParams, item.href)} />
          ))}
        </nav>
      </div>
    </aside>
  );
}
