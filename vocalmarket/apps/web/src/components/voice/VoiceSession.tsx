/**
 * Full voice session UI.
 *
 * Composes VoiceButton + AudioVisualizer + transcript display + product results.
 * Owns the VoiceClient instance and exposes session state via local React state.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import type { AgentResponse, Vertical } from "@/types";
import { VoiceClient, type VoiceClientStatus } from "@/lib/voice-client";
import { AudioVisualizer } from "./AudioVisualizer";
import { VoiceButton } from "./VoiceButton";

interface VoiceSessionProps {
  userId: string;
  vertical: Vertical;
  conversationId: string;
}

interface Message {
  id: string;
  role: "user" | "assistant";
  text: string;
  products?: AgentResponse["products"];
}

export function VoiceSession({ userId, vertical, conversationId }: VoiceSessionProps) {
  const [status, setStatus] = useState<VoiceClientStatus>("idle");
  const [messages, setMessages] = useState<Message[]>([]);
  const [liveTranscript, setLiveTranscript] = useState("");
  const clientRef = useRef<VoiceClient | null>(null);
  const msgEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const client = new VoiceClient(conversationId, userId, vertical, {
      onStatusChange: setStatus,
      onTranscription: (text) => {
        setLiveTranscript(text);
      },
      onAgentResponse: (response) => {
        setLiveTranscript("");
        setMessages((prev) => [
          ...prev,
          {
            id: `user-${Date.now()}`,
            role: "user",
            text: response.text, // transcription echoed back
          },
          {
            id: `ai-${Date.now()}`,
            role: "assistant",
            text: response.text,
            products: response.products,
          },
        ]);
      },
      onError: (msg) => console.error("Voice error:", msg),
    });
    clientRef.current = client;
    let mounted = true;
    (async () => {
      await client.connect();
      if (!mounted) client.disconnect();
    })();

    return () => {
      mounted = false;
      client.disconnect();
    };
  }, [userId, vertical, conversationId]);

  useEffect(() => {
    msgEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleStart = useCallback(() => {
    clientRef.current?.startListening();
  }, []);

  const handleStop = useCallback(() => {
    clientRef.current?.stopListening();
  }, []);

  return (
    <div className="flex h-full flex-col">
      {/* Message history */}
      <div className="flex-1 overflow-y-auto px-4 py-6 space-y-4">
        {messages.length === 0 && (
          <p className="text-center text-slate-600 text-sm mt-12">
            Tap the mic and start speaking
          </p>
        )}

        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
          >
            <div
              className={[
                "max-w-xs rounded-2xl px-4 py-3 text-sm leading-relaxed",
                msg.role === "user"
                  ? "bg-indigo-600 text-white rounded-br-sm"
                  : "bg-slate-800 text-slate-100 border border-slate-700 rounded-bl-sm",
              ].join(" ")}
            >
              <p>{msg.text}</p>
              {msg.products && msg.products.length > 0 && (
                <ProductList products={msg.products} />
              )}
            </div>
          </div>
        ))}

        {liveTranscript && (
          <div className="flex justify-end">
            <div className="max-w-xs rounded-2xl bg-indigo-600/20 border border-indigo-500/30 px-4 py-3 text-sm text-indigo-300 italic">
              {liveTranscript}…
            </div>
          </div>
        )}

        <div ref={msgEndRef} />
      </div>

      {/* Voice controls */}
      <div className="border-t border-slate-800 bg-slate-900 px-4 py-6 flex flex-col items-center gap-4">
        <AudioVisualizer
          isListening={status === "listening"}
          isSpeaking={status === "speaking"}
        />
        <VoiceButton
          status={status}
          onPressStart={handleStart}
          onPressStop={handleStop}
        />
      </div>
    </div>
  );
}

function ProductList({ products }: { products: NonNullable<AgentResponse["products"]> }) {
  return (
    <div className="mt-3 space-y-2">
      {products.slice(0, 3).map((p) => (
        <div
          key={p.id}
          className="rounded-lg border border-slate-600 bg-slate-700/50 p-2 text-xs"
        >
          <div className="flex items-center justify-between">
            <span className="font-medium text-slate-100">{p.name}</span>
            {p.isCurated && (
              <span className="rounded-full bg-amber-500/20 px-2 py-0.5 text-amber-300 text-xs border border-amber-500/30">
                Preferred
              </span>
            )}
          </div>
          <div className="mt-0.5 text-slate-400">
            {p.currency} {p.price.toFixed(2)} · {p.inStock ? "In stock" : "Out of stock"}
          </div>
        </div>
      ))}
    </div>
  );
}
