import { Fragment, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  ArrowLeftRight,
  ChevronDown,
  ChevronUp,
  CircleDollarSign,
  Filter,
  RefreshCw,
  Target,
  TrendingUp,
  X,
} from "lucide-react";
import { apiGet, apiPost, errorMessage } from "../lib/api";
import {
  cn,
  fmtDateTime,
  fmtFullDateTime,
  fmtMoney,
  fmtNumber,
  fmtPct,
  fmtPrice,
  fmtSignedMoney,
  humanize,
  pnlClass,
  pnlTone,
  shortSymbol,
} from "../lib/format";
import { useDocumentTitle, usePolling } from "../lib/hooks";
import type { ActionResponse, BotSettings, TradeRow, TradesResponse } from "../lib/types";
import { useToast } from "../context/toast";
import {
  Badge,
  Button,
  Card,
  CardHeader,
  ConfirmDialog,
  EmptyState,
  ErrorState,
  PageHeader,
  PageSkeleton,
  Select,
  SideBadge,
  StatCard,
  StatusBadge,
  SyncLabel,
} from "../components/ui";

export function TradesPage() {
  useDocumentTitle("Trades");
  const navigate = useNavigate();
  const toast = useToast();
  const [params, setParams] = useSearchParams();
  const status = params.get("status") ?? "";
  const mode = params.get("mode") ?? "";
  const symbol = params.get("symbol") ?? "";

  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [pendingClose, setPendingClose] = useState<TradeRow | null>(null);
  const [closing, setClosing] = useState(false);

  const { data: settings } = usePolling<BotSettings>(() => apiGet("/api/v1/settings"), 0);

  const query = useMemo(() => {
    const search = new URLSearchParams();
    if (status) search.set("status", status);
    if (mode) search.set("mode", mode);
    if (symbol) search.set("symbol", symbol);
    search.set("limit", "500");
    return search.toString();
  }, [status, mode, symbol]);

  const { data, error, loading, lastUpdated, refresh } = usePolling<TradesResponse>(
    () => apiGet(`/api/v1/trades?${query}`),
    20_000,
    [query],
  );

  const setFilter = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
    setExpandedId(null);
  };

  const closeTrade = async () => {
    if (!pendingClose) return;
    setClosing(true);
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
      setClosing(false);
    }
  };

  if (loading && !data) return <PageSkeleton cards={6} rows={8} />;
  if (error && !data) return <ErrorState message={error} retry={() => void refresh()} />;
  if (!data) return <ErrorState message="No trade journal returned." retry={() => void refresh()} />;

  const stats = data.stats;
  const symbolOptions = Array.from(
    new Set(
      `${settings?.symbols ?? ""}`
        .split(",")
        .map((value) => shortSymbol(value.trim()))
        .filter(Boolean),
    ),
  );

  const hasFilters = Boolean(status || mode || symbol);

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow={
          <>
            <ArrowLeftRight className="h-3 w-3" /> Trade journal
          </>
        }
        title="Trades"
        description="Every paper and live position with entry, exit, fees, R multiple and exit reason."
        actions={
          <>
            <SyncLabel updatedAt={lastUpdated} loading={loading} />
            <Button variant="secondary" size="sm" icon={RefreshCw} onClick={() => void refresh()}>
              Refresh
            </Button>
          </>
        }
      />

      {error ? (
        <div className="rounded-xl border border-rose-500/25 bg-rose-500/[0.07] px-4 py-2.5 text-xs text-rose-200">
          {error}
        </div>
      ) : null}

      <section className="grid grid-cols-2 gap-3 lg:grid-cols-3 xl:grid-cols-6">
        <StatCard
          label="Net realized"
          value={fmtSignedMoney(stats.net_pnl)}
          hint={`From ${fmtMoney(stats.starting_balance)} starting`}
          icon={CircleDollarSign}
          tone={pnlTone(stats.net_pnl)}
          trend={stats.net_pnl > 0 ? "up" : stats.net_pnl < 0 ? "down" : "flat"}
        />
        <StatCard
          label="Today"
          value={fmtSignedMoney(stats.today_pnl)}
          hint="Realized today"
          icon={TrendingUp}
          tone={pnlTone(stats.today_pnl)}
        />
        <StatCard
          label="Win rate"
          value={`${stats.win_rate.toFixed(1)}%`}
          hint={`${stats.wins}W · ${stats.losses}L`}
          icon={Target}
          tone={stats.win_rate >= 50 ? "emerald" : "amber"}
        />
        <StatCard
          label="Profit factor"
          value={stats.profit_factor >= 999 ? "∞" : stats.profit_factor.toFixed(2)}
          hint="Gross profit ÷ gross loss"
          icon={TrendingUp}
          tone={stats.profit_factor >= 1 ? "emerald" : "rose"}
        />
        <StatCard
          label="Average R"
          value={stats.avg_r.toFixed(2)}
          hint={`${stats.trades} closed trades`}
          icon={ArrowLeftRight}
          tone={stats.avg_r > 0 ? "emerald" : stats.avg_r < 0 ? "rose" : "slate"}
        />
        <StatCard
          label="Max drawdown"
          value={fmtPct(stats.max_drawdown_pct)}
          hint={`${stats.open_positions} position(s) open`}
          icon={CircleDollarSign}
          tone="rose"
        />
      </section>

      <Card>
        <CardHeader
          title="Journal"
          description={`Showing ${data.trades.length} of the latest ${data.limit} records.`}
          icon={Filter}
          action={
            hasFilters ? (
              <Button
                size="sm"
                variant="ghost"
                icon={X}
                onClick={() => setParams({}, { replace: true })}
              >
                Clear filters
              </Button>
            ) : null
          }
        />

        <div className="grid gap-2.5 border-b border-slate-800/60 px-4 py-3 sm:grid-cols-2 lg:grid-cols-4 sm:px-5">
          <div className="flex items-center gap-1 rounded-xl border border-slate-800 bg-slate-950/40 p-1">
            {[
              { value: "", label: "All" },
              { value: "open", label: "Open" },
              { value: "closed", label: "Closed" },
            ].map((option) => (
              <button
                key={option.value}
                type="button"
                onClick={() => setFilter("status", option.value)}
                className={cn(
                  "flex-1 rounded-lg px-2 py-1.5 text-[11px] font-semibold transition",
                  status === option.value
                    ? "bg-slate-800 text-white shadow"
                    : "text-slate-500 hover:text-slate-300",
                )}
              >
                {option.label}
              </button>
            ))}
          </div>
          <Select value={mode} onChange={(event) => setFilter("mode", event.target.value)}>
            <option value="">All modes</option>
            <option value="paper">Paper</option>
            <option value="live">Live</option>
          </Select>
          <Select value={symbol} onChange={(event) => setFilter("symbol", event.target.value)}>
            <option value="">All symbols</option>
            {symbolOptions.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </Select>
          <div className="flex items-center justify-end gap-2 text-[10px] uppercase tracking-[0.12em] text-slate-600">
            <span>{stats.trades} closed</span>
            <span>·</span>
            <span>{stats.open_positions} open</span>
          </div>
        </div>

        {data.trades.length ? (
          <>
            <div className="divide-y divide-slate-800/50 xl:hidden">
              {data.trades.map((trade) => {
                const open = trade.status === "open";
                const pnl = open ? trade.unrealized : trade.pnl;
                return (
                  <div key={trade.id} className="px-4 py-4 sm:px-5">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-sm font-semibold text-white">{trade.symbol}</span>
                          <Badge tone={trade.mode === "live" ? "rose" : "sky"}>{trade.mode}</Badge>
                        </div>
                        <p className="num mt-1 text-[10px] text-slate-600">
                          #{trade.id} · {fmtDateTime(trade.opened_at)}
                        </p>
                      </div>
                      <StatusBadge status={trade.status} />
                    </div>
                    <div className="mt-3 flex items-end justify-between gap-4">
                      <div className="min-w-0">
                        <SideBadge side={trade.side} />
                        <p className="num mt-2 truncate text-[11px] text-slate-500">
                          {fmtPrice(trade.entry)} <span className="text-slate-700">→</span>{" "}
                          {open ? fmtPrice(trade.current) : fmtPrice(trade.exit_price)}
                          <span className="ml-2 text-slate-600">Qty {trade.qty.toFixed(5)}</span>
                        </p>
                      </div>
                      <div className="shrink-0 text-right">
                        <p className={cn("num text-sm font-semibold", pnlClass(pnl))}>
                          {fmtSignedMoney(pnl)}
                        </p>
                        <p className="num mt-1 text-[10px] text-slate-600">
                          R {trade.r_multiple.toFixed(2)}
                        </p>
                      </div>
                    </div>
                    {open ? (
                      <Button
                        size="sm"
                        variant="secondary"
                        icon={X}
                        onClick={() => setPendingClose(trade)}
                        className="mt-3 w-full"
                      >
                        Close at market
                      </Button>
                    ) : null}
                  </div>
                );
              })}
            </div>
            <div className="hidden overflow-x-auto xl:block">
            <table className="w-full min-w-[980px] whitespace-nowrap text-sm">
              <thead>
                <tr className="border-b border-slate-800/70 text-[10px] uppercase tracking-[0.14em] text-slate-500">
                  <th className="px-4 py-2.5 text-left font-semibold sm:px-5">Opened</th>
                  <th className="px-4 py-2.5 text-left font-semibold">Market</th>
                  <th className="px-4 py-2.5 text-left font-semibold">Side</th>
                  <th className="px-4 py-2.5 text-right font-semibold">Qty</th>
                  <th className="px-4 py-2.5 text-right font-semibold">Entry / mark</th>
                  <th className="px-4 py-2.5 text-right font-semibold">P&L</th>
                  <th className="px-4 py-2.5 text-right font-semibold">R</th>
                  <th className="px-4 py-2.5 text-right font-semibold">Status</th>
                  <th className="px-4 py-2.5 text-right font-semibold sm:px-5"> </th>
                </tr>
              </thead>
              <tbody>
                {data.trades.map((trade) => {
                  const open = trade.status === "open";
                  const pnl = open ? trade.unrealized : trade.pnl;
                  const expanded = expandedId === trade.id;
                  return (
                    <Fragment key={trade.id}>
                      <tr
                        key={trade.id}
                        onClick={() => setExpandedId(expanded ? null : trade.id)}
                        className={cn(
                          "cursor-pointer border-b border-slate-800/40 transition hover:bg-white/[0.025]",
                          expanded && "bg-white/[0.025]",
                        )}
                      >
                        <td className="num px-4 py-3 text-xs text-slate-500 sm:px-5">
                          {fmtDateTime(trade.opened_at)}
                        </td>
                        <td className="px-4 py-3">
                          <div className="font-semibold text-white">{trade.symbol}</div>
                          <div className="mt-1 flex items-center gap-1.5">
                            <Badge tone={trade.mode === "live" ? "rose" : "sky"}>{trade.mode}</Badge>
                            <span className="text-[10px] text-slate-600">#{trade.id}</span>
                          </div>
                        </td>
                        <td className="px-4 py-3">
                          <SideBadge side={trade.side} />
                        </td>
                        <td className="num px-4 py-3 text-right text-slate-400">
                          {trade.qty.toFixed(5)}
                        </td>
                        <td className="num px-4 py-3 text-right text-slate-300">
                          <div>{fmtPrice(trade.entry)}</div>
                          <div className="mt-1 text-[10px] text-slate-600">
                            → {open ? fmtPrice(trade.current) : fmtPrice(trade.exit_price)}
                          </div>
                        </td>
                        <td className={cn("num px-4 py-3 text-right font-semibold", pnlClass(pnl))}>
                          {fmtSignedMoney(pnl)}
                        </td>
                        <td
                          className={cn(
                            "num px-4 py-3 text-right",
                            trade.r_multiple > 0
                              ? "text-emerald-400"
                              : trade.r_multiple < 0
                                ? "text-rose-400"
                                : "text-slate-500",
                          )}
                        >
                          {trade.r_multiple.toFixed(2)}
                        </td>
                        <td className="px-4 py-3 text-right">
                          <StatusBadge status={trade.status} />
                        </td>
                        <td className="px-4 py-3 text-right sm:px-5">
                          <div className="flex items-center justify-end gap-2">
                            {open ? (
                              <Button
                                size="sm"
                                variant="ghost"
                                icon={X}
                                onClick={(event) => {
                                  event.stopPropagation();
                                  setPendingClose(trade);
                                }}
                                className="text-slate-500 hover:text-rose-300"
                              >
                                Close
                              </Button>
                            ) : null}
                            {expanded ? (
                              <ChevronUp className="h-3.5 w-3.5 text-slate-500" />
                            ) : (
                              <ChevronDown className="h-3.5 w-3.5 text-slate-500" />
                            )}
                          </div>
                        </td>
                      </tr>
                      {expanded ? (
                        <tr key={`${trade.id}-detail`} className="border-b border-slate-800/50 bg-slate-950/35">
                          <td colSpan={9} className="px-4 py-4 sm:px-5">
                            <div className="grid gap-3 whitespace-normal sm:grid-cols-2 lg:grid-cols-4">
                              <Detail label="Stop loss" value={fmtPrice(trade.stop)} />
                              <Detail label="Take profit" value={fmtPrice(trade.take_profit)} />
                              <Detail label="Leverage" value={`${trade.leverage}x`} />
                              <Detail label="Fees" value={fmtNumber(trade.fees, 4)} />
                              <Detail label="Signal" value={trade.signal_id ? `#${trade.signal_id}` : "—"} />
                              <Detail label="Closed" value={fmtFullDateTime(trade.closed_at)} />
                              <Detail label="Exit reason" value={humanize(trade.exit_reason)} />
                              <Detail label="Current / mark" value={fmtPrice(trade.current)} />
                              <Detail label="Mode" value={trade.mode} />
                            </div>
                            {trade.notes ? (
                              <p className="mt-3 whitespace-normal rounded-lg border border-slate-800/60 bg-slate-950/40 px-3 py-2 text-xs leading-5 text-slate-400">
                                {trade.notes}
                              </p>
                            ) : null}
                          </td>
                        </tr>
                      ) : null}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
            </div>
          </>
        ) : (
          <EmptyState
            title={hasFilters ? "No trades match these filters" : "No trades recorded yet"}
            description={
              hasFilters
                ? "Relax a filter to inspect the wider journal."
                : "The engine has not opened a position. Check the scanner for the current blocker."
            }
            action={
              hasFilters ? (
                <Button size="sm" variant="secondary" onClick={() => setParams({}, { replace: true })}>
                  Clear filters
                </Button>
              ) : (
                <Button size="sm" variant="secondary" onClick={() => navigate("/signals")}>
                  Inspect signals
                </Button>
              )
            }
          />
        )}
      </Card>

      <ConfirmDialog
        open={Boolean(pendingClose)}
        title={`Close ${pendingClose?.symbol ?? "position"}?`}
        message={
          pendingClose ? (
            <span>
              This sends a market close for trade #{pendingClose.id}. Unrealized P&L is{" "}
              <strong className={cn("num", pendingClose.unrealized >= 0 ? "text-emerald-300" : "text-rose-300")}>
                {fmtSignedMoney(pendingClose.unrealized)}
              </strong>
              .
            </span>
          ) : (
            ""
          )
        }
        confirmLabel="Close at market"
        loading={closing}
        onCancel={() => setPendingClose(null)}
        onConfirm={() => void closeTrade()}
      />
    </div>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-slate-800/60 bg-slate-950/30 px-3 py-2">
      <p className="text-[9px] font-semibold uppercase tracking-[0.14em] text-slate-600">{label}</p>
      <p className="num mt-1 text-xs text-slate-300">{value}</p>
    </div>
  );
}
