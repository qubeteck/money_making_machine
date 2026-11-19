import { useCallback, useEffect, useRef, useState } from "react";
import { apiGet, errorMessage } from "./api";

export type AsyncState<T> = {
  data: T | null;
  error: string | null;
  loading: boolean;
  lastUpdated: Date | null;
  refresh: (silent?: boolean) => Promise<void>;
};

/**
 * Fetch a resource immediately and then on an interval.
 *
 * `intervalMs = 0` disables background polling. A stable loader ref means pages
 * can pass inline arrow functions without resetting the interval every render.
 */
export function usePolling<T>(
  loader: () => Promise<T>,
  intervalMs = 15_000,
  deps: unknown[] = [],
): AsyncState<T> {
  const loaderRef = useRef(loader);
  loaderRef.current = loader;

  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const mountedRef = useRef(true);

  const refresh = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const value = await loaderRef.current();
      if (!mountedRef.current) return;
      setData(value);
      setError(null);
      setLastUpdated(new Date());
    } catch (cause) {
      if (!mountedRef.current) return;
      if (cause instanceof DOMException && cause.name === "AbortError") return;
      setError(errorMessage(cause));
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    void refresh();
    if (intervalMs <= 0) {
      return () => {
        mountedRef.current = false;
      };
    }
    const timer = window.setInterval(() => {
      void refresh(true);
    }, intervalMs);
    return () => {
      mountedRef.current = false;
      window.clearInterval(timer);
    };
    // Callers opt into re-fetching by adding a dependency. The loader itself
    // is intentionally excluded because it is typically an inline closure.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [intervalMs, refresh, ...deps]);

  return { data, error, loading, lastUpdated, refresh };
}

export function useDocumentTitle(title: string): void {
  useEffect(() => {
    const previous = document.title;
    document.title = `${title} · Money Machine`;
    return () => {
      document.title = previous;
    };
  }, [title]);
}

/** A tiny "now" ticker for relative timestamps and countdowns. */
export function useNow(intervalMs = 30_000): Date {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), intervalMs);
    return () => window.clearInterval(timer);
  }, [intervalMs]);
  return now;
}

export function useTicker(): { tick: number } {
  const [tick, setTick] = useState(0);
  useEffect(() => {
    const timer = window.setInterval(() => setTick((value) => value + 1), 1_000);
    return () => window.clearInterval(timer);
  }, []);
  return { tick };
}

export type TickerStreamStatus = "connecting" | "live" | "reconnecting" | "offline" | "unauthorized";

export interface TickerStream {
  status: TickerStreamStatus;
  tickers: import("./types").Ticker[];
  updatedAt: string | null;
  intervalSeconds: number | null;
  error: string | null;
  reconnect: () => void;
}

/**
 * Connect to `/ws/prices` using a short-lived token, with REST fallback while
 * the socket is down. Browsers cannot attach an Authorization header to a
 * WebSocket handshake, so the token is passed in the query string.
 */
export function useTickerStream(): TickerStream {
  const [status, setStatus] = useState<TickerStreamStatus>("connecting");
  const [tickers, setTickers] = useState<import("./types").Ticker[]>([]);
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);
  const [intervalSeconds, setIntervalSeconds] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  const reconnect = useCallback(() => {
    setError(null);
    setAttempt((value) => value + 1);
  }, []);

  useEffect(() => {
    let socket: WebSocket | null = null;
    let disposed = false;
    let retryTimer: number | undefined;
    let fallbackTimer: number | undefined;
    let retryDelay = 1_500;

    const loadFallback = async () => {
      try {
        const data = await apiGet<import("./types").TickersResponse>("/api/v1/tickers");
        if (disposed) return;
        setTickers(data.tickers ?? []);
        setUpdatedAt(data.updated_at ?? new Date().toISOString());
        setError(null);
      } catch (cause) {
        if (!disposed) setError(errorMessage(cause));
      }
    };

    const startFallback = () => {
      if (fallbackTimer !== undefined) return;
      void loadFallback();
      fallbackTimer = window.setInterval(() => void loadFallback(), 15_000);
    };

    const stopFallback = () => {
      if (fallbackTimer !== undefined) {
        window.clearInterval(fallbackTimer);
        fallbackTimer = undefined;
      }
    };

    const connect = async () => {
      if (disposed) return;
      setStatus((current) => (current === "live" ? current : "connecting"));
      let wsUrl = "/ws/prices";
      let token = "";
      try {
        const credentials = await apiPostWsToken();
        if (disposed) return;
        if (credentials.ws_url) wsUrl = credentials.ws_url;
        token = credentials.token || "";
      } catch (cause) {
        if (disposed) return;
        const message = errorMessage(cause);
        if (message.toLowerCase().includes("unauthorized")) {
          setStatus("unauthorized");
        } else {
          setStatus("offline");
        }
        setError(message);
        startFallback();
        return;
      }

      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      const query = token ? `?token=${encodeURIComponent(token)}` : "";
      socket = new WebSocket(`${protocol}//${window.location.host}${wsUrl}${query}`);

      socket.addEventListener("open", () => {
        if (disposed) return;
        retryDelay = 1_500;
        setStatus("live");
        setError(null);
        stopFallback();
      });

      socket.addEventListener("message", (event) => {
        if (disposed) return;
        try {
          const payload = JSON.parse(event.data) as import("./types").TickerMessage;
          if (payload.type === "connection_established") return;
          if (Array.isArray(payload.tickers)) {
            setTickers(payload.tickers);
            setUpdatedAt(payload.updated_at ?? payload.timestamp ?? new Date().toISOString());
            if (payload.interval_seconds) setIntervalSeconds(payload.interval_seconds);
          }
        } catch {
          // Ignore malformed frames; the next tick will repair the view.
        }
      });

      socket.addEventListener("close", (event) => {
        if (disposed) return;
        if (event.code === 1008) {
          setStatus("unauthorized");
          setError("The WebSocket token was rejected. Sign in again or reconnect.");
          startFallback();
          return;
        }
        setStatus("reconnecting");
        startFallback();
        retryTimer = window.setTimeout(() => {
          retryDelay = Math.min(retryDelay * 1.7, 15_000);
          void connect();
        }, retryDelay);
      });

      socket.addEventListener("error", () => {
        if (disposed) return;
        setStatus((current) => (current === "live" ? "reconnecting" : "offline"));
      });
    };

    void connect();

    return () => {
      disposed = true;
      socket?.close();
      if (retryTimer !== undefined) window.clearTimeout(retryTimer);
      stopFallback();
    };
  }, [attempt]);

  return { status, tickers, updatedAt, intervalSeconds, error, reconnect };
}

async function apiPostWsToken(): Promise<import("./types").WsTokenResponse> {
  const response = await fetch("/auth/ws-token", {
    method: "POST",
    headers: {
      Accept: "application/json",
      "X-Requested-With": "XMLHttpRequest",
    },
    credentials: "same-origin",
  });
  if (!response.ok) {
    if (response.status === 401) throw new Error("Unauthorized");
    throw new Error(`WebSocket token request failed (${response.status})`);
  }
  return (await response.json()) as import("./types").WsTokenResponse;
}
