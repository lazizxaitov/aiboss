"use client";

import { useRouter } from "next/navigation";
import { useRef, useState, type PointerEvent } from "react";

import { Drawer } from "@/components/ui/drawer";
import { useMobileComposer } from "@/components/mobile/mobile-composer-context";
import { transcribeVoiceMessage } from "@/lib/core-api";

const HOLD_THRESHOLD_MS = 300;
const MIN_RECORDING_MS = 400;
const CANCEL_DRAG_UP_PX = 80;
const MAX_IMAGE_BYTES = 8 * 1024 * 1024;

type Phase = "idle" | "recording" | "processing";

function pickMimeType(): string | undefined {
  if (typeof MediaRecorder === "undefined" || typeof MediaRecorder.isTypeSupported !== "function") return undefined;
  return ["audio/webm", "audio/mp4", "audio/ogg"].find((type) => MediaRecorder.isTypeSupported(type));
}

function extensionFor(mimeType: string): string {
  if (mimeType.includes("mp4")) return "m4a";
  if (mimeType.includes("ogg")) return "ogg";
  return "webm";
}

function readFileAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error ?? new Error("Не удалось прочитать файл"));
    reader.readAsDataURL(file);
  });
}

export function MobileActionButton() {
  const router = useRouter();
  const { setPendingDraft } = useMobileComposer();

  const [phase, setPhase] = useState<Phase>("idle");
  const [seconds, setSeconds] = useState(0);
  const [menuOpen, setMenuOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const holdTimerRef = useRef<number | null>(null);
  const holdTriggeredRef = useRef(false);
  const startYRef = useRef(0);
  const cancelledRef = useRef(false);
  const startedAtRef = useRef(0);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const timerIntervalRef = useRef<number | null>(null);

  const photoInputRef = useRef<HTMLInputElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const stopStream = () => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  };

  const goToChat = () => router.push("/m/chat");

  const finishRecording = async (blob: Blob) => {
    setPhase("processing");
    try {
      const text = await transcribeVoiceMessage(blob, `voice.${extensionFor(blob.type)}`);
      if (!text.trim()) {
        setError("Не удалось распознать голос — попробуйте ещё раз");
        return;
      }
      setPendingDraft({ kind: "text", text: text.trim() });
      goToChat();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось отправить голосовое сообщение");
    } finally {
      setPhase("idle");
      setSeconds(0);
    }
  };

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const mimeType = pickMimeType();
      const recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
      chunksRef.current = [];
      cancelledRef.current = false;
      startedAtRef.current = Date.now();
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };
      recorder.onstop = () => {
        stopStream();
        if (timerIntervalRef.current) {
          window.clearInterval(timerIntervalRef.current);
          timerIntervalRef.current = null;
        }
        const tooShort = Date.now() - startedAtRef.current < MIN_RECORDING_MS;
        if (cancelledRef.current || tooShort) {
          setPhase("idle");
          setSeconds(0);
          return;
        }
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" });
        void finishRecording(blob);
      };
      mediaRecorderRef.current = recorder;
      recorder.start();
      setError(null);
      setPhase("recording");
      setSeconds(0);
      timerIntervalRef.current = window.setInterval(() => setSeconds((value) => value + 1), 1000);
    } catch {
      setError("Нет доступа к микрофону");
      setPhase("idle");
    }
  };

  const onPointerDown = (event: PointerEvent<HTMLButtonElement>) => {
    if (phase !== "idle") return;
    startYRef.current = event.clientY;
    holdTriggeredRef.current = false;
    holdTimerRef.current = window.setTimeout(() => {
      holdTriggeredRef.current = true;
      void startRecording();
    }, HOLD_THRESHOLD_MS);
  };

  const onPointerMove = (event: PointerEvent<HTMLButtonElement>) => {
    if (phase !== "recording") return;
    cancelledRef.current = startYRef.current - event.clientY > CANCEL_DRAG_UP_PX;
  };

  const endHold = () => {
    if (holdTimerRef.current) {
      window.clearTimeout(holdTimerRef.current);
      holdTimerRef.current = null;
    }
    if (holdTriggeredRef.current) {
      mediaRecorderRef.current?.stop();
      mediaRecorderRef.current = null;
      holdTriggeredRef.current = false;
    } else if (phase === "idle") {
      setMenuOpen(true);
    }
  };

  const onPhotoPicked = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setMenuOpen(false);
    if (!file.type.startsWith("image/")) {
      setError("Выберите изображение");
      return;
    }
    if (file.size > MAX_IMAGE_BYTES) {
      setError("Файл слишком большой (максимум 8 МБ)");
      return;
    }
    try {
      const dataUrl = await readFileAsDataUrl(file);
      setPendingDraft({ kind: "image", text: "", imageDataUrl: dataUrl, fileName: file.name });
      goToChat();
    } catch {
      setError("Не удалось прочитать файл");
    }
  };

  const onFilePicked = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setMenuOpen(false);
    if (file.type.startsWith("image/")) {
      if (file.size > MAX_IMAGE_BYTES) {
        setError("Файл слишком большой (максимум 8 МБ)");
        return;
      }
      try {
        const dataUrl = await readFileAsDataUrl(file);
        setPendingDraft({ kind: "image", text: "", imageDataUrl: dataUrl, fileName: file.name });
        goToChat();
      } catch {
        setError("Не удалось прочитать файл");
      }
      return;
    }
    // The AI agent doesn't read arbitrary document contents yet (same as the
    // Telegram bot today) — send the filename as a note so the conversation
    // at least records that a file was shared, instead of silently dropping it.
    setPendingDraft({ kind: "text", text: `Пользователь прикрепил файл: ${file.name}` });
    goToChat();
  };

  const label = phase === "recording" ? `Идёт запись · 0:${String(seconds).padStart(2, "0")} — потяните вверх для отмены` : phase === "processing" ? "Распознаём..." : null;

  return (
    <>
      {label ? (
        <div className="pointer-events-none fixed inset-x-3 bottom-24 z-40 rounded-2xl border border-[#3a3d43] bg-[#2E3137] px-4 py-2 text-center text-xs text-slate-300 shadow-[0_12px_30px_rgba(0,0,0,0.3)]">
          {label}
        </div>
      ) : null}
      {error ? (
        <div className="fixed inset-x-3 bottom-24 z-40 rounded-2xl border border-rose-500/30 bg-rose-500/10 px-4 py-2 text-center text-xs text-rose-200">
          {error}
        </div>
      ) : null}

      <button
        type="button"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endHold}
        onPointerCancel={endHold}
        onContextMenu={(event) => event.preventDefault()}
        disabled={phase === "processing"}
        className="flex min-h-14 select-none flex-col items-center justify-center gap-1 rounded-2xl text-[11px] text-slate-300 [touch-action:none] disabled:opacity-60"
      >
        <span aria-hidden="true" className={`text-xl leading-none ${phase === "recording" ? "text-rose-400" : ""}`}>
          {phase === "recording" ? "●" : "＋"}
        </span>
        <span>Действие</span>
      </button>

      <input ref={photoInputRef} type="file" accept="image/*" capture="environment" className="hidden" onChange={onPhotoPicked} />
      <input ref={fileInputRef} type="file" className="hidden" onChange={onFilePicked} />

      <Drawer open={menuOpen} onClose={() => setMenuOpen(false)} title="Отправить" className="max-w-sm">
        <div className="flex flex-col gap-2">
          <button
            type="button"
            onClick={() => photoInputRef.current?.click()}
            className="flex items-center gap-3 rounded-2xl px-3 py-3 text-left text-sm text-slate-200 hover:bg-[#343840]"
          >
            📷 Фото
          </button>
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            className="flex items-center gap-3 rounded-2xl px-3 py-3 text-left text-sm text-slate-200 hover:bg-[#343840]"
          >
            📎 Файл
          </button>
        </div>
      </Drawer>
    </>
  );
}
