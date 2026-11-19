import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ArrowRight,
  CheckCircle2,
  CircleSlash,
  Filter,
  ListChecks,
  RefreshCw,
  Search,
  Signal as SignalIcon,
  Target,
  Terminal,
  XCircle,
  Zap,
} from "lucide-react";
import { apiGet, errorMessage } from "../lib/api";
import {
  cn,
  compactStatus,
  compactStructure,
  compactTrend,
  fmtFullDateTime,
  fmtPrice,
  fmtTime,
  scoreTone,
  trendTone,
} from "../lib/format";
import { useDocumentTitle, usePolling } from "../lib/hooks";
import type { Scan, ScansResponse, Signal } from "../lib/types";
import { useToast } from "../context/toast";
import { ScoreBreakdown, SignalsTable, type SignalRow } from "../components/tables";
import {
  AlertBanner,
  Badge,
  Button,
  Card,
  CardHeader,
  EmptyState,
  ErrorState,
  PageHeader,
  PageSkeleton,
  ScoreRing,
  Select,
  SideBadge,
  StatusBadge,
  SyncLabel,
  TextInput,
} from "../components/ui";

type Tab = "signals" | "scans";

interface SignalsResponse {
  signals: Signal[];
}

export function SignalsPage() {
  useDocumentTitle("Signals");
  const navigate = useNavigate();
  const toast = useToast();
  const [tab, setTab] = useState<Tab>("signals");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [side, setSide] = useState("");
  const [status, setStatus] = useState("");
  const [search, setSearch] = useState("");

  const { data, error, loading, lastUpdated, refresh } = usePolling<{
    signals: Signal[];
    scans: Scan[];
  }>(async () => {
    const [signals, scans] = await Promise.all([
      apiGet<SignalsResponse>("/api/v1/signals?limit=100"),
      apiGet<ScansResponse>("/api/v1/scans?limit=120"),
    ]);
    return { signals: signals.signals ?? [], scans: scans.scans ?? [] };
  }, 15_000);

  const signals = data?.signals ?? [];
  const scans = data?.scans ?? [];

  const filteredSignals = useMemo(() => {
    const term = search.trim().toUpperCase();
    return signals.filter((signal) => {
      if (side && signal.side !== side) return false;
      if (status && signal.status !== status) return false;
      if (term && !signal.symbol.toUpperCase().includes(term)) return false;
      return true;
    });
  }, [signals, side, status, search]);

  const filteredScans = useMemo(() => {
    const term = search.trim().toUpperCase();
    return scans.filter((scan) => {
      if (term && !scan.symbol.toUpperCase().includes(term)) return false;
      if (status && scan.status !== status) return false;
      return true;
    });
  }, [scans, search, status]);

  const selected =
    filteredSignals.find((signal) => signal.id === selectedId) ?? filteredSignals[0] ?? null;

  const counts = useMemo(() => {
    return signals.reduce(
      (acc, signal) => {
        acc.total += 1;
        if (signal.status === "executed") acc.executed += 1;
        else if (signal.status === "rejected" || signal.status === "error") acc.rejected += 1;
        return acc;
      },
      { total: 0, executed: 0, rejected: 0 },
    );
  }, [signals]);

  if (loading && !data) return <PageSkeleton cards={3} rows={8} />;
  if (error && !data) return <ErrorState message={error} retry={() => void refresh()} />;

  const signalRows: SignalRow[] = filteredSignals.map((signal) => ({
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
            <SignalIcon className="h-3 w-3" /> Confluence research
          </>
        }
        title="Signals"
        description="Inspect every confluence calculation, entry level, score component and scan blocker."
        actions={
          <>
            <SyncLabel updatedAt={lastUpdated} loading={loading} />
            <Button variant="secondary" size="sm" icon={RefreshCw} onClick={() => void refresh()}>
              Refresh
            </Button>
            <Button variant="secondary" size="sm" icon={ArrowRight} onClick={() => navigate("/trades")}>
              Trade journal
            </Button>
          </>
        }
      />

      {error ? (
        <div className="rounded-xl border border-rose-500/25 bg-rose-500/[0.07] px-4 py-2.5 text-xs text-rose-200">
          {error}
        </div>
      ) : null}

      <section className="grid grid-cols-3 gap-3 sm:max-w-xl">
        <div className="rounded-xl border border-slate-800/70 bg-[#0a1120]/80 px-4 py-3">
          <p className="text-[9px] font-semibold uppercase tracking-[0.16em] text-slate-600">Signals</p>
          <p className="num mt-1 text-xl font-semibold text-white">{counts.total}</p>
        </div>
        <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/[0.05] px-4 py-3">
          <p className="text-[9px] font-semibold uppercase tracking-[0.16em] text-emerald-500/70">
            Executed
          </p>
          <p className="num mt-1 text-xl font-semibold text-emerald-300">{counts.executed}</p>
        </div>
        <div className="rounded-xl border border-rose-500/20 bg-rose-500/[0.05] px-4 py-3">
          <p className="text-[9px] font-semibold uppercase tracking-[0.16em] text-rose-500/70">
            Rejected
          </p>
          <p className="num mt-1 text-xl font-semibold text-rose-300">{counts.rejected}</p>
        </div>
      </section>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-1 rounded-xl border border-slate-800 bg-slate-950/40 p-1">
          {(
            [
              { key: "signals", label: "Signal log", icon: Zap },
              { key: "scans", label: "Scan history", icon: Terminal },
            ] as const
          ).map((item) => {
            const Icon = item.icon;
            return (
              <button
                key={item.key}
                type="button"
                onClick={() => {
                  setTab(item.key);
                  setStatus("");
                }}
                className={cn(
                  "flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[11px] font-semibold transition",
                  tab === item.key
                    ? "bg-slate-800 text-white shadow"
                    : "text-slate-500 hover:text-slate-300",
                )}
              >
                <Icon className="h-3.5 w-3.5" /> {item.label}
              </button>
            );
          })}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <div className="relative w-48">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-600" />
            <TextInput
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Filter symbol"
              className="h-9 pl-9 text-xs"
            />
          </div>
          {tab === "signals" ? (
            <div className="flex items-center gap-1 rounded-lg border border-slate-800 bg-slate-950/40 p-1">
              {[
                { value: "", label: "All" },
                { value: "long", label: "Long" },
                { value: "short", label: "Short" },
              ].map((option) => (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => setSide(option.value)}
                  className={cn(
                    "rounded-md px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.08em] transition",
                    side === option.value
                      ? "bg-slate-800 text-white"
                      : "text-slate-500 hover:text-slate-300",
                  )}
                >
                  {option.label}
                </button>
              ))}
            </div>
          ) : null}
          <div className="w-40">
            <Select
              value={status}
              onChange={(event) => setStatus(event.target.value)}
              className="h-9 text-xs"
            >
              <option value="">All statuses</option>
              {tab === "signals" ? (
                <>
                  <option value="executed">Executed</option>
                  <option value="rejected">Rejected</option>
                  <option value="error">Error</option>
                  <option value="new">New</option>
                </>
              ) : (
                <>
                  <option value="signal">Signal</option>
                  <option value="below-threshold">Below threshold</option>
                  <option value="no-trend">No trend</option>
                  <option value="waiting-trigger">Waiting trigger</option>
                </>
              )}
            </Select>
          </div>
        </div>
      </div>

      {tab === "signals" ? (
        <section className="grid items-start gap-3 lg:grid-cols-[minmax(0,1fr)_380px]">
          <Card className="min-w-0">
            <CardHeader
              title="Signal log"
              description={`${filteredSignals.length} of the latest ${signals.length} signals.`}
              icon={Zap}
              action={<Badge tone="slate">score ≥ threshold</Badge>}
            />
            <SignalsTable
              rows={signalRows}
              selectedId={selected?.id ?? null}
              onSelect={(row) => setSelectedId(row.id)}
            />
          </Card>

          <div className="min-w-0 space-y-3">
            {selected ? (
              <>
                <Card>
                  <CardHeader
                    title={
                      <span className="flex items-center gap-2">
                        {selected.symbol} <SideBadge side={selected.side} />
                      </span>
                    }
                    description={fmtFullDateTime(selected.created_at)}
                    action={<StatusBadge status={selected.status} />}
                  />
                  <div className="space-y-4 p-4">
                    <div className="flex items-center gap-4">
                      <ScoreRing score={selected.score} />
                      <div className="min-w-0 space-y-1.5 text-[11px]">
                        <div className="flex items-center gap-2">
                          <span className="text-slate-500">Trend</span>
                          <Badge
                            tone={trendTone(selected.htf_trend)}
                            title={selected.htf_trend}
                          >
                            {compactTrend(selected.htf_trend)}
                          </Badge>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="text-slate-500">Structure</span>
                          <span className="text-slate-300">{selected.structure_timeframe}</span>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="text-slate-500">Entry TF</span>
                          <span className="text-slate-300">{selected.entry_timeframe}</span>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="text-slate-500">R:R</span>
                          <span className="num text-slate-300">{selected.rr.toFixed(2)}</span>
                        </div>
                      </div>
                    </div>

                    <div className="grid grid-cols-3 gap-2">
                      <Level label="Entry" value={fmtPrice(selected.entry)} />
                      <Level label="Stop" value={fmtPrice(selected.stop)} tone="rose" />
                      <Level label="Target" value={fmtPrice(selected.take_profit)} tone="emerald" />
                    </div>

                    <div>
                      <div className="mb-2 flex items-center justify-between">
                        <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500">
                          Score breakdown
                        </p>
                        <span className="num text-[10px] text-slate-500">
                          {Object.values(selected.components).reduce((sum, value) => sum + Number(value), 0)}/100
                        </span>
                      </div>
                      <ScoreBreakdown components={selected.components} />
                    </div>

                    {selected.reject_reason ? (
                      <AlertBanner tone="rose" title="Rejected by risk">
                        {selected.reject_reason}
                      </AlertBanner>
                    ) : null}

                    {selected.reasons.length ? (
                      <div>
                        <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500">
                          Confluence notes
                        </p>
                        <ul className="space-y-1.5">
                          {selected.reasons.map((reason, index) => (
                            <li key={`${reason}-${index}`} className="flex items-start gap-2 text-[11px] leading-5 text-slate-400">
                              <CheckCircle2 className="mt-0.5 h-3 w-3 shrink-0 text-emerald-500/70" />
                              {reason}
                            </li>
                          ))}
                        </ul>
                      </div>
                    ) : null}
                  </div>
                </Card>

                <Button
                  variant="secondary"
                  size="sm"
                  icon={ArrowRight}
                  className="w-full"
                  onClick={() => navigate(selected.status === "executed" ? "/trades" : "/trades?status=open")}
                >
                  Open trade journal
                </Button>
              </>
            ) : (
              <Card>
                <EmptyState
                  icon={CircleSlash}
                  title="No signal selected"
                  description="Nothing matches the current filters."
                  action={
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => {
                        setSide("");
                        setStatus("");
                        setSearch("");
                      }}
                    >
                      Clear filters
                    </Button>
                  }
                />
              </Card>
            )}
          </div>
        </section>
      ) : (
        <Card>
          <CardHeader
            title="Scan history"
            description="Every evaluated market, including setups that did not qualify."
            icon={Terminal}
            action={<Badge tone="slate">{filteredScans.length} rows</Badge>}
          />
          {filteredScans.length ? (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[960px] text-sm">
                <thead>
                  <tr className="border-b border-slate-800/70 text-[10px] uppercase tracking-[0.14em] text-slate-500">
                    <th className="px-4 py-2.5 text-left font-semibold sm:px-5">Time</th>
                    <th className="px-4 py-2.5 text-left font-semibold">Market</th>
                    <th className="px-4 py-2.5 text-right font-semibold">Price</th>
                    <th className="px-4 py-2.5 text-left font-semibold">HTF trend</th>
                    <th className="px-4 py-2.5 text-left font-semibold">Structure</th>
                    <th className="px-4 py-2.5 text-right font-semibold">Score</th>
                    <th className="px-4 py-2.5 text-left font-semibold">Status</th>
                    <th className="px-4 py-2.5 text-left font-semibold sm:px-5">Reason</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredScans.map((scan) => (
                    <tr
                      key={scan.id}
                      className="border-b border-slate-800/40 transition last:border-0 hover:bg-white/[0.02]"
                    >
                      <td className="num px-4 py-3 text-xs text-slate-500 sm:px-5">
                        {fmtTime(scan.created_at)}
                      </td>
                      <td className="px-4 py-3 font-semibold text-white">{scan.symbol}</td>
                      <td className="num px-4 py-3 text-right text-slate-300">{fmtPrice(scan.price)}</td>
                      <td className="whitespace-nowrap px-4 py-3">
                        <Badge tone={trendTone(scan.trend)} title={scan.trend}>
                          {compactTrend(scan.trend)}
                        </Badge>
                      </td>
                      <td className="max-w-[150px] truncate whitespace-nowrap px-4 py-3 text-xs capitalize text-slate-400" title={scan.structure}>
                        {compactStructure(scan.structure)}
                      </td>
                      <td className="num px-4 py-3 text-right">
                        <span
                          className={cn(
                            "font-semibold",
                            scoreTone(scan.score) === "emerald"
                              ? "text-emerald-300"
                              : scoreTone(scan.score) === "amber"
                                ? "text-amber-300"
                                : "text-rose-300",
                          )}
                        >
                          {scan.score.toFixed(1)}
                        </span>
                      </td>
                      <td className="whitespace-nowrap px-4 py-3">
                        <Badge
                          tone={scan.status.includes("signal") ? "emerald" : "slate"}
                          title={scan.status}
                        >
                          {compactStatus(scan.status)}
                        </Badge>
                      </td>
                      <td className="max-w-[340px] truncate px-4 py-3 text-xs text-slate-500 sm:px-5" title={scan.reason}>
                        {scan.reason || "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState
              icon={Filter}
              title="No scans match these filters"
              description="Change the status filter or wait for the next engine scan."
            />
          )}
        </Card>
      )}

      <div className="grid gap-3 sm:grid-cols-3">
        <InfoCard
          icon={Target}
          title="Confluence threshold"
          body="A signal needs 70+ points. The 4H trend (25), 1H structure (20) and the fresh 15M trigger (15) carry most of the weight."
        />
        <InfoCard
          icon={ListChecks}
          title="Risk filter comes next"
          body="A qualified score can still be rejected by position limits, daily loss guardrails, cooldowns or exchange minimums."
        />
        <InfoCard
          icon={XCircle}
          title="No signal is normal"
          body="The rules are deliberately strict. Hours or days without a setup are expected, not a malfunction."
        />
      </div>
    </div>
  );
}

function Level({
  label,
  value,
  tone = "slate",
}: {
  label: string;
  value: string;
  tone?: "emerald" | "rose" | "slate";
}) {
  return (
    <div className="rounded-lg border border-slate-800/60 bg-slate-950/40 px-2.5 py-2">
      <p className="text-[9px] font-semibold uppercase tracking-[0.12em] text-slate-600">{label}</p>
      <p
        className={cn(
          "num mt-1 text-xs font-semibold",
          tone === "emerald" && "text-emerald-300",
          tone === "rose" && "text-rose-300",
          tone === "slate" && "text-slate-200",
        )}
      >
        {value}
      </p>
    </div>
  );
}

function InfoCard({
  icon: Icon,
  title,
  body,
}: {
  icon: typeof Target;
  title: string;
  body: string;
}) {
  return (
    <div className="rounded-xl border border-slate-800/60 bg-slate-900/30 px-4 py-3.5">
      <div className="flex items-center gap-2 text-slate-400">
        <Icon className="h-3.5 w-3.5" />
        <p className="text-xs font-semibold text-slate-200">{title}</p>
      </div>
      <p className="mt-1.5 text-[11px] leading-5 text-slate-500">{body}</p>
    </div>
  );
}
