import type { ReactNode } from "react";
import { ArrowDownRight, ArrowUpRight, MoveHorizontal, X } from "lucide-react";
import {
  cn,
  compactStatus,
  compactStructure,
  compactTrend,
  fmtDateTime,
  fmtDuration,
  fmtPrice,
  fmtSignedMoney,
  fmtTime,
  humanize,
  pnlClass,
  scoreTone,
  sideLabel,
  trendTone,
} from "../lib/format";
import type { JobRun, LogEntry, Tone } from "../lib/types";
import { Badge, Button, EmptyState, MiniStat, Progress, ScoreBar, SideBadge, StatusBadge } from "./ui";

/* ------------------------------------------------------------------ markets */

function TableScrollHint() {
  return (
    <div className="flex items-center gap-2 border-b border-slate-800/50 px-4 py-2 text-[10px] text-slate-600 sm:px-5 lg:hidden">
      <MoveHorizontal className="h-3 w-3 shrink-0" />
      Swipe side to side to see every column
    </div>
  );
}

export interface MarketRow {
  symbol: string;
  price: number;
  trend: string;
  structure: string;
  score: number;
  status: string;
  reason?: string;
  updatedAt?: string | null;
}

export function MarketsTable({ rows }: { rows: MarketRow[] }) {
  if (!rows.length) {
    return (
      <EmptyState
        title="Waiting for the first scan"
        description="Market rows appear after the engine evaluates the configured symbols."
      />
    );
  }

  return (
    <div className="overflow-x-auto">
      <TableScrollHint />
      <table className="w-full min-w-[620px] text-sm">
        <thead>
          <tr className="border-b border-slate-800/70 text-[10px] uppercase tracking-[0.14em] text-slate-500">
            <th className="px-4 py-2.5 text-left font-semibold sm:px-5">Instrument</th>
            <th className="px-4 py-2.5 text-right font-semibold">Price</th>
            <th className="px-4 py-2.5 text-right font-semibold">Bias</th>
            <th className="px-4 py-2.5 text-right font-semibold">Confluence</th>
            <th className="px-4 py-2.5 text-right font-semibold sm:px-5">Status</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.symbol}
              className="border-b border-slate-800/40 transition last:border-0 hover:bg-white/[0.02]"
            >
              <td className="whitespace-nowrap px-4 py-3 sm:px-5">
                <div className="font-semibold text-white">{row.symbol}</div>
                <div className="mt-0.5 text-[10px] uppercase tracking-[0.12em] text-slate-600">
                  Perpetual · USDT
                </div>
              </td>
              <td className="num whitespace-nowrap px-4 py-3 text-right text-slate-200">
                {fmtPrice(row.price)}
              </td>
              <td className="whitespace-nowrap px-4 py-3 text-right">
                <Badge tone={trendTone(row.trend)} title={row.trend}>
                  {compactTrend(row.trend)}
                </Badge>
                <div
                  className="ml-auto mt-1 max-w-[150px] truncate text-[10px] text-slate-600"
                  title={row.structure || "No structure"}
                >
                  {compactStructure(row.structure)}
                </div>
              </td>
              <td className="px-4 py-3 text-right">
                <div className="ml-auto w-20">
                  <ScoreBar score={row.score} showLabel />
                </div>
              </td>
              <td className="whitespace-nowrap px-4 py-3 text-right sm:px-5">
                <Badge
                  tone={
                    row.status.includes("signal")
                      ? "emerald"
                      : row.status.includes("below")
                        ? "amber"
                        : "slate"
                  }
                  title={row.reason || humanize(row.status)}
                >
                  {compactStatus(row.status)}
                </Badge>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ------------------------------------------------------------------ positions */

export interface PositionRow {
  id: number;
  symbol: string;
  side: string;
  qty: number;
  entry: number;
  current: number;
  stop: number;
  takeProfit: number;
  pnl: number;
  pnlPct?: number;
  risk?: string;
  mode: string;
  leverage?: number;
  openedAt?: string | null;
}

export function PositionsTable({
  rows,
  onClose,
  closingId,
}: {
  rows: PositionRow[];
  onClose?: (row: PositionRow) => void;
  closingId?: number | null;
}) {
  if (!rows.length) {
    return (
      <EmptyState
        title="No open positions"
        description="The risk engine has no live exposure right now. Qualified setups will appear here."
      />
    );
  }

  return (
    <div className="overflow-x-auto">
      <TableScrollHint />
      <table className="w-full min-w-[680px] text-sm">
        <thead>
          <tr className="border-b border-slate-800/70 text-[10px] uppercase tracking-[0.14em] text-slate-500">
            <th className="px-4 py-2.5 text-left font-semibold sm:px-5">Market</th>
            <th className="px-4 py-2.5 text-left font-semibold">Side</th>
            <th className="px-4 py-2.5 text-right font-semibold">Entry</th>
            <th className="px-4 py-2.5 text-right font-semibold">Mark</th>
            <th className="px-4 py-2.5 text-right font-semibold">Stop / target</th>
            <th className="px-4 py-2.5 text-right font-semibold">Unrealized</th>
            {onClose ? <th className="px-4 py-2.5 text-right font-semibold sm:px-5">Manage</th> : null}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.id}
              title={row.openedAt ? `Opened ${fmtDateTime(row.openedAt)}` : undefined}
              className="border-b border-slate-800/40 transition last:border-0 hover:bg-white/[0.02]"
            >
              <td className="whitespace-nowrap px-4 py-3 sm:px-5">
                <div className="font-semibold text-white">{row.symbol}</div>
                <div className="mt-1 flex items-center gap-1.5">
                  <Badge tone={row.mode.toLowerCase() === "live" ? "rose" : "sky"}>
                    {row.mode}
                  </Badge>
                  {row.leverage ? (
                    <span className="text-[10px] text-slate-600">{row.leverage}x</span>
                  ) : null}
                  <span className="text-[10px] text-slate-600">#{row.id}</span>
                </div>
              </td>
              <td className="whitespace-nowrap px-4 py-3">
                <SideBadge side={row.side} />
              </td>
              <td className="num whitespace-nowrap px-4 py-3 text-right text-slate-300">
                {fmtPrice(row.entry)}
              </td>
              <td className="num whitespace-nowrap px-4 py-3 text-right font-medium text-slate-100">
                {fmtPrice(row.current)}
              </td>
              <td className="whitespace-nowrap px-4 py-3 text-right">
                <div className="num text-[11px] text-rose-300/75">
                  <span className="mr-1 text-[9px] uppercase tracking-[0.1em] text-slate-600">SL</span>
                  {fmtPrice(row.stop)}
                </div>
                <div className="num mt-1 text-[11px] text-emerald-300/75">
                  <span className="mr-1 text-[9px] uppercase tracking-[0.1em] text-slate-600">TP</span>
                  {fmtPrice(row.takeProfit)}
                </div>
              </td>
              <td className={cn("num whitespace-nowrap px-4 py-3 text-right font-semibold", pnlClass(row.pnl))}>
                {fmtSignedMoney(row.pnl)}
                {typeof row.pnlPct === "number" ? (
                  <div className="text-[10px] font-medium opacity-70">
                    {row.pnlPct > 0 ? "+" : ""}
                    {row.pnlPct.toFixed(2)}%
                  </div>
                ) : null}
              </td>
              {onClose ? (
                <td className="whitespace-nowrap px-4 py-3 text-right sm:px-5">
                  <Button
                    size="sm"
                    variant="ghost"
                    icon={X}
                    loading={closingId === row.id}
                    onClick={() => onClose(row)}
                    className="text-slate-500 hover:text-rose-300"
                  >
                    Close
                  </Button>
                </td>
              ) : null}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ------------------------------------------------------------------ signals */

export interface SignalRow {
  id: number;
  createdAt: string;
  symbol: string;
  side: string;
  score: number;
  status: string;
  entry: number;
  stop: number;
  takeProfit: number;
  rr?: number;
  strategy?: string;
  timeframe?: string;
}

export function SignalsTable({
  rows,
  onSelect,
  selectedId,
}: {
  rows: SignalRow[];
  onSelect?: (row: SignalRow) => void;
  selectedId?: number | null;
}) {
  if (!rows.length) {
    return (
      <EmptyState
        title="No signals yet"
        description="The strategy requires a 4H trend, aligned 1H structure, a pullback and a fresh 15M trigger."
      />
    );
  }

  return (
    <div className="overflow-x-auto">
      <TableScrollHint />
      <table className="w-full min-w-[620px] text-sm">
        <thead>
          <tr className="border-b border-slate-800/70 text-[10px] uppercase tracking-[0.14em] text-slate-500">
            <th className="px-4 py-2.5 text-left font-semibold sm:px-5">Market</th>
            <th className="px-4 py-2.5 text-left font-semibold">Bias</th>
            <th className="px-4 py-2.5 text-right font-semibold">Score</th>
            <th className="px-4 py-2.5 text-right font-semibold">R:R</th>
            <th className="px-4 py-2.5 text-right font-semibold sm:px-5">Status</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.id}
              onClick={onSelect ? () => onSelect(row) : undefined}
              className={cn(
                "border-b border-slate-800/40 transition last:border-0",
                onSelect && "cursor-pointer hover:bg-white/[0.03]",
                selectedId === row.id && "bg-emerald-500/[0.045]",
              )}
            >
              <td className="whitespace-nowrap px-4 py-3 sm:px-5">
                <div className="font-semibold text-white">{row.symbol}</div>
                <div className="mt-1 flex items-center gap-2">
                  <SideBadge side={row.side} />
                  <span className="num text-[10px] text-slate-600">{fmtTime(row.createdAt)}</span>
                </div>
              </td>
              <td
                className="max-w-[180px] truncate whitespace-nowrap px-4 py-3 text-xs text-slate-400"
                title={row.strategy || "SMC confluence"}
              >
                {row.strategy ?? "SMC confluence"}
                {row.timeframe ? (
                  <span className="ml-1 text-slate-600">· {row.timeframe}</span>
                ) : null}
              </td>
              <td className="px-4 py-3 text-right">
                <div className="ml-auto w-20">
                  <ScoreBar score={row.score} showLabel />
                </div>
              </td>
              <td className="num whitespace-nowrap px-4 py-3 text-right text-slate-400">
                {row.rr ? `${row.rr.toFixed(1)}R` : "—"}
              </td>
              <td className="whitespace-nowrap px-4 py-3 text-right sm:px-5">
                <StatusBadge status={row.status} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Compact signal list for narrow dashboard columns. */
export function SignalFeed({
  rows,
  onSelect,
  className,
}: {
  rows: SignalRow[];
  onSelect?: (row: SignalRow) => void;
  className?: string;
}) {
  if (!rows.length) {
    return (
      <EmptyState
        title="No signals yet"
        description="The strategy requires a 4H trend, aligned 1H structure, a pullback and a fresh 15M trigger."
      />
    );
  }

  return (
    <div className={cn("divide-y divide-slate-800/50", className)}>
      {rows.map((row) => (
        <button
          key={row.id}
          type="button"
          onClick={onSelect ? () => onSelect(row) : undefined}
          className={cn(
            "block w-full px-4 py-3 text-left transition sm:px-5",
            onSelect && "hover:bg-white/[0.025]",
          )}
        >
          <div className="flex items-center justify-between gap-2">
            <div className="flex min-w-0 items-center gap-2">
              <span className="truncate text-xs font-semibold text-white">{row.symbol}</span>
              <SideBadge side={row.side} />
            </div>
            <StatusBadge status={row.status} />
          </div>
          <div className="mt-2 flex items-center gap-3">
            <div className="min-w-0 flex-1">
              <ScoreBar score={row.score} />
            </div>
            <span className="num shrink-0 text-[10px] font-semibold text-slate-400">
              {row.score.toFixed(1)}
            </span>
            <span className="num shrink-0 text-[10px] text-slate-600">{fmtTime(row.createdAt)}</span>
          </div>
        </button>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ jobs */

function jobTone(status: string): Tone {
  if (status === "error") return "rose";
  if (status === "skipped") return "amber";
  return "emerald";
}

export function JobsTable({ jobs }: { jobs: JobRun[] }) {
  if (!jobs.length) {
    return (
      <EmptyState
        title="No job runs recorded"
        description="Scheduled scans and reports are logged here after the first scheduler tick."
      />
    );
  }

  return (
    <div className="overflow-x-auto">
      <TableScrollHint />
      <table className="w-full min-w-[760px] text-sm">
        <thead>
          <tr className="border-b border-slate-800/70 text-[10px] uppercase tracking-[0.14em] text-slate-500">
            <th className="px-4 py-2.5 text-left font-semibold sm:px-5">Job</th>
            <th className="px-4 py-2.5 text-left font-semibold">Started</th>
            <th className="px-4 py-2.5 text-left font-semibold">Status</th>
            <th className="px-4 py-2.5 text-right font-semibold">Duration</th>
            <th className="px-4 py-2.5 text-left font-semibold sm:px-5">Message</th>
          </tr>
        </thead>
        <tbody>
          {jobs.map((job) => (
            <tr
              key={job.id}
              className="border-b border-slate-800/40 transition last:border-0 hover:bg-white/[0.02]"
            >
              <td className="px-4 py-3 font-medium text-slate-200 sm:px-5">
                {job.job_name.replace(/_/g, " ")}
              </td>
              <td className="num px-4 py-3 text-xs text-slate-500">{fmtDateTime(job.started_at)}</td>
              <td className="px-4 py-3">
                <div className="flex items-center gap-1.5">
                  <Badge tone={jobTone(job.status)}>{job.status}</Badge>
                  {job.attempts > 1 ? (
                    <span className="text-[10px] text-slate-600">×{job.attempts}</span>
                  ) : null}
                </div>
              </td>
              <td className="num px-4 py-3 text-right text-xs text-slate-400">
                {fmtDuration(job.duration_seconds)}
              </td>
              <td
                className="max-w-[320px] truncate px-4 py-3 text-xs text-slate-500 sm:px-5"
                title={job.message}
              >
                {job.message || "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ------------------------------------------------------------------ logs */

const levelDot: Record<string, string> = {
  ERROR: "bg-rose-400",
  WARNING: "bg-amber-400",
  WARN: "bg-amber-400",
  INFO: "bg-sky-400",
  DEBUG: "bg-slate-500",
};

export function LogsList({ logs, className }: { logs: LogEntry[]; className?: string }) {
  if (!logs.length) {
    return (
      <EmptyState
        title="No engine events yet"
        description="Scans, fills and errors are recorded in the activity journal."
      />
    );
  }
  return (
    <div className={cn("divide-y divide-slate-800/50", className)}>
      {logs.map((log, index) => {
        const level = (log.level || "INFO").toUpperCase();
        return (
          <div key={`${log.created_at}-${index}`} className="flex items-start gap-3 px-4 py-2.5 sm:px-5">
            <span
              className={cn(
                "mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full",
                levelDot[level] ?? "bg-slate-500",
              )}
            />
            <div className="min-w-0 flex-1">
              <p className="text-xs leading-5 text-slate-400">{log.message}</p>
              <p className="num mt-0.5 text-[10px] text-slate-600">
                {fmtTime(log.created_at)} · {level}
              </p>
            </div>
          </div>
        );
      })}
    </div>
  );
}

/* ------------------------------------------------------------------ scores */

const COMPONENT_MAX: Record<string, number> = {
  "HTF trend": 25,
  "HTF momentum": 10,
  "HTF structure": 20,
  "HTF zone": 15,
  "LTF trigger": 15,
  "LTF zone": 10,
  Volume: 5,
};

const COMPONENT_ORDER = Object.keys(COMPONENT_MAX);

export function ScoreBreakdown({ components }: { components: Record<string, number> }) {
  const names = Array.from(
    new Set([...COMPONENT_ORDER, ...Object.keys(components ?? {})]),
  );
  return (
    <div className="space-y-2.5">
      {names.map((name) => {
        const value = Number(components?.[name] ?? 0);
        const max = COMPONENT_MAX[name] ?? Math.max(value, 15);
        const tone = value <= 0 ? "slate" : value >= max ? "emerald" : "amber";
        return (
          <div key={name}>
            <div className="mb-1 flex items-center justify-between text-[11px]">
              <span className="text-slate-400">{name}</span>
              <span className={cn("num font-semibold", value > 0 ? "text-slate-200" : "text-slate-600")}>
                {value}/{max}
              </span>
            </div>
            <Progress value={(value / max) * 100} tone={tone} />
          </div>
        );
      })}
    </div>
  );
}

/* ------------------------------------------------------------------ compact */

export function PositionSummary({ pnl, count }: { pnl: number; count: number }) {
  return (
    <div className="flex flex-wrap gap-2">
      <MiniStat label="Open" value={count} />
      <MiniStat
        label="Unrealized"
        value={fmtSignedMoney(pnl)}
        tone={pnl > 0 ? "emerald" : pnl < 0 ? "rose" : "slate"}
      />
    </div>
  );
}

export function MoveIndicator({ value }: { value: number }) {
  const positive = value >= 0;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-0.5 text-[11px] font-semibold",
        positive ? "text-emerald-400" : "text-rose-400",
      )}
    >
      {positive ? <ArrowUpRight className="h-3 w-3" /> : <ArrowDownRight className="h-3 w-3" />}
      {Math.abs(value).toFixed(2)}%
    </span>
  );
}

export function asNode(value: ReactNode): ReactNode {
  return value;
}
