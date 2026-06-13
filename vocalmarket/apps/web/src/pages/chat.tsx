import { type FormEvent, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useApp } from "@/contexts/AppContext";
import { Badge } from "@/components/ui/Badge";
import { VoiceSession } from "@/components/voice/VoiceSession";
import type { Vertical } from "@/types";

const VERTICAL_LABELS: Record<Vertical, string> = {
  grocery: "Grocery",
  b2b_procurement: "B2B Procurement",
  healthcare: "Healthcare",
};

const VERTICAL_BADGE: Record<Vertical, "success" | "indigo" | "warning"> = {
  grocery: "success",
  b2b_procurement: "indigo",
  healthcare: "warning",
};

type InputMode = "voice" | "text";

export default function ChatPage() {
  const { vertical: paramVertical } = useParams<{ vertical: string }>();
  const { vertical: ctxVertical, setVertical, user, toast } = useApp();
  const navigate = useNavigate();

  const vertical: Vertical = (paramVertical as Vertical) ?? ctxVertical;
  const userId = user?.id ?? localStorage.getItem("userId") ?? "anonymous";
  const conversationIdRef = useRef(`${userId}-${vertical}-${Date.now()}`);
  const conversationId = conversationIdRef.current;

  const [inputMode, setInputMode] = useState<InputMode>("voice");
  const [textInput, setTextInput] = useState("");
  const [sending, setSending] = useState(false);

  function handleVerticalChange(v: Vertical) {
    setVertical(v);
    navigate(`/chat/${v}`, { replace: true });
  }

  async function handleTextSubmit(e: FormEvent) {
    e.preventDefault();
    if (!textInput.trim() || sending) return;
    setSending(true);
    try {
      toast("Text mode routes through /api/conversations — connect the API to enable.", "info");
      setTextInput("");
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="flex h-full flex-col bg-slate-950">
      {/* Top bar */}
      <div className="flex h-14 shrink-0 items-center justify-between border-b border-slate-800 bg-slate-900 px-4">
        <div className="flex items-center gap-2.5">
          <Badge variant={VERTICAL_BADGE[vertical]}>
            {VERTICAL_LABELS[vertical] ?? vertical}
          </Badge>
          <span className="text-xs text-slate-500">·</span>
          <span className="text-xs text-slate-500">Live session</span>
        </div>

        <div className="flex items-center gap-2">
          <select
            value={vertical}
            onChange={(e) => handleVerticalChange(e.target.value as Vertical)}
            className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-300 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
          >
            <option value="grocery">Grocery</option>
            <option value="b2b_procurement">B2B Procurement</option>
            <option value="healthcare">Healthcare</option>
          </select>

          <div className="flex rounded-lg border border-slate-700 bg-slate-800 p-0.5">
            <button
              onClick={() => setInputMode("voice")}
              className={[
                "rounded-md px-3 py-1 text-xs font-medium transition-colors",
                inputMode === "voice"
                  ? "bg-slate-700 text-slate-100"
                  : "text-slate-500 hover:text-slate-300",
              ].join(" ")}
            >
              Voice
            </button>
            <button
              onClick={() => setInputMode("text")}
              className={[
                "rounded-md px-3 py-1 text-xs font-medium transition-colors",
                inputMode === "text"
                  ? "bg-slate-700 text-slate-100"
                  : "text-slate-500 hover:text-slate-300",
              ].join(" ")}
            >
              Text
            </button>
          </div>
        </div>
      </div>

      {/* Session */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {inputMode === "voice" ? (
          <VoiceSession
            userId={userId}
            vertical={vertical}
            conversationId={conversationId}
          />
        ) : (
          <TextSession
            textInput={textInput}
            setTextInput={setTextInput}
            sending={sending}
            onSubmit={handleTextSubmit}
          />
        )}
      </div>
    </div>
  );
}

interface TextSessionProps {
  textInput: string;
  setTextInput: (v: string) => void;
  sending: boolean;
  onSubmit: (e: FormEvent) => void;
}

function TextSession({ textInput, setTextInput, sending, onSubmit }: TextSessionProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null);

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <div className="flex-1 overflow-y-auto px-4 py-6">
        <p className="mt-12 text-center text-sm text-slate-600">
          Type a message to start the conversation
        </p>
        <div ref={messagesEndRef} />
      </div>

      <form
        onSubmit={onSubmit}
        className="flex items-end gap-2 border-t border-slate-800 bg-slate-900 px-4 py-3"
      >
        <textarea
          value={textInput}
          onChange={(e) => setTextInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              onSubmit(e as unknown as FormEvent);
            }
          }}
          placeholder="Type a message…"
          rows={1}
          className="flex-1 resize-none rounded-xl border border-slate-700 bg-slate-800 px-3.5 py-2.5 text-sm text-slate-100 placeholder-slate-500 outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20"
          style={{ maxHeight: "120px" }}
        />
        <button
          type="submit"
          disabled={!textInput.trim() || sending}
          className="flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-600 text-white transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {sending ? (
            <svg className="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
          ) : (
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5" />
            </svg>
          )}
        </button>
      </form>
    </div>
  );
}
