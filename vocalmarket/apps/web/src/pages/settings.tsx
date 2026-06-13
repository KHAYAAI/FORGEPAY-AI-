import { type FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { updateProfile } from "@/lib/api";
import { clearAuth, setUser } from "@/lib/auth";
import { useApp } from "@/contexts/AppContext";
import type { Vertical } from "@/types";

const VERTICAL_OPTIONS: Array<{ value: Vertical; label: string }> = [
  { value: "grocery", label: "Grocery" },
  { value: "b2b_procurement", label: "B2B Procurement" },
  { value: "healthcare", label: "Healthcare" },
];

export default function SettingsPage() {
  const { user, vertical, setVertical, refreshUser, toast } = useApp();
  const navigate = useNavigate();

  const [name, setName] = useState(user?.name ?? "");
  const [saving, setSaving] = useState(false);

  async function handleProfileSave(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      const updated = await updateProfile({ name });
      setUser(updated);
      refreshUser();
      toast("Profile saved", "success");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to save profile";
      toast(msg, "error");
    } finally {
      setSaving(false);
    }
  }

  function handleSignOut() {
    clearAuth();
    navigate("/login");
  }

  return (
    <div className="min-h-full bg-slate-950 px-4 py-8 sm:px-8">
      <div className="mb-8">
        <h1 className="text-xl font-semibold text-slate-100">Settings</h1>
        <p className="mt-1 text-sm text-slate-400">Manage your account and preferences</p>
      </div>

      <div className="max-w-lg space-y-6">
        {/* Profile */}
        <Section title="Profile" description="Your display name shown in conversations">
          <form onSubmit={handleProfileSave} className="space-y-4">
            <div>
              <label htmlFor="email" className="mb-1.5 block text-xs font-medium text-slate-400">
                Email address
              </label>
              <input
                id="email"
                type="email"
                value={user?.email ?? ""}
                disabled
                className="w-full rounded-lg border border-slate-700 bg-slate-800/50 px-3.5 py-2.5 text-sm text-slate-500 cursor-not-allowed"
              />
            </div>
            <div>
              <label htmlFor="name" className="mb-1.5 block text-xs font-medium text-slate-400">
                Display name
              </label>
              <input
                id="name"
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Your name"
                className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3.5 py-2.5 text-sm text-slate-100 placeholder-slate-500 outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20"
              />
            </div>
            <div className="flex justify-end">
              <button
                type="submit"
                disabled={saving}
                className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-indigo-500 disabled:opacity-60"
              >
                {saving ? "Saving…" : "Save changes"}
              </button>
            </div>
          </form>
        </Section>

        {/* Preferences */}
        <Section title="Preferences" description="Default settings applied to new conversations">
          <div>
            <label className="mb-1.5 block text-xs font-medium text-slate-400">
              Default vertical
            </label>
            <select
              value={vertical}
              onChange={(e) => setVertical(e.target.value as Vertical)}
              className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3.5 py-2.5 text-sm text-slate-100 outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20"
            >
              {VERTICAL_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
            <p className="mt-1.5 text-xs text-slate-500">
              Applied when opening Chat without a specific vertical selected
            </p>
          </div>
        </Section>

        {/* Organisation */}
        {user?.org_id && (
          <Section title="Organisation" description="Your team account details">
            <div className="rounded-lg border border-slate-700 bg-slate-800/50 px-4 py-3">
              <div className="flex items-center justify-between text-sm">
                <span className="text-slate-400">Org ID</span>
                <span className="font-mono text-xs text-slate-300">{user.org_id}</span>
              </div>
              {user.role && (
                <div className="mt-2 flex items-center justify-between text-sm">
                  <span className="text-slate-400">Role</span>
                  <span className="text-slate-300 capitalize">{user.role}</span>
                </div>
              )}
            </div>
          </Section>
        )}

        {/* Danger zone */}
        <Section title="Sign out" description="End your current session on this device">
          <button
            onClick={handleSignOut}
            className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-2 text-sm font-medium text-red-400 transition hover:bg-red-500/20"
          >
            Sign out of VocalMarket
          </button>
        </Section>
      </div>
    </div>
  );
}

function Section({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900 p-6">
      <div className="mb-5">
        <h2 className="text-sm font-semibold text-slate-100">{title}</h2>
        <p className="mt-0.5 text-xs text-slate-500">{description}</p>
      </div>
      {children}
    </div>
  );
}
