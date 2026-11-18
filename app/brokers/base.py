from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.strategy.confluence import Analysis


@dataclass(slots=True)
class Fill:
    price: float
    qty: float
    fee: float
    external_id: str = ""


class BrokerError(RuntimeError):
    pass


class Broker(ABC):
    name = "base"

    @abstractmethod
    def open_position(self, analysis: Analysis, qty: float, leverage: int) -> Fill:
        raise NotImplementedError

    @abstractmethod
    def close_position(
        self, symbol: str, side: str, qty: float, price: float, external_id: str = "", leverage: int = 3
    ) -> Fill:
        raise NotImplementedError
