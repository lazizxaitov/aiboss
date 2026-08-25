"use client";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/cn";
import type { BusinessFreshnessSnapshot } from "@/lib/business-refresh";

export function LiveSyncIndicator({
  snapshot,
  className,
}: {
  snapshot: BusinessFreshnessSnapshot | null;
  className?: string;
}) {
  const label = snapshot?.label ?? "Обновление...";
  const variant =
    snapshot?.state === "live"
      ? "accent"
      : snapshot?.state === "delayed"
        ? "soft"
        : snapshot?.state === "stale"
          ? "neutral"
          : snapshot?.state === "error"
            ? "neutral"
            : "neutral";

  return (
    <Badge variant={variant} className={cn("whitespace-nowrap", className)}>
      {label}
    </Badge>
  );
}
