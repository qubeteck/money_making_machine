from __future__ import annotations

import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.brokers.base import BrokerError
from app.brokers.mexc import MexcBroker


class FakeExchange:
    def fetch_balance(self, params):
        return {
            "info": {"data": [{"currency": "USDT", "equity": "1234.5"}]},
            "USDT": {"total": "1000"},
        }

    def market(self, symbol):
        return {
            "contractSize": 0.0001,
            "precision": {"amount": 1},
            "limits": {"amount": {"min": 1}},
        }

    def fetch_order(self, *args):
        return {}


broker = object.__new__(MexcBroker)
broker.exchange = FakeExchange()
broker._lock = threading.RLock()
print("equity", broker.equity())
print("contracts 0.02", broker._to_contracts("BTC/USDT:USDT", 0.02))
print("base 200", broker._from_contracts("BTC/USDT:USDT", 200))
try:
    broker._to_contracts("BTC/USDT:USDT", 0.00005)
except BrokerError as exc:
    print("minimum rejected:", str(exc)[:80])
print("BROKER SMOKE OK")
