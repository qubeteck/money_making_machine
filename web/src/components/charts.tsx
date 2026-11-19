import { useEffect, useId, useMemo, useRef } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  HistogramSeries,
  LineSeries,
  createChart,
  type UTCTimestamp,
} from "lightweight-charts";
import { cn, fmtMoney, fmtPrice } from "../lib/format";
import type { Candle, EquitySeries } from "../lib/types";
import { EmptyState, ErrorState, Skeleton } from "./ui";

const CHART_COLORS = ["#34d399", "#38bdf8", "#fbbf24", "#a78bfa", "#fb7185", "#2dd4bf", "#f472b6"];

const tooltipStyle = {
  background: "#0b1322",
  border: "1px solid rgba(51,65,85,.9)",
  borderRadius: 12,
  boxShadow: "0 20px 60px -20px rgba(0,0,0,.8)",
  fontSize: 12,
  color: "#e2e8f0",
  padding: "8px 10px",
};

export function EquityChart({
  data,
  height = 280,
  label = "Equity",
  className,
}: {
  data: EquitySeries | null | undefined;
  height?: number | string;
  label?: string;
  className?: string;
}) {
  const gradientId = useId().replace(/[:]/g, "");
  const points = useMemo(() => {
    if (!data) return [];
    return data.labels.map((item, index) => ({
      label: item,
      value: Number(data.values[index] ?? 0),
    }));
  }, [data]);

  if (!points.length) {
    return (
      <div className={cn("grid place-items-center", className)} style={{ height }}>
        <div className="text-center">
          <p className="text-sm font-medium text-slate-400">No equity snapshots yet</p>
          <p className="mt-1 text-xs text-slate-600">
            The engine records a snapshot every five minutes.
          </p>
        </div>
      </div>
    );
  }

  const first = points[0].value;
  const last = points[points.length - 1].value;
  const change = last - first;
  const changePct = first ? (change / first) * 100 : 0;
  const positive = change >= 0;
  const stroke = positive ? "#34d399" : "#fb7185";

  return (
    <div className={cn("relative", className)}>
      <div className="pointer-events-none absolute left-1 top-0 z-10 flex items-baseline gap-2">
        <span className="num text-lg font-semibold text-white">{fmtMoney(last)}</span>
        <span
          className={cn(
            "num text-[11px] font-semibold",
            positive ? "text-emerald-400" : "text-rose-400",
          )}
        >
          {positive ? "+" : "−"}
          {fmtMoney(Math.abs(change))} ({positive ? "+" : "−"}
          {Math.abs(changePct).toFixed(2)}%)
        </span>
      </div>
      <div style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={points} margin={{ top: 30, right: 8, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={stroke} stopOpacity={0.24} />
                <stop offset="100%" stopColor={stroke} stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke="rgba(148,163,184,.08)" vertical={false} />
            <XAxis
              dataKey="label"
              tick={{ fill: "#64748b", fontSize: 10 }}
              tickLine={false}
              axisLine={false}
              minTickGap={42}
              interval="preserveStartEnd"
            />
            <YAxis
              domain={["auto", "auto"]}
              tick={{ fill: "#64748b", fontSize: 10 }}
              tickLine={false}
              axisLine={false}
              width={58}
              tickFormatter={(value) => `$${Number(value).toLocaleString("en-US", { maximumFractionDigits: 0 })}`}
            />
            <Tooltip
              contentStyle={tooltipStyle}
              labelStyle={{ color: "#94a3b8", fontSize: 11, marginBottom: 4 }}
              itemStyle={{ color: "#e2e8f0", fontSize: 12 }}
              formatter={(value) => [fmtMoney(Number(value)), label]}
            />
            <Area
              type="monotone"
              dataKey="value"
              stroke={stroke}
              strokeWidth={2}
              fill={`url(#${gradientId})`}
              dot={false}
              activeDot={{ r: 3.5, fill: stroke, strokeWidth: 0 }}
              isAnimationActive={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

export function CurveChart({
  curve,
  height = 280,
  className,
}: {
  curve: [string, number][];
  height?: number;
  className?: string;
}) {
  const data = useMemo<EquitySeries>(() => {
    return {
      labels: curve.map(([timestamp]) => {
        const date = new Date(timestamp);
        return Number.isNaN(date.getTime())
          ? String(timestamp).slice(5, 16)
          : date.toLocaleDateString(undefined, { month: "short", day: "2-digit" });
      }),
      values: curve.map(([, value]) => Number(value)),
    };
  }, [curve]);

  return <EquityChart data={data} height={height} label="Backtest equity" className={className} />;
}

export function AllocationDonut({
  data,
  height = 220,
}: {
  data: EquitySeries | null | undefined;
  height?: number;
}) {
  const points = useMemo(() => {
    if (!data) return [];
    return data.labels
      .map((label, index) => ({ label, value: Number(data.values[index] ?? 0) }))
      .filter((item) => item.value > 0);
  }, [data]);

  const total = points.reduce((sum, item) => sum + item.value, 0);

  if (!points.length) {
    return (
      <div className="grid place-items-center" style={{ height }}>
        <p className="text-xs text-slate-600">No open exposure.</p>
      </div>
    );
  }

  return (
    <div>
      <div className="relative" style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={points}
              dataKey="value"
              nameKey="label"
              innerRadius="68%"
              outerRadius="92%"
              paddingAngle={2}
              stroke="none"
              isAnimationActive={false}
            >
              {points.map((entry, index) => (
                <Cell
                  key={entry.label}
                  fill={CHART_COLORS[index % CHART_COLORS.length]}
                  opacity={0.9}
                />
              ))}
            </Pie>
            <Tooltip
              contentStyle={tooltipStyle}
              formatter={(value) => [fmtMoney(Number(value)), "Notional"]}
            />
          </PieChart>
        </ResponsiveContainer>
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-[9px] font-semibold uppercase tracking-[0.18em] text-slate-500">
            Exposure
          </span>
          <span className="num text-lg font-semibold text-white">{fmtMoney(total)}</span>
        </div>
      </div>
      <ul className="mt-3 grid grid-cols-2 gap-x-3 gap-y-1.5">
        {points.map((item, index) => (
          <li key={item.label} className="flex items-center justify-between gap-2 text-[11px]">
            <span className="flex min-w-0 items-center gap-1.5 text-slate-400">
              <span
                className="h-1.5 w-1.5 shrink-0 rounded-full"
                style={{ background: CHART_COLORS[index % CHART_COLORS.length] }}
              />
              <span className="truncate">{item.label}</span>
            </span>
            <span className="num shrink-0 text-slate-300">
              {total ? `${((item.value / total) * 100).toFixed(0)}%` : "—"}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function Sparkline({
  values,
  width = 108,
  height = 32,
  className,
}: {
  values: number[];
  width?: number;
  height?: number;
  className?: string;
}) {
  if (values.length < 2) {
    return <div className={cn("h-8 w-[108px]", className)} />;
  }
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const step = width / (values.length - 1);
  const path = values
    .map((value, index) => {
      const x = index * step;
      const y = height - ((value - min) / span) * (height - 4) - 2;
      return `${index === 0 ? "M" : "L"}${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");
  const positive = values[values.length - 1] >= values[0];
  const stroke = positive ? "#34d399" : "#fb7185";
  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className={cn("overflow-visible", className)}
      aria-hidden
    >
      <path d={path} fill="none" stroke={stroke} strokeWidth="1.5" strokeLinejoin="round" />
    </svg>
  );
}

export function CandleChart({
  candles,
  loading,
  error,
  height = 360,
}: {
  candles: Candle[];
  loading?: boolean;
  error?: string | null;
  height?: number;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container || candles.length === 0) return;

    const chart = createChart(container, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "#7c8ba1",
        fontFamily:
          '"JetBrains Mono Variable", ui-monospace, SFMono-Regular, Menlo, monospace',
        fontSize: 10,
        attributionLogo: false,
      },
      grid: {
        vertLines: { color: "rgba(148,163,184,.06)" },
        horzLines: { color: "rgba(148,163,184,.06)" },
      },
      rightPriceScale: {
        borderColor: "rgba(148,163,184,.12)",
        scaleMargins: { top: 0.08, bottom: 0.24 },
      },
      timeScale: {
        borderColor: "rgba(148,163,184,.12)",
        timeVisible: true,
        secondsVisible: false,
        rightOffset: 3,
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: "rgba(148,163,184,.35)", labelBackgroundColor: "#1e293b" },
        horzLine: { color: "rgba(148,163,184,.35)", labelBackgroundColor: "#1e293b" },
      },
      localization: {
        priceFormatter: (value: number) => fmtPrice(value),
      },
    });

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#34d399",
      downColor: "#fb7185",
      borderVisible: false,
      wickUpColor: "#34d399",
      wickDownColor: "#fb7185",
      priceLineVisible: false,
    });

    candleSeries.setData(
      candles.map((item) => ({
        time: item.time as UTCTimestamp,
        open: item.open,
        high: item.high,
        low: item.low,
        close: item.close,
      })),
    );

    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "volume",
      priceLineVisible: false,
      lastValueVisible: false,
    });
    chart.priceScale("volume").applyOptions({
      scaleMargins: { top: 0.82, bottom: 0 },
    });
    volumeSeries.setData(
      candles.map((item) => ({
        time: item.time as UTCTimestamp,
        value: item.volume,
        color: item.close >= item.open ? "rgba(52,211,153,.22)" : "rgba(251,113,133,.22)",
      })),
    );

    const emaValues: { time: UTCTimestamp; value: number }[] = [];
    const multiplier = 2 / (20 + 1);
    let ema: number | null = null;
    candles.forEach((item, index) => {
      ema = ema === null ? item.close : item.close * multiplier + ema * (1 - multiplier);
      if (index >= 19 && ema !== null) {
        emaValues.push({ time: item.time as UTCTimestamp, value: ema });
      }
    });
    if (emaValues.length) {
      const emaSeries = chart.addSeries(LineSeries, {
        color: "rgba(56,189,248,.8)",
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
      });
      emaSeries.setData(emaValues);
    }

    chart.timeScale().fitContent();

    return () => {
      chart.remove();
    };
  }, [candles]);

  if (error) {
    return (
      <div style={{ height }} className="overflow-hidden rounded-xl border border-slate-800/60">
        <ErrorState message={error} compact />
      </div>
    );
  }

  if (loading && candles.length === 0) {
    return <Skeleton className="w-full rounded-xl" style={{ height }} />;
  }

  if (candles.length === 0) {
    return (
      <div style={{ height }} className="rounded-xl border border-slate-800/60">
        <EmptyState
          title="No candles returned"
          description="The exchange feed did not return data for this symbol and timeframe."
        />
      </div>
    );
  }

  return <div ref={containerRef} style={{ height }} className="w-full" />;
}
