"use client";

import { type ReactNode, useEffect } from "react";
import { createPortal } from "react-dom";

import { cn } from "@/lib/cn";

type DrawerProps = {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  badges?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
};

export function Drawer({
  open,
  onClose,
  title,
  description,
  badges,
  actions,
  children,
  className,
}: DrawerProps) {
  useEffect(() => {
    if (!open) return;

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [open, onClose]);

  useEffect(() => {
    if (!open) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [open]);

  if (!open || typeof document === "undefined") {
    return null;
  }

  return createPortal(
    <div className="fixed inset-0 z-[120]">
      <button
        type="button"
        aria-label="Закрыть drawer"
        className="absolute inset-0 cursor-default bg-black/55 backdrop-blur-[2px]"
        onClick={onClose}
      />

      <aside
        className={cn(
          "absolute right-0 top-0 flex h-full w-full max-w-[min(40rem,100vw)] flex-col border-l border-[#3a3d43] bg-[linear-gradient(180deg,#2E3137_0%,#26292e_100%)] shadow-[0_24px_80px_rgba(0,0,0,0.28)]",
          className,
        )}
      >
        <div className="flex items-start justify-between gap-4 border-b border-[#3a3d43] px-6 py-5">
          <div className="min-w-0">
            <p className="text-[11px] uppercase tracking-[0.3em] text-slate-500">Подробности</p>
            <h2 className="mt-2 truncate text-2xl font-semibold tracking-[-0.05em] text-[#f4f7fb]">{title}</h2>
            {description ? <p className="mt-2 text-sm leading-6 text-slate-400">{description}</p> : null}
            {badges ? <div className="mt-3 flex flex-wrap gap-2">{badges}</div> : null}
          </div>

          <div className="flex items-center gap-2">
            {actions}
            <button
              type="button"
              onClick={onClose}
              className="inline-flex h-10 w-10 items-center justify-center rounded-full border border-[#3a3d43] bg-[#343840] text-slate-200 transition hover:border-[#4a4e56] hover:text-[#f4f7fb]"
              aria-label="Закрыть"
            >
              ×
            </button>
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">{children}</div>
      </aside>
    </div>,
    document.body,
  );
}
