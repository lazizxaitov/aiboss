export type NavigationItem = {
  label: string;
  href: string;
  note: string;
};

export const dashboardNavigation: NavigationItem[] = [
  { label: "Обзор", href: "/", note: "Единый бизнес-экран" },
  { label: "Продажи", href: "/sales", note: "Воронка и прогноз" },
  { label: "Финансы", href: "/finance", note: "Денежный поток и отчётность" },
  { label: "Маркетинг", href: "/marketing", note: "Каналы и окупаемость" },
  { label: "Товары", href: "/products", note: "Ассортимент и Product 360" },
  { label: "Склад", href: "/inventory", note: "Остатки и баланс" },
  { label: "Клиенты", href: "/customers", note: "Клиентская база и LTV" },
  { label: "Телеграм", href: "/telegram", note: "Каналы и сигналы" },
  { label: "Сигналы", href: "/alerts", note: "События и аномалии" },
  { label: "Руководитель", href: "/ceo", note: "Краткая сводка по бизнесу" },
  { label: "Рекомендации", href: "/recommendations", note: "Следующие действия" },
];

export function getDashboardItem(pathname: string) {
  return (
    dashboardNavigation.find((item) => {
      if (item.href === "/") {
        return pathname === "/";
      }

      return pathname === item.href || pathname.startsWith(`${item.href}/`);
    }) ?? dashboardNavigation[0]
  );
}

export const overviewSections = [
  {
    title: "Ключевые показатели",
    note: "Сводный слой для быстрых решений на уровне руководства.",
  },
  {
    title: "Продажи",
    note: "Воронка, прогноз, сделки и действия команды.",
  },
  {
    title: "Финансы",
    note: "Денежный поток, прибыль и убыток, контроль затрат.",
  },
  {
    title: "Маркетинг",
    note: "Каналы, кампании и эффективность контента.",
  },
  {
    title: "Остатки",
    note: "Текущий баланс, наличие и движение ресурсов.",
  },
  { title: "Телеграм", note: "Каналы, охват и обратная связь по сообщениям." },
  {
    title: "Сигналы",
    note: "События, на которые нужно реагировать сразу.",
  },
  {
    title: "Сводка руководителя",
    note: "Короткий обзор рисков, возможностей и приоритетов.",
  },
  { title: "Рекомендации", note: "Следующие шаги, подсказки и предложения по действиям." },
] as const;
