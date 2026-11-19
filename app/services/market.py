from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from collections import defaultdict, deque

import httpx

from app.config import get_settings
from app.strategy.types import Candle, MEXC_INTERVALS, timeframe_seconds

logger = logging.getLogger(__name__)

MEXC_FUTURES_BASE = "https://contract.mexc.com"
BINANCE_BASE = "https://fapi.binance.com"


def normalize_symbol(raw: str, exchange: str = "mexc") -> str:
    """Accept BTCUSDT, BTC_USDT, BTC/USDT or BTC/USDT:USDT and return a ccxt swap symbol.

    The ``exchange`` argument is read from ``get_settings().exchange``
    (``"mexc"``, ``"binance"``, ``"bybit"``, ``"pepperstone"`` or ``"ctrader"``)
    so the same raw token works for all supported exchanges.
    """
    value = (raw or "").strip().upper().replace("_", "/").replace("-", "/")
    if not value:
        return ""
    if ":" in value:
        base, settle = value.split(":", 1)
        return f"{base}:{settle}"
    if "/" in value:
        parts = value.split("/", 1)
        base, quote = parts[0], parts[1]
        if exchange == "binance":
            return f"{base}/{quote}"
        if exchange == "bybit":
            # Bybit USDT-M linear inverse format
            return f"{base}/{quote}:USDT"
        if exchange == "pepperstone":
            # Pepperstone uses the same format as MEXC
            return f"{base}/{quote}:USDT"
        if exchange == "ctrader":
            # cTrader uses symbol format like "BTCUSD"
            return f"{base}{quote}"
        return f"{base}/{quote}:USDT"
    for quote in ("USDT", "USDC", "USD"):
        if value.endswith(quote) and len(value) > len(quote):
            base = value[: -len(quote)]
            if exchange == "binance":
                return f"{base}/{quote}"
            if exchange == "bybit":
                return f"{base}/{quote}:USDT"
            if exchange == "pepperstone":
                return f"{base}/{quote}:USDT"
            if exchange == "ctrader":
                return f"{base}{quote}"
            return f"{base}/{quote}:USDT"
    if exchange == "binance":
        return f"{value}/USDT"
    if exchange == "bybit":
        return f"{value}/USDT:USDT"
    if exchange == "pepperstone":
        return f"{value}/USDT:USDT"
    if exchange == "ctrader":
        return f"{value}/USD"
    return f"{value}/USDT:USDT"


def display_symbol(symbol: str) -> str:
    return symbol.split(":", 1)[0]


def contract_symbol(symbol: str) -> str:
    pair = display_symbol(normalize_symbol(symbol))
    return pair.replace("/", "_")


class MarketData:
    """Public market data for supported exchanges (MEXC, Binance, Bybit, Pepperstone, cTrader)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._exchange = None
        self._cache: dict[tuple[str, str, int], tuple[float, list[Candle]]] = {}
        self._cache_ttl = get_settings().market_cache_seconds
        self._exchange_name = get_settings().exchange

    def _get_exchange(self):
        if self._exchange is None or self._exchange_name != get_settings().exchange:
            import ccxt

            exchange_id = self._exchange_name or "mexc"
            cfg = {"enableRateLimit": True, "timeout": 20000}
            if exchange_id == "binance":
                cfg["defaultType"] = "spot"
                cfg["options"] = {"adjustForTimeDifference": True}
            elif exchange_id == "bybit":
                cfg["defaultType"] = "inverse"
                cfg["options"] = {"adjustForTimeDifference": True}
            elif exchange_id == "pepperstone":
                cfg["defaultType"] = "cash"
                cfg["options"] = {"adjustForTimeDifference": True}
            elif exchange_id == "ctrader":
                cfg["defaultType"] = "cfd"
                cfg["options"] = {"adjustForTimeDifference": True}
            else:
                cfg["options"] = {
                    "defaultType": "swap",
                    "adjustForTimeDifference": True,
                }
            exchange_class = getattr(ccxt, exchange_id)
            self._exchange = exchange_class(cfg)
        return self._exchange

    def _fetch_ccxt(self, symbol: str, timeframe: str, limit: int) -> list[Candle]:
        exchange = self._get_exchange()
        with self._lock:
            exchange.load_markets()
            if symbol not in exchange.markets:
                raise ValueError(f"{symbol} not found in MEXC markets")
            rows = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit + 2)
        return [
            Candle(
                ts=int(row[0] // 1000),
                open=float(row[1]),
                high=float(row[2]),
                low=float(row[3]),
                close=float(row[4]),
                volume=float(row[5] or 0.0),
            )
            for row in rows
        ]

    def _fetch_rest(self, symbol: str, timeframe: str, limit: int) -> list[Candle]:
        interval = MEXC_INTERVALS.get(timeframe)
        if interval is None:
            raise ValueError(f"No MEXC interval mapping for {timeframe}")
        url = f"{MEXC_FUTURES_BASE}/api/v1/contract/kline/{contract_symbol(symbol)}"
        response = httpx.get(url, params={"interval": interval}, timeout=20.0)
        response.raise_for_status()
        payload = response.json()
        if not payload.get("success"):
            raise ValueError(f"MEXC REST error: {payload}")
        data = payload.get("data") or {}
        times = data.get("time") or []
        candles = [
            Candle(
                ts=int(times[i]),
                open=float(data["open"][i]),
                high=float(data["high"][i]),
                low=float(data["low"][i]),
                close=float(data["close"][i]),
                volume=float((data.get("vol") or [0] * len(times))[i] or 0.0),
            )
            for i in range(len(times))
        ]
        return candles[-limit:]

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 300, use_cache: bool = True) -> list[Candle]:
        symbol = normalize_symbol(symbol)
        key = (symbol, timeframe, limit)
        
        # Enhanced caching with change detection
        if use_cache:
            ohlcv_cache = get_ohlcv_cache()
            cached_data = ohlcv_cache.get(key)
            
            if cached_data is not None:
                # Check if data has changed
                try:
                    # For OHLCV data, check if last candle timestamp has changed
                    # indicating new data is available
                    last_cached_candle = cached_data[-1] if cached_data else None
                    if last_cached_candle:
                        # Check if there are newer candles available
                        try:
                            fresh_candles = self._fetch_ccxt(symbol, timeframe, min(10, limit))
                            latest_fresh_candle = fresh_candles[-1]
                            
                            # If fresh data is newer than cached data, fetch complete dataset
                            if latest_fresh_candle.ts > last_cached_candle.ts:
                                # Cache has changed, fetch fresh data
                                return self._fetch_and_cache_ohlcv(symbol, timeframe, limit, ohlcv_cache, key)
                            else:
                                # Use cached data
                                return cached_data
                        except Exception as exc:
                            logger.debug("Change detection failed for %s %s: %s, using cache", symbol, timeframe, exc)
                            return cached_data
                except Exception as exc:
                    logger.warning("Change detection failed for %s %s: %s, falling back to fresh fetch", symbol, timeframe, exc)
                    return self._fetch_and_cache_ohlcv(symbol, timeframe, limit, ohlcv_cache, key)
        
        return self._fetch_and_cache_ohlcv(symbol, timeframe, limit, ohlcv_cache, key)
    
    def _fetch_and_cache_ohlcv(self, symbol: str, timeframe: str, limit: int, 
                              ohlcv_cache: MarketDataCache, key: tuple) -> list[Candle]:
        """Fetch OHLCV data and cache it with enhanced tracking."""
        try:
            candles = self._fetch_ccxt(symbol, timeframe, limit)
        except Exception as exc:
            logger.warning("ccxt fetch failed for %s %s: %s; trying REST", symbol, timeframe, exc)
            candles = self._fetch_rest(symbol, timeframe, limit)

        now_epoch = int(datetime.now(timezone.utc).timestamp())
        closed = [c for c in candles if c.ts + timeframe_seconds(timeframe) <= now_epoch]
        result = closed[-limit:]
        if not result:
            raise ValueError(f"No closed candles returned for {symbol} {timeframe}")
        
        # Cache with extended TTL for OHLCV data
        ohlcv_cache.set(key, result, ttl=self._cache_ttl)
        return result

    def fetch_history(self, symbol: str, timeframe: str, days: int, max_candles: int = 30000) -> list[Candle]:
        """Paginated history for backtests. Closed candles only."""
        symbol = normalize_symbol(symbol, self._exchange_name)
        tf_sec = timeframe_seconds(timeframe)
        now_epoch = int(datetime.now(timezone.utc).timestamp())
        start = now_epoch - max(1, days) * 86400

        try:
            exchange = self._get_exchange()
            with self._lock:
                exchange.load_markets()
                if symbol not in exchange.markets:
                    raise ValueError(f"{symbol} not found in {self._exchange_name} markets")
                collected: dict[int, Candle] = {}
                since_ms = start * 1000
                tf_ms = tf_sec * 1000
                for _ in range(40):
                    rows = exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=since_ms, limit=1000)
                    if not rows:
                        break
                    for row in rows:
                        candle = Candle(
                            ts=int(row[0] // 1000),
                            open=float(row[1]),
                            high=float(row[2]),
                            low=float(row[3]),
                            close=float(row[4]),
                            volume=float(row[5] or 0.0),
                        )
                        collected[candle.ts] = candle
                    since_ms = int(rows[-1][0]) + tf_ms
                    if len(rows) < 1000 or since_ms >= now_epoch * 1000 or len(collected) >= max_candles:
                        break
        except Exception as exc:
            logger.warning("ccxt history failed for %s %s: %s; trying REST", symbol, timeframe, exc)
            collected = self._fetch_rest_history(symbol, timeframe, start, now_epoch, max_candles)

        expected = min(max_candles, max(1, (now_epoch - start) // tf_sec))
        if len(collected) < expected * 0.85:
            logger.info(
                "History coverage for %s %s is %s/%s candles; merging REST history",
                symbol,
                timeframe,
                len(collected),
                expected,
            )
            try:
                collected.update(self._fetch_rest_history(symbol, timeframe, start, now_epoch, max_candles))
            except Exception as exc:
                logger.warning("REST history fallback failed for %s %s: %s", symbol, timeframe, exc)

        candles = [c for ts, c in sorted(collected.items()) if ts + tf_sec <= now_epoch]
        if not candles:
            raise ValueError(f"No history returned for {symbol} {timeframe}")
        return candles

    def _fetch_rest_history(
        self, symbol: str, timeframe: str, start: int, end: int, max_candles: int
    ) -> dict[int, Candle]:
        interval = MEXC_INTERVALS.get(timeframe)
        if interval is None:
            raise ValueError(f"No MEXC interval mapping for {timeframe}")
        tf_sec = timeframe_seconds(timeframe)
        window = 2000 * tf_sec
        symbol_normalized = normalize_symbol(symbol, self._exchange_name)
        if self._exchange_name == "binance":
            # Binance REST kline endpoint
            url = "https://fapi.binance.com/fapi/v1/klines"
        else:
            url = f"{MEXC_FUTURES_BASE}/api/v1/contract/kline/{contract_symbol(symbol)}"
        collected: dict[int, Candle] = {}
        cursor = start
        for _ in range(40):
            if cursor >= end or len(collected) >= max_candles:
                break
            params = {"interval": interval, "start": cursor, "end": min(cursor + window, end)}
            if self._exchange_name == "binance":
                params["symbol"] = symbol_normalized.replace("/", "").replace(":", "")
                params["limit"] = 1000
            else:
                params["interval"] = interval
            response = httpx.get(url, params=params, timeout=30.0)
            response.raise_for_status()
            payload = response.json()
            if self._exchange_name == "binance":
                data = payload.get("k") or {}
                times = data.get("t") or []
                open_p = data.get("o") or []
                high_p = data.get("h") or []
                low_p = data.get("l") or []
                close_p = data.get("c") or []
                vol_p = data.get("v") or []
                for i in range(len(times)):
                    candle = Candle(
                        ts=int(times[i] / 1000),
                        open=float(open_p[i]),
                        high=float(high_p[i]),
                        low=float(low_p[i]),
                        close=float(close_p[i]),
                        volume=float(vol_p[i] or 0.0),
                    )
                    collected[candle.ts] = candle
            else:
                data = payload.get("data") or {}
                times = data.get("time") or []
                for i in range(len(times)):
                    candle = Candle(
                        ts=int(times[i]),
                        open=float(data["open"][i]),
                        high=float(data["high"][i]),
                        low=float(data["low"][i]),
                        close=float(data["close"][i]),
                        volume=float((data.get("vol") or [0] * len(times))[i] or 0.0),
                    )
                    collected[candle.ts] = candle
            if not times:
                break
            cursor = max(times) + tf_sec if self._exchange_name != "binance" else int(times[-1] / 1000) + tf_sec
        return collected

    def fetch_price(self, symbol: str) -> float:
        symbol = normalize_symbol(symbol, self._exchange_name)
        price_cache = get_symbol_prices_cache()
        cache_key = f"price:{symbol}"
        
        # Check cache first
        cached_price = price_cache.get(cache_key)
        if cached_price is not None:
            return cached_price

        try:
            exchange = self._get_exchange()
            with self._lock:
                exchange.load_markets()
                ticker = exchange.fetch_ticker(symbol)
            price = float(ticker.get("last") or 0.0)
            if price > 0:
                # Cache the price
                price_cache.set(cache_key, price, ttl=30)
                return price
        except Exception as exc:
            logger.warning("ccxt ticker failed for %s: %s; trying REST", symbol, exc)

        # Fallback to REST API
        if self._exchange_name == "binance":
            url = "https://fapi.binance.com/fapi/v1/ticker/price"
            params = {"symbol": symbol.replace("/", "").replace(":", "").upper()}
        else:
            url = f"{MEXC_FUTURES_BASE}/api/v1/contract/ticker"
            params = {"symbol": contract_symbol(symbol)}
        
        try:
            response = httpx.get(url, params=params, timeout=15.0)
            response.raise_for_status()
            data = response.json()
            price = float(data.get("lastPrice") or 0.0)
            if price <= 0:
                raise ValueError(f"Could not fetch price for {symbol}")
            
            # Cache the price
            price_cache.set(cache_key, price, ttl=30)
            return price
        except Exception as exc:
            logger.error("Both ccxt and REST price fetch failed for %s: %s", symbol, exc)
            raise


class MarketDataCache:
    """Enhanced market data cache with change detection and multi-level caching."""
    
    def __init__(self, ttl_seconds=30, max_size=1000):
        self.cache = {}
        self.cache_timestamps = {}
        self.ttls = {}
        self.max_size = max_size
        self.cache_hits = 0
        self.cache_misses = 0
        self.change_detectors = {}
        self.last_hash = {}
        
        # Performance tracking
        self.access_patterns = defaultdict(lambda: deque(maxlen=100))
        self.failure_counts = defaultdict(int)
    
    def set(self, key, value, ttl=None):
        """Set cache entry with TTL."""
        if len(self.cache) >= self.max_size:
            self._evict_oldest()
        
        self.cache[key] = value
        self.cache_timestamps[key] = time.monotonic()
        self.ttls[key] = ttl or self.default_ttl
        
        # Track access pattern
        self.access_patterns[key].append(time.monotonic())
    
    def get(self, key, default=None):
        """Get cache entry with TTL check."""
        now = time.monotonic()
        
        # Check if entry exists and not expired
        if key in self.cache:
            timestamp = self.cache_timestamps[key]
            ttl = self.ttls.get(key)
            
            if ttl is None or (now - timestamp) < ttl:
                self.cache_hits += 1
                return self.cache[key]
            else:
                # Expired, remove it
                del self.cache[key]
                del self.cache_timestamps[key]
                if key in self.ttls:
                    del self.ttls[key]
        
        self.cache_misses += 1
        return default
    
    def _evict_oldest(self):
        """Evict oldest cache entries when at max capacity."""
        if not self.cache:
            return
        
        # Find oldest entry
        oldest_key = min(self.cache_timestamps.keys(), 
                        key=lambda k: self.cache_timestamps[k])
        
        # Remove oldest and its associated data
        del self.cache[oldest_key]
        del self.cache_timestamps[oldest_key]
        if oldest_key in self.ttls:
            del self.ttls[oldest_key]
        if oldest_key in self.access_patterns:
            del self.access_patterns[oldest_key]
    
    def has_changed(self, key, new_data):
        """Check if data has changed since last cache entry."""
        cached = self.get(key)
        if cached is None:
            return True
        
        # Simple hash comparison for detecting changes
        try:
            # Convert to string representation for comparison
            cached_str = str(cached)
            current_hash = hash((cached_str, len(cached_str)))
            
            if current_hash != self.last_hash.get(key):
                self.last_hash[key] = current_hash
                return True
        except Exception:
            # If hashing fails, assume changed
            return True
        
        return False
    
    def get_stats(self):
        """Get cache performance statistics."""
        total_requests = self.cache_hits + self.cache_misses
        hit_rate = (self.cache_hits / total_requests * 100) if total_requests > 0 else 0
        
        return {
            'hits': self.cache_hits,
            'misses': self.cache_misses,
            'hit_rate_percent': round(hit_rate, 2),
            'cache_size': len(self.cache),
            'max_size': self.max_size
        }
    
    def clear_pattern(self, pattern):
        """Clear cache entries matching pattern (e.g., symbol prefix)."""
        keys_to_remove = [k for k in self.cache.keys() if pattern in k]
        for key in keys_to_remove:
            del self.cache[key]
            del self.cache_timestamps[key]
            if key in self.ttls:
                del self.ttls[key]
            if key in self.access_patterns:
                del self.access_patterns[key]

# Global cache instances for different data types
_ohlcv_cache = None
_symbol_prices_cache = None
_ticker_snapshot_cache = None
_cache_lock = threading.Lock()


def get_ohlcv_cache() -> MarketDataCache:
    global _ohlcv_cache
    with _cache_lock:
        if _ohlcv_cache is None:
            _ohlcv_cache = MarketDataCache(ttl_seconds=60)  # OHLCV cache for 1 minute
        return _ohlcv_cache


def get_symbol_prices_cache() -> MarketDataCache:
    global _symbol_prices_cache
    with _cache_lock:
        if _symbol_prices_cache is None:
            _symbol_prices_cache = MarketDataCache(ttl_seconds=30)  # Prices cache for 30 seconds
        return _symbol_prices_cache


def get_ticker_snapshot_cache() -> MarketDataCache:
    global _ticker_snapshot_cache
    with _cache_lock:
        if _ticker_snapshot_cache is None:
            _ticker_snapshot_cache = MarketDataCache(ttl_seconds=15)  # Ticker cache for 15 seconds
        return _ticker_snapshot_cache


def clear_all_caches():
    """Clear all caches - useful for testing or cache invalidation."""
    global _ohlcv_cache, _symbol_prices_cache, _ticker_snapshot_cache
    with _cache_lock:
        if _ohlcv_cache:
            _ohlcv_cache.cache.clear()
            _ohlcv_cache.cache_timestamps.clear()
            _ohlcv_cache.ttls.clear()
        if _symbol_prices_cache:
            _symbol_prices_cache.cache.clear()
            _symbol_prices_cache.cache_timestamps.clear()
            _symbol_prices_cache.ttls.clear()
        if _ticker_snapshot_cache:
            _ticker_snapshot_cache.cache.clear()
            _ticker_snapshot_cache.cache_timestamps.clear()
            _ticker_snapshot_cache.ttls.clear()


_market: MarketData | None = None
_market_lock = threading.Lock()


def get_market() -> MarketData:
    global _market
    with _market_lock:
        if _market is None:
            _market = MarketData()
        return _market
