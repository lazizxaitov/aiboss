"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type ChangeEvent, type FormEvent, type PointerEvent } from "react";

import { streamAiChat, transcribeVoiceMessage, type AiChatMessage } from "@/lib/core-api";

const CONVERSATION_ID_KEY = "aibos_mobile_chat_conversation_id";

const HOLD_THRESHOLD_MS = 300;
const MIN_RECORDING_MS = 400;
const CANCEL_DRAG_UP_PX = 80;
const MAX_IMAGE_BYTES = 8 * 1024 * 1024;

// Voice-reactive recording indicator: a ring of dots around a glowing orb,
// each dot tracking a slice of the live microphone spectrum so the whole
// thing pulses and spreads outward with the user's voice (the same idea as
// ChatGPT's/Claude's voice mode indicator).
const VOICE_DOT_COUNT = 8;
const VOICE_DOT_ANGLES = Array.from({ length: VOICE_DOT_COUNT }, (_, index) => (index / VOICE_DOT_COUNT) * 2 * Math.PI);
const VOICE_DOT_BASE_RADIUS = 30;
const VOICE_DOT_MAX_SPREAD = 26;

type ChatItem = {
  id: string;
  role: "user" | "assistant";
  text: string;
  imageDataUrl?: string;
};

type RecordingPhase = "idle" | "recording" | "processing";

function newId(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;
}

function getConversationId(): string {
  if (typeof window === "undefined") return newId();
  const existing = window.localStorage.getItem(CONVERSATION_ID_KEY);
  if (existing) return existing;
  const created = newId();
  window.localStorage.setItem(CONVERSATION_ID_KEY, created);
  return created;
}

function toApiContent(item: ChatItem): AiChatMessage["content"] {
  if (!item.imageDataUrl) return item.text;
  const parts: AiChatMessage["content"] = [];
  if (item.text) parts.push({ type: "text", text: item.text });
  parts.push({ type: "image_url", image_url: { url: item.imageDataUrl } });
  return parts;
}

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

export default function MobileChatPage() {
  const router = useRouter();
  const [items, setItems] = useState<ChatItem[]>([]);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const conversationIdRef = useRef(getConversationId());
  const scrollRef = useRef<HTMLDivElement | null>(null);

  // Voice recording state — a mobile-only push-to-talk button on the right
  // of the composer, replacing the old bottom-nav Action button now that
  // attaching and recording both happen right where the conversation is
  // visible.
  const [recordingPhase, setRecordingPhase] = useState<RecordingPhase>("idle");
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  // Per-dot volume levels (0..1), each fed by a slice of the live frequency
  // spectrum — purely cosmetic, recording works the same with or without it.
  const [voiceLevels, setVoiceLevels] = useState<number[]>(() => Array(VOICE_DOT_COUNT).fill(0));
  const holdTimerRef = useRef<number | null>(null);
  const holdTriggeredRef = useRef(false);
  const startYRef = useRef(0);
  const cancelledRef = useRef(false);
  const startedAtRef = useRef(0);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const timerIntervalRef = useRef<number | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const visualizerFrameRef = useRef<number | null>(null);
  // getUserMedia() can take a beat on mobile (permission prompt, device
  // acquisition) — long enough that a quick press-and-release can finish
  // before startRecording() ever assigns mediaRecorderRef.current. This flag
  // lets startRecording know the button was already released by the time
  // the recorder became ready, so it can stop it immediately instead of
  // recording on in the background with nothing left to stop it.
  const pendingStopRef = useRef(false);

  const photoInputRef = useRef<HTMLInputElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const scrollToEnd = () => {
    requestAnimationFrame(() => {
      scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
    });
  };

  const send = async (text: string, imageDataUrl?: string) => {
    if (!text.trim() && !imageDataUrl) return;
    setError(null);
    const userItem: ChatItem = { id: newId(), role: "user", text: text.trim(), imageDataUrl };
    const assistantId = newId();
    const history = [...items, userItem];
    setItems([...history, { id: assistantId, role: "assistant", text: "" }]);
    setSending(true);
    scrollToEnd();
    let acc = "";
    try {
      await streamAiChat(
        history.map((item) => ({ role: item.role, content: toApiContent(item) })),
        (chunk) => {
          acc += chunk;
          setItems((current) => current.map((item) => (item.id === assistantId ? { ...item, text: acc } : item)));
          scrollToEnd();
        },
        undefined,
        "ai_chat",
        undefined,
        undefined,
        undefined,
        conversationIdRef.current,
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось получить ответ ИИ");
      setItems((current) => current.filter((item) => item.id !== assistantId));
    } finally {
      setSending(false);
      scrollToEnd();
    }
  };

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const text = draft;
    setDraft("");
    void send(text);
  };

  const onNewChat = () => {
    const created = newId();
    window.localStorage.setItem(CONVERSATION_ID_KEY, created);
    conversationIdRef.current = created;
    setItems([]);
    setError(null);
    setDraft("");
  };

  // --- Attach: photo / file -------------------------------------------------

  const onPhotoPicked = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
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
      void send("", dataUrl);
    } catch {
      setError("Не удалось прочитать файл");
    }
  };

  const onFilePicked = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    if (file.type.startsWith("image/")) {
      if (file.size > MAX_IMAGE_BYTES) {
        setError("Файл слишком большой (максимум 8 МБ)");
        return;
      }
      try {
        const dataUrl = await readFileAsDataUrl(file);
        void send("", dataUrl);
      } catch {
        setError("Не удалось прочитать файл");
      }
      return;
    }
    // The AI agent doesn't read arbitrary document contents yet (same as the
    // Telegram bot today) — send the filename as a note so the conversation
    // at least records that a file was shared, instead of silently dropping it.
    void send(`Пользователь прикрепил файл: ${file.name}`);
  };

  // --- Voice: hold to record, release to send -------------------------------

  const stopStream = () => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  };

  const startVisualizer = (stream: MediaStream) => {
    try {
      const AudioContextCtor = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
      if (!AudioContextCtor) return;
      const audioContext = new AudioContextCtor();
      const source = audioContext.createMediaStreamSource(stream);
      const analyser = audioContext.createAnalyser();
      analyser.fftSize = 64;
      analyser.smoothingTimeConstant = 0.75;
      source.connect(analyser);
      audioContextRef.current = audioContext;
      analyserRef.current = analyser;
      const data = new Uint8Array(analyser.frequencyBinCount);
      const binsPerDot = Math.max(1, Math.floor(data.length / VOICE_DOT_COUNT));
      const tick = () => {
        if (!analyserRef.current) return;
        analyserRef.current.getByteFrequencyData(data);
        const next: number[] = [];
        for (let dot = 0; dot < VOICE_DOT_COUNT; dot += 1) {
          let sum = 0;
          for (let bin = 0; bin < binsPerDot; bin += 1) sum += data[dot * binsPerDot + bin] ?? 0;
          next.push(Math.min(1, sum / binsPerDot / 160));
        }
        setVoiceLevels(next);
        visualizerFrameRef.current = requestAnimationFrame(tick);
      };
      tick();
    } catch {
      // The dot animation is a nice-to-have — recording still works without it.
    }
  };

  const stopVisualizer = () => {
    if (visualizerFrameRef.current) {
      cancelAnimationFrame(visualizerFrameRef.current);
      visualizerFrameRef.current = null;
    }
    analyserRef.current = null;
    if (audioContextRef.current) {
      audioContextRef.current.close().catch(() => {});
      audioContextRef.current = null;
    }
    setVoiceLevels(Array(VOICE_DOT_COUNT).fill(0));
  };

  const finishRecording = async (blob: Blob) => {
    setRecordingPhase("processing");
    try {
      const text = await transcribeVoiceMessage(blob, `voice.${extensionFor(blob.type)}`);
      if (!text.trim()) {
        setError("Не удалось распознать голос — попробуйте ещё раз");
        return;
      }
      await send(text.trim());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось отправить голосовое сообщение");
    } finally {
      setRecordingPhase("idle");
      setRecordingSeconds(0);
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
        stopVisualizer();
        if (timerIntervalRef.current) {
          window.clearInterval(timerIntervalRef.current);
          timerIntervalRef.current = null;
        }
        const tooShort = Date.now() - startedAtRef.current < MIN_RECORDING_MS;
        if (cancelledRef.current || tooShort) {
          setRecordingPhase("idle");
          setRecordingSeconds(0);
          return;
        }
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" });
        void finishRecording(blob);
      };
      mediaRecorderRef.current = recorder;
      recorder.start();
      startVisualizer(stream);
      setError(null);
      setRecordingPhase("recording");
      setRecordingSeconds(0);
      timerIntervalRef.current = window.setInterval(() => setRecordingSeconds((value) => value + 1), 1000);
      if (pendingStopRef.current) {
        // The button was already released while getUserMedia/MediaRecorder
        // were still spinning up — stop right away.
        pendingStopRef.current = false;
        recorder.stop();
      }
    } catch {
      setError("Нет доступа к микрофону");
      setRecordingPhase("idle");
    }
  };

  const onMicPointerDown = (event: PointerEvent<HTMLButtonElement>) => {
    if (recordingPhase !== "idle") return;
    startYRef.current = event.clientY;
    holdTriggeredRef.current = false;
    holdTimerRef.current = window.setTimeout(() => {
      holdTriggeredRef.current = true;
      void startRecording();
    }, HOLD_THRESHOLD_MS);
  };

  const onMicPointerMove = (event: PointerEvent<HTMLButtonElement>) => {
    if (recordingPhase !== "recording") return;
    cancelledRef.current = startYRef.current - event.clientY > CANCEL_DRAG_UP_PX;
  };

  const onMicPointerUp = () => {
    if (holdTimerRef.current) {
      window.clearTimeout(holdTimerRef.current);
      holdTimerRef.current = null;
    }
    if (holdTriggeredRef.current) {
      holdTriggeredRef.current = false;
      if (mediaRecorderRef.current) {
        mediaRecorderRef.current.stop();
        mediaRecorderRef.current = null;
      } else {
        // startRecording() hasn't finished setting up the recorder yet —
        // tell it to stop itself the moment it's ready.
        pendingStopRef.current = true;
      }
    }
  };

  useEffect(
    () => () => {
      if (holdTimerRef.current) window.clearTimeout(holdTimerRef.current);
      if (timerIntervalRef.current) window.clearInterval(timerIntervalRef.current);
      stopStream();
      stopVisualizer();
    },
    [],
  );

  const voiceAverageLevel = voiceLevels.reduce((sum, value) => sum + value, 0) / voiceLevels.length;
  const recordingLabel =
    recordingPhase === "recording"
      ? `0:${String(recordingSeconds).padStart(2, "0")} — потяните вверх для отмены`
      : recordingPhase === "processing"
        ? "Распознаём..."
        : null;

  return (
    // This route sits outside the (shell) tab-bar layout on purpose — a full-
    // screen chat, like Claude's/ChatGPT's own mobile app, rather than one
    // more tab. h-dvh (not the shell's fixed-chrome calc, which doesn't apply
    // here) plus its own safe-area padding is what actually pins the header
    // under the notch/Dynamic Island and the composer to the real bottom
    // edge, above the home indicator.
    <div className="flex h-dvh w-full min-w-0 flex-col bg-[#1E1E21] text-[#f4f7fb]">
      <header
        className="sticky top-0 z-10 flex shrink-0 items-center gap-1 border-b border-[#3a3d43] bg-[#1E1E21]/95 px-2 backdrop-blur"
        style={{ paddingTop: "max(0.75rem, env(safe-area-inset-top))", paddingBottom: "0.75rem" }}
      >
        <button
          type="button"
          onClick={() => router.push("/m")}
          aria-label="Назад"
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-lg text-slate-300 active:bg-[#2E3137]"
        >
          ←
        </button>
        <p className="flex-1 truncate text-center text-sm font-semibold text-[#f4f7fb]">Чат с ИИ</p>
        <button
          type="button"
          onClick={onNewChat}
          aria-label="Новый диалог"
          title="Новый диалог"
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-lg text-slate-300 active:bg-[#2E3137]"
        >
          ＋
        </button>
      </header>

      <div ref={scrollRef} className="min-h-0 flex-1 space-y-3 overflow-y-auto overflow-x-hidden px-4 py-4">
        {items.length === 0 ? <p className="pt-10 text-center text-sm text-slate-500">Задайте вопрос ИИ, прикрепите файл/фото или отправьте голосовое сообщение.</p> : null}
        {items.map((item) => (
          <div key={item.id} className={`flex ${item.role === "user" ? "justify-end" : "justify-start"}`}>
            <div
              className={`max-w-[85%] min-w-0 whitespace-pre-wrap break-words rounded-2xl px-4 py-2.5 text-sm leading-6 ${
                item.role === "user" ? "bg-[#FFF27A] text-[#1E1E21]" : "bg-[#2E3137] text-[#f4f7fb]"
              }`}
            >
              {item.imageDataUrl ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={item.imageDataUrl} alt="" className="mb-2 max-h-56 w-full rounded-xl object-cover" />
              ) : null}
              {item.text || (item.role === "assistant" && sending ? "..." : "")}
            </div>
          </div>
        ))}
      </div>

      {recordingPhase !== "idle" ? (
        <div className="pointer-events-none mb-3 flex flex-col items-center gap-2 px-4">
          <div className="relative flex h-24 w-24 items-center justify-center">
            {/* Soft outer glow — breathes with the overall loudness. */}
            <div
              className="absolute inset-0 rounded-full bg-[#FFF27A]/15 blur-xl transition-transform duration-150 ease-out"
              style={{ transform: `scale(${1 + voiceAverageLevel * 0.9})` }}
            />
            {/* Central orb — the calm resting state while idle-listening or processing. */}
            <div
              className={`absolute h-12 w-12 rounded-full bg-gradient-to-br from-[#FFF27A] to-[#f0c94a] shadow-[0_0_25px_rgba(255,242,122,0.5)] transition-transform duration-150 ease-out ${
                recordingPhase === "processing" ? "animate-pulse" : ""
              }`}
              style={{ transform: `scale(${1 + voiceAverageLevel * 0.3})` }}
            />
            {/* Ring of dots that spreads outward with the live microphone volume,
                each one tracking its own slice of the frequency spectrum. */}
            {recordingPhase === "recording"
              ? VOICE_DOT_ANGLES.map((angle, index) => {
                  const level = voiceLevels[index] ?? 0;
                  const radius = VOICE_DOT_BASE_RADIUS + level * VOICE_DOT_MAX_SPREAD;
                  const x = Math.cos(angle) * radius;
                  const y = Math.sin(angle) * radius;
                  return (
                    <span
                      key={index}
                      className="absolute left-1/2 top-1/2 h-2 w-2 rounded-full bg-[#FFF27A] shadow-[0_0_10px_rgba(255,242,122,0.85)] transition-transform duration-100 ease-out"
                      style={{
                        transform: `translate(-50%, -50%) translate(${x}px, ${y}px)`,
                        opacity: 0.55 + level * 0.45,
                      }}
                    />
                  );
                })
              : null}
          </div>
          <p className={`text-xs ${cancelledRef.current ? "text-rose-300" : "text-slate-300"}`}>{recordingLabel}</p>
        </div>
      ) : null}
      {error ? <p className="px-4 pb-2 text-center text-xs text-rose-300">{error}</p> : null}

      <form
        onSubmit={onSubmit}
        className="flex shrink-0 items-center gap-2 border-t border-[#3a3d43] bg-[#1E1E21] px-4 pt-3"
        style={{ paddingBottom: "max(0.75rem, env(safe-area-inset-bottom))" }}
      >
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          disabled={sending || recordingPhase !== "idle"}
          title="Прикрепить файл"
          className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full border border-[#3a3d43] bg-[#2E3137] text-base text-slate-200 disabled:opacity-50"
        >
          📎
        </button>
        <button
          type="button"
          onClick={() => photoInputRef.current?.click()}
          disabled={sending || recordingPhase !== "idle"}
          title="Прикрепить фото"
          className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full border border-[#3a3d43] bg-[#2E3137] text-base text-slate-200 disabled:opacity-50"
        >
          📷
        </button>
        <input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="Написать ИИ..."
          disabled={sending || recordingPhase !== "idle"}
          className="h-11 min-w-0 flex-1 rounded-full border border-[#3a3d43] bg-[#2E3137] px-4 text-sm text-[#f4f7fb] outline-none placeholder:text-slate-500 focus:border-[#FFF27A]/40"
        />
        {draft.trim() ? (
          <button
            type="submit"
            disabled={sending}
            className="h-11 shrink-0 rounded-full bg-[#FFF27A] px-5 text-sm font-medium text-[#1E1E21] disabled:cursor-not-allowed disabled:opacity-50"
          >
            {sending ? "..." : "→"}
          </button>
        ) : (
          <button
            type="button"
            onPointerDown={onMicPointerDown}
            onPointerMove={onMicPointerMove}
            onPointerUp={onMicPointerUp}
            onPointerCancel={onMicPointerUp}
            onContextMenu={(event) => event.preventDefault()}
            disabled={sending || recordingPhase === "processing"}
            title="Удерживайте, чтобы записать голосовое сообщение"
            className={`flex h-11 w-11 shrink-0 select-none items-center justify-center rounded-full text-base [touch-action:none] disabled:opacity-50 ${
              recordingPhase === "recording" ? "bg-rose-500 text-white" : "bg-[#FFF27A] text-[#1E1E21]"
            }`}
          >
            🎤
          </button>
        )}
      </form>

      <input ref={photoInputRef} type="file" accept="image/*" capture="environment" className="hidden" onChange={onPhotoPicked} />
      <input ref={fileInputRef} type="file" className="hidden" onChange={onFilePicked} />
    </div>
  );
}
