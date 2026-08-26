import type {
  FinanceWorkspaceView,
  InventoryWorkspaceView,
  VisitsWorkspaceTab,
} from "@/lib/core-api";

export const INVENTORY_VIEWS: Array<{ view: InventoryWorkspaceView; label: string }> = [
  { view: "current_stock", label: "Текущие остатки" },
  { view: "movements", label: "Движение запасов" },
  { view: "purchases", label: "Поступления" },
  { view: "warehouses", label: "Склады" },
];

export const VISITS_TABS: Array<{ tab: VisitsWorkspaceTab; label: string }> = [
  { tab: "visits", label: "Визиты" },
  { tab: "sales_reps", label: "Торговые представители" },
  { tab: "working_zones", label: "Рабочие зоны" },
  { tab: "capabilities", label: "Покрытие данных" },
];

export const FINANCE_VIEWS: Array<{ view: FinanceWorkspaceView; label: string }> = [
  { view: "overview", label: "Обзор" },
  { view: "payments", label: "Платежи" },
  { view: "returns", label: "Возвраты" },
  { view: "cash_operations", label: "Кассовые операции" },
  { view: "bank_operations", label: "Банковские операции" },
];
