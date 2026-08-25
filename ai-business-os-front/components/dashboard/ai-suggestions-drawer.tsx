"use client";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Drawer } from "@/components/ui/drawer";
import { Surface } from "@/components/ui/surface";
import { cn } from "@/lib/cn";
import { getLauncherAIActionLabel, getLauncherAIPriorityLabel } from "@/lib/launcher/ai-presentation";
import type { LauncherSuggestion, LauncherSuggestionPreview } from "@/lib/launcher/types";

type AiSuggestionsDrawerProps = {
  open: boolean;
  editMode: boolean;
  suggestions: LauncherSuggestion[];
  selectedSuggestionId: string | null;
  preview: LauncherSuggestionPreview | null;
  onClose: () => void;
  onSelectPreview: (suggestion: LauncherSuggestion) => void;
  onApply: (suggestion: LauncherSuggestion) => void;
  onDismiss: (suggestionId: string) => void;
};

export function AiSuggestionsDrawer({
  open,
  editMode,
  suggestions,
  selectedSuggestionId,
  preview,
  onClose,
  onSelectPreview,
  onApply,
  onDismiss,
}: AiSuggestionsDrawerProps) {
  return (
    <Drawer
      open={open}
      onClose={onClose}
      title="Предложения ИИ"
      description="Подсказки ИИ показывают безопасные изменения раскладки без автоприменения."
      badges={
        <>
          <Badge variant="accent">{suggestions.length} предложений</Badge>
          {editMode ? <Badge variant="neutral">Предпросмотр отключён в режиме редактирования</Badge> : null}
        </>
      }
    >
      {suggestions.length > 0 ? (
        <div className="space-y-3">
          {suggestions.map((suggestion) => {
            const active = selectedSuggestionId === suggestion.id;
            return (
              <Surface
                key={suggestion.id}
                className={cn(
                  "border-[#3a3d43] px-4 py-4",
                  active && "border-[#FFF27A]/30 bg-[#343840] shadow-[0_12px_24px_rgba(0,0,0,0.18)]",
                )}
              >
                <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant="soft">{getLauncherAIPriorityLabel(suggestion.priority)}</Badge>
                      {active ? <Badge variant="accent">Выбран</Badge> : null}
                    </div>
                    <h3 className="mt-3 text-[18px] font-semibold tracking-[-0.04em] text-[#f4f7fb]">
                      {suggestion.title}
                    </h3>
                    <p className="mt-2 text-sm leading-6 text-slate-300">{suggestion.summary}</p>
                    <p className="mt-2 text-sm font-medium leading-6 text-slate-400">{suggestion.reason}</p>

                    <div className="mt-3 flex flex-wrap gap-2">
                      {suggestion.actions.map((action) => (
                        <Badge key={`${suggestion.id}-${action.type}-${action.widgetId}`} variant="neutral">
                          {getLauncherAIActionLabel(action)} · {action.widgetId}
                        </Badge>
                      ))}
                    </div>
                  </div>

                  <div className="flex shrink-0 flex-wrap items-center gap-2">
                    <Button
                      type="button"
                      size="sm"
                      variant={active && preview ? "primary" : "secondary"}
                      disabled={editMode}
                      onClick={() => onSelectPreview(suggestion)}
                    >
                      Посмотреть
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      variant="soft"
                      disabled={editMode}
                      onClick={() => onApply(suggestion)}
                    >
                      Применить
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      onClick={() => onDismiss(suggestion.id)}
                    >
                      Скрыть
                    </Button>
                  </div>
                </div>
              </Surface>
            );
          })}
        </div>
      ) : (
        <div className="flex h-full min-h-[280px] items-center justify-center">
          <div className="max-w-xl rounded-[28px] border border-dashed border-[#3a3d43] bg-[#2E3137] px-6 py-8 text-center">
            <p className="text-[18px] font-semibold tracking-[-0.04em] text-[#f4f7fb]">Пока нет предложений</p>
            <p className="mt-2 text-sm leading-6 text-slate-400">
              Когда появится безопасная подсказка, она будет доступна здесь.
            </p>
          </div>
        </div>
      )}
    </Drawer>
  );
}
