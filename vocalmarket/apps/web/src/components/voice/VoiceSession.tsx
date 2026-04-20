/**
 * Full voice session UI.
 *
 * Composes VoiceButton + AudioVisualizer + transcript display + product results.
 * Owns the VoiceClient instance and exposes session state via local React state.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import type { AgentResponse, Vertical } from "../../../shared/types/voice";
import { VoiceClient, type VoiceClientStatus } from "../../lib/voice-client";
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
    client.connect();

    return () => {
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
          <p className="text-center text-gray-400 text-sm mt-12">
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
                "max-w-xs rounded-2xl px-4 py-3 text-sm",
                msg.role === "user"
                  ? "bg-indigo-500 text-white rounded-br-sm"
                  : "bg-gray-100 text-gray-900 rounded-bl-sm",
              ].join(" ")}
            >
              <p>{msg.text}</p>
              {msg.products && msg.products.length > 0 && (
                <ProductList products={msg.products} />
              )}
            </div>
          </div>
        ))}

        {/* Live transcription preview */}
        {liveTranscript && (
          <div className="flex justify-end">
            <div className="max-w-xs rounded-2xl bg-indigo-100 px-4 py-3 text-sm text-indigo-700 italic">
              {liveTranscript}…
            </div>
          </div>
        )}

        <div ref={msgEndRef} />
      </div>

      {/* Voice controls */}
      <div className="border-t bg-white px-4 py-6 flex flex-col items-center gap-4">
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
          className="rounded-lg border border-gray-200 bg-white p-2 text-xs text-gray-700"
        >
          <div className="flex items-center justify-between">
            <span className="font-medium">{p.name}</span>
            {p.isCurated && (
              <span className="rounded-full bg-amber-100 px-2 py-0.5 text-amber-700 text-xs">
                Preferred
              </span>
            )}
          </div>
          <div className="text-gray-500">
            {p.currency} {p.price.toFixed(2)} · {p.inStock ? "In stock" : "Out of stock"}
          </div>
        </div>
      ))}
    </div>
  );
}
