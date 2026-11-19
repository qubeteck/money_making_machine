import { useEffect, useRef, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import {
  Activity,
  ArrowLeftRight,
  ChevronDown,
  ExternalLink,
  FlaskConical,
  LayoutDashboard,
  LogOut,
  Menu,
  Pause,
  Play,
  Radio,
  RefreshCw,
  Server,
  Settings,
  ShieldAlert,
  Sparkles,
  X,
  Zap,
} from "lucide-react";
import { apiGet, apiPost, errorMessage } from "../lib/api";
import { cn, fmtPct, timeAgo } from "../lib/format";
import { usePolling } from "../lib/hooks";
import type { ActionResponse, ScanTriggerResult, SystemInfo } from "../lib/types";
import { useAuth } from "../context/auth";
import { useToast } from "../context/toast";
import { Badge, Button, ModeBadge, SyncLabel } from "./ui";

interface NavItem {
  to: string;
  label: string;
  icon: typeof LayoutDashboard;
  end?: boolean;
}

const workspaceNav: NavItem[] = [
  { to: "/", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/command-center", label: "Command Center", icon: Activity },
  { to: "/trades", label: "Trades", icon: ArrowLeftRight },
  { to: "/signals", label: "Signals", icon: Zap },
];

const researchNav: NavItem[] = [
  { to: "/live", label: "Live Prices", icon: Radio },
  { to: "/backtest", label: "Backtest", icon: FlaskConical },
];

const systemNav: NavItem[] = [
  { to: "/settings", label: "Settings", icon: Settings },
  { to: "/diagnostics", label: "Diagnostics", icon: Server },
];

const allNav = [...workspaceNav, ...researchNav, ...systemNav];

function NavSection({
  title,
  items,
  onNavigate,
}: {
  title: string;
  items: NavItem[];
  onNavigate?: () => void;
}) {
  return (
    <div>
      <p className="px-3 pb-2 text-[9px] font-bold uppercase tracking-[0.2em] text-slate-600">
        {title}
      </p>
      <nav className="space-y-1">
        {items.map((item) => {
          const Icon = item.icon;
          return (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              onClick={onNavigate}
              className={({ isActive }) =>
                cn(
                  "group flex items-center gap-3 rounded-xl border px-3 py-2.5 text-[13px] font-medium transition",
                  isActive
                    ? "border-emerald-500/20 bg-emerald-500/[0.08] text-white shadow-[inset_0_1px_0_rgba(255,255,255,.04)]"
                    : "border-transparent text-slate-400 hover:bg-white/[0.035] hover:text-slate-100",
                )
              }
            >
              {({ isActive }) => (
                <>
                  <Icon
                    className={cn(
                      "h-4 w-4 shrink-0 transition",
                      isActive ? "text-emerald-400" : "text-slate-500 group-hover:text-slate-300",
                    )}
                  />
                  <span className="truncate">{item.label}</span>
                  {isActive ? <span className="ml-auto h-1.5 w-1.5 rounded-full bg-emerald-400" /> : null}
                </>
              )}
            </NavLink>
          );
        })}
      </nav>
    </div>
  );
}

function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <div className="flex items-center gap-3">
      <div className="relative h-10 w-10 shrink-0 overflow-visible rounded-xl border border-emerald-400/25 bg-[#07101f] shadow-lg shadow-emerald-950/30">
        <img
          src="/ui/logo-192.png"
          alt="Money Machine"
          className="h-full w-full rounded-[11px] object-cover"
        />
        <span className="absolute -right-0.5 -top-0.5 h-2 w-2 rounded-full border border-[#070b12] bg-emerald-400" />
      </div>
      {!compact ? (
        <div className="min-w-0">
          <p className="text-[13px] font-bold tracking-[0.08em] text-white">MONEY MACHINE</p>
          <p className="text-[9px] font-semibold uppercase tracking-[0.2em] text-slate-500">
            Trading control plane
          </p>
        </div>
      ) : null}
    </div>
  );
}

function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  const { data: system } = usePolling<SystemInfo>(() => apiGet("/api/v1/system"), 30_000);
  const lastJob = system?.jobs?.[0];
  return (
    <div className="flex h-full flex-col px-4 py-5">
      <div className="mb-7 px-2">
        <Brand />
      </div>

      <div className="flex-1 space-y-6 overflow-y-auto pb-4">
        <NavSection title="Workspace" items={workspaceNav} onNavigate={onNavigate} />
        <NavSection title="Research" items={researchNav} onNavigate={onNavigate} />
        <NavSection title="Operations" items={systemNav} onNavigate={onNavigate} />
      </div>

      <div className="space-y-3 border-t border-slate-800/60 pt-4">
        <div className="rounded-xl border border-slate-800/70 bg-slate-900/40 p-3">
          <div className="flex items-center justify-between gap-2">
            <span className="text-[9px] font-bold uppercase tracking-[0.18em] text-slate-600">
              Engine
            </span>
            {system ? (
              <Badge
                tone={system.paused ? "amber" : "emerald"}
                dot
                pulse={!system.paused}
              >
                {system.paused ? "Paused" : "Running"}
              </Badge>
            ) : (
              <Badge tone="slate" dot>
                connecting
              </Badge>
            )}
          </div>
          <dl className="mt-3 space-y-1.5 text-[11px]">
            <div className="flex items-center justify-between gap-2">
              <dt className="text-slate-600">Mode</dt>
              <dd
                className={cn(
                  "font-semibold uppercase",
                  system?.mode === "LIVE" ? "text-rose-300" : "text-sky-300",
                )}
              >
                {system?.mode ?? "—"}
              </dd>
            </div>
            <div className="flex items-center justify-between gap-2">
              <dt className="text-slate-600">Risk / trade</dt>
              <dd className="num text-slate-300">{system ? fmtPct(system.risk_pct) : "—"}</dd>
            </div>
            <div className="flex items-center justify-between gap-2">
              <dt className="text-slate-600">Scan interval</dt>
              <dd className="num text-slate-300">
                {system ? `${system.scan_interval_seconds}s` : "—"}
              </dd>
            </div>
            <div className="flex items-center justify-between gap-2">
              <dt className="text-slate-600">Last job</dt>
              <dd className="truncate text-slate-400" title={lastJob?.job_name}>
                {lastJob ? timeAgo(lastJob.started_at) : "—"}
              </dd>
            </div>
          </dl>
        </div>

        <div className="flex items-center justify-between px-1 text-[10px] text-slate-600">
          <a href="/" className="transition hover:text-slate-400">
            Classic dashboard
          </a>
          <a href="/docs" className="inline-flex items-center gap-1 transition hover:text-slate-400">
            API <ExternalLink className="h-2.5 w-2.5" />
          </a>
        </div>
        <p className="px-1 text-[9px] leading-4 text-slate-700">
          Paper first. Backtest, then smallest size. No system is guaranteed to profit.
        </p>
      </div>
    </div>
  );
}

export function AppShell() {
  const navigate = useNavigate();
  const location = useLocation();
  const toast = useToast();
  const { user, logout, required } = useAuth();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [userOpen, setUserOpen] = useState(false);
  const [busyAction, setBusyAction] = useState<"pause" | "scan" | null>(null);
  const userMenuRef = useRef<HTMLDivElement | null>(null);

  const { data: system, refresh, lastUpdated } = usePolling<SystemInfo>(
    () => apiGet("/api/v1/system"),
    30_000,
  );

  const current = allNav.find((item) =>
    item.end ? location.pathname === item.to : location.pathname.startsWith(item.to),
  );

  useEffect(() => {
    setMobileOpen(false);
    setUserOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    if (!userOpen) return;
    const onClick = (event: MouseEvent) => {
      if (!userMenuRef.current?.contains(event.target as Node)) setUserOpen(false);
    };
    window.addEventListener("mousedown", onClick);
    return () => window.removeEventListener("mousedown", onClick);
  }, [userOpen]);

  const togglePause = async () => {
    const paused = Boolean(system?.paused);
    setBusyAction("pause");
    try {
      const response = await apiPost<ActionResponse>(
        paused ? "/api/v1/actions/resume" : "/api/v1/actions/pause",
      );
      toast.success(paused ? "Engine resumed" : "Engine paused", response.message);
      await refresh(true);
    } catch (cause) {
      toast.error("Engine action failed", errorMessage(cause));
    } finally {
      setBusyAction(null);
    }
  };

  const scanNow = async () => {
    setBusyAction("scan");
    try {
      const response = await apiPost<ScanTriggerResult>("/api/v1/jobs/scan");
      if (response.status === "skipped") {
        toast.info("Scan skipped", response.result.reason || "The engine is busy.");
      } else {
        toast.success(
          "Scan complete",
          `Evaluated ${response.result.evaluated ?? 0} · opened ${response.result.opened ?? 0} · closed ${response.result.closed ?? 0}`,
        );
      }
      await refresh(true);
    } catch (cause) {
      toast.error("Scan failed", errorMessage(cause));
    } finally {
      setBusyAction(null);
    }
  };

  const handleLogout = async () => {
    await logout();
    navigate("/login", { replace: true });
  };

  const initials = (user?.username || "MM")
    .split(/[\s_.-]+/)
    .slice(0, 2)
    .map((part) => part.charAt(0).toUpperCase())
    .join("");

  return (
    <div className="app-background min-h-screen">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-[264px] border-r border-slate-800/60 bg-[#070b12]/90 backdrop-blur-xl lg:block">
        <SidebarContent />
      </aside>

      {mobileOpen ? (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button
            type="button"
            className="absolute inset-0 bg-slate-950/70 backdrop-blur-sm"
            aria-label="Close navigation"
            onClick={() => setMobileOpen(false)}
          />
          <div className="drawer-enter relative h-full w-[280px] border-r border-slate-800/70 bg-[#070b12] shadow-2xl">
            <button
              type="button"
              onClick={() => setMobileOpen(false)}
              className="absolute right-3 top-4 z-10 rounded-lg p-2 text-slate-500 hover:bg-white/5 hover:text-white"
              aria-label="Close menu"
            >
              <X className="h-4 w-4" />
            </button>
            <SidebarContent onNavigate={() => setMobileOpen(false)} />
          </div>
        </div>
      ) : null}

      <div className="lg:pl-[264px]">
        <header className="sticky top-0 z-20 border-b border-slate-800/60 bg-[#070b12]/80 backdrop-blur-xl">
          <div className="flex h-16 items-center gap-3 px-4 sm:px-6">
            <button
              type="button"
              onClick={() => setMobileOpen(true)}
              className="rounded-lg border border-slate-800 bg-slate-900/60 p-2 text-slate-400 transition hover:text-white lg:hidden"
              aria-label="Open navigation"
            >
              <Menu className="h-4 w-4" />
            </button>

            <div className="min-w-0">
              <p className="text-[9px] font-semibold uppercase tracking-[0.2em] text-slate-600">
                Workspace
              </p>
              <h2 className="truncate text-sm font-semibold text-white">
                {current?.label ?? "Money Machine"}
              </h2>
            </div>

            <div className="ml-auto flex items-center gap-2 sm:gap-2.5">
              {system ? (
                <div className="hidden md:block">
                  <ModeBadge mode={system.mode} paused={system.paused} />
                </div>
              ) : null}

              <div className="hidden items-center gap-2 sm:flex">
                <Button
                  size="sm"
                  variant="ghost"
                  icon={busyAction === "scan" ? RefreshCw : Sparkles}
                  loading={busyAction === "scan"}
                  onClick={scanNow}
                  disabled={busyAction !== null}
                  className="border border-slate-800 bg-slate-900/40"
                >
                  Scan now
                </Button>
                <Button
                  size="sm"
                  variant={system?.paused ? "primary" : "outline"}
                  icon={system?.paused ? Play : Pause}
                  loading={busyAction === "pause"}
                  onClick={togglePause}
                  disabled={busyAction !== null || !system}
                >
                  {system?.paused ? "Resume" : "Pause"}
                </Button>
              </div>

              <div className="relative" ref={userMenuRef}>
                <button
                  type="button"
                  onClick={() => setUserOpen((value) => !value)}
                  className="flex items-center gap-2 rounded-xl border border-slate-800 bg-slate-900/50 py-1.5 pl-1.5 pr-2 text-left transition hover:border-slate-700"
                  aria-label="Account menu"
                  aria-expanded={userOpen}
                >
                  <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-emerald-400/15 text-[10px] font-bold text-emerald-300">
                    {initials || "MM"}
                  </span>
                  <span className="hidden max-w-[120px] sm:block">
                    <span className="block truncate text-[11px] font-semibold text-slate-200">
                      {user?.username ?? "Operator"}
                    </span>
                    <span className="block text-[9px] uppercase tracking-[0.12em] text-slate-600">
                      {system?.environment ?? "local"}
                    </span>
                  </span>
                  <ChevronDown className="h-3.5 w-3.5 text-slate-500" />
                </button>

                {userOpen ? (
                  <div className="menu-enter absolute right-0 mt-2 w-64 overflow-hidden rounded-xl border border-slate-700/70 bg-[#0b1322] shadow-2xl shadow-black/60">
                    <div className="border-b border-slate-800/70 px-4 py-3">
                      <p className="text-sm font-semibold text-white">{user?.username ?? "Operator"}</p>
                      <p className="mt-0.5 text-[11px] text-slate-500">
                        {user?.email || (user?.telegramLinked ? "Telegram linked" : "Dashboard session")}
                      </p>
                      <div className="mt-2 flex items-center gap-1.5">
                        <Badge tone={required ? "emerald" : "amber"}>
                          {required ? "Authenticated" : "Auth disabled"}
                        </Badge>
                        {user?.method ? (
                          <span className="text-[9px] uppercase tracking-[0.1em] text-slate-600">
                            {user.method.replace(/_/g, " ")}
                          </span>
                        ) : null}
                      </div>
                    </div>
                    <div className="p-1.5">
                      <button
                        type="button"
                        onClick={() => navigate("/settings")}
                        className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-xs text-slate-300 transition hover:bg-white/5 hover:text-white"
                      >
                        <Settings className="h-3.5 w-3.5 text-slate-500" /> Settings
                      </button>
                      <a
                        href="/"
                        className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-xs text-slate-300 transition hover:bg-white/5 hover:text-white"
                      >
                        <LayoutDashboard className="h-3.5 w-3.5 text-slate-500" /> Classic dashboard
                      </a>
                      <a
                        href="/docs"
                        className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-xs text-slate-300 transition hover:bg-white/5 hover:text-white"
                      >
                        <Server className="h-3.5 w-3.5 text-slate-500" /> API docs
                      </a>
                      {required ? (
                        <button
                          type="button"
                          onClick={handleLogout}
                          className="mt-1 flex w-full items-center gap-2 rounded-lg border-t border-slate-800/70 px-3 py-2 text-xs text-rose-300 transition hover:bg-rose-500/10"
                        >
                          <LogOut className="h-3.5 w-3.5" /> Sign out
                        </button>
                      ) : null}
                    </div>
                  </div>
                ) : null}
              </div>
            </div>
          </div>

          <div className="flex items-center justify-between border-t border-slate-800/40 px-4 py-2 sm:px-6">
            <div className="flex items-center gap-2">
              <span
                className={cn(
                  "h-1.5 w-1.5 rounded-full",
                  system?.paused ? "bg-amber-400" : "bg-emerald-400",
                  system?.paused ? "" : "animate-pulse",
                )}
              />
              <span className="text-[10px] font-medium uppercase tracking-[0.14em] text-slate-600">
                {system
                  ? system.paused
                    ? "Entries paused · positions still managed"
                    : `Engine scanning every ${system.scan_interval_seconds}s`
                  : "Connecting to engine"}
              </span>
            </div>
            <div className="flex items-center gap-3">
              <SyncLabel updatedAt={lastUpdated} />
              {system?.mode === "LIVE" ? (
                <span className="hidden items-center gap-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-rose-300 sm:flex">
                  <ShieldAlert className="h-3 w-3" /> Real orders
                </span>
              ) : null}
            </div>
          </div>
        </header>

        <main className="mx-auto w-full max-w-[1680px] px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
          <Outlet />
          <footer className="mt-10 flex flex-col gap-2 border-t border-slate-800/50 pt-5 text-[10px] text-slate-600 sm:flex-row sm:items-center sm:justify-between">
            <p>Money Machine · multi-timeframe SMC engine · paper trading by default</p>
            <p>Trading involves substantial risk. Past performance does not guarantee future results.</p>
          </footer>
        </main>
      </div>
    </div>
  );
}
