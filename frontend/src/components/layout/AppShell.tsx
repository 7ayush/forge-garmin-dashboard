import React, { useEffect, useState } from "react";
import {
  Activity,
  Dumbbell,
  Flame,
  HeartPulse,
  Moon,
  Plus,
  RefreshCw,
  Scale,
  Settings,
  Sparkles,
  TrendingUp,
  UserCheck,
} from "lucide-react";
import { forgeApi } from "../../api/client";
import type { AccountInfo, PageRoute, SyncState } from "../../types/forge";

export const NAV_ITEMS: Array<{
  route: PageRoute;
  label: string;
  shortLabel: string;
  icon: React.ComponentType<{ className?: string }>;
}> = [
  { route: "today", label: "Today", shortLabel: "Today", icon: Activity },
  { route: "strength", label: "Strength Lab", shortLabel: "Strength", icon: Dumbbell },
  { route: "engine", label: "Engine", shortLabel: "Engine", icon: HeartPulse },
  { route: "recovery", label: "Recovery", shortLabel: "Recovery", icon: Moon },
  { route: "body", label: "Physique", shortLabel: "Body", icon: Scale },
  { route: "fuel", label: "Fuel", shortLabel: "Fuel", icon: Flame },
  { route: "progress", label: "Progress", shortLabel: "Progress", icon: TrendingUp },
  { route: "tips", label: "Tips & Reports", shortLabel: "Tips", icon: Sparkles },
  { route: "settings", label: "Settings", shortLabel: "Settings", icon: Settings },
];

export function AppShell({
  activeRoute,
  onNavigate,
  athleteName,
  deviceName,
  syncState,
  syncingNow,
  onSyncNow,
  onOpenQuickLog,
  onAccountChange,
  children,
}: {
  activeRoute: PageRoute;
  onNavigate: (route: PageRoute) => void;
  athleteName?: string;
  deviceName?: string;
  syncState?: SyncState | null;
  syncingNow: boolean;
  onSyncNow: () => void;
  onOpenQuickLog: () => void;
  onAccountChange?: () => void;
  children: React.ReactNode;
}) {
  const [account, setAccount] = useState<AccountInfo | null>(null);
  const [loginOpen, setLoginOpen] = useState(false);
  const [loginEmail, setLoginEmail] = useState("");
  const [loginPassword, setLoginPassword] = useState("");
  const [loginError, setLoginError] = useState<string | null>(null);
  const [loginBusy, setLoginBusy] = useState(false);

  useEffect(() => {
    forgeApi
      .getAccounts()
      .then((res) => {
        const first = res.accounts[0] ?? null;
        setAccount(first);
        if (first?.email) setLoginEmail(first.email);
      })
      .catch(() => {});
  }, []);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!loginEmail || !loginPassword) return;
    setLoginBusy(true);
    setLoginError(null);
    try {
      const res = await forgeApi.loginAccount(loginEmail, loginPassword);
      setAccount(res.accounts[0] ?? null);
      setLoginOpen(false);
      setLoginPassword("");
      onAccountChange?.();
    } catch (err) {
      setLoginError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoginBusy(false);
    }
  };

  const handleLogout = async () => {
    try {
      const res = await forgeApi.logoutAccount();
      setAccount(res.accounts[0] ?? null);
      onAccountChange?.();
    } catch {
      // ignore
    }
  };
  const lastSynced = syncState?.running
    ? syncState.total > 0
      ? `Syncing ${syncState.progress}/${syncState.total}`
      : "Syncing..."
    : syncState?.last_sync_at
    ? new Date(syncState.last_sync_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
    : "Ready";

  return (
    <div className="min-h-screen pb-20 lg:pb-0 lg:pl-60">
      {/* Desktop Left Navigation Rail */}
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-60 flex-col border-r border-slate-800/80 bg-[#070a10]/95 px-3 py-5 backdrop-blur-xl lg:flex">
        <div className="mb-6 flex items-center gap-2.5 px-2.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl border border-emerald-400/40 bg-emerald-500/15 font-display text-base font-extrabold text-emerald-300 shadow-[0_0_20px_rgba(16,185,129,0.2)]">
            F
          </div>
          <div>
            <div className="font-display text-sm font-extrabold tracking-wider text-slate-100">
              FORGE // OS
            </div>
            <div className="font-mono-num text-[10px] tracking-widest text-emerald-400/85 uppercase">
              Bio-Telemetry Lab
            </div>
          </div>
        </div>

        {account && (
          <div className="mb-4 rounded-xl border border-slate-800/80 bg-slate-950/60 p-2.5">
            <div className="mb-1.5 flex items-center justify-between text-[10px] font-semibold tracking-wider text-slate-400 uppercase">
              <span className="flex items-center gap-1.5">
                <UserCheck className="h-3 w-3 text-emerald-400" />
                Garmin Account
              </span>
              <span
                title={account.authenticated ? "Connected" : "Sign in required"}
                className={`h-2 w-2 rounded-full ${
                  account.authenticated ? "bg-emerald-400" : "bg-amber-400"
                }`}
              />
            </div>
            <div className="truncate text-xs font-semibold text-slate-200">
              {athleteName || account.label || "Garmin Connect"}
            </div>
            {account.email && (
              <div className="truncate text-[10px] text-slate-400">{account.email}</div>
            )}
            <div className="mt-2 flex gap-1.5">
              <button
                type="button"
                onClick={() => {
                  setLoginError(null);
                  setLoginOpen(true);
                }}
                className="flex-1 rounded-lg border border-slate-700/80 bg-slate-900 px-2 py-1 text-[10px] font-semibold text-slate-200 transition hover:border-emerald-500/40 hover:text-emerald-300"
              >
                {account.authenticated ? "Switch" : "Sign In"}
              </button>
              {account.authenticated && (
                <button
                  type="button"
                  onClick={() => void handleLogout()}
                  className="rounded-lg border border-slate-800 px-2 py-1 text-[10px] text-slate-400 transition hover:border-rose-500/40 hover:text-rose-300"
                >
                  Sign Out
                </button>
              )}
            </div>
          </div>
        )}

        <nav className="flex-1 space-y-1">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const active = activeRoute === item.route;
            return (
              <button
                key={item.route}
                type="button"
                onClick={() => onNavigate(item.route)}
                className={`flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-xs font-medium transition-all ${
                  active
                    ? "border border-emerald-500/35 bg-emerald-500/12 text-emerald-200 shadow-[inset_0_0_16px_rgba(16,185,129,0.08)]"
                    : "border border-transparent text-slate-400 hover:bg-slate-800/45 hover:text-slate-100"
                }`}
              >
                <Icon className={`h-4 w-4 ${active ? "text-emerald-300" : "text-slate-400"}`} />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>

        <div className="mt-4 space-y-2.5 rounded-xl border border-slate-800/80 bg-slate-950/60 p-3">
          <div className="flex items-center justify-between text-[11px]">
            <span className="text-slate-400">Device</span>
            <span className="font-mono-num font-medium text-slate-200">{deviceName || "Forerunner 965"}</span>
          </div>
          <div className="flex items-center justify-between text-[11px]">
            <span className="text-slate-400">Sync</span>
            <span className="font-mono-num text-emerald-300">{syncingNow || syncState?.running ? "Syncing..." : lastSynced}</span>
          </div>
          <button
            type="button"
            onClick={onSyncNow}
            disabled={syncingNow || syncState?.running}
            className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-slate-700/80 bg-slate-900/90 px-2.5 py-1.5 text-[11px] font-medium text-slate-200 transition hover:border-emerald-400/50 hover:text-emerald-200 disabled:opacity-50"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${syncingNow || syncState?.running ? "animate-spin text-emerald-400" : ""}`} />
            Sync Garmin
          </button>
        </div>
      </aside>

      {/* Top Header */}
      <header className="sticky top-0 z-20 border-b border-slate-800/80 bg-[#05070b]/85 px-4 py-3 backdrop-blur-xl sm:px-6">
        <div className="mx-auto flex max-w-[1440px] items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg border border-emerald-400/40 bg-emerald-500/15 font-display text-sm font-extrabold text-emerald-300 lg:hidden">
              F
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="font-display text-sm font-bold tracking-tight text-slate-100 sm:text-base">
                  {NAV_ITEMS.find((n) => n.route === activeRoute)?.label ?? "FORGE"}
                </h1>
                <span className="hidden rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 font-mono-num text-[10px] font-medium text-emerald-300 sm:inline-block">
                  {athleteName || "Ayush Kaushik"}
                </span>
              </div>
              <p className="font-mono-num text-[10px] text-slate-400 lg:hidden">
                {deviceName || "Forerunner 965"} · Synced {lastSynced}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onSyncNow}
              disabled={syncingNow || syncState?.running}
              className="inline-flex items-center gap-1.5 rounded-xl border border-slate-700/80 bg-slate-900/75 px-3 py-1.5 text-xs font-medium text-slate-200 transition hover:border-emerald-400/45 lg:hidden"
              title="Sync Garmin Connect"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${syncingNow || syncState?.running ? "animate-spin text-emerald-400" : ""}`} />
              <span className="hidden sm:inline">Sync</span>
            </button>
            <button
              type="button"
              onClick={onOpenQuickLog}
              className="inline-flex items-center gap-1.5 rounded-xl border border-emerald-400/40 bg-emerald-500/15 px-3.5 py-1.5 text-xs font-semibold text-emerald-200 shadow-[0_0_20px_rgba(16,185,129,0.16)] transition hover:bg-emerald-500/25"
            >
              <Plus className="h-3.5 w-3.5" />
              <span>Quick Log</span>
            </button>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="mx-auto max-w-[1440px] px-4 py-5 sm:px-6 sm:py-6">{children}</main>

      {/* Mobile Bottom Navigation */}
      <nav className="fixed inset-x-0 bottom-0 z-30 flex items-center justify-around border-t border-slate-800/90 bg-[#070a10]/95 px-1 py-1.5 backdrop-blur-xl lg:hidden">
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          const active = activeRoute === item.route;
          return (
            <button
              key={item.route}
              type="button"
              onClick={() => onNavigate(item.route)}
              className={`flex min-w-0 flex-1 flex-col items-center gap-0.5 rounded-lg py-1 text-[10px] font-medium transition ${
                active ? "text-emerald-300" : "text-slate-400 hover:text-slate-200"
              }`}
            >
              <Icon className="h-4 w-4" />
              <span className="truncate">{item.shortLabel}</span>
            </button>
          );
        })}
      </nav>
      {loginOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm">
          <form
            onSubmit={handleLogin}
            className="w-full max-w-sm rounded-2xl border border-slate-800 bg-[#0b1018] p-5 shadow-2xl"
          >
            <h3 className="text-sm font-bold text-slate-100">
              Sign in to Garmin Connect
            </h3>
            <p className="mt-1 text-xs text-slate-400">
              Your OAuth tokens are stored locally on your machine.
            </p>
            <input
              type="email"
              required
              autoFocus
              value={loginEmail}
              onChange={(e) => setLoginEmail(e.target.value)}
              placeholder="Garmin Connect email"
              className="mt-3 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-100 outline-none focus:border-emerald-500"
            />
            <input
              type="password"
              required
              value={loginPassword}
              onChange={(e) => setLoginPassword(e.target.value)}
              placeholder="Garmin Connect password"
              className="mt-2 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-100 outline-none focus:border-emerald-500"
            />
            {loginError && (
              <p className="mt-2 text-xs text-rose-400">{loginError}</p>
            )}
            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setLoginOpen(false)}
                className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-800"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={loginBusy}
                className="rounded-lg bg-emerald-500 px-3 py-1.5 text-xs font-semibold text-slate-950 hover:bg-emerald-400 disabled:opacity-50"
              >
                {loginBusy ? "Signing in..." : "Sign In"}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
