"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";

import { useMobileComposer } from "@/components/mobile/mobile-composer-context";
import { streamAiChat, type AiChatMessage } from "@/lib/core-api";

const CONVERSATION_ID_KEY = "aibos_mobile_chat_conversation_id";

type ChatItem = {
  id: string;
  role: "user" | "assistant";
  text: string;
  imageDataUrl?: string;
};

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

export default function MobileChatPage() {
  const { pendingDraft, setPendingDraft } = useMobileComposer();
  const [items, setItems] = useState<ChatItem[]>([]);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const conversationIdRef = useRef(getConversationId());
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const consumedDraftRef = useRef(false);

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

  // Auto-send whatever the Action button prepared (voice transcript, photo,
  // or file note) the moment this page mounts, exactly once.
  useEffect(() => {
    if (!pendingDraft || consumedDraftRef.current) return;
    consumedDraftRef.current = true;
    const draftToSend = pendingDraft;
    setPendingDraft(null);
    if (draftToSend.kind === "text") {
      void send(draftToSend.text);
    } else {
      void send(draftToSend.text, draftToSend.imageDataUrl);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingDraft]);

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const text = draft;
    setDraft("");
    void send(text);
  };

  return (
    <div className="flex h-[calc(100dvh-9.5rem)] min-h-0 w-full min-w-0 flex-col">
      <div ref={scrollRef} className="min-h-0 flex-1 space-y-3 overflow-y-auto overflow-x-hidden pb-3">
        {items.length === 0 ? <p className="pt-10 text-center text-sm text-slate-500">Задайте вопрос ИИ или отправьте голосовое сообщение кнопкой «Действие».</p> : null}
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

      {error ? <p className="pb-2 text-center text-xs text-rose-300">{error}</p> : null}

      <form onSubmit={onSubmit} className="flex items-center gap-2 border-t border-[#3a3d43] pt-3">
        <input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="Написать ИИ..."
          disabled={sending}
          className="h-11 min-w-0 flex-1 rounded-full border border-[#3a3d43] bg-[#2E3137] px-4 text-sm text-[#f4f7fb] outline-none placeholder:text-slate-500 focus:border-[#FFF27A]/40"
        />
        <button
          type="submit"
          disabled={sending || !draft.trim()}
          className="h-11 shrink-0 rounded-full bg-[#FFF27A] px-5 text-sm font-medium text-[#1E1E21] disabled:cursor-not-allowed disabled:opacity-50"
        >
          {sending ? "..." : "→"}
        </button>
      </form>
    </div>
  );
}
