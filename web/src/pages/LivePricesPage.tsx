import { useEffect, useMemo, useState } from "react";
import {
  ArrowDownRight,
  ArrowUpRight,
  Radio,
  RefreshCw,
  Rss,
  ShieldCheck,
  Wifi,
  WifiOff,
} from "lucide-react";
import {
  cn,
  compactStatus,
  compactStructure,
  compactTrend,
  fmtDateTime,
  fmtPrice,
  fmtTime,
  humanize,
  scoreTone,
  trendTone,
} from "../lib/format";
import { useDocumentTitle, useTickerStream } from "../lib/hooks";
import type { Ticker } from "../lib/types";
import { Sparkline } from "../components/charts";
import { MarketsTable, type MarketRow } from "../components/tables";
import {
  AlertBanner,
  Badge,
  Button,
  Card,
  CardHeader,
  EmptyState,
  KeyValue,
  PageHeader,
  ScoreBar,
  StatCard,
} from "../components/ui";

interface TrackedPrice {
  price: number;
  previous: number;
  first: number;
  history: number[];
  updatedAt: string | null;
}

export function LivePricesPage() {
  useDocumentTitle("Live Prices");
  const { status, tickers, updatedAt, intervalSeconds, error, reconnect } = useTickerStream();
  const [tracked, setTracked] = useState<Map<string, TrackedPrice>>(new Map());

  useEffect(() => {
    if (!tickers.length) return;
    setTracked((current) => {
      const next = new Map(current);
      for (const ticker of tickers) {
        const existing = next.get(ticker.symbol);
        next.set(ticker.symbol, {
          price: ticker.price,
          previous: existing ? existing.price : ticker.price,
          first: existing ? existing.first : ticker.price,
          history: [...(existing?.history ?? []), ticker.price].slice(-48),
          updatedAt: ticker.updated_at ?? updatedAt,
        });
      }
      return next;
    });
  }, [tickers, updatedAt]);

  const marketRows: MarketRow[] = useMemo(
    () =>
      tickers.map((ticker) => ({
        symbol: ticker.symbol,
        price: ticker.price,
        trend: ticker.trend,
        structure: ticker.structure,
        score: ticker.score,
        status: ticker.status,
        updatedAt: ticker.updated_at,
      })),
    [tickers],
  );

  const statusTone =
    status === "live" ? "emerald" : status === "connecting" || status === "reconnecting" ? "amber" : "rose";
  const connected = status === "live";
  const totalMoves = useMemo(() => {
    let up = 0;
    let down = 0;
    for (const item of tracked.values()) {
      if (item.price > item.previous) up += 1;
      else if (item.price < item.previous) down += 1;
    }
    return { up, down };
  }, [tracked]);

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow={
          <>
            <Radio className="h-3 w-3" /> Exchange feed
          </>
        }
        title="Live prices"
        description="WebSocket ticker feed backed by the latest engine scan. If the socket drops, the page falls back to a REST snapshot."
        actions={
          <>
            <Badge tone={statusTone} dot pulse={connected}>
              {status === "live"
                ? "WebSocket live"
                : status === "reconnecting"
                  ? "Reconnecting"
                  : status === "unauthorized"
                    ? "Token rejected"
                    : status === "connecting"
                      ? "Connecting"
                      : "REST fallback"}
            </Badge>
            <Button variant="secondary" size="sm" icon={RefreshCw} onClick={reconnect}>
              Reconnect
            </Button>
          </>
        }
      />

      {error ? (
        <AlertBanner
          tone={status === "unauthorized" ? "rose" : "amber"}
          title={status === "unauthorized" ? "Live socket not authorized" : "Live stream unavailable"}
          action={
            <Button size="sm" variant="ghost" onClick={reconnect}>
              Retry
            </Button>
          }
        >
          {error}
        </AlertBanner>
      ) : null}

      <section className="grid grid-cols-2 gap-3 xl:grid-cols-4">
        <StatCard
          label="Feed status"
          value={connected ? "Live" : "Fallback"}
          hint={connected ? "Streaming from the engine hub" : "Polling the REST snapshot every 15s"}
          icon={connected ? Wifi : WifiOff}
          tone={connected ? "emerald" : "amber"}
        />
        <StatCard
          label="Instruments"
          value={tickers.length}
          hint="Configured scanner symbols"
          icon={Rss}
          tone="sky"
        />
        <StatCard
          label="Ticker changes"
          value={`${totalMoves.up}↑ / ${totalMoves.down}↓`}
          hint="Compared with the previous frame"
          icon={ArrowUpRight}
          tone="violet"
        />
        <StatCard
          label="Last frame"
          value={fmtTime(updatedAt)}
          hint={intervalSeconds ? `Push interval ${intervalSeconds}s` : "Event driven"}
          icon={RefreshCw}
          tone="slate"
        />
      </section>

      {tickers.length ? (
        <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {tickers.map((ticker) => {
            const item = tracked.get(ticker.symbol);
            const previous = item?.previous ?? ticker.price;
            const changePct = previous ? ((ticker.price - previous) / previous) * 100 : 0;
            const first = item?.first ?? ticker.price;
            const sessionPct = first ? ((ticker.price - first) / first) * 100 : 0;
            const tone = scoreTone(ticker.score);
            const positive = changePct >= 0;
            return (
              <Card key={ticker.symbol} className="p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="text-sm font-semibold text-white">{ticker.symbol}</h3>
                      <Badge tone={trendTone(ticker.trend)} title={ticker.trend}>
                        {compactTrend(ticker.trend)}
                      </Badge>
                    </div>
                    <p
                      className="mt-0.5 truncate text-[10px] uppercase tracking-[0.12em] text-slate-600"
                      title={ticker.status}
                    >
                      {compactStatus(ticker.status)}
                    </p>
                  </div>
                  <span className="num shrink-0 text-right text-lg font-semibold text-white">
                    {fmtPrice(ticker.price)}
                  </span>
                </div>

                <div className="mt-3 flex items-end justify-between gap-3">
                  <div>
                    <span
                      className={cn(
                        "num inline-flex items-center gap-1 text-[11px] font-semibold",
                        positive ? "text-emerald-400" : "text-rose-400",
                      )}
                    >
                      {positive ? (
                        <ArrowUpRight className="h-3 w-3" />
                      ) : (
                        <ArrowDownRight className="h-3 w-3" />
                      )}
                      {positive ? "+" : ""}
                      {changePct.toFixed(3)}%
                    </span>
                    <p className="mt-1 text-[10px] text-slate-600">
                      Session {sessionPct >= 0 ? "+" : ""}
                      {sessionPct.toFixed(3)}%
                    </p>
                  </div>
                  <Sparkline values={item?.history ?? [ticker.price]} width={120} height={36} />
                </div>

                <div className="mt-3 border-t border-slate-800/60 pt-3">
                  <div className="flex items-center justify-between text-[10px] uppercase tracking-[0.12em] text-slate-600">
                    <span>Confluence</span>
                    <span
                      className={cn(
                        "num font-semibold",
                        tone === "emerald"
                          ? "text-emerald-300"
                          : tone === "amber"
                            ? "text-amber-300"
                            : "text-rose-300",
                      )}
                    >
                      {ticker.score.toFixed(1)}
                    </span>
                  </div>
                  <div className="mt-1.5">
                    <ScoreBar score={ticker.score} />
                  </div>
                  <div className="mt-3 flex items-center justify-between text-[10px] text-slate-600">
                    <span className="truncate capitalize" title={ticker.structure}>
                      {compactStructure(ticker.structure)}
                    </span>
                    <span className="shrink-0">{fmtTime(ticker.updated_at)}</span>
                  </div>
                </div>
              </Card>
            );
          })}
        </section>
      ) : (
        <Card>
          <EmptyState
            icon={Radio}
            title={status === "connecting" ? "Connecting to the feed" : "No prices yet"}
            description={
              status === "connecting"
                ? "The browser is negotiating a short-lived WebSocket token with the engine."
                : "Start the engine and confirm the configured symbols. The scanner writes a price on every cycle."
            }
          />
        </Card>
      )}

      <section className="grid gap-3 xl:grid-cols-3">
        <Card className="min-w-0 xl:col-span-2">
          <CardHeader
            title="Scanner snapshot"
            description="The same data the strategy sees during its latest evaluation."
            icon={Rss}
            action={<Badge tone="slate">{marketRows.length} rows</Badge>}
          />
          <MarketsTable rows={marketRows} />
        </Card>

        <Card className="min-w-0">
          <CardHeader
            title="Feed diagnostics"
            description="Transport details for this browser session."
            icon={ShieldCheck}
          />
          <div className="px-4 py-2">
            <KeyValue label="Transport" value={connected ? "WebSocket /ws/prices" : "REST /api/v1/tickers"} />
            <KeyValue label="Status" value={humanize(status)} />
            <KeyValue label="Last frame" value={fmtDateTime(updatedAt)} />
            <KeyValue label="Push interval" value={intervalSeconds ? `${intervalSeconds}s` : "Event driven"} />
            <KeyValue label="Tracked symbols" value={tickers.length} />
          </div>
          <div className="px-4 pb-4">
            <div className="rounded-xl border border-slate-800/70 bg-slate-950/40 px-3 py-3 text-[11px] leading-5 text-slate-500">
              The REST fallback is intentionally slower. It reads the latest scan snapshot
              from SQLite instead of hammering the exchange. Prices update when the engine
              scans.
            </div>
          </div>
        </Card>
      </section>
    </div>
  );
}
