import { useNavigate } from "react-router-dom";
import {
  Activity,
  ArrowUpRight,
  Clock,
  Database,
  ExternalLink,
  Gauge,
  KeyRound,
  Layers,
  ListChecks,
  RefreshCw,
  Server,
  ShieldCheck,
  Terminal,
  TriangleAlert,
  Wifi,
} from "lucide-react";
import { apiGet, errorMessage } from "../lib/api";
import { fmtDuration, fmtMoney, fmtPct, fmtSignedMoney, fmtUptime, humanize } from "../lib/format";
import { useDocumentTitle, usePolling } from "../lib/hooks";
import type { JobRun, Metrics, SystemInfo } from "../lib/types";
import { JobsTable } from "../components/tables";
import {
  AlertBanner,
  Badge,
  Button,
  Card,
  CardHeader,
  ErrorState,
  KeyValue,
  PageHeader,
  PageSkeleton,
  StatCard,
  SyncLabel,
} from "../components/ui";

export function DiagnosticsPage() {
  useDocumentTitle("Diagnostics");
  const navigate = useNavigate();
  const { data, error, loading, lastUpdated, refresh } = usePolling<{
    system: SystemInfo;
    metrics: Metrics;
    jobs: JobRun[];
  }>(async () => {
    const [system, metrics, jobs] = await Promise.all([
      apiGet<SystemInfo>("/api/v1/system"),
      apiGet<Metrics>("/api/v1/metrics"),
      apiGet<{ jobs: JobRun[] }>("/api/v1/jobs?limit=10"),
    ]);
    return { system, metrics, jobs: jobs.jobs ?? [] };
  }, 15_000);

  if (loading && !data) return <PageSkeleton cards={6} rows={8} />;
  if (error && !data) return <ErrorState message={error} retry={() => void refresh()} />;
  if (!data) return <ErrorState message="No diagnostics returned." retry={() => void refresh()} />;

  const { system, metrics, jobs } = data;
  const healthy = metrics.scheduler_running;
  const errorJobs = metrics.jobs_errors_24h + metrics.bot_errors_24h;

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow={
          <>
            <Server className="h-3 w-3" /> Operations
          </>
        }
        title="Diagnostics"
        description="Scheduler heartbeat, job history, runtime counters and environment capabilities."
        actions={
          <>
            <SyncLabel updatedAt={lastUpdated} loading={loading} />
            <Button variant="secondary" size="sm" icon={RefreshCw} onClick={() => void refresh()}>
              Refresh
            </Button>
            <a
              href="/docs"
              className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-slate-800 px-2.5 text-xs font-semibold text-slate-300 transition hover:border-slate-700 hover:bg-white/[0.03] hover:text-white"
            >
              <Terminal className="h-3.5 w-3.5" /> API docs <ExternalLink className="h-3 w-3" />
            </a>
          </>
        }
      />

      {error ? (
        <AlertBanner tone="rose" title="Diagnostics refresh failed">
          {error}
        </AlertBanner>
      ) : null}

      <Card className="overflow-hidden">
        <div className="flex flex-col gap-4 p-5 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-start gap-4">
            <span
              className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl border ${
                healthy
                  ? "border-emerald-500/25 bg-emerald-500/10 text-emerald-400"
                  : "border-rose-500/25 bg-rose-500/10 text-rose-400"
              }`}
            >
              {healthy ? <ShieldCheck className="h-5 w-5" /> : <TriangleAlert className="h-5 w-5" />}
            </span>
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="text-base font-semibold text-white">
                  {healthy ? "Engine services are healthy" : "Scheduler is not running"}
                </h2>
                <Badge tone={healthy ? "emerald" : "rose"} dot pulse={healthy}>
                  {healthy ? "Operational" : "Attention"}
                </Badge>
              </div>
              <p className="mt-1 max-w-2xl text-xs leading-5 text-slate-500">
                {healthy
                  ? `Scheduler active · database ${system.database} · version ${system.version} · ${system.environment}.`
                  : "Scheduled scans and position management are not running. Restart the app and inspect the server logs."}
              </p>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <Button variant="secondary" size="sm" icon={RefreshCw} onClick={() => void refresh()}>
              Re-check
            </Button>
            <Button variant="ghost" size="sm" icon={Gauge} onClick={() => navigate("/settings")}>
              Settings
            </Button>
          </div>
        </div>
      </Card>

      <section className="grid grid-cols-2 gap-3 lg:grid-cols-3 xl:grid-cols-6">
        <StatCard
          label="Scheduler"
          value={metrics.scheduler_running ? "Running" : "Stopped"}
          hint="APScheduler state"
          icon={Activity}
          tone={metrics.scheduler_running ? "emerald" : "rose"}
        />
        <StatCard
          label="Uptime"
          value={fmtUptime(metrics.uptime_seconds)}
          hint={metrics.version}
          icon={Clock}
          tone="sky"
        />
        <StatCard
          label="Equity"
          value={fmtMoney(metrics.equity)}
          hint={`${fmtMoney(metrics.balance)} balance`}
          icon={Layers}
          tone="emerald"
        />
        <StatCard
          label="Open P&L"
          value={fmtSignedMoney(metrics.open_pnl)}
          hint={`${metrics.trades_open} open · ${metrics.trades_closed} closed`}
          icon={Gauge}
          tone={metrics.open_pnl >= 0 ? "emerald" : "rose"}
        />
        <StatCard
          label="Signals 24h"
          value={metrics.signals_24h}
          hint={`${metrics.trades_total} total trades`}
          icon={Wifi}
          tone="violet"
        />
        <StatCard
          label="Errors 24h"
          value={errorJobs}
          hint={`${metrics.jobs_errors_24h} job · ${metrics.bot_errors_24h} bot`}
          icon={TriangleAlert}
          tone={errorJobs > 0 ? "rose" : "emerald"}
        />
      </section>

      <section className="grid gap-3 xl:grid-cols-3">
        <Card>
          <CardHeader
            title="Services & environment"
            description="Capabilities resolved at process start."
            icon={Server}
            action={<Badge tone={healthy ? "emerald" : "rose"}>{metrics.environment}</Badge>}
          />
          <div className="px-4 py-2">
            <KeyValue label="App version" value={system.version} />
            <KeyValue label="Environment" value={system.environment} />
            <KeyValue label="Database" value={system.database} icon={Database} />
            <KeyValue label="Dashboard auth" value={system.dashboard_auth ? "Enabled" : "Disabled"} icon={ShieldCheck} />
            <KeyValue label="API token auth" value={system.api_token_configured ? "Configured" : "Not configured"} icon={KeyRound} />
            <KeyValue label="MEXC credentials" value={system.mexc_configured ? "Configured" : "Missing"} />
            <KeyValue label="Telegram bot" value={system.telegram_configured ? "Configured" : "Missing"} />
          </div>
        </Card>

        <Card>
          <CardHeader
            title="Runtime counters"
            description="Snapshot from the shared journal."
            icon={Activity}
            action={<Badge tone={metrics.paused ? "amber" : "emerald"} dot>{metrics.paused ? "Paused" : "Active"}</Badge>}
          />
          <div className="px-4 py-2">
            <KeyValue label="Mode" value={humanize(metrics.mode)} />
            <KeyValue label="Equity" value={fmtMoney(metrics.equity)} />
            <KeyValue label="Balance" value={fmtMoney(metrics.balance)} />
            <KeyValue label="Open P&L" value={fmtSignedMoney(metrics.open_pnl)} />
            <KeyValue label="Trades total" value={metrics.trades_total} />
            <KeyValue label="Trades open / closed" value={`${metrics.trades_open} / ${metrics.trades_closed}`} />
            <KeyValue label="Signals 24h" value={metrics.signals_24h} />
            <KeyValue label="Job runs total" value={metrics.jobs_total} />
          </div>
        </Card>

        <Card>
          <CardHeader
            title="Cadence & limits"
            description="Loop timings and risk defaults."
            icon={Gauge}
          />
          <div className="px-4 py-2">
            <KeyValue label="Scan interval" value={`${system.scan_interval_seconds}s`} />
            <KeyValue label="SSE interval" value={`${system.sse_interval_seconds}s`} />
            <KeyValue label="WS interval" value={`${system.ws_interval_seconds}s`} />
            <KeyValue label="Risk / trade" value={fmtPct(system.risk_pct)} />
            <KeyValue label="Live allowed" value={system.live_allowed ? "Yes" : "No"} />
            <KeyValue label="Job errors 24h" value={metrics.jobs_errors_24h} />
            <KeyValue label="Bot errors 24h" value={metrics.bot_errors_24h} />
          </div>
          <div className="border-t border-slate-800/60 px-4 py-3">
            <p className="text-[10px] uppercase tracking-[0.12em] text-slate-600">Configured symbols</p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {system.symbols.length ? (
                system.symbols.map((symbol) => (
                  <Badge key={symbol} tone="slate">
                    {symbol}
                  </Badge>
                ))
              ) : (
                <span className="text-[11px] text-slate-600">None configured</span>
              )}
            </div>
          </div>
        </Card>
      </section>

      <Card>
        <CardHeader
          title="Job history"
          description="Latest scheduler runs with duration, attempts and messages."
          icon={ListChecks}
          action={<Badge tone="slate">{jobs.length} recent</Badge>}
        />
        <JobsTable jobs={jobs} />
        {jobs.length ? (
          <div className="flex flex-wrap items-center justify-between gap-2 border-t border-slate-800/60 px-4 py-3 text-[10px] text-slate-600 sm:px-5">
            <span>
              Last run {jobs[0]?.job_name.replace(/_/g, " ")} · {fmtDuration(jobs[0]?.duration_seconds)}
            </span>
            <span>Scheduled runs are recorded automatically.</span>
          </div>
        ) : null}
      </Card>

      <section className="grid gap-3 lg:grid-cols-2">
        <Card>
          <CardHeader title="Useful endpoints" description="Same-origin references for operators." icon={Terminal} />
          <div className="grid gap-2 p-4 sm:grid-cols-2">
            {[
              { href: "/docs", label: "Swagger API docs", note: "Interactive OpenAPI" },
              { href: "/health", label: "Health check", note: "Database + scheduler" },
              { href: "/metrics", label: "Raw metrics", note: "Liveness counters" },
              { href: "/api/v1/status", label: "Status JSON", note: "Account status" },
              { href: "/api/v1/system", label: "System JSON", note: "Config snapshot" },
              { href: "/advanced", label: "Legacy command center", note: "Jinja dashboard" },
            ].map((link) => (
              <a
                key={link.href}
                href={link.href}
                className="group flex items-center justify-between gap-2 rounded-xl border border-slate-800/60 bg-slate-950/30 px-3 py-2.5 transition hover:border-slate-700 hover:bg-white/[0.025]"
              >
                <div>
                  <p className="text-xs font-semibold text-slate-200">{link.label}</p>
                  <p className="mt-0.5 text-[10px] text-slate-600">{link.note}</p>
                </div>
                <ArrowUpRight className="h-3.5 w-3.5 text-slate-600 transition group-hover:text-slate-300" />
              </a>
            ))}
          </div>
        </Card>

        <Card>
          <CardHeader title="Operational notes" description="What to inspect when something looks wrong." icon={ShieldCheck} />
          <div className="space-y-3 p-4">
            {[
              {
                title: "No fresh trades",
                body: "Check Signals → Scan history. If scans are fresh but scores are below threshold, the engine is working as designed.",
              },
              {
                title: "Scheduler stopped",
                body: "The API can still serve data, but scans and trailing management stop. Restart the process and check server logs.",
              },
              {
                title: "Clock drift",
                body: "Session windows and candle timestamps use UTC. Keep the host clock synchronized.",
              },
              {
                title: "Kill switch",
                body: "Available on Overview and Settings. It closes positions at market and pauses entries immediately.",
              },
            ].map((note) => (
              <div key={note.title} className="rounded-xl border border-slate-800/60 bg-slate-950/30 px-3.5 py-3">
                <p className="text-xs font-semibold text-slate-200">{note.title}</p>
                <p className="mt-1 text-[11px] leading-5 text-slate-500">{note.body}</p>
              </div>
            ))}
          </div>
        </Card>
      </section>
    </div>
  );
}
