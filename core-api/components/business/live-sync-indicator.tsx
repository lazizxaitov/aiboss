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
  if (!snapshot) {
    return (
      <Badge variant="soft" className={className}>
        Обновление...
      </Badge>
    );
  }

  const variant =
    snapshot.state === "live"
      ? "success"
      : snapshot.state === "delayed"
        ? "warning"
        : snapshot.state === "stale"
          ? "danger"
          : "soft";

  return (
    <Badge variant={variant} className={cn("whitespace-nowrap", className)}>
      {snapshot.label}
    </Badge>
  );
}
