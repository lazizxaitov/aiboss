'use client';

import Link from "next/link";
import { usePathname } from "next/navigation";
import { dashboardNavigation } from "@/lib/navigation";
import { cn } from "@/lib/cn";

export function AppDock() {
  const pathname = usePathname();

  return (
    <div className="border-b border-[#3a3d43] bg-[#2E3137]/80 backdrop-blur-xl">
      <div className="mx-auto max-w-[1600px] px-4 py-3 sm:px-6 lg:px-8">
        <div className="flex gap-2 overflow-x-auto rounded-[24px] border border-[#3a3d43] bg-[#2E3137] p-2 shadow-[0_1px_2px_rgba(15,23,42,0.03),0_10px_30px_rgba(15,23,42,0.04)]">
          {dashboardNavigation.map((item) => {
            const active =
              item.href === "/"
                ? pathname === "/"
                : pathname === item.href || pathname.startsWith(`${item.href}/`);

            return (
              <Link
                key={item.href}
                href={item.href}
                title={item.note}
                aria-label={item.label}
                className={cn(
                  "shrink-0 rounded-2xl border px-3.5 py-2 text-sm font-medium transition-colors duration-200",
                  active
                    ? "border-[#FFF27A]/30 bg-[#FFF27A] text-[#1E1E21] shadow-sm"
                    : "border-transparent bg-[#2E3137] text-slate-400 hover:border-[#3a3d43] hover:bg-[#343840] hover:text-[#f4f7fb]",
                )}
              >
                {item.label}
              </Link>
            );
          })}
        </div>
      </div>
    </div>
  );
}
