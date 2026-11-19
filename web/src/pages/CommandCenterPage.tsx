import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Activity,
  ArrowRight,
  ChartCandlestick,
  CircleDollarSign,
  Gauge,
  Pause,
  Play,
  RefreshCw,
  Sparkles,
  TrendingUp,
  Wifi,
  WifiOff,
  Zap as ZapIcon,
} from "lucide-react";
import { apiGet, apiPost, errorMessage } from "../lib/api";
import {
  cn,
  compactStatus,
  compactTrend,
  fmtMoney,
  fmtPct,
  fmtPrice,
  fmtSignedMoney,
  fmtTime,
  pnlTone,
} from "../lib/format";
import { useDocumentTitle, usePolling } from "../lib/hooks";
import type {
  ActionResponse,
  CandlesResponse,
  Candle,
  DashboardSnapshot,
  EquitySeries,
  JobRun,
  Metrics,
  ScanTriggerResult,
} from "../lib/types";
import { useToast } from "../context/toast";
import { AllocationDonut, CandleChart, EquityChart } from "../components/charts";
import {
  JobsTable,
  type MarketRow,
  MarketsTable,
  type PositionRow,
  PositionsTable,
} from "../components/tables";
import {
  AlertBanner,
  Badge,
  Button,
  Card,
  CardHeader,
  EmptyState,
  ErrorState,
  MiniStat,
  PageHeader,
  PageSkeleton,
  ScoreBar,
  Select,
  SideBadge,
  StatCard,
  StatusBadge,
  SyncLabel,
} from "../components/ui";

type StreamStatus = "connecting" | "live" | "offline";

const TIMEFRAMES = ["5m", "15m", "30m", "1h", "4h", "1d"];

export function CommandCenterPage() {
  useDocumentTitle("Command Center");
  const toast = useToast();
  const navigate = useNavigate();

  const [snapshot, setSnapshot] = useState<DashboardSnapshot | null>(null);
  const [initialLoading, setInitialLoading] = useState(true);
  const [snapshotError, setSnapshotError] = useState<string | null>(null);
  const [streamStatus, setStreamStatus] = useState<StreamStatus>("connecting");
  const [streamUpdatedAt, setStreamUpdatedAt] = useState<Date | null>(null);
  const [busy, setBusy] = useState<"scan" | "pause" | null>(null);

  const [symbol, setSymbol] = useState("");
  const [timeframe, setTimeframe] = useState("15m");
  const [candles, setCandles] = useState<Candle[]>([]);
  const [candlesLoading, setCandlesLoading] = useState(false);
  const [candlesError, setCandlesError] = useState<string | null>(null);

  const lastEventRef = useRef(0);

  const loadSnapshot = useCallback(async () => {
    try {
      const data = await apiGet<DashboardSnapshot>("/api/advanced/dashboard-snapshot");
      setSnapshot(data);
      setSnapshotError(null);
      setStreamUpdatedAt(new Date());
      setInitialLoading(false);
      return data;
    } catch (cause) {
      setSnapshotError(errorMessage(cause));
      setInitialLoading(false);
      return null;
    }
  }, []);

  const { data: equity, refresh: refreshEquity } = usePolling<EquitySeries>(
    () => apiGet("/api/advanced/equity?limit=800"),
    30_000,
  );

  const { data: operations, refresh: refreshOperations } = usePolling<{
    jobs: JobRun[];
    metrics: Metrics;
  }>(async () => {
    const [jobs, metrics] = await Promise.all([
      apiGet<{ jobs: JobRun[] }>("/api/v1/jobs?limit=8"),
      apiGet<Metrics>("/api/v1/metrics"),
    ]);
    return { jobs: jobs.jobs ?? [], metrics };
  }, 20_000);

  useEffect(() => {
    void loadSnapshot();

    let disposed = false;
    let source: EventSource | null = null;

    try {
      source = new EventSource("/api/advanced/stream");
      source.addEventListener("open", () => {
        if (!disposed) setStreamStatus("live");
      });
      source.addEventListener("snapshot", (event) => {
        if (disposed) return;
        try {
          const payload = JSON.parse((event as MessageEvent).data) as DashboardSnapshot;
          lastEventRef.current = Date.now();
          setSnapshot(payload);
          setSnapshotError(null);
          setStreamStatus("live");
          setStreamUpdatedAt(new Date());
          setInitialLoading(false);
        } catch {
          // Ignore malformed snapshots; the next event will replace the view.
        }
      });
      source.addEventListener("error", () => {
        if (!disposed) setStreamStatus("offline");
      });
    } catch {
      setStreamStatus("offline");
    }

    const fallback = window.setInterval(() => {
      if (Date.now() - lastEventRef.current > 15_000) {
        void loadSnapshot();
      }
    }, 12_000);

    return () => {
      disposed = true;
      window.clearInterval(fallback);
      source?.close();
    };
  }, [loadSnapshot]);

  useEffect(() => {
    if (!snapshot) return;
    if (!symbol) {
      setSymbol(snapshot.overview.symbols[0] || "BTC/USDT");
      setTimeframe(snapshot.overview.entry_timeframe || "15m");
    }
  }, [snapshot, symbol]);

  useEffect(() => {
    if (!symbol) return;
    let active = true;
    const controller = new AbortController();

    const load = async () => {
      setCandlesLoading(true);
      try {
        const response = await apiGet<CandlesResponse>(
          `/api/advanced/candles?symbol=${encodeURIComponent(symbol)}&timeframe=${timeframe}&limit=180`,
          { signal: controller.signal },
        );
        if (!active) return;
        setCandles(response.candles ?? []);
        setCandlesError(null);
      } catch (cause) {
        if (!active) return;
        setCandlesError(errorMessage(cause));
      } finally {
        if (active) setCandlesLoading(false);
      }
    };

    void load();
    const timer = window.setInterval(() => void load(), 30_000);
    return () => {
      active = false;
      controller.abort();
      window.clearInterval(timer);
    };
  }, [symbol, timeframe]);

  const scanNow = async () => {
    setBusy("scan");
    try {
      const response = await apiPost<ScanTriggerResult>("/api/v1/jobs/scan");
      if (response.status === "skipped") {
        toast.info("Scan skipped", response.result.reason || "Another scan is already running.");
      } else {
        toast.success(
          "Scan complete",
          `Evaluated ${response.result.evaluated ?? 0} · opened ${response.result.opened ?? 0} · closed ${response.result.closed ?? 0}`,
        );
      }
      await Promise.all([loadSnapshot(), refreshEquity(), refreshOperations()]);
    } catch (cause) {
      toast.error("Scan failed", errorMessage(cause));
    } finally {
      setBusy(null);
    }
  };

  const togglePause = async () => {
    if (!snapshot) return;
    const paused = snapshot.overview.paused;
    setBusy("pause");
    try {
      const response = await apiPost<ActionResponse>(
        paused ? "/api/v1/actions/resume" : "/api/v1/actions/pause",
      );
      toast.success(paused ? "Engine resumed" : "Engine paused", response.message);
      await loadSnapshot();
    } catch (cause) {
      toast.error("Engine action failed", errorMessage(cause));
    } finally {
      setBusy(null);
    }
  };

  const markets: MarketRow[] = useMemo(
    () =>
      (snapshot?.markets ?? []).map((market) => ({
        symbol: market.symbol,
        price: market.price,
        trend: market.trend,
        structure: market.structure,
        score: market.score,
        status: market.status,
        updatedAt: market.updated_at,
      })),
    [snapshot],
  );

  const positions: PositionRow[] = useMemo(
    () =>
      (snapshot?.positions ?? []).map((position) => ({
        id: position.id,
        symbol: position.symbol,
        side: position.side === "BUY" ? "long" : "short",
        qty: position.qty,
        entry: position.entry,
        current: position.current,
        stop: position.sl,
        takeProfit: position.tp,
        pnl: position.pnl,
        risk: position.risk,
        mode: position.mode.toLowerCase(),
        openedAt: position.opened_at,
      })),
    [snapshot],
  );

  if (initialLoading && !snapshot) return <PageSkeleton cards={4} />;
  if (!snapshot && snapshotError) {
    return <ErrorState message={snapshotError} retry={() => void loadSnapshot()} />;
  }
  if (!snapshot) return <ErrorState message="No dashboard snapshot returned." retry={() => void loadSnapshot()} />;

  const overview = snapshot.overview;
  const statusTone = streamStatus === "live" ? "emerald" : streamStatus === "offline" ? "rose" : "amber";

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow={
          <>
            <Activity className="h-3 w-3" /> Live workspace
          </>
        }
        title="Command Center"
        description="Streaming engine state, MEXC candles, allocation and operations in one view."
        actions={
          <>
            <Badge tone={statusTone} dot pulse={streamStatus === "live"}>
              {streamStatus === "live" ? "SSE live" : streamStatus === "offline" ? "Polling fallback" : "Connecting"}
            </Badge>
            <SyncLabel updatedAt={streamUpdatedAt} label="Stream" />
            <Button
              variant="secondary"
              size="sm"
              icon={RefreshCw}
              onClick={() => {
                void loadSnapshot();
                void refreshEquity();
                void refreshOperations();
              }}
            >
              Refresh
            </Button>
            <Button
              variant="secondary"
              size="sm"
              icon={Sparkles}
              loading={busy === "scan"}
              disabled={busy !== null}
              onClick={scanNow}
            >
              Scan now
            </Button>
            <Button
              variant={overview.paused ? "primary" : "outline"}
              size="sm"
              icon={overview.paused ? Play : Pause}
              loading={busy === "pause"}
              disabled={busy !== null}
              onClick={togglePause}
            >
              {overview.paused ? "Resume" : "Pause"}
            </Button>
          </>
        }
      />

      {snapshotError ? <AlertBanner tone="rose" title="Live refresh failed">{snapshotError}</AlertBanner> : null}
      {!overview.paused && overview.mode === "LIVE" ? (
        <AlertBanner tone="rose" title="Live execution is running">
          The engine can open real MEXC positions while this indicator is visible.
        </AlertBanner>
      ) : null}

      <section className="grid grid-cols-2 gap-3 xl:grid-cols-4">
        <StatCard
          label="Account balance"
          value={fmtMoney(overview.balance)}
          hint="Realized balance"
          icon={CircleDollarSign}
          tone="sky"
        />
        <StatCard
          label="Equity"
          value={fmtMoney(overview.equity)}
          hint="Includes unrealized P&L"
          icon={TrendingUp}
          tone="emerald"
        />
        <StatCard
          label="Daily P&L"
          value={fmtSignedMoney(overview.daily_pnl)}
          hint={`${overview.daily_pnl_pct >= 0 ? "+" : ""}${overview.daily_pnl_pct.toFixed(2)}% realized`}
          icon={TrendingUp}
          tone={pnlTone(overview.daily_pnl)}
          trend={overview.daily_pnl > 0 ? "up" : overview.daily_pnl < 0 ? "down" : "flat"}
        />
        <StatCard
          label="Win rate"
          value={`${overview.win_rate.toFixed(1)}%`}
          hint={
            overview.trades
              ? `${overview.trades} closed · drawdown ${fmtPct(overview.drawdown)}`
              : "No closed trades yet"
          }
          icon={Gauge}
          tone={overview.win_rate >= 50 ? "emerald" : "amber"}
        />
      </section>

      <section className="grid gap-3 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader
            title="Equity performance"
            description="Snapshots from the running engine and realized trade journal."
            icon={TrendingUp}
            action={<Badge tone={overview.mode === "LIVE" ? "rose" : "sky"}>{overview.mode}</Badge>}
          />
          <div className="px-3 pb-4 pt-2 sm:px-4">
            <EquityChart data={equity} height={270} />
          </div>
        </Card>
        <Card>
          <CardHeader
            title="Portfolio allocation"
            description="Open notional exposure plus cash."
            icon={CircleDollarSign}
          />
          <div className="px-4 pb-4 pt-2">
            <AllocationDonut data={snapshot.allocation} height={205} />
          </div>
        </Card>
      </section>

      <section className="grid grid-cols-2 gap-3 xl:grid-cols-4">
        {markets.map((market) => (
          <button
            key={market.symbol}
            type="button"
            onClick={() => setSymbol(market.symbol)}
            className={cn(
              "group rounded-2xl border p-4 text-left transition",
              symbol === market.symbol
                ? "border-emerald-500/35 bg-emerald-500/[0.055]"
                : "border-slate-800/70 bg-[#0a1120]/70 hover:border-slate-700",
            )}
          >
            <div className="flex items-center justify-between gap-2">
              <span className="truncate text-xs font-semibold text-white">{market.symbol}</span>
              <Badge
                tone={
                  market.trend.toLowerCase().includes("bull")
                    ? "emerald"
                    : market.trend.toLowerCase().includes("bear")
                      ? "rose"
                      : "slate"
                }
                title={market.trend}
              >
                {compactTrend(market.trend)}
              </Badge>
            </div>
            <p className="num mt-2 text-lg font-semibold text-slate-100">{fmtPrice(market.price)}</p>
            <div className="mt-2">
              <ScoreBar score={market.score} showLabel />
            </div>
            <p
              className="mt-2 truncate text-[10px] uppercase tracking-[0.1em] text-slate-600"
              title={market.status}
            >
              {compactStatus(market.status)}
            </p>
          </button>
        ))}
      </section>

      <Card>
        <CardHeader
          title="Market chart"
          description="MEXC futures candles with a 20-period EMA overlay and volume."
          icon={ChartCandlestick}
          action={
            <div className="flex items-center gap-2">
              <div className="w-32">
                <Select value={symbol} onChange={(event) => setSymbol(event.target.value)}>
                  {overview.symbols.map((item) => (
                    <option key={item} value={item}>
                      {item}
                    </option>
                  ))}
                </Select>
              </div>
              <div className="w-24">
                <Select
                  value={timeframe}
                  onChange={(event) => setTimeframe(event.target.value)}
                >
                  {TIMEFRAMES.map((item) => (
                    <option key={item} value={item}>
                      {item}
                    </option>
                  ))}
                </Select>
              </div>
            </div>
          }
        />
        <div className="px-3 pb-4 pt-3 sm:px-5">
          <CandleChart
            candles={candles}
            loading={candlesLoading}
            error={candlesError}
            height={360}
          />
          <div className="mt-3 flex flex-wrap items-center gap-4 text-[10px] uppercase tracking-[0.12em] text-slate-600">
            <span className="inline-flex items-center gap-1.5">
              <span className="h-1.5 w-4 rounded-full bg-emerald-400" /> Up candle
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="h-1.5 w-4 rounded-full bg-rose-400" /> Down candle
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="h-1.5 w-4 rounded-full bg-sky-400" /> EMA 20
            </span>
            <span className="ml-auto">{candles.length} candles · {timeframe}</span>
          </div>
        </div>
      </Card>

      <section className="grid gap-3 xl:grid-cols-3">
        <div className="min-w-0 space-y-3 xl:col-span-2">
          <Card>
            <CardHeader
              title="Open positions"
              description="Live exposure from the engine's journal."
              icon={CircleDollarSign}
              action={<Badge tone="sky">{positions.length} open</Badge>}
            />
            <PositionsTable rows={positions} />
          </Card>

          <Card>
            <CardHeader
              title="Market watch"
              description="Latest scan result per configured symbol."
              icon={Sparkles}
              action={<Badge tone="slate">{markets.length} instruments</Badge>}
            />
            <MarketsTable rows={markets} />
          </Card>
        </div>

        <div className="min-w-0 space-y-3">
          <Card>
            <CardHeader
              title="Strategy signals"
              description="Latest confluence checks."
              icon={ZapIcon}
              action={
                <Button variant="ghost" size="sm" icon={ArrowRight} onClick={() => navigate("/signals")}>
                  All
                </Button>
              }
            />
            {snapshot.signals.length ? (
              <div className="divide-y divide-slate-800/50">
                {snapshot.signals.slice(0, 7).map((signal, index) => (
                  <div
                    key={`${signal.symbol}-${signal.time}-${index}`}
                    className="flex items-center gap-3 px-4 py-3"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-semibold text-white">{signal.symbol}</span>
                        <SideBadge side={signal.side} />
                      </div>
                      <p className="mt-0.5 truncate text-[10px] text-slate-500">
                        {signal.strategy} · {signal.tf} · {signal.time}
                      </p>
                    </div>
                    <div className="w-16 shrink-0">
                      <ScoreBar score={signal.confidence} showLabel />
                    </div>
                    <StatusBadge status={signal.status} />
                  </div>
                ))}
              </div>
            ) : (
              <EmptyState title="No signals yet" description="Waiting for a qualified setup." />
            )}
          </Card>

          <Card>
            <CardHeader
              title="Runtime"
              description="Scheduler and API counters."
              icon={Activity}
              action={
                <Badge tone={operations?.metrics.scheduler_running ? "emerald" : "rose"} dot>
                  {operations?.metrics.scheduler_running ? "Online" : "Stopped"}
                </Badge>
              }
            />
            <div className="grid grid-cols-2 gap-2 p-4">
              <MiniStat label="Open P&L" value={fmtSignedMoney(overview.open_pnl)} tone={pnlTone(overview.open_pnl)} />
              <MiniStat label="Open positions" value={overview.open_positions} tone="sky" />
              <MiniStat label="Signals today" value={overview.signals_today} tone="emerald" />
              <MiniStat label="Uptime" value={operations ? `${Math.floor((operations.metrics.uptime_seconds ?? 0) / 60)}m` : "—"} />
              <MiniStat label="Job errors 24h" value={operations?.metrics.jobs_errors_24h ?? "—"} tone={(operations?.metrics.jobs_errors_24h ?? 0) > 0 ? "rose" : "slate"} />
              <MiniStat label="Bot errors 24h" value={operations?.metrics.bot_errors_24h ?? "—"} tone={(operations?.metrics.bot_errors_24h ?? 0) > 0 ? "rose" : "slate"} />
            </div>
            <div className="border-t border-slate-800/60 px-4 py-3">
              <div className="flex items-center justify-between text-[10px] uppercase tracking-[0.12em] text-slate-600">
                <span className="inline-flex items-center gap-1.5">
                  {streamStatus === "live" ? (
                    <Wifi className="h-3 w-3 text-emerald-400" />
                  ) : (
                    <WifiOff className="h-3 w-3 text-rose-400" />
                  )}
                  {streamStatus === "live" ? "Stream connected" : "Stream unavailable"}
                </span>
                <span>{snapshot.server_time ? fmtTime(snapshot.server_time) : ""}</span>
              </div>
            </div>
          </Card>
        </div>
      </section>

      <Card>
        <CardHeader
          title="Recent jobs"
          description="Scheduled scans and reports recorded by the engine."
          icon={Activity}
          action={<Badge tone="slate">{operations?.jobs.length ?? 0} recent</Badge>}
        />
        {operations ? <JobsTable jobs={operations.jobs} /> : null}
      </Card>
    </div>
  );
}
