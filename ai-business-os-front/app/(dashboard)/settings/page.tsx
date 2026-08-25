import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Surface } from "@/components/ui/surface";

export const dynamic = "force-dynamic";

const notificationRows = [
  { title: "Ежедневные сводки", description: "Короткий обзор по ключевым событиям за день" },
  { title: "Системные уведомления", description: "Сообщения о статусе синхронизации и доступе" },
  { title: "Напоминания", description: "Напоминания о задачах и важных действиях" },
];

const appearanceRows = [
  { title: "Тема", value: "Светлая" },
  { title: "Плотность интерфейса", value: "Стандартная" },
  { title: "Язык", value: "Русский" },
  { title: "Часовой пояс", value: "Asia/Tashkent" },
];

const securityRows = [
  { title: "Двухфакторная аутентификация", value: "Включить" },
  { title: "Активные сессии", value: "3 устройства" },
  { title: "Смена пароля", value: "Доступно" },
];

export default function Page() {
  return (
    <section className="space-y-6">
      <Surface className="overflow-hidden">
        <div className="min-h-0 rounded-[28px] bg-[#2E3137] p-6 sm:p-7 lg:p-8">
          <div className="flex flex-col gap-6 xl:flex-row xl:items-end xl:justify-between">
            <div className="max-w-3xl space-y-3">
              <p className="text-xs uppercase tracking-[0.32em] text-slate-400">Настройки</p>
              <h1 className="text-3xl font-semibold tracking-[-0.04em] text-[#f4f7fb] sm:text-[34px]">
                Общие параметры профиля и интерфейса
              </h1>
              <p className="max-w-2xl text-sm leading-6 text-slate-400 sm:text-[15px]">
                Здесь настраиваются базовые параметры работы платформы: профиль, уведомления,
                внешний вид и безопасность. Все блоки адаптируются под ширину экрана и не
                оставляют пустых областей справа.
              </p>
            </div>

            <div className="flex flex-wrap gap-3">
              <Button variant="secondary">Сбросить изменения</Button>
              <Button variant="primary">Сохранить настройки</Button>
            </div>
          </div>
        </div>
      </Surface>

      <div className="grid gap-6 xl:grid-cols-[1.25fr_0.95fr]">
        <Surface>
          <div className="min-h-0 rounded-[28px] bg-[#2E3137] p-6 sm:p-7">
            <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
              <div className="space-y-2">
                <p className="text-xs uppercase tracking-[0.32em] text-slate-400">Общие</p>
                <h2 className="text-2xl font-semibold tracking-[-0.04em] text-[#f4f7fb]">
                  Профиль пользователя
                </h2>
                <p className="max-w-xl text-sm leading-6 text-slate-400">
                  Основные данные профиля, которые используются в интерфейсе и уведомлениях.
                </p>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="rounded-2xl border border-[#3a3d43] bg-[#343840] px-4 py-3">
                  <p className="text-xs uppercase tracking-[0.24em] text-slate-400">Статус</p>
                  <p className="mt-1 text-sm font-medium text-slate-200">Активен</p>
                </div>
                <div className="rounded-2xl border border-[#3a3d43] bg-[#343840] px-4 py-3">
                  <p className="text-xs uppercase tracking-[0.24em] text-slate-400">Роль</p>
                  <p className="mt-1 text-sm font-medium text-slate-200">Administrator</p>
                </div>
              </div>
            </div>

            <div className="mt-6 grid gap-4 md:grid-cols-2">
              <label className="space-y-2">
                <span className="text-sm font-medium text-slate-200">Имя</span>
                <Input defaultValue="Administrator" />
              </label>
              <label className="space-y-2">
                <span className="text-sm font-medium text-slate-200">Фамилия</span>
                <Input defaultValue="User" />
              </label>
              <label className="space-y-2">
                <span className="text-sm font-medium text-slate-200">Email</span>
                <Input placeholder="user@example.com" />
              </label>
              <label className="space-y-2">
                <span className="text-sm font-medium text-slate-200">Телефон</span>
                <Input placeholder="+998 90 000 00 00" />
              </label>
            </div>

            <div className="mt-6 flex flex-wrap gap-3">
              <Button variant="primary">Обновить профиль</Button>
              <Button variant="ghost">Сменить пароль</Button>
            </div>
          </div>
        </Surface>

        <div className="grid gap-6">
          <Surface>
            <div className="min-h-0 rounded-[28px] bg-[#2E3137] p-6 sm:p-7">
              <div className="flex items-start justify-between gap-4">
                <div className="space-y-2">
                  <p className="text-xs uppercase tracking-[0.32em] text-slate-400">Уведомления</p>
                  <h2 className="text-2xl font-semibold tracking-[-0.04em] text-[#f4f7fb]">
                    Что показывать
                  </h2>
                </div>
                <Button variant="soft" size="sm">
                  Настроить
                </Button>
              </div>

              <div className="mt-5 space-y-3">
                {notificationRows.map((row) => (
                  <SettingRow key={row.title} title={row.title} description={row.description} />
                ))}
              </div>
            </div>
          </Surface>

          <Surface>
            <div className="min-h-0 rounded-[28px] bg-[#2E3137] p-6 sm:p-7">
              <div className="space-y-2">
                <p className="text-xs uppercase tracking-[0.32em] text-slate-400">Интерфейс</p>
                <h2 className="text-2xl font-semibold tracking-[-0.04em] text-[#f4f7fb]">
                  Внешний вид
                </h2>
              </div>

              <div className="mt-5 grid gap-3 sm:grid-cols-2">
                {appearanceRows.map((row) => (
                  <div key={row.title} className="rounded-2xl border border-[#3a3d43] bg-[#343840] px-4 py-4">
                    <p className="text-xs uppercase tracking-[0.24em] text-slate-400">{row.title}</p>
                    <p className="mt-2 text-sm font-medium text-slate-200">{row.value}</p>
                  </div>
                ))}
              </div>
            </div>
          </Surface>
        </div>
      </div>

      <div className="grid gap-6 xl:grid-cols-[0.95fr_1.05fr]">
        <Surface>
          <div className="min-h-0 rounded-[28px] bg-[#2E3137] p-6 sm:p-7">
            <div className="space-y-2">
              <p className="text-xs uppercase tracking-[0.32em] text-slate-400">Безопасность</p>
              <h2 className="text-2xl font-semibold tracking-[-0.04em] text-[#f4f7fb]">
                Доступ и защита
              </h2>
            </div>

            <div className="mt-5 space-y-3">
              {securityRows.map((row) => (
                <div
                  key={row.title}
                  className="flex items-center justify-between rounded-2xl border border-[#3a3d43] bg-[#2E3137] px-4 py-4"
                >
                  <div>
                    <p className="text-sm font-medium text-slate-200">{row.title}</p>
                    <p className="mt-1 text-sm text-slate-400">{row.value}</p>
                  </div>
                  <span className="h-3 w-3 rounded-full bg-emerald-500" />
                </div>
              ))}
            </div>
          </div>
        </Surface>

        <Surface>
          <div className="min-h-0 rounded-[28px] bg-[#2E3137] p-6 sm:p-7">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
              <div className="space-y-2">
                <p className="text-xs uppercase tracking-[0.32em] text-slate-400">Рабочие параметры</p>
                <h2 className="text-2xl font-semibold tracking-[-0.04em] text-[#f4f7fb]">
                  Автосохранение и поведение
                </h2>
              </div>
              <Button variant="secondary" size="sm">
                Проверить соединение
              </Button>
            </div>

            <div className="mt-5 grid gap-3 md:grid-cols-2">
              <CompactPanel title="Автосохранение" value="Включено" note="Настройки сохраняются автоматически" />
              <CompactPanel title="Окружение" value="Production" note="Основная рабочая среда" />
              <CompactPanel title="Обновления" value="Авто" note="Интерфейс обновляется в фоне" />
              <CompactPanel title="Сессия" value="12 ч" note="Срок активности пользователя" />
            </div>
          </div>
        </Surface>
      </div>

      <Surface>
        <div className="min-h-0 rounded-[28px] bg-[#2E3137] p-6 sm:p-7">
          <div className="flex flex-col gap-5 lg:flex-row lg:items-center lg:justify-between">
            <div className="space-y-2">
              <p className="text-xs uppercase tracking-[0.32em] text-slate-400">Интеграции</p>
              <h2 className="text-2xl font-semibold tracking-[-0.04em] text-[#f4f7fb]">SmartUp</h2>
              <p className="max-w-2xl text-sm leading-6 text-slate-400">
                Отдельная страница для подключения SmartUp, проверки доступа и запуска
                синхронизации по организациям.
              </p>
            </div>

            <Link
              href="/settings/integrations/smartup"
              className="inline-flex h-11 items-center justify-center rounded-full bg-slate-950 px-4 text-sm font-medium text-white transition hover:bg-slate-800"
            >
              Открыть SmartUp
            </Link>
          </div>
        </div>
      </Surface>
    </section>
  );
}

function SettingRow({ title, description }: { title: string; description: string }) {
  return (
    <div className="flex items-center justify-between gap-4 rounded-2xl border border-[#3a3d43] bg-[#343840] px-4 py-4">
      <div className="min-w-0">
        <p className="text-sm font-medium text-slate-200">{title}</p>
        <p className="mt-1 text-sm leading-6 text-slate-400">{description}</p>
      </div>
      <button
        type="button"
        className="flex h-6 w-11 items-center rounded-full bg-[#1E1E21] p-0.5 transition hover:bg-[#3a3d43]"
        aria-label={title}
      >
        <span className="h-5 w-5 rounded-full bg-[#2E3137] shadow-sm" />
      </button>
    </div>
  );
}

function CompactPanel({
  title,
  value,
  note,
}: {
  title: string;
  value: string;
  note: string;
}) {
  return (
    <div className="rounded-2xl border border-[#3a3d43] bg-[#343840] px-4 py-4">
      <p className="text-xs uppercase tracking-[0.24em] text-slate-400">{title}</p>
      <p className="mt-2 text-lg font-semibold tracking-[-0.03em] text-[#f4f7fb]">{value}</p>
      <p className="mt-1 text-sm leading-6 text-slate-400">{note}</p>
    </div>
  );
}
