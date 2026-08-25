"use client";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Surface } from "@/components/ui/surface";
import { cn } from "@/lib/cn";
import type { LauncherSuggestionPreview } from "@/lib/launcher/types";
import {
  getLauncherAIActionLabel,
  getLauncherAIPreviewBadge,
} from "@/lib/launcher/ai-presentation";

type AiPreviewBannerProps = {
  preview: LauncherSuggestionPreview;
  onApply: () => void;
  onCancel: () => void;
  onOpenSuggestions?: () => void;
};

export function AiPreviewBanner({ preview, onApply, onCancel, onOpenSuggestions }: AiPreviewBannerProps) {
  return (
    <Surface className="border-[#FFF27A]/30 bg-[linear-gradient(180deg,#2E3137_0%,#26292e_100%)] px-4 py-4 shadow-[0_16px_36px_rgba(0,0,0,0.18)] sm:px-5">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="accent">Предпросмотр изменений ИИ</Badge>
            <Badge variant="neutral">{getLauncherAIPreviewBadge(preview.appliedActions, preview.rejectedActions)}</Badge>
          </div>
          <h3 className="mt-3 text-[22px] font-semibold tracking-[-0.04em] text-[#f4f7fb]">
            {preview.suggestion.title}
          </h3>
          <p className="mt-2 max-w-4xl text-sm leading-6 text-slate-300">{preview.suggestion.summary}</p>
          <p className="mt-3 text-sm font-medium text-slate-300">{preview.message}</p>

          <div className="mt-4 flex flex-wrap gap-2">
            {preview.actions.map((item) => (
              <Badge
                key={`${preview.suggestion.id}-${item.action.type}-${item.action.widgetId}`}
                variant={item.applied ? "accent" : "soft"}
                className={cn(item.applied ? "border-[#FFF27A]/30" : "border-[#3a3d43]")}
              >
                <span className="mr-2">{getLauncherAIActionLabel(item.action)}</span>
                <span className="opacity-70">·</span>
                <span className="ml-2">{item.message}</span>
              </Badge>
            ))}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {onOpenSuggestions ? (
            <Button type="button" size="sm" variant="ghost" onClick={onOpenSuggestions}>
              Предложения
            </Button>
          ) : null}
          <Button type="button" size="sm" variant="secondary" onClick={onCancel}>
            Отмена
          </Button>
          <Button type="button" size="sm" variant="primary" onClick={onApply}>
            Применить
          </Button>
        </div>
      </div>
    </Surface>
  );
}
