import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { listConversations } from "@/lib/api";
import { Badge } from "@/components/ui/Badge";
import { useApp } from "@/contexts/AppContext";
import type { Conversation, Vertical } from "@/types";

const VERTICAL_BADGE: Record<Vertical, "success" | "indigo" | "warning"> = {
  grocery: "success",
  b2b_procurement: "indigo",
  healthcare: "warning",
};

const VERTICAL_LABELS: Record<Vertical, string> = {
  grocery: "Grocery",
  b2b_procurement: "B2B Procurement",
  healthcare: "Healthcare",
};

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

export default function ConversationsPage() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [loading, setLoading] = useState(true);
  const { toast } = useApp();
  const navigate = useNavigate();

  useEffect(() => {
    listConversations()
      .then(setConversations)
      .catch((err: Error) => {
        toast(err.message ?? "Failed to load conversations", "error");
        setConversations(MOCK_CONVERSATIONS);
      })
      .finally(() => setLoading(false));
  }, [toast]);

  function handleOpen(conv: Conversation) {
    navigate(`/chat/${conv.vertical}`);
  }

  return (
    <div className="min-h-full bg-slate-950 px-4 py-8 sm:px-8">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-100">Conversations</h1>
          <p className="mt-1 text-sm text-slate-400">Your conversation history across all channels</p>
        </div>
        <button
          onClick={() => navigate("/chat")}
          className="flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-indigo-500"
        >
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4.5v15m7.5-7.5h-15" />
          </svg>
          New chat
        </button>
      </div>

      {loading ? (
        <ConversationsSkeleton />
      ) : conversations.length === 0 ? (
        <EmptyState onNew={() => navigate("/chat")} />
      ) : (
        <div className="space-y-2">
          {conversations.map((conv) => (
            <button
              key={conv.id}
              onClick={() => handleOpen(conv)}
              className="group w-full rounded-xl border border-slate-800 bg-slate-900 p-4 text-left transition hover:border-slate-700 hover:bg-slate-800/60"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex min-w-0 items-start gap-3">
                  {/* Vertical icon */}
                  <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-slate-800 text-slate-400">
                    <VerticalIcon vertical={conv.vertical} />
                  </div>

                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <Badge variant={VERTICAL_BADGE[conv.vertical]}>
                        {VERTICAL_LABELS[conv.vertical] ?? conv.vertical}
                      </Badge>
                      <span className="text-xs text-slate-500">
                        {conv.message_count} message{conv.message_count !== 1 ? "s" : ""}
                      </span>
                    </div>
                    {conv.last_message && (
                      <p className="mt-1.5 truncate text-sm text-slate-400">
                        {conv.last_message}
                      </p>
                    )}
                  </div>
                </div>

                <div className="shrink-0 text-right">
                  <p className="text-xs text-slate-500">{timeAgo(conv.updated_at)}</p>
                  <svg
                    className="mt-2 ml-auto h-4 w-4 text-slate-600 transition group-hover:text-slate-400"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                  </svg>
                </div>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function VerticalIcon({ vertical }: { vertical: Vertical }) {
  if (vertical === "grocery") {
    return (
      <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
          d="M15.75 10.5V6a3.75 3.75 0 10-7.5 0v4.5m11.356-1.993l1.263 12c.07.665-.45 1.243-1.119 1.243H4.25a1.125 1.125 0 01-1.12-1.243l1.264-12A1.125 1.125 0 015.513 7.5h12.974c.576 0 1.059.435 1.119 1.007z" />
      </svg>
    );
  }
  if (vertical === "b2b_procurement") {
    return (
      <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
          d="M3.75 21h16.5M4.5 3h15M5.25 3v18m13.5-18v18M9 6.75h1.5m-1.5 3h1.5m-1.5 3h1.5m3-6H15m-1.5 3H15m-1.5 3H15M9 21v-3.375c0-.621.504-1.125 1.125-1.125h3.75c.621 0 1.125.504 1.125 1.125V21" />
      </svg>
    );
  }
  return (
    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
        d="M9 12h3.75M9 15h3.75M9 18h3.75m3 .75H18a2.25 2.25 0 002.25-2.25V6.108c0-1.135-.845-2.098-1.976-2.192a48.424 48.424 0 00-1.123-.08m-5.801 0c-.065.21-.1.433-.1.664 0 .414.336.75.75.75h4.5a.75.75 0 00.75-.75 2.25 2.25 0 00-.1-.664m-5.8 0A2.251 2.251 0 0113.5 2.25H15c1.012 0 1.867.668 2.15 1.586m-5.8 0c-.376.023-.75.05-1.124.08C9.095 4.01 8.25 4.973 8.25 6.108V8.25m0 0H4.875c-.621 0-1.125.504-1.125 1.125v11.25c0 .621.504 1.125 1.125 1.125h9.75c.621 0 1.125-.504 1.125-1.125V9.375c0-.621-.504-1.125-1.125-1.125H8.25z" />
    </svg>
  );
}

function ConversationsSkeleton() {
  return (
    <div className="space-y-2">
      {[1, 2, 3, 4].map((i) => (
        <div key={i} className="h-16 rounded-xl border border-slate-800 bg-slate-900 animate-pulse" />
      ))}
    </div>
  );
}

function EmptyState({ onNew }: { onNew: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-2xl border border-slate-800 bg-slate-900 py-16 text-center">
      <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-slate-800 text-slate-500">
        <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
            d="M20.25 8.511c.884.284 1.5 1.128 1.5 2.097v4.286c0 1.136-.847 2.1-1.98 2.193-.34.027-.68.052-1.02.072v3.091l-3-3c-1.354 0-2.694-.055-4.02-.163a2.115 2.115 0 01-.825-.242m9.345-8.334a2.126 2.126 0 00-.476-.095 48.64 48.64 0 00-8.048 0c-1.131.094-1.976 1.057-1.976 2.192v4.286c0 .837.46 1.58 1.155 1.951m9.345-8.334V6.637c0-1.621-1.152-3.026-2.76-3.235A48.455 48.455 0 0011.25 3c-2.115 0-4.198.137-6.24.402-1.608.209-2.76 1.614-2.76 3.235v6.226c0 1.621 1.152 3.026 2.76 3.235.577.075 1.157.14 1.74.194V21l4.155-4.155" />
        </svg>
      </div>
      <p className="text-sm font-medium text-slate-300">No conversations yet</p>
      <p className="mt-1 text-xs text-slate-500">Start a voice or text session to begin</p>
      <button
        onClick={onNew}
        className="mt-5 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-indigo-500"
      >
        Start a conversation
      </button>
    </div>
  );
}

const MOCK_CONVERSATIONS: Conversation[] = [
  {
    id: "conv-1",
    vertical: "grocery",
    created_at: new Date(Date.now() - 3_600_000).toISOString(),
    updated_at: new Date(Date.now() - 3_600_000).toISOString(),
    message_count: 6,
    last_message: "Milk 2L is R32.99, available for same-day delivery",
  },
  {
    id: "conv-2",
    vertical: "b2b_procurement",
    created_at: new Date(Date.now() - 86_400_000).toISOString(),
    updated_at: new Date(Date.now() - 86_400_000).toISOString(),
    message_count: 14,
    last_message: "Found 3 ISO 9001 certified bolt suppliers under R45,000",
  },
  {
    id: "conv-3",
    vertical: "healthcare",
    created_at: new Date(Date.now() - 2 * 86_400_000).toISOString(),
    updated_at: new Date(Date.now() - 2 * 86_400_000).toISOString(),
    message_count: 4,
    last_message: "Ibuprofen 200mg is available OTC, no prescription required",
  },
];
