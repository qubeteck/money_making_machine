from __future__ import annotations

import logging
import math
import threading
from typing import Any

from app.brokers.base import Broker, BrokerError, Fill
from app.config import get_settings
from app.services.market import normalize_symbol
from app.strategy.confluence import Analysis

logger = logging.getLogger(__name__)


class MexcBroker(Broker):
    """
    Minimal MEXC USDT-perpetual adapter via ccxt.

    Live mode assumptions:
      * API key has futures trading permission and IP whitelist.
      * Account is in one-way position mode (hedged=False).
      * Isolated margin, leverage set per symbol.
      * Stops and targets are managed by this bot, not resting on the exchange.
        Add exchange-side stop orders before increasing size.

    Test with a tiny amount first. This adapter is intentionally conservative,
    but exchange APIs and ccxt versions change.
    """

    name = "mexc"

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.mexc_api_key or not settings.mexc_secret:
            raise BrokerError("MEXC_API_KEY and MEXC_SECRET are not configured")
        try:
            import ccxt
        except ImportError as exc:  # pragma: no cover
            raise BrokerError("ccxt is not installed") from exc

        self._lock = threading.RLock()
        self.exchange = ccxt.mexc(
            {
                "apiKey": settings.mexc_api_key,
                "secret": settings.mexc_secret,
                "password": settings.mexc_password or None,
                "enableRateLimit": True,
                "options": {
                    "defaultType": "swap",
                    "adjustForTimeDifference": True,
                },
            }
        )
        self.exchange.load_markets()

    def _symbol(self, symbol: str) -> str:
        normalized = normalize_symbol(symbol)
        if normalized not in self.exchange.markets:
            raise BrokerError(f"{normalized} is not a MEXC futures market")
        return normalized

    def _set_leverage(self, symbol: str, leverage: int) -> None:
        try:
            with self._lock:
                self.exchange.set_leverage(int(leverage), symbol)
        except Exception as exc:  # exchange may keep existing leverage; don't hide the reason
            logger.warning("Could not set leverage for %s: %s", symbol, exc)

    def _to_contracts(self, symbol: str, base_qty: float) -> float:
        """The bot sizes in base units; MEXC orders use contract counts."""
        market = self.exchange.market(symbol)
        contract_size = float(market.get("contractSize") or 1.0)
        step = float((market.get("precision") or {}).get("amount") or 1.0)
        raw = base_qty / contract_size
        # Round down so we never exceed the risk-sized quantity.
        contracts = math.floor(raw / step) * step
        min_amount = float(((market.get("limits") or {}).get("amount") or {}).get("min") or step)
        if contracts < min_amount or contracts <= 0:
            raise BrokerError(
                f"{symbol} quantity {base_qty:g} is below the MEXC minimum "
                f"({min_amount:g} contract(s) × {contract_size:g} base = {min_amount * contract_size:g})"
            )
        return contracts

    def _from_contracts(self, symbol: str, contracts: float) -> float:
        market = self.exchange.market(symbol)
        return contracts * float(market.get("contractSize") or 1.0)

    def _enrich_order(self, order: dict, symbol: str) -> dict:
        """MEXC's create response only contains the order id; fetch the fill."""
        order_id = order.get("id")
        if not order_id:
            return order
        try:
            with self._lock:
                fetched = self.exchange.fetch_order(str(order_id), symbol)
        except Exception as exc:
            logger.warning("Could not fetch MEXC order %s for %s: %s", order_id, symbol, exc)
            return order
        merged = dict(order)
        merged.update({key: value for key, value in fetched.items() if value is not None})
        return merged

    def open_position(self, analysis: Analysis, qty: float, leverage: int) -> Fill:
        symbol = self._symbol(analysis.symbol)
        self._set_leverage(symbol, leverage)
        contracts = self._to_contracts(symbol, qty)
        side = "buy" if analysis.side == "long" else "sell"
        params: dict[str, Any] = {
            "leverage": int(leverage),
            "openType": 1,  # isolated
            "hedged": False,  # one-way position mode
        }
        try:
            with self._lock:
                order = self.exchange.create_order(symbol, "market", side, contracts, None, params)
        except Exception as exc:
            raise BrokerError(f"MEXC open order failed: {exc}") from exc

        order = self._enrich_order(order, symbol)
        price = float(order.get("average") or order.get("price") or analysis.entry)
        filled_contracts = float(order.get("filled") or contracts)
        filled_base = self._from_contracts(symbol, filled_contracts)
        if filled_base <= 0:
            raise BrokerError("MEXC open order returned no fill")
        fee = float((order.get("fee") or {}).get("cost") or 0.0)
        if fee <= 0:
            fee = price * filled_base * 0.0005
        return Fill(price=price, qty=filled_base, fee=fee, external_id=str(order.get("id", "")))

    def close_position(
        self, symbol: str, side: str, qty: float, price: float, external_id: str = "", leverage: int = 3
    ) -> Fill:
        symbol = self._symbol(symbol)
        contracts = self._to_contracts(symbol, qty)
        close_side = "sell" if side == "long" else "buy"
        params: dict[str, Any] = {
            "reduceOnly": True,
            "openType": 1,  # isolated
            "leverage": int(leverage),
            "hedged": False,  # one-way position mode
        }
        try:
            with self._lock:
                order = self.exchange.create_order(symbol, "market", close_side, contracts, None, params)
        except Exception as exc:
            raise BrokerError(f"MEXC close order failed: {exc}") from exc

        order = self._enrich_order(order, symbol)
        fill_price = float(order.get("average") or order.get("price") or price)
        filled_contracts = float(order.get("filled") or contracts)
        filled_base = self._from_contracts(symbol, filled_contracts)
        if filled_base <= 0:
            raise BrokerError("MEXC close order returned no fill")
        fee = float((order.get("fee") or {}).get("cost") or 0.0)
        if fee <= 0:
            fee = fill_price * filled_base * 0.0005
        return Fill(price=fill_price, qty=filled_base, fee=fee, external_id=str(order.get("id", "")))

    def equity(self) -> float | None:
        try:
            with self._lock:
                balance = self.exchange.fetch_balance({"type": "swap"})
            raw = balance.get("info") or {}
            for entry in raw.get("data") or []:
                if str(entry.get("currency", "")).upper() == "USDT":
                    equity = float(entry.get("equity") or 0.0)
                    if equity > 0:
                        return equity
            usdt = balance.get("USDT", {})
            total = float(usdt.get("total") or 0.0)
            return total if total > 0 else None
        except Exception as exc:
            logger.warning("Could not fetch MEXC balance: %s", exc)
            return None
