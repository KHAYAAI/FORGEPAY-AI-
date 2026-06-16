import { useNavigate } from "react-router-dom";
import { useApp } from "@/contexts/AppContext";
import { Badge } from "@/components/ui/Badge";
import type { Vertical } from "@/types";

const VERTICALS: Array<{
  id: Vertical;
  label: string;
  description: string;
  badge: string;
  badgeVariant: "success" | "indigo" | "warning";
  icon: React.ReactNode;
}> = [
  {
    id: "grocery",
    label: "Grocery",
    description: "Voice-first grocery shopping with same-day delivery in South Africa.",
    badge: "Consumer",
    badgeVariant: "success",
    icon: (
      <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
          d="M15.75 10.5V6a3.75 3.75 0 10-7.5 0v4.5m11.356-1.993l1.263 12c.07.665-.45 1.243-1.119 1.243H4.25a1.125 1.125 0 01-1.12-1.243l1.264-12A1.125 1.125 0 015.513 7.5h12.974c.576 0 1.059.435 1.119 1.007z" />
      </svg>
    ),
  },
  {
    id: "b2b_procurement",
    label: "B2B Procurement",
    description: "AI-powered supplier discovery, RFQ management, and spend control.",
    badge: "Enterprise",
    badgeVariant: "indigo",
    icon: (
      <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
          d="M3.75 21h16.5M4.5 3h15M5.25 3v18m13.5-18v18M9 6.75h1.5m-1.5 3h1.5m-1.5 3h1.5m3-6H15m-1.5 3H15m-1.5 3H15M9 21v-3.375c0-.621.504-1.125 1.125-1.125h3.75c.621 0 1.125.504 1.125 1.125V21" />
      </svg>
    ),
  },
  {
    id: "healthcare",
    label: "Healthcare",
    description: "Compliant prescription and OTC ordering with geography-aware compliance.",
    badge: "Regulated",
    badgeVariant: "warning",
    icon: (
      <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
          d="M9 12h3.75M9 15h3.75M9 18h3.75m3 .75H18a2.25 2.25 0 002.25-2.25V6.108c0-1.135-.845-2.098-1.976-2.192a48.424 48.424 0 00-1.123-.08m-5.801 0c-.065.21-.1.433-.1.664 0 .414.336.75.75.75h4.5a.75.75 0 00.75-.75 2.25 2.25 0 00-.1-.664m-5.8 0A2.251 2.251 0 0113.5 2.25H15c1.012 0 1.867.668 2.15 1.586m-5.8 0c-.376.023-.75.05-1.124.08C9.095 4.01 8.25 4.973 8.25 6.108V8.25m0 0H4.875c-.621 0-1.125.504-1.125 1.125v11.25c0 .621.504 1.125 1.125 1.125h9.75c.621 0 1.125-.504 1.125-1.125V9.375c0-.621-.504-1.125-1.125-1.125H8.25zM6.75 12h.008v.008H6.75V12zm0 3h.008v.008H6.75V15zm0 3h.008v.008H6.75V18z" />
      </svg>
    ),
  },
];

export default function HomePage() {
  const { user, vertical, setVertical } = useApp();
  const navigate = useNavigate();

  function handleLaunch(v: Vertical) {
    setVertical(v);
    if (v === "grocery") {
      navigate("/shop");
      return;
    }
    navigate(`/chat/${v}`);
  }

  const greeting = (() => {
    const h = new Date().getHours();
    if (h < 12) return "Good morning";
    if (h < 17) return "Good afternoon";
    return "Good evening";
  })();

  return (
    <div className="min-h-full bg-slate-950 px-4 py-8 sm:px-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-2xl font-semibold text-slate-100">
          {greeting}{user?.name ? `, ${user.name.split(" ")[0]}` : ""}
        </h1>
        <p className="mt-1 text-sm text-slate-400">
          Select a vertical to start a conversation
        </p>
      </div>

      {/* Vertical cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {VERTICALS.map((v) => (
          <button
            key={v.id}
            onClick={() => handleLaunch(v.id)}
            className={[
              "group relative flex flex-col gap-4 rounded-2xl border p-6 text-left transition-all duration-200",
              "hover:border-indigo-500/50 hover:bg-slate-800/60",
              vertical === v.id
                ? "border-indigo-500/40 bg-slate-800/40"
                : "border-slate-800 bg-slate-900",
            ].join(" ")}
          >
            <div className="flex items-start justify-between">
              <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-slate-800 text-slate-400 group-hover:text-indigo-400 transition-colors">
                {v.icon}
              </div>
              <Badge variant={v.badgeVariant}>{v.badge}</Badge>
            </div>

            <div>
              <h2 className="font-semibold text-slate-100">{v.label}</h2>
              <p className="mt-1 text-sm text-slate-400 leading-relaxed">{v.description}</p>
            </div>

            <div className="flex items-center gap-1.5 text-xs font-medium text-indigo-400 group-hover:text-indigo-300">
              {v.id === "grocery" ? "Browse products" : "Start conversation"}
              <svg className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.5 4.5L21 12m0 0l-7.5 7.5M21 12H3" />
              </svg>
            </div>

            {vertical === v.id && (
              <div className="absolute right-3 top-3 h-2 w-2 rounded-full bg-indigo-400" />
            )}
          </button>
        ))}
      </div>

      {/* Quick links */}
      <div className="mt-8 grid gap-3 sm:grid-cols-2">
        <button
          onClick={() => navigate("/conversations")}
          className="flex items-center gap-3 rounded-xl border border-slate-800 bg-slate-900 px-4 py-3.5 text-left transition hover:border-slate-700 hover:bg-slate-800/60"
        >
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-slate-800 text-slate-400">
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                d="M20.25 8.511c.884.284 1.5 1.128 1.5 2.097v4.286c0 1.136-.847 2.1-1.98 2.193-.34.027-.68.052-1.02.072v3.091l-3-3c-1.354 0-2.694-.055-4.02-.163a2.115 2.115 0 01-.825-.242m9.345-8.334a2.126 2.126 0 00-.476-.095 48.64 48.64 0 00-8.048 0c-1.131.094-1.976 1.057-1.976 2.192v4.286c0 .837.46 1.58 1.155 1.951m9.345-8.334V6.637c0-1.621-1.152-3.026-2.76-3.235A48.455 48.455 0 0011.25 3c-2.115 0-4.198.137-6.24.402-1.608.209-2.76 1.614-2.76 3.235v6.226c0 1.621 1.152 3.026 2.76 3.235.577.075 1.157.14 1.74.194V21l4.155-4.155" />
            </svg>
          </div>
          <div>
            <p className="text-sm font-medium text-slate-200">Recent conversations</p>
            <p className="text-xs text-slate-500">View your history</p>
          </div>
          <svg className="ml-auto h-4 w-4 text-slate-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
          </svg>
        </button>

        <button
          onClick={() => navigate("/orders")}
          className="flex items-center gap-3 rounded-xl border border-slate-800 bg-slate-900 px-4 py-3.5 text-left transition hover:border-slate-700 hover:bg-slate-800/60"
        >
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-slate-800 text-slate-400">
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                d="M15.75 10.5V6a3.75 3.75 0 10-7.5 0v4.5m11.356-1.993l1.263 12c.07.665-.45 1.243-1.119 1.243H4.25a1.125 1.125 0 01-1.12-1.243l1.264-12A1.125 1.125 0 015.513 7.5h12.974c.576 0 1.059.435 1.119 1.007z" />
            </svg>
          </div>
          <div>
            <p className="text-sm font-medium text-slate-200">Order history</p>
            <p className="text-xs text-slate-500">Track your purchases</p>
          </div>
          <svg className="ml-auto h-4 w-4 text-slate-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
          </svg>
        </button>
      </div>
    </div>
  );
}
