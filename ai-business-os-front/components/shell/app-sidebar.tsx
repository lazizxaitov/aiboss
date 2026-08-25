"use client";
/* eslint-disable @next/next/no-img-element */

import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/cn";

type SidebarItem = {
  href: string;
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
  { href: "/", icon: "dashboard" },
  { href: "/ceo", icon: "analytics" },
  { href: "/sales", icon: "sales" },
  { href: "/visits", icon: "visits" },
  { href: "/products", icon: "product" },
  { href: "/inventory", icon: "inventory" },
  { href: "/customers", icon: "customer" },
  { href: "/finance", icon: "payout" },
];

const settingsItems: SidebarItem[] = [
  { href: "/settings", icon: "profile" },
  { href: "/settings/integrations/smartup", icon: "settings" },
  { href: "/alerts", icon: "inbox" },
];

function isActive(pathname: string, href: string) {
  if (href === "/") {
    return pathname === "/";
  }

  return pathname === href || pathname.startsWith(`${href}/`);
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
      className={cn(
        "flex h-12 w-12 items-center justify-center rounded-full transition duration-200",
        active
          ? "bg-[#50545c] text-[#f4f7fb] shadow-[0_10px_24px_rgba(0,0,0,0.18)]"
          : "text-slate-300 hover:text-[#f4f7fb]",
      )}
      title={item.href}
    >
      <span className={cn("flex h-6 w-6 items-center justify-center", active ? "text-[#f4f7fb]" : "text-slate-400")}>
        <SidebarIcon name={item.icon} active={active} />
      </span>
    </Link>
  );
}

export function AppSidebar() {
  const pathname = usePathname();

  return (
    <aside className="hidden shrink-0 lg:flex lg:h-[calc(100dvh-8rem)] lg:w-[88px] lg:self-start lg:sticky lg:top-[6.5rem] lg:z-30">
      <div className="flex h-full w-[88px] flex-col items-center overflow-hidden rounded-[20px] bg-[#2E3137] px-0 py-[16px] shadow-[0_18px_50px_rgba(0,0,0,0.22)]">
        <nav className="flex w-full flex-1 flex-col items-center gap-[22px]">
          {mainItems.map((item) => (
            <SidebarLink key={item.href} item={item} active={isActive(pathname, item.href)} />
          ))}
        </nav>

        <div className="flex-1" />

        <nav className="flex w-full flex-col items-center gap-[22px] pb-[24px]">
          {settingsItems.map((item) => (
            <SidebarLink key={item.href} item={item} active={isActive(pathname, item.href)} />
          ))}
        </nav>
      </div>
    </aside>
  );
}
