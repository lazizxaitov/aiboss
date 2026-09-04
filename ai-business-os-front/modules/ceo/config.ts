import type { ModuleConfig } from "@/modules/shared/types";

export const ceoModule: ModuleConfig = {
  kind: "ceo",
  eyebrow: "Аналитика маркетинга",
  title: "Аналитика маркетинга",
  description: "Instagram, YouTube и реклама в Meta в одном месте — с разбором от AI.",
  accent: "Маркетинг",
  status: "Бизнес-данные",
  note: "Здесь собраны посты Instagram, видео YouTube и реклама в Meta — с AI-разбором того, что работает и что стоит изменить.",
  stats: [
    { label: "Посты Instagram", value: "0", note: "с данными за период" },
    { label: "Видео YouTube", value: "0", note: "с данными за период" },
    { label: "Реклама Meta", value: "0 UZS", note: "потрачено" },
  ],
  sources: [
    "Instagram (Meta)",
    "YouTube",
    "Реклама в Meta",
  ],
  actions: [
    "Показывать топ постов Instagram по вовлечённости.",
    "Показывать топ видео YouTube по просмотрам.",
    "Давать AI-разбор маркетинговых результатов и рекомендации.",
  ],
  points: [
    "Лучшие посты и видео за период — в одном месте.",
    "Реклама в Meta: расход, показы, охват.",
    "AI-комментарий с выводами и рекомендациями по контенту.",
  ],
};
