import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ArrowRight,
  CircleDollarSign,
  Gauge,
  Pause,
  Play,
  RefreshCw,
  ShieldAlert,
  Sparkles,
  Target,
  TrendingUp,
  Wallet,
  Zap,
} from "lucide-react";
import { apiGet, apiPost, errorMessage } from "../lib/api";
import {
  cn,
  compactTrend,
  fmtMoney,
  fmtPct,
  fmtSignedMoney,
  fmtTime,
  pnlTone,
} from "../lib/format";
import { useDocumentTitle, usePolling } from "../lib/hooks";
import type {
  ActionResponse,
  DashboardData,
  ScanTriggerResult,
} from "../lib/types";
import { useToast } from "../context/toast";
import { EquityChart } from "../components/charts";
import {
  type MarketRow,
  type PositionRow,
  type SignalRow,
  LogsList,
  MarketsTable,
  PositionsTable,
  SignalFeed,
} from "../components/tables";
import {
  AlertBanner,
  Badge,
  Button,
  Card,
  CardHeader,
  ConfirmDialog,
  ErrorState,
  KeyValue,
  MiniStat,
  PageHeader,
  PageSkeleton,
  SyncLabel,
  StatCard,
} from "../components/ui";

export function OverviewPage() {
  useDocumentTitle("Overview");
  const navigate = useNavigate();
  const toast = useToast();
  const [busy, setBusy] = useState<"scan" | "pause" | null>(null);
  const [killOpen, setKillOpen] = useState(false);
  const [killBusy, setKillBusy] = useState(false);
  const [pendingClose, setPendingClose] = useState<PositionRow | null>(null);
  const [closingId, setClosingId] = useState<number | null>(null);

  const { data, error, loading, lastUpdated, refresh } = usePolling<DashboardData>(
    () => apiGet("/api/v1/dashboard"),
    15_000,
  );

  const scanNow = async () => {
    setBusy("scan");
    try {
      const response = await apiPost<ScanTriggerResult>("/api/v1/jobs/scan");
      if (response.status === "skipped") {
        toast.info("Scan skipped", response.result.reason || "Another scan is already running.");
      } else {
        toast.success(
          "Scan complete",
          `Evaluated ${response.result.evaluated ?? 0} setups · opened ${response.result.opened ?? 0} · closed ${response.result.closed ?? 0}`,
        );
      }
      await refresh(true);
    } catch (cause) {
      toast.error("Scan failed", errorMessage(cause));
    } finally {
      setBusy(null);
    }
  };

  const togglePause = async () => {
    if (!data) return;
    setBusy("pause");
    try {
      const response = await apiPost<ActionResponse>(
        data.status.paused ? "/api/v1/actions/resume" : "/api/v1/actions/pause",
      );
      toast.success(data.status.paused ? "Engine resumed" : "Engine paused", response.message);
      await refresh(true);
    } catch (cause) {
      toast.error("Engine action failed", errorMessage(cause));
    } finally {
      setBusy(null);
    }
  };

  const engageKill = async () => {
    setKillBusy(true);
    try {
      const response = await apiPost<ActionResponse>("/api/v1/actions/kill");
      toast.success("Kill switch engaged", response.message);
      setKillOpen(false);
      await refresh(true);
    } catch (cause) {
      toast.error("Kill switch failed", errorMessage(cause));
    } finally {
      setKillBusy(false);
    }
  };

  const closePosition = async () => {
    if (!pendingClose) return;
    setClosingId(pendingClose.id);
    try {
      const response = await apiPost<ActionResponse>(
        `/api/v1/actions/trades/${pendingClose.id}/close`,
      );
      toast.success("Position closed", response.message);
      setPendingClose(null);
      await refresh(true);
    } catch (cause) {
      toast.error("Could not close position", errorMessage(cause));
    } finally {
      setClosingId(null);
    }
  };

  if (loading && !data) return <PageSkeleton cards={4} />;
  if (error && !data) return <ErrorState message={error} retry={() => void refresh()} />;
  if (!data) return <ErrorState message="No dashboard data returned." retry={() => void refresh()} />;

  const { status, settings } = data;
  const markets: MarketRow[] = data.scans.map((scan) => ({
    symbol: scan.symbol,
    price: scan.price,
    trend: scan.trend,
    structure: scan.structure,
    score: scan.score,
    status: scan.status,
    reason: scan.reason,
    updatedAt: scan.created_at,
  }));
  const positions: PositionRow[] = data.positions.map((position) => ({
    id: position.id,
    symbol: position.symbol,
    side: position.side,
    qty: position.qty,
    entry: position.entry,
    current: position.current,
    stop: position.stop,
    takeProfit: position.take_profit,
    pnl: position.unrealized,
    pnlPct: position.unrealized_pct,
    risk: position.risk,
    mode: position.mode,
    leverage: position.leverage,
    openedAt: position.opened_at,
  }));
  const signals: SignalRow[] = data.signals.slice(0, 5).map((signal) => ({
    id: signal.id,
    createdAt: signal.created_at,
    symbol: signal.symbol,
    side: signal.side,
    score: signal.score,
    status: signal.status,
    entry: signal.entry,
    stop: signal.stop,
    takeProfit: signal.take_profit,
    rr: signal.rr,
    strategy: `${compactTrend(signal.htf_trend)} · ${signal.structure_timeframe}`,
    timeframe: signal.entry_timeframe,
  }));

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow={
          <>
            <span
              className={cn(
                "h-1.5 w-1.5 rounded-full",
                status.paused ? "bg-amber-400" : "animate-pulse bg-emerald-400",
              )}
            />
            Live command deck
          </>
        }
        title="Trading overview"
        description="Multi-timeframe confluence: 4H trend filter, 1H structure and 15M execution trigger. Paper mode is the default."
        actions={
          <>
            <SyncLabel updatedAt={lastUpdated} loading={loading} />
            <Button
              variant="secondary"
              size="sm"
              icon={RefreshCw}
              loading={busy === "scan"}
              disabled={busy !== null}
              onClick={scanNow}
            >
              Scan now
            </Button>
            <Button
              variant={status.paused ? "primary" : "outline"}
              size="sm"
              icon={status.paused ? Play : Pause}
              loading={busy === "pause"}
              disabled={busy !== null}
              onClick={togglePause}
            >
              {status.paused ? "Resume engine" : "Pause engine"}
            </Button>
            <Button
              variant="danger"
              size="sm"
              icon={ShieldAlert}
              onClick={() => setKillOpen(true)}
            >
              Kill switch
            </Button>
          </>
        }
      />

      {!status.paper_mode ? (
        <AlertBanner
          tone="rose"
          icon={ShieldAlert}
          title="LIVE mode is armed"
          action={
            <Button size="sm" variant="ghost" onClick={() => navigate("/settings")}>
              Review settings
            </Button>
          }
        >
          Real orders are sent to the exchange. Confirm position sizing, leverage and stops
          before resuming entries.
        </AlertBanner>
      ) : null}

      {error ? <AlertBanner tone="rose" title="Refresh failed">{error}</AlertBanner> : null}

      <section className="grid grid-cols-2 gap-3 xl:grid-cols-4">
        <StatCard
          label="Account equity"
          value={fmtMoney(status.equity)}
          hint={`${fmtMoney(status.balance)} realized balance`}
          icon={Wallet}
          tone="emerald"
        />
        <StatCard
          label="Today's P&L"
          value={fmtSignedMoney(status.today_pnl)}
          hint={`${status.today_pnl_pct >= 0 ? "+" : ""}${status.today_pnl_pct.toFixed(2)}% · realized today`}
          icon={TrendingUp}
          tone={pnlTone(status.today_pnl)}
          trend={status.today_pnl > 0 ? "up" : status.today_pnl < 0 ? "down" : "flat"}
        />
        <StatCard
          label="Open P&L"
          value={fmtSignedMoney(status.open_pnl)}
          hint={`${status.open_positions} of ${status.max_open_positions} position slots used`}
          icon={CircleDollarSign}
          tone={pnlTone(status.open_pnl)}
          trend={status.open_pnl > 0 ? "up" : status.open_pnl < 0 ? "down" : "flat"}
        />
        <StatCard
          label="Win rate"
          value={`${status.win_rate.toFixed(1)}%`}
          hint={`${status.wins}W · ${status.losses}L · ${status.trades} closed · PF ${status.profit_factor.toFixed(2)}`}
          icon={Target}
          tone={status.win_rate >= 50 ? "emerald" : "amber"}
        />
      </section>

      <section className="grid gap-3 xl:grid-cols-3">
        <Card className="flex flex-col xl:col-span-2">
          <CardHeader
            title="Equity curve"
            description="Account equity snapshots recorded by the engine, in USDT."
            icon={TrendingUp}
            action={<Badge tone={status.paper_mode ? "sky" : "rose"}>{status.mode} account</Badge>}
          />
          <div className="flex flex-1 flex-col px-3 pb-4 pt-2 sm:px-4">
            <EquityChart data={data.equity} height="100%" className="min-h-[276px] flex-1" />
          </div>
        </Card>

        <Card>
          <CardHeader
            title="Risk guardrails"
            description="Hard limits enforced before every order."
            icon={Gauge}
          />
          <div className="px-4 py-2">
            <KeyValue label="Risk per trade" value={fmtPct(settings.risk_pct)} />
            <KeyValue label="Daily loss stop" value={fmtPct(settings.max_daily_loss_pct)} />
            <KeyValue
              label="Max open positions"
              value={`${status.open_positions} / ${settings.max_open_positions}`}
            />
            <KeyValue label="Leverage cap" value={`${settings.leverage}x`} />
            <KeyValue label="Minimum confluence" value={`${Math.round(settings.min_score)}/100`} />
            <KeyValue label="Session filter" value={settings.session_filter ? "On" : "Off"} />
            <KeyValue label="3-loss cooldown" value="6 hours" />
          </div>
          <div className="px-4 pb-4">
            <div className="rounded-xl border border-slate-800/70 bg-slate-950/40 px-3 py-3 text-[11px] leading-5 text-slate-500">
              One position per market. Stops come from structure plus ATR. Leverage only caps
              notional exposure — it does not multiply risk per trade.
            </div>
            <div className="mt-3 grid grid-cols-2 gap-2">
              <MiniStat label="Avg R" value={status.avg_r.toFixed(2)} />
              <MiniStat label="Max drawdown" value={fmtPct(status.max_drawdown_pct)} tone="rose" />
              <MiniStat label="Signals today" value={status.signals_today} tone="sky" />
              <MiniStat label="Open positions" value={status.open_positions} tone="emerald" />
            </div>
          </div>
        </Card>
      </section>

      <section className="grid gap-3 xl:grid-cols-3">
        <div className="min-w-0 space-y-3 xl:col-span-2">
          <Card>
            <CardHeader
              title="Open positions"
              description="Live exposure managed by the engine."
              icon={CircleDollarSign}
              action={
                <div className="flex items-center gap-2">
                  <Badge tone="sky">{positions.length} open</Badge>
                  <Button
                    variant="ghost"
                    size="sm"
                    icon={ArrowRight}
                    onClick={() => navigate("/trades?status=open")}
                  >
                    Journal
                  </Button>
                </div>
              }
            />
            <PositionsTable
              rows={positions}
              onClose={(row) => setPendingClose(row)}
              closingId={closingId}
            />
          </Card>

          <Card>
            <CardHeader
              title="Market scanner"
              description="Latest evaluation per configured symbol."
              icon={Sparkles}
              action={<Badge tone="slate">{markets.length} instruments</Badge>}
            />
            <MarketsTable rows={markets} />
          </Card>
        </div>

        <div className="min-w-0 space-y-3">
          <Card>
            <CardHeader
              title="Recent signals"
              description="Confluence checks, executed or rejected."
              icon={Zap}
              action={
                <Button variant="ghost" size="sm" icon={ArrowRight} onClick={() => navigate("/signals")}>
                  All
                </Button>
              }
            />
            <SignalFeed rows={signals} onSelect={() => navigate("/signals")} />
          </Card>

          <Card>
            <CardHeader
              title="Engine activity"
              description="Scans, fills, errors and risk events."
              icon={RefreshCw}
              action={<Badge tone="slate">log</Badge>}
            />
            <LogsList logs={data.logs.slice(0, 5)} />
          </Card>
        </div>
      </section>

      <ConfirmDialog
        open={killOpen}
        title="Engage the kill switch?"
        message="Every open position will be closed at market and the engine will pause. This cannot be undone from the dashboard."
        confirmLabel="Close all & pause"
        loading={killBusy}
        onCancel={() => setKillOpen(false)}
        onConfirm={() => void engageKill()}
      />

      <ConfirmDialog
        open={Boolean(pendingClose)}
        title={`Close ${pendingClose?.symbol ?? "position"}?`}
        message={
          pendingClose ? (
            <span>
              A market order will close position #{pendingClose.id}. Current unrealized P&L is{" "}
              <strong className={cn("num", pendingClose.pnl >= 0 ? "text-emerald-300" : "text-rose-300")}>
                {fmtSignedMoney(pendingClose.pnl)}
              </strong>
              .
            </span>
          ) : (
            ""
          )
        }
        confirmLabel="Close position"
        loading={closingId !== null}
        onCancel={() => setPendingClose(null)}
        onConfirm={() => void closePosition()}
      />
    </div>
  );
}
