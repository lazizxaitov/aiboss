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
    <div className="fixed inset-0 z-[120] flex items-center justify-center p-4 sm:p-6">
      <button
        type="button"
        aria-label="Закрыть панель"
        className="absolute inset-0 cursor-default bg-black/55 backdrop-blur-[2px]"
        onClick={onClose}
      />

      <aside
        className={cn(
          "relative flex max-h-[calc(100dvh-2rem)] w-full max-w-[min(64rem,calc(100vw-2rem))] flex-col overflow-hidden rounded-[28px] border border-[#3a3d43] bg-[linear-gradient(180deg,#2E3137_0%,#26292e_100%)] shadow-[0_24px_80px_rgba(0,0,0,0.28)] sm:max-h-[calc(100dvh-3rem)]",
          className,
        )}
      >
        <div className="flex items-start justify-between gap-4 border-b border-[#3a3d43] px-5 py-5 sm:px-6">
          <div className="min-w-0">
            <p className="text-[11px] uppercase tracking-[0.3em] text-slate-400">Подробности</p>
            <h2 className="mt-2 truncate text-2xl font-semibold tracking-[-0.05em] text-[#f4f7fb]">{title}</h2>
            {description ? <p className="mt-2 text-sm leading-6 text-slate-400">{description}</p> : null}
            {badges ? <div className="mt-3 flex flex-wrap gap-2">{badges}</div> : null}
          </div>

          <div className="flex items-center gap-2">
            {actions}
            <button
              type="button"
              onClick={onClose}
              className="inline-flex h-10 w-10 items-center justify-center rounded-full border border-[#3a3d43] bg-[#2E3137] text-slate-300 transition hover:border-[#4a4e56] hover:text-white"
              aria-label="Закрыть"
            >
              ×
            </button>
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5 sm:px-6">{children}</div>
      </aside>
    </div>,
    document.body,
  );
}
