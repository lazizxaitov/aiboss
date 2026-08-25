export type ModuleConfig = {
  kind: "sales" | "finance" | "marketing" | "inventory" | "telegram" | "alerts" | "ceo" | "recommendations";
  eyebrow: string;
  title: string;
  description: string;
  status: string;
  note: string;
  points: string[];
  accent?: string;
  stats?: Array<{
    label: string;
    value: string;
    note: string;
  }>;
  sources?: string[];
  actions?: string[];
};
