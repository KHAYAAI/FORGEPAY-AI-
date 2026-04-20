/**
 * Main chat page — renders VoiceSession for the active vertical.
 * Route: /chat/:vertical
 */

import { useRef } from "react";
import { useParams } from "react-router-dom";
import type { Vertical } from "../../shared/types/voice";
import { VoiceSession } from "../components/voice/VoiceSession";

const VERTICAL_LABELS: Record<Vertical, string> = {
  grocery: "Grocery",
  b2b_procurement: "B2B Procurement",
  healthcare: "Healthcare",
};

export default function ChatPage() {
  const { vertical = "grocery" } = useParams<{ vertical: Vertical }>();
  const userId = localStorage.getItem("userId") ?? "anonymous";
  const conversationIdRef = useRef(`${userId}-${vertical}-${Date.now()}`);
  const conversationId = conversationIdRef.current;

  return (
    <div className="flex h-screen flex-col bg-white">
      <header className="flex items-center border-b px-4 py-3">
        <h1 className="text-lg font-semibold text-gray-900">
          VocalMarket · {VERTICAL_LABELS[vertical as Vertical] ?? vertical}
        </h1>
      </header>
      <main className="flex-1 overflow-hidden">
        <VoiceSession
          userId={userId}
          vertical={vertical as Vertical}
          conversationId={conversationId}
        />
      </main>
    </div>
  );
}
