import clsx from "clsx";

export const cn = clsx;

const numberFormat = new Intl.NumberFormat("en-US", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const compactFormat = new Intl.NumberFormat("en-US", {
  notation: "compact",
  maximumFractionDigits: 1,
});

export function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

export function fmtMoney(value: number | null | undefined, digits = 2): string {
  if (!isFiniteNumber(value)) return "—";
  if (digits === 2) return `$${numberFormat.format(value)}`;
  return `$${value.toLocaleString("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })}`;
}

export function fmtSignedMoney(value: number | null | undefined, digits = 2): string {
  if (!isFiniteNumber(value)) return "—";
  const sign = value > 0 ? "+" : value < 0 ? "−" : "";
  return `${sign}${fmtMoney(Math.abs(value), digits)}`;
}

export function fmtNumber(value: number | null | undefined, digits = 2): string {
  if (!isFiniteNumber(value)) return "—";
  return value.toLocaleString("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function fmtCompact(value: number | null | undefined): string {
  if (!isFiniteNumber(value)) return "—";
  return compactFormat.format(value);
}

export function fmtPrice(value: number | null | undefined): string {
  if (!isFiniteNumber(value) || value === 0) return "—";
  const absolute = Math.abs(value);
  if (absolute >= 1000) {
    return value.toLocaleString("en-US", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  }
  if (absolute >= 1) return value.toFixed(4);
  if (absolute >= 0.01) return value.toFixed(5);
  return value.toFixed(6);
}

export function fmtPct(
  value: number | null | undefined,
  digits = 2,
  signed = false,
): string {
  if (!isFiniteNumber(value)) return "—";
  const sign = signed && value > 0 ? "+" : "";
  return `${sign}${value.toFixed(digits)}%`;
}

export function fmtSignedPct(value: number | null | undefined, digits = 2): string {
  return fmtPct(value, digits, true);
}

/** Parse ISO timestamps. SQLite-sourced timestamps may arrive without a zone. */
export function parseDate(value: string | null | undefined): Date | null {
  if (!value) return null;
  let text = String(value).trim();
  if (!text) return null;
  if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?$/.test(text)) {
    text += "Z";
  }
  const date = new Date(text);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function fmtDateTime(value: string | null | undefined): string {
  const date = parseDate(value);
  if (!date) return "—";
  return date.toLocaleString(undefined, {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function fmtFullDateTime(value: string | null | undefined): string {
  const date = parseDate(value);
  if (!date) return "—";
  return date.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function fmtTime(value: string | null | undefined): string {
  const date = parseDate(value);
  if (!date) return "—";
  return date.toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function fmtShortTime(value: string | null | undefined): string {
  const date = parseDate(value);
  if (!date) return "—";
  return date.toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
  });
}

const relativeFormat = new Intl.RelativeTimeFormat(undefined, {
  numeric: "auto",
  style: "short",
});

export function timeAgo(value: string | null | undefined): string {
  const date = parseDate(value);
  if (!date) return "—";
  const diffSeconds = Math.round((date.getTime() - Date.now()) / 1000);
  const absolute = Math.abs(diffSeconds);
  if (absolute < 45) return "just now";
  if (absolute < 3_600) return relativeFormat.format(Math.round(diffSeconds / 60), "minute");
  if (absolute < 86_400) return relativeFormat.format(Math.round(diffSeconds / 3_600), "hour");
  if (absolute < 604_800) return relativeFormat.format(Math.round(diffSeconds / 86_400), "day");
  return fmtDateTime(value);
}

export function fmtDuration(seconds: number | null | undefined): string {
  if (!isFiniteNumber(seconds)) return "—";
  if (seconds < 1) return `${Math.max(0, Math.round(seconds * 1000))} ms`;
  if (seconds < 60) return `${seconds.toFixed(1)} s`;
  const minutes = Math.floor(seconds / 60);
  const remainder = Math.round(seconds % 60);
  if (minutes < 60) return `${minutes}m ${remainder}s`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ${minutes % 60}m`;
}

export function fmtUptime(seconds: number | null | undefined): string {
  if (!isFiniteNumber(seconds) || seconds < 0) return "—";
  const days = Math.floor(seconds / 86_400);
  const hours = Math.floor((seconds % 86_400) / 3_600);
  const minutes = Math.floor((seconds % 3_600) / 60);
  if (days > 0) return `${days}d ${hours}h`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}

export function humanize(value: string | null | undefined): string {
  if (!value) return "—";
  return String(value)
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

export function shortSymbol(symbol: string): string {
  return symbol.split(":")[0];
}

export function trendTone(trend: string | null | undefined): "emerald" | "rose" | "slate" {
  const value = String(trend ?? "").toLowerCase();
  if (value.includes("bull") || value === "up" || value.includes("long")) return "emerald";
  if (value.includes("bear") || value === "down" || value.includes("short")) return "rose";
  return "slate";
}

/** A short trend label for dense cards and tables; keep the full value in a title. */
export function compactTrend(trend: string | null | undefined): string {
  const value = String(trend ?? "").toLowerCase();
  if (value.includes("bull")) return "Bullish";
  if (value.includes("bear")) return "Bearish";
  if (value.includes("neutral") || value.includes("range")) return "Neutral";
  return humanize(trend);
}

/** Strip parenthetical detail such as "(EMA50 < EMA200)" for table cells. */
export function compactStructure(structure: string | null | undefined): string {
  if (!structure) return "—";
  return structure
    .replace(/\s*\([^)]*\)\s*/g, " ")
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/** Friendly short labels for engine statuses. */
export function compactStatus(status: string | null | undefined): string {
  switch (String(status ?? "").toLowerCase()) {
    case "structure-misaligned":
      return "Structure off";
    case "trend-misaligned":
      return "Trend off";
    case "below-threshold":
      return "Below threshold";
    case "waiting-trigger":
      return "Waiting trigger";
    case "no-trend":
      return "No trend";
    case "no-trigger":
      return "No trigger";
    case "signal":
      return "Signal";
    default:
      return humanize(status);
  }
}

export function scoreTone(score: number): "emerald" | "amber" | "rose" {
  if (score >= 70) return "emerald";
  if (score >= 45) return "amber";
  return "rose";
}

export function pnlClass(value: number): string {
  if (value > 0) return "text-emerald-400";
  if (value < 0) return "text-rose-400";
  return "text-slate-400";
}

export function pnlTone(value: number): "emerald" | "rose" | "slate" {
  if (value > 0) return "emerald";
  if (value < 0) return "rose";
  return "slate";
}

export function sideLabel(side: string): string {
  return String(side).toLowerCase() === "long" ? "LONG" : "SHORT";
}

export function signalStatusTone(status: string): "emerald" | "rose" | "amber" | "sky" | "slate" {
  switch (String(status).toLowerCase()) {
    case "executed":
      return "emerald";
    case "rejected":
      return "rose";
    case "error":
      return "rose";
    case "new":
      return "sky";
    case "below-threshold":
      return "amber";
    default:
      return "slate";
  }
}

export function tradeStatusTone(status: string): "emerald" | "sky" | "slate" {
  return String(status).toLowerCase() === "open" ? "sky" : "emerald";
}

export function last<T>(items: T[]): T | undefined {
  return items.length ? items[items.length - 1] : undefined;
}

export function nf(value: unknown, fallback = 0): number {
  const number = typeof value === "number" ? value : Number(value);
  return Number.isFinite(number) ? number : fallback;
}
