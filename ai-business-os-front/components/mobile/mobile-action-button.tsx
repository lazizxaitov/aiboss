"use client";

import { useRouter } from "next/navigation";

// This used to be the recording button itself (photo/file drawer on a tap,
// hold-to-record voice), with the transcript handed off to /m/chat through
// MobileComposerProvider since a nav-bar button and the chat route are two
// separate pages. That handoff is gone now: attaching a file/photo and
// recording voice all live directly in the chat composer (app/m/chat/page.tsx)
// instead, where the user can already see the conversation they're adding
// to. All this button does now is open that chat.
export function MobileActionButton() {
  const router = useRouter();

  return (
    <button
      type="button"
      onClick={() => router.push("/m/chat")}
      className="flex min-h-14 flex-col items-center justify-center gap-1 rounded-2xl text-[11px] text-slate-300"
    >
      <span aria-hidden="true" className="text-xl leading-none">
        💬
      </span>
      <span>Чат с ИИ</span>
    </button>
  );
}
