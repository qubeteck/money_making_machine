from __future__ import annotations

from app.brokers.base import Broker, Fill
from app.strategy.confluence import Analysis


class PaperBroker(Broker):
    """Simulated fills with slippage and taker fees. Default execution mode."""

    name = "paper"

    def __init__(self, fee_pct: float = 0.05, slippage_pct: float = 0.02) -> None:
        self.fee_pct = max(0.0, fee_pct) / 100.0
        self.slippage_pct = max(0.0, slippage_pct) / 100.0

    def open_position(self, analysis: Analysis, qty: float, leverage: int) -> Fill:
        # Buys fill a little high, sells a little low.
        direction = 1 if analysis.side == "long" else -1
        price = analysis.entry * (1 + direction * self.slippage_pct)
        fee = price * qty * self.fee_pct
        return Fill(price=price, qty=qty, fee=fee)

    def close_position(
        self, symbol: str, side: str, qty: float, price: float, external_id: str = "", leverage: int = 3
    ) -> Fill:
        direction = 1 if side == "long" else -1
        fill = price * (1 - direction * self.slippage_pct)
        fee = fill * qty * self.fee_pct
        return Fill(price=fill, qty=qty, fee=fee)
