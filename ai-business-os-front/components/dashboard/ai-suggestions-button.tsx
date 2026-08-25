"use client";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/cn";

type AiSuggestionsButtonProps = {
  count: number;
  open: boolean;
  onClick: () => void;
};

export function AiSuggestionsButton({ count, open, onClick }: AiSuggestionsButtonProps) {
  return (
    <Button
      type="button"
      variant={open ? "primary" : "secondary"}
      size="sm"
      onClick={onClick}
      className={cn("shrink-0", open && "shadow-[0_12px_28px_rgba(15,23,42,0.18)]")}
    >
      <span>Предложения ИИ</span>
      <Badge variant={open ? "neutral" : "soft"} className="ml-1">
        {count}
      </Badge>
    </Button>
  );
}

