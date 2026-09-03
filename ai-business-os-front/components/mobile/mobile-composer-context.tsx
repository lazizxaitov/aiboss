"use client";

import { createContext, useContext, useState, type ReactNode } from "react";

// A message the Action button (voice/photo/file) prepared, waiting to be
// auto-sent once /m/chat mounts. Kept in a context that's provided by the
// /m shell layout — since that layout persists across client-side
// navigation to any page nested inside it, this survives the
// hold-button-then-navigate-to-chat handoff with no size limits or
// serialization the way sessionStorage would have.
export type PendingDraft =
  | { kind: "text"; text: string }
  | { kind: "image"; text: string; imageDataUrl: string; fileName: string };

type MobileComposerContextValue = {
  pendingDraft: PendingDraft | null;
  setPendingDraft: (draft: PendingDraft | null) => void;
};

const MobileComposerContext = createContext<MobileComposerContextValue | null>(null);

export function MobileComposerProvider({ children }: { children: ReactNode }) {
  const [pendingDraft, setPendingDraft] = useState<PendingDraft | null>(null);
  return <MobileComposerContext.Provider value={{ pendingDraft, setPendingDraft }}>{children}</MobileComposerContext.Provider>;
}

export function useMobileComposer(): MobileComposerContextValue {
  const context = useContext(MobileComposerContext);
  if (!context) {
    throw new Error("useMobileComposer must be used within MobileComposerProvider");
  }
  return context;
}
