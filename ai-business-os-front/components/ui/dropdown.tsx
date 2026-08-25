"use client";

import { cloneElement, isValidElement, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import type {
  CSSProperties,
  KeyboardEvent as ReactKeyboardEvent,
  MouseEvent as ReactMouseEvent,
  ReactElement,
  ReactNode,
} from "react";
import { createPortal } from "react-dom";

import { cn } from "@/lib/cn";

type DropdownAlign = "left" | "right" | "stretch";

type DropdownTriggerProps = {
  className?: string;
  onClick?: (event: ReactMouseEvent<HTMLElement>) => void;
  onKeyDown?: (event: ReactKeyboardEvent<HTMLElement>) => void;
  "aria-haspopup"?: string;
  "aria-expanded"?: boolean;
};

type DropdownProps = {
  trigger: ReactElement | ReactNode;
  children: (close: () => void) => ReactNode;
  className?: string;
  panelClassName?: string;
  triggerClassName?: string;
  align?: DropdownAlign;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
};

export function Dropdown({
  trigger,
  children,
  className,
  panelClassName,
  triggerClassName,
  align = "left",
  open,
  onOpenChange,
}: DropdownProps) {
  const [internalOpen, setInternalOpen] = useState(false);
  const resolvedOpen = open ?? internalOpen;
  const rootRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const [panelStyle, setPanelStyle] = useState<CSSProperties | null>(null);

  const setOpen = useMemo(
    () => (next: boolean) => {
      if (onOpenChange) {
        onOpenChange(next);
      } else {
        setInternalOpen(next);
      }
    },
    [onOpenChange],
  );
  const triggerElement = trigger as ReactElement<DropdownTriggerProps>;

  useLayoutEffect(() => {
    if (!resolvedOpen) return;

    const updatePosition = () => {
      const root = rootRef.current;
      const panel = panelRef.current;
      if (!root || !panel) return;

      const trigger = root.querySelector("[data-dropdown-trigger='true']") as HTMLElement | null;
      const anchor = trigger ?? root;
      const triggerRect = anchor.getBoundingClientRect();
      const panelRect = panel.getBoundingClientRect();
      const gap = 4;
      const viewportPadding = 8;

      let left = triggerRect.left;
      if (align === "right") {
        left = triggerRect.right - panelRect.width;
      } else if (align === "stretch") {
        left = triggerRect.left;
      }

      const maxLeft = window.innerWidth - viewportPadding - panelRect.width;
      const safeLeft = Math.min(Math.max(left, viewportPadding), Math.max(viewportPadding, maxLeft));
      const safeTop = triggerRect.bottom + gap;
      const maxWidth = Math.max(0, window.innerWidth - viewportPadding * 2);

      setPanelStyle({
        position: "fixed",
        top: Math.round(safeTop),
        left: Math.round(safeLeft),
        width: align === "stretch" ? triggerRect.width : undefined,
        maxWidth,
        zIndex: 200,
        visibility: "visible",
      });
    };

    updatePosition();
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);

    return () => {
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
    };
  }, [align, resolvedOpen]);

  useEffect(() => {
    if (!resolvedOpen) return;

    const handlePointerDown = (event: PointerEvent) => {
      const target = event.target as Node | null;
      if (target && (rootRef.current?.contains(target) || panelRef.current?.contains(target))) return;
      setOpen(false);
    };

    const handleEscape = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };

    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleEscape);

    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleEscape);
    };
  }, [resolvedOpen, setOpen]);

  return (
    <div ref={rootRef} className={cn("relative isolate", className)}>
      {isValidElement(trigger)
        ? cloneElement(triggerElement, {
            className: cn(triggerElement.props.className, "w-full outline-none", triggerClassName),
            "data-dropdown-trigger": "true",
            "aria-haspopup": "menu",
            "aria-expanded": resolvedOpen,
            onClick: (event: ReactMouseEvent<HTMLElement>) => {
              triggerElement.props.onClick?.(event);
              if (!event.defaultPrevented) {
                setOpen(!resolvedOpen);
              }
            },
            onKeyDown: (event: ReactKeyboardEvent<HTMLElement>) => {
              triggerElement.props.onKeyDown?.(event);
              if (event.defaultPrevented) return;
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                setOpen(!resolvedOpen);
              }
            },
          } as DropdownTriggerProps & Record<string, unknown>)
        : (
          <div
            role="button"
            tabIndex={0}
            className={cn("w-full outline-none", triggerClassName)}
            onClick={() => setOpen(!resolvedOpen)}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                setOpen(!resolvedOpen);
              }
            }}
          >
            {trigger}
          </div>
        )}
      {resolvedOpen && typeof document !== "undefined"
        ? createPortal(
            <div
              ref={panelRef}
              style={panelStyle ?? { visibility: "hidden" }}
              className={cn(
                "rounded-[24px] border border-[#3a3d43] bg-[#2E3137] shadow-[0_24px_60px_rgba(0,0,0,0.2)]",
                panelClassName,
              )}
            >
              {children(() => setOpen(false))}
            </div>,
            document.body,
          )
        : null}
    </div>
  );
}
