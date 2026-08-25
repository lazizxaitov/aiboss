import { MetricCard } from "@/components/ui/metric-card";

type MetricTileVariant = "revenue" | "expense" | "flow" | "marketing" | "cac" | "romi" | "default";

type MetricTileProps = {
  label: string;
  value: string;
  note: string;
  size?: "compact" | "regular" | "wide" | "hero";
  variant?: MetricTileVariant;
  uiScale?: number;
};

export function MetricTile({
  label,
  value,
  note,
  size = "regular",
  variant = "default",
  uiScale = 1,
}: MetricTileProps) {
  const tone = variant === "revenue"
    ? "emerald"
    : variant === "expense"
      ? "rose"
      : variant === "flow"
        ? "violet"
        : variant === "marketing"
          ? "sky"
          : variant === "cac"
            ? "amber"
            : variant === "romi"
              ? "sky"
              : "slate";

  return (
    <MetricCard
      label={label}
      value={value}
      note={note}
      tone={tone}
      compact={size === "compact"}
      detail={uiScale >= 1.08 ? "Расширенный вид" : undefined}
    />
  );
}
