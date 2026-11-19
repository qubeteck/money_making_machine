import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import {
  ArrowRight,
  BarChart3,
  FlaskConical,
  Gauge,
  History,
  Info,
  Layers,
  Play,
  RefreshCw,
  TriangleAlert,
} from "lucide-react";
import { apiGet, apiPost, errorMessage } from "../lib/api";
import {
  cn,
  fmtDateTime,
  fmtMoney,
  fmtPct,
  fmtPrice,
  fmtSignedMoney,
  humanize,
  pnlClass,
  pnlTone,
  shortSymbol,
  signalStatusTone,
} from "../lib/format";
import { useDocumentTitle, usePolling } from "../lib/hooks";
import type {
  BacktestRequest,
  BacktestResult,
  BacktestTrade,
  BotSettings,
} from "../lib/types";
import { useToast } from "../context/toast";
import { CurveChart } from "../components/charts";
import {
  AlertBanner,
  Badge,
  Button,
  Card,
  CardHeader,
  EmptyState,
  ErrorState,
  Field,
  PageHeader,
  PageSkeleton,
  SideBadge,
  StatCard,
  TextInput,
  selectClass,
} from "../components/ui";

interface FormState {
  symbol: string;
  days: string;
  starting_balance: string;
  risk_pct: string;
  min_score: string;
  leverage: string;
  fee_pct: string;
  slippage_pct: string;
}

const FALLBACK_FORM: FormState = {
  symbol: "BTC/USDT",
  days: "90",
  starting_balance: "1000",
  risk_pct: "1",
  min_score: "70",
  leverage: "3",
  fee_pct: "0.06",
  slippage_pct: "0.03",
};

function formFromSettings(settings: BotSettings): FormState {
  const firstSymbol = settings.symbols.split(",")[0]?.trim() || FALLBACK_FORM.symbol;
  return {
    symbol: shortSymbol(firstSymbol),
    days: FALLBACK_FORM.days,
    starting_balance: String(settings.starting_balance ?? 1000),
    risk_pct: String(settings.risk_pct ?? 1),
    min_score: String(settings.min_score ?? 70),
    leverage: String(settings.leverage ?? 3),
    fee_pct: String(settings.taker_fee_pct ?? 0.06),
    slippage_pct: String(settings.slippage_pct ?? 0.03),
  };
}

export function BacktestPage() {
  useDocumentTitle("Backtest");
  const toast = useToast();
  const { data: settings, loading, error: settingsError } = usePolling<BotSettings>(
    () => apiGet("/api/v1/settings"),
    0,
  );
  const [form, setForm] = useState<FormState>(FALLBACK_FORM);
  const [initialized, setInitialized] = useState(false);
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const runningRef = useRef(false);

  useEffect(() => {
    if (!settings || initialized) return;
    setForm(formFromSettings(settings));
    setInitialized(true);
  }, [settings, initialized]);

  const set = (key: keyof FormState, value: string) => {
    setForm((current) => ({ ...current, [key]: value }));
  };

  const symbolOptions = useMemo(() => {
    if (!settings) return [];
    return Array.from(
      new Set(
        settings.symbols
          .split(",")
          .map((value) => shortSymbol(value.trim()))
          .filter(Boolean),
      ),
    );
  }, [settings]);

  const runBacktest = async (event: FormEvent) => {
    event.preventDefault();
    if (runningRef.current) return;
    const payload: BacktestRequest = {
      symbol: form.symbol.trim().toUpperCase(),
      days: Number(form.days),
      starting_balance: Number(form.starting_balance),
      risk_pct: Number(form.risk_pct),
      min_score: Number(form.min_score),
      leverage: Number(form.leverage),
      fee_pct: Number(form.fee_pct),
      slippage_pct: Number(form.slippage_pct),
    };

    if (!payload.symbol) {
      setRunError("Enter a symbol, for example BTC/USDT.");
      return;
    }
    if (![payload.days, payload.starting_balance, payload.risk_pct, payload.min_score, payload.leverage, payload.fee_pct, payload.slippage_pct].every(Number.isFinite)) {
      setRunError("Every numeric field must be a valid number.");
      return;
    }
    if (payload.days < 5 || payload.days > 180) {
      setRunError("Lookback must be between 5 and 180 days.");
      return;
    }
    if (payload.starting_balance < 10) {
      setRunError("Starting balance must be at least $10.");
      return;
    }
    if (payload.risk_pct < 0.05 || payload.risk_pct > 5) {
      setRunError("Risk per trade must be between 0.05% and 5%.");
      return;
    }
    if (payload.min_score < 0 || payload.min_score > 100) {
      setRunError("Minimum score must be between 0 and 100.");
      return;
    }
    if (payload.leverage < 1 || payload.leverage > 50) {
      setRunError("Leverage must be between 1x and 50x.");
      return;
    }
    if (payload.fee_pct < 0 || payload.fee_pct > 1 || payload.slippage_pct < 0 || payload.slippage_pct > 1) {
      setRunError("Fee and slippage must each be between 0% and 1%.");
      return;
    }

    runningRef.current = true;
    setRunning(true);
    setRunError(null);
    try {
      const response = await apiPost<BacktestResult>("/api/v1/backtest", payload);
      setResult(response);
      toast.success(
        "Backtest complete",
        `${response.trades} trades · ${fmtSignedMoney(response.net_pnl)} net · ${fmtPct(response.return_pct)} return`,
      );
    } catch (cause) {
      setRunError(errorMessage(cause));
      toast.error("Backtest failed", errorMessage(cause));
    } finally {
      runningRef.current = false;
      setRunning(false);
    }
  };

  if (loading && !settings) return <PageSkeleton cards={4} rows={5} />;
  if (settingsError && !settings) {
    return <ErrorState message={settingsError} retry={() => window.location.reload()} />;
  }

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow={
          <>
            <FlaskConical className="h-3 w-3" /> Research sandbox
          </>
        }
        title="Backtest"
        description="Replay the multi-timeframe strategy over historical MEXC candles. Fills include fees and slippage but remain an approximation."
        actions={
          <>
            <Badge tone="violet">
              <Layers className="h-3 w-3" /> Strategy replay
            </Badge>
            <Badge tone="slate">Isolated from live engine</Badge>
          </>
        }
      />

      {runError ? (
        <AlertBanner tone="rose" title="Backtest could not run">
          {runError}
        </AlertBanner>
      ) : null}

      <div className="grid items-start gap-3 xl:grid-cols-[390px_minmax(0,1fr)]">
        <Card className="xl:sticky xl:top-24">
          <CardHeader
            title="Simulation setup"
            description="Defaults are copied from your live bot settings."
            icon={Gauge}
          />
          <form onSubmit={runBacktest} className="space-y-5 p-4 sm:p-5">
            <div className="space-y-3">
              <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500">
                Instrument
              </p>
              <Field label="Symbol" htmlFor="bt-symbol" hint="MEXC USDT perpetual, e.g. BTC/USDT.">
                <TextInput
                  id="bt-symbol"
                  value={form.symbol}
                  onChange={(event) => set("symbol", event.target.value)}
                  list="backtest-symbols"
                  placeholder="BTC/USDT"
                  required
                />
                <datalist id="backtest-symbols">
                  {symbolOptions.map((symbol) => (
                    <option key={symbol} value={symbol} />
                  ))}
                </datalist>
              </Field>
              <Field label="Lookback window" htmlFor="bt-days" hint="More days means slower simulation and more trades.">
                <div className="flex gap-2">
                  <TextInput
                    id="bt-days"
                    type="number"
                    min={5}
                    max={180}
                    value={form.days}
                    onChange={(event) => set("days", event.target.value)}
                    required
                  />
                </div>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {[30, 60, 90, 180].map((days) => (
                    <button
                      key={days}
                      type="button"
                      onClick={() => set("days", String(days))}
                      className={cn(
                        "rounded-md border px-2 py-1 text-[10px] font-semibold transition",
                        form.days === String(days)
                          ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-300"
                          : "border-slate-800 text-slate-500 hover:border-slate-700 hover:text-slate-300",
                      )}
                    >
                      {days}d
                    </button>
                  ))}
                </div>
              </Field>
            </div>

            <div className="space-y-3 border-t border-slate-800/60 pt-4">
              <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500">
                Risk & scoring
              </p>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Risk / trade %" htmlFor="bt-risk">
                  <TextInput
                    id="bt-risk"
                    type="number"
                    min={0.05}
                    max={5}
                    step={0.01}
                    value={form.risk_pct}
                    onChange={(event) => set("risk_pct", event.target.value)}
                    required
                  />
                </Field>
                <Field label="Min score" htmlFor="bt-score">
                  <TextInput
                    id="bt-score"
                    type="number"
                    min={0}
                    max={100}
                    step={1}
                    value={form.min_score}
                    onChange={(event) => set("min_score", event.target.value)}
                    required
                  />
                </Field>
                <Field label="Leverage cap" htmlFor="bt-leverage">
                  <TextInput
                    id="bt-leverage"
                    type="number"
                    min={1}
                    max={50}
                    step={1}
                    value={form.leverage}
                    onChange={(event) => set("leverage", event.target.value)}
                    required
                  />
                </Field>
                <Field label="Starting balance" htmlFor="bt-balance">
                  <TextInput
                    id="bt-balance"
                    type="number"
                    min={10}
                    max={10000000}
                    step={10}
                    value={form.starting_balance}
                    onChange={(event) => set("starting_balance", event.target.value)}
                    required
                  />
                </Field>
              </div>
            </div>

            <div className="space-y-3 border-t border-slate-800/60 pt-4">
              <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500">
                Execution costs
              </p>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Taker fee %" htmlFor="bt-fee" hint="Per side.">
                  <TextInput
                    id="bt-fee"
                    type="number"
                    min={0}
                    max={1}
                    step={0.01}
                    value={form.fee_pct}
                    onChange={(event) => set("fee_pct", event.target.value)}
                    required
                  />
                </Field>
                <Field label="Slippage %" htmlFor="bt-slippage" hint="Per fill.">
                  <TextInput
                    id="bt-slippage"
                    type="number"
                    min={0}
                    max={1}
                    step={0.01}
                    value={form.slippage_pct}
                    onChange={(event) => set("slippage_pct", event.target.value)}
                    required
                  />
                </Field>
              </div>
            </div>

            <Button
              type="submit"
              variant="primary"
              loading={running}
              icon={running ? RefreshCw : Play}
              className="w-full"
            >
              {running ? "Running simulation…" : "Run backtest"}
            </Button>
            <p className="text-[10px] leading-5 text-slate-600">
              Historical data reuse may take up to a minute for longer windows. This does
              not place orders or alter bot state.
            </p>
          </form>
        </Card>

        <div className="space-y-3">
          {running && !result ? (
            <Card>
              <CardHeader title="Running simulation" description="Fetching candles and replaying the confluence rules." icon={FlaskConical} />
              <div className="p-5">
                <div className="skeleton h-72 rounded-xl" />
                <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
                  {Array.from({ length: 4 }).map((_, index) => (
                    <div key={index} className="skeleton h-20 rounded-xl" />
                  ))}
                </div>
              </div>
            </Card>
          ) : result ? (
            <>
              <section className="grid grid-cols-2 gap-3 lg:grid-cols-4">
                <StatCard
                  label="Net P&L"
                  value={fmtSignedMoney(result.net_pnl)}
                  hint={`${fmtMoney(result.final_equity)} final equity`}
                  icon={BarChart3}
                  tone={pnlTone(result.net_pnl)}
                  trend={result.net_pnl > 0 ? "up" : result.net_pnl < 0 ? "down" : "flat"}
                />
                <StatCard
                  label="Return"
                  value={fmtPct(result.return_pct, 2, true)}
                  hint={`${result.days} days · ${result.trades} trades`}
                  icon={ArrowRight}
                  tone={result.return_pct > 0 ? "emerald" : "rose"}
                />
                <StatCard
                  label="Win rate"
                  value={`${result.win_rate.toFixed(1)}%`}
                  hint={`${result.wins}W · ${result.losses}L`}
                  icon={Gauge}
                  tone={result.win_rate >= 50 ? "emerald" : "amber"}
                />
                <StatCard
                  label="Profit factor"
                  value={result.profit_factor >= 999 ? "∞" : result.profit_factor.toFixed(2)}
                  hint={`Expectancy ${fmtSignedMoney(result.expectancy)}`}
                  icon={FlaskConical}
                  tone={result.profit_factor >= 1 ? "emerald" : "rose"}
                />
                <StatCard
                  label="Max drawdown"
                  value={fmtPct(result.max_drawdown_pct)}
                  hint="Peak-to-trough on the equity curve"
                  icon={TriangleAlert}
                  tone="rose"
                />
                <StatCard
                  label="Average R"
                  value={result.avg_r.toFixed(2)}
                  hint="Per closed trade"
                  icon={Gauge}
                  tone={result.avg_r > 0 ? "emerald" : "rose"}
                />
                <StatCard
                  label="Candles"
                  value={result.candles.toLocaleString("en-US")}
                  hint={result.data_start ? `From ${fmtDateTime(result.data_start)}` : "Historical window"}
                  icon={History}
                  tone="sky"
                />
                <StatCard
                  label="Data through"
                  value={result.data_end ? fmtDateTime(result.data_end) : "—"}
                  hint={result.symbol}
                  icon={Layers}
                  tone="violet"
                />
              </section>

              {result.warnings.length ? (
                <Card className="p-4">
                  <div className="flex items-start gap-3 text-amber-200">
                    <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" />
                    <div>
                      <p className="text-xs font-semibold">Simulation notes</p>
                      <ul className="mt-1.5 list-inside list-disc space-y-1 text-[11px] leading-5 text-amber-200/70">
                        {result.warnings.map((warning, index) => (
                          <li key={index}>{warning}</li>
                        ))}
                      </ul>
                    </div>
                  </div>
                </Card>
              ) : null}

              <Card>
                <CardHeader
                  title="Equity curve"
                  description={`${result.symbol} · ${result.days}-day replay · starting balance ${fmtMoney(result.starting_balance)}`}
                  icon={BarChart3}
                  action={<Badge tone={result.net_pnl >= 0 ? "emerald" : "rose"}>{fmtPct(result.return_pct, 2, true)}</Badge>}
                />
                <div className="px-3 pb-3 pt-2 sm:px-4">
                  {result.curve.length ? (
                    <CurveChart curve={result.curve} height={320} />
                  ) : (
                    <EmptyState
                      title="No equity curve"
                      description="The simulation returned no snapshots. Try a longer window."
                    />
                  )}
                </div>
              </Card>

              <Card>
                <CardHeader
                  title="Simulated trades"
                  description={`${result.trade_list.length} round trips. P&L includes estimated fees and slippage.`}
                  icon={History}
                  action={<Badge tone="slate">{result.trade_list.length} rows</Badge>}
                />
                {result.trade_list.length ? (
                  <div className="max-h-[560px] overflow-auto">
                    <table className="w-full min-w-[980px] text-sm">
                      <thead className="sticky top-0 z-10 bg-[#0a1120]">
                        <tr className="border-b border-slate-800/70 text-[10px] uppercase tracking-[0.14em] text-slate-500">
                          <th className="px-4 py-2.5 text-left font-semibold sm:px-5">#</th>
                          <th className="px-4 py-2.5 text-left font-semibold">Opened</th>
                          <th className="px-4 py-2.5 text-left font-semibold">Side</th>
                          <th className="px-4 py-2.5 text-right font-semibold">Entry</th>
                          <th className="px-4 py-2.5 text-right font-semibold">Exit</th>
                          <th className="px-4 py-2.5 text-right font-semibold">Qty</th>
                          <th className="px-4 py-2.5 text-right font-semibold">P&L</th>
                          <th className="px-4 py-2.5 text-right font-semibold">R</th>
                          <th className="px-4 py-2.5 text-right font-semibold">Score</th>
                          <th className="px-4 py-2.5 text-left font-semibold sm:px-5">Exit reason</th>
                        </tr>
                      </thead>
                      <tbody>
                        {result.trade_list.map((trade: BacktestTrade, index) => (
                          <tr
                            key={`${trade.opened_at}-${index}`}
                            className="border-b border-slate-800/40 transition last:border-0 hover:bg-white/[0.02]"
                          >
                            <td className="px-4 py-2.5 text-xs text-slate-600 sm:px-5">{index + 1}</td>
                            <td className="num px-4 py-2.5 text-xs text-slate-500">
                              {fmtDateTime(trade.opened_at)}
                            </td>
                            <td className="px-4 py-2.5">
                              <SideBadge side={trade.side} />
                            </td>
                            <td className="num px-4 py-2.5 text-right text-slate-300">
                              {fmtPrice(trade.entry)}
                            </td>
                            <td className="num px-4 py-2.5 text-right text-slate-300">
                              {fmtPrice(trade.exit)}
                            </td>
                            <td className="num px-4 py-2.5 text-right text-slate-500">
                              {trade.qty.toFixed(5)}
                            </td>
                            <td className={cn("num px-4 py-2.5 text-right font-semibold", pnlClass(trade.pnl))}>
                              {fmtSignedMoney(trade.pnl)}
                            </td>
                            <td
                              className={cn(
                                "num px-4 py-2.5 text-right text-xs font-semibold",
                                trade.r_multiple > 0
                                  ? "text-emerald-400"
                                  : trade.r_multiple < 0
                                    ? "text-rose-400"
                                    : "text-slate-500",
                              )}
                            >
                              {trade.r_multiple.toFixed(2)}
                            </td>
                            <td className="num px-4 py-2.5 text-right text-xs text-slate-400">
                              {trade.score.toFixed(0)}
                            </td>
                            <td className="px-4 py-2.5 text-xs capitalize text-slate-500 sm:px-5">
                              {humanize(trade.reason)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <EmptyState
                    title="No trades generated"
                    description="Try a longer window, a lower minimum score or a different symbol. Strict confluence rules can legitimately produce zero fills."
                  />
                )}
              </Card>
            </>
          ) : (
            <>
              <Card>
                <CardHeader
                  title="Research before risk"
                  description="A backtest is a sanity check, not a promise."
                  icon={FlaskConical}
                />
                <div className="p-5">
                  <div className="rounded-xl border border-slate-800/70 bg-slate-950/40 p-4">
                    <p className="text-sm font-semibold text-slate-200">
                      Run a simulation to see the equity path, drawdown and trade list.
                    </p>
                    <p className="mt-1.5 text-xs leading-6 text-slate-500">
                      The replay uses the same 4H trend filter, 1H structure and 15M trigger
                      as the live engine, with one position at a time and structural stops.
                      Fill assumptions are conservative but still approximate.
                    </p>
                  </div>

                  <div className="mt-4 grid gap-3 sm:grid-cols-2">
                    <Checklist
                      title="What is modeled"
                      items={[
                        "Confluence score threshold",
                        "Structural stop and take-profit",
                        "Risk-based position sizing",
                        "Fees and slippage per fill",
                        "Maximum of one position per symbol",
                      ]}
                    />
                    <Checklist
                      title="What is not modeled"
                      items={[
                        "Exchange outage or partial fills",
                        "Funding payments",
                        "Order-book impact",
                        "Latency and requotes",
                        "Future market regime",
                      ]}
                    />
                  </div>

                  <div className="mt-4 rounded-xl border border-sky-500/20 bg-sky-500/[0.05] px-3.5 py-3">
                    <div className="flex items-center gap-2 text-xs font-semibold text-sky-200">
                      <Info className="h-3.5 w-3.5" /> Practical workflow
                    </div>
                    <p className="mt-1 text-[11px] leading-5 text-sky-200/70">
                      Start in paper mode, compare the live journal with the backtest, then
                      reduce the period until the two stories align. Any live arming should
                      use the smallest position the exchange allows.
                    </p>
                  </div>
                </div>
              </Card>

              <Card>
                <CardHeader
                  title="Current execution assumptions"
                  description="Pulled from the running bot settings."
                  icon={Gauge}
                  action={<Badge tone="slate">{settings?.symbols.split(",").length ?? 0} configured</Badge>}
                />
                <div className="grid gap-3 p-4 sm:grid-cols-2 lg:grid-cols-4">
                  <Assumption label="Trend filter" value={settings?.trend_timeframe ?? "4h"} />
                  <Assumption label="Structure" value={settings?.structure_timeframe ?? "1h"} />
                  <Assumption label="Trigger" value={settings?.entry_timeframe ?? "15m"} />
                  <Assumption label="Risk / trade" value={settings ? fmtPct(settings.risk_pct) : "—"} />
                  <Assumption label="Minimum score" value={settings ? `${Math.round(settings.min_score)}/100` : "—"} />
                  <Assumption label="Leverage cap" value={settings ? `${settings.leverage}x` : "—"} />
                  <Assumption label="Fee per side" value={settings ? fmtPct(settings.taker_fee_pct, 3) : "—"} />
                  <Assumption label="Slippage" value={settings ? fmtPct(settings.slippage_pct, 3) : "—"} />
                </div>
              </Card>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function Checklist({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="rounded-xl border border-slate-800/60 bg-slate-950/30 p-3.5">
      <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">{title}</p>
      <ul className="mt-2 space-y-1.5">
        {items.map((item) => (
          <li key={item} className="flex items-start gap-2 text-[11px] leading-5 text-slate-400">
            <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-slate-600" />
            {item}
          </li>
        ))}
      </ul>
    </div>
  );
}

function Assumption({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-slate-800/60 bg-slate-950/40 px-3 py-2.5">
      <p className="text-[9px] font-semibold uppercase tracking-[0.14em] text-slate-600">{label}</p>
      <p className="num mt-1 text-sm font-semibold text-slate-200">{value}</p>
    </div>
  );
}
