"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Drawer } from "@/components/ui/drawer";
import { Surface } from "@/components/ui/surface";
import { createDeviceLink, disconnectDevice, getPairedDevices, type PairedDevice } from "@/lib/core-api";

function formatDate(value?: string | null): string {
  if (!value) return "";
  try {
    return new Date(value).toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit", year: "numeric" });
  } catch {
    return "";
  }
}

export function DeviceLinkCard() {
  const [devices, setDevices] = useState<PairedDevice[] | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [modalOpen, setModalOpen] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const next = await getPairedDevices();
      setDevices(next);
      return next;
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось получить список устройств");
      return null;
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const disconnect = async (deviceId: string) => {
    if (!window.confirm("Отключить это устройство от AI Business OS?")) return;
    setBusyId(deviceId);
    setError(null);
    try {
      setDevices(await disconnectDevice(deviceId));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось отключить устройство");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <>
      <Surface>
        <div className="rounded-[28px] bg-[#2E3137] p-6 sm:p-7">
          <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
            <div className="max-w-2xl space-y-2">
              <p className="text-xs uppercase tracking-[0.32em] text-slate-400">Интеграции</p>
              <h2 className="text-2xl font-semibold tracking-[-0.04em] text-[#f4f7fb]">Мобильные устройства</h2>
              <p className="text-sm leading-6 text-slate-400">
                Отсканируйте QR-код телефоном, чтобы открыть мобильную версию AI Business OS и
                добавить её иконку на главный экран — без ввода пароля вручную на телефоне каждый раз.
              </p>
              <p className="text-sm font-medium text-slate-200">
                {devices?.length ? `Подключено устройств: ${devices.length}` : "Нет подключённых устройств"}
              </p>
            </div>
            <Button
              variant="primary"
              onClick={() => {
                setError(null);
                setModalOpen(true);
              }}
              disabled={devices === null}
            >
              Добавить устройство
            </Button>
          </div>

          {devices?.length ? (
            <ul className="mt-5 space-y-2">
              {devices.map((device) => (
                <li
                  key={device.device_id}
                  className="flex items-center justify-between gap-3 rounded-2xl border border-[#3a3d43] bg-[#343840] px-4 py-3"
                >
                  <div className="min-w-0">
                    <p className="truncate text-sm text-slate-200">{device.label}</p>
                    {device.linked_at ? <p className="text-xs text-slate-500">Подключено {formatDate(device.linked_at)}</p> : null}
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => disconnect(device.device_id)}
                    disabled={busyId !== null}
                  >
                    {busyId === device.device_id ? "..." : "Отключить"}
                  </Button>
                </li>
              ))}
            </ul>
          ) : null}

          {error ? <p className="mt-3 text-sm text-rose-300">{error}</p> : null}
        </div>
      </Surface>

      <DeviceConnectModal open={modalOpen} onClose={() => setModalOpen(false)} onPoll={refresh} />
    </>
  );
}

function DeviceConnectModal({
  open,
  onClose,
  onPoll,
}: {
  open: boolean;
  onClose: () => void;
  onPoll: () => Promise<PairedDevice[] | null>;
}) {
  const [link, setLink] = useState<{ deep_link?: string | null; qr_data_uri?: string | null; expires_at?: string | null } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [connected, setConnected] = useState(false);
  const knownDeviceIdsRef = useRef<Set<string>>(new Set());

  const requestLink = useCallback(async () => {
    setLoading(true);
    setError(null);
    setConnected(false);
    try {
      const current = await getPairedDevices();
      knownDeviceIdsRef.current = new Set(current.map((device) => device.device_id));
      setLink(await createDeviceLink(window.location.origin));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось создать код подключения");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!open) {
      setLink(null);
      setConnected(false);
      setError(null);
      return;
    }
    void requestLink();
  }, [open, requestLink]);

  useEffect(() => {
    if (!open || !link || connected) return;
    const interval = window.setInterval(() => {
      void onPoll().then((next) => {
        if (!next) return;
        if (next.some((device) => !knownDeviceIdsRef.current.has(device.device_id))) {
          setConnected(true);
        }
      });
    }, 2500);
    return () => window.clearInterval(interval);
  }, [open, link, connected, onPoll]);

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title="Добавить мобильное устройство"
      description="Откройте камеру на телефоне и отсканируйте этот QR-код — откроется мобильная версия AI Business OS с предложением войти и добавить иконку на главный экран."
      className="max-w-md"
    >
      <div className="flex flex-col items-center gap-4 text-center">
        {connected ? (
          <div className="space-y-3 py-6">
            <p className="text-lg font-semibold text-[#f4f7fb]">Готово!</p>
            <p className="text-sm text-slate-300">Устройство подключено к AI Business OS.</p>
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
                alt="QR-код для подключения мобильного устройства"
                className="h-56 w-56 rounded-2xl bg-white p-3"
              />
            ) : (
              <p className="text-sm text-amber-300">QR-код недоступен — используйте ссылку ниже.</p>
            )}
            {link.deep_link ? (
              <a className="inline-flex text-sm text-[#FFF27A] underline" href={link.deep_link} target="_blank" rel="noreferrer">
                Открыть на этом устройстве
              </a>
            ) : null}
            <p className="text-xs text-slate-500">Код одноразовый и действует 5 минут.</p>
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
