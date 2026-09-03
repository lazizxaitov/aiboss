"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Drawer } from "@/components/ui/drawer";
import { Surface } from "@/components/ui/surface";
import {
  createTelegramLink,
  disconnectTelegram,
  disconnectTelegramChat,
  getTelegramLinkStatus,
  type TelegramLinkedUser,
  type TelegramLinkStatus,
} from "@/lib/core-api";

function displayName(user: TelegramLinkedUser): string {
  const name = [user.first_name, user.last_name].filter(Boolean).join(" ").trim();
  if (name && user.username) return `${name} (@${user.username})`;
  if (name) return name;
  if (user.username) return `@${user.username}`;
  return `Telegram …${user.chat_id.slice(-4)}`;
}

export function TelegramLinkCard() {
  const [status, setStatus] = useState<TelegramLinkStatus | null>(null);
  const [busyChatId, setBusyChatId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [modalOpen, setModalOpen] = useState(false);

  const refreshStatus = useCallback(async () => {
    try {
      const next = await getTelegramLinkStatus();
      setStatus(next);
      return next;
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось получить статус Telegram");
      return null;
    }
  }, []);

  useEffect(() => {
    void refreshStatus();
  }, [refreshStatus]);

  const disconnectAll = async () => {
    if (!window.confirm("Отключить всех Telegram-пользователей от AI Business OS?")) return;
    setBusyChatId("__all__");
    setError(null);
    try {
      setStatus(await disconnectTelegram());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось отключить Telegram");
    } finally {
      setBusyChatId(null);
    }
  };

  const disconnectOne = async (chatId: string) => {
    if (!window.confirm("Отключить этого Telegram-пользователя?")) return;
    setBusyChatId(chatId);
    setError(null);
    try {
      setStatus(await disconnectTelegramChat(chatId));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось отключить пользователя");
    } finally {
      setBusyChatId(null);
    }
  };

  return (
    <>
      <Surface>
        <div className="rounded-[28px] bg-[#2E3137] p-6 sm:p-7">
          <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
            <div className="max-w-2xl space-y-2">
              <p className="text-xs uppercase tracking-[0.32em] text-slate-400">Интеграции</p>
              <h2 className="text-2xl font-semibold tracking-[-0.04em] text-[#f4f7fb]">Telegram</h2>
              <p className="text-sm leading-6 text-slate-400">
                Подключите Telegram-аккаунты к AI Business OS — можно добавить несколько
                пользователей, каждый получит доступ к тому же AI-диалогу и бизнес-данным.
              </p>
              <p className="text-sm font-medium text-slate-200">
                {status?.connected ? `Подключено пользователей: ${status.users.length}` : "Не подключён"}
              </p>
            </div>
            <div className="flex shrink-0 flex-col items-stretch gap-2 sm:flex-row lg:items-start">
              <Button
                variant="primary"
                onClick={() => {
                  setError(null);
                  setModalOpen(true);
                }}
                disabled={status === null}
              >
                Подключить Telegram
              </Button>
              {status?.connected ? (
                <Button variant="secondary" onClick={disconnectAll} disabled={busyChatId !== null}>
                  {busyChatId === "__all__" ? "Обработка..." : "Отключить всех"}
                </Button>
              ) : null}
            </div>
          </div>

          {status?.users.length ? (
            <ul className="mt-5 space-y-2">
              {status.users.map((user) => (
                <li
                  key={user.chat_id}
                  className="flex items-center justify-between gap-3 rounded-2xl border border-[#3a3d43] bg-[#343840] px-4 py-3"
                >
                  <span className="truncate text-sm text-slate-200">{displayName(user)}</span>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => disconnectOne(user.chat_id)}
                    disabled={busyChatId !== null}
                  >
                    {busyChatId === user.chat_id ? "..." : "Отключить"}
                  </Button>
                </li>
              ))}
            </ul>
          ) : null}

          {error ? <p className="mt-3 text-sm text-rose-300">{error}</p> : null}
        </div>
      </Surface>

      <TelegramConnectModal open={modalOpen} onClose={() => setModalOpen(false)} onPoll={refreshStatus} />
    </>
  );
}

function TelegramConnectModal({
  open,
  onClose,
  onPoll,
}: {
  open: boolean;
  onClose: () => void;
  onPoll: () => Promise<TelegramLinkStatus | null>;
}) {
  const [link, setLink] = useState<TelegramLinkStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [connectedUser, setConnectedUser] = useState<TelegramLinkedUser | null>(null);
  const knownChatIdsRef = useRef<Set<string>>(new Set());

  const requestLink = useCallback(async () => {
    setLoading(true);
    setError(null);
    setConnectedUser(null);
    try {
      // Snapshot who's already connected first, so the poller below can tell
      // a brand-new scan apart from users that were already linked.
      const current = await getTelegramLinkStatus();
      knownChatIdsRef.current = new Set(current.users.map((user) => user.chat_id));
      setLink(await createTelegramLink());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось создать код подключения");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!open) {
      setLink(null);
      setConnectedUser(null);
      setError(null);
      return;
    }
    void requestLink();
  }, [open, requestLink]);

  // While the modal is open with an active code, poll for the scan being
  // completed on the phone (via the bot's Mini App) so the modal can
  // confirm success and close itself instead of the user having to guess.
  useEffect(() => {
    if (!open || !link || connectedUser) return;
    const interval = window.setInterval(() => {
      void onPoll().then((next) => {
        if (!next) return;
        const newUser = next.users.find((user) => !knownChatIdsRef.current.has(user.chat_id));
        if (newUser) {
          setConnectedUser(newUser);
        }
      });
    }, 2500);
    return () => window.clearInterval(interval);
  }, [open, link, connectedUser, onPoll]);

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title="Подключить Telegram"
      description="Откройте панель бота в Telegram и нажмите «Сканировать QR», либо отсканируйте код обычной камерой телефона."
      className="max-w-md"
    >
      <div className="flex flex-col items-center gap-4 text-center">
        {connectedUser ? (
          <div className="space-y-3 py-6">
            <p className="text-lg font-semibold text-[#f4f7fb]">Готово!</p>
            <p className="text-sm text-slate-300">{displayName(connectedUser)} теперь подключён к AI Business OS.</p>
            <Button variant="primary" onClick={onClose}>
              Закрыть
            </Button>
          </div>
        ) : loading && !link ? (
          <p className="py-10 text-sm text-slate-400">Создаём код подключения...</p>
        ) : link ? (
          <>
            {link.qr_data_uri ? (
              // eslint-disable-next-line @next/next/no-img-element -- data: URI, not an optimizable asset
              <img
                src={link.qr_data_uri}
                alt="QR-код для подключения Telegram"
                className="h-56 w-56 rounded-2xl bg-white p-3"
              />
            ) : (
              <p className="text-sm text-amber-300">QR-код недоступен — используйте ссылку или команду ниже.</p>
            )}
            <div className="w-full space-y-2 rounded-2xl border border-[#555961] bg-[#343840] p-4 text-left">
              <p className="text-sm font-medium text-slate-200">Или откройте Telegram и отправьте боту:</p>
              <code className="block break-all rounded-xl bg-[#25282d] px-3 py-3 text-sm text-[#FFF27A]">
                /start {link.token}
              </code>
              {link.deep_link ? (
                <a className="inline-flex text-sm text-[#FFF27A] underline" href={link.deep_link} target="_blank" rel="noreferrer">
                  Открыть Telegram
                </a>
              ) : null}
            </div>
            <p className="text-xs text-slate-500">Код одноразовый и действует 10 минут.</p>
            <Button variant="ghost" size="sm" onClick={requestLink}>
              Обновить код
            </Button>
          </>
        ) : null}
        {error ? <p className="text-sm text-rose-300">{error}</p> : null}
      </div>
    </Drawer>
  );
}
