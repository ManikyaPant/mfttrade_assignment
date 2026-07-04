"""Order execution and trade recording."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from config import BacktestConfig
from instruments import Instrument
from utils import get_logger

if TYPE_CHECKING:  # avoid a circular import
    from portfolio import Portfolio

logger = get_logger(__name__)


class Side(int, Enum):
    """Trade direction."""

    BUY = 1
    SELL = -1

    def __str__(self) -> str:
        return self.name


@dataclass(frozen=True)
class Order:
    """Trade request in lots."""

    instrument: Instrument
    side: Side
    quantity: int


@dataclass(frozen=True)
class Trade:
    """An executed fill."""

    timestamp: datetime
    instrument: Instrument
    side: Side
    price: float
    quantity: int

    @property
    def signed_quantity(self) -> int:
        # Positive for buys, negative for sells.
        return self.side.value * self.quantity


class ExecutionEngine:
    """Validate orders and apply fills."""

    def __init__(self, config: BacktestConfig, portfolio: "Portfolio") -> None:
        self._config = config
        self._portfolio = portfolio

    def execute(
        self, order: Order, fill_price: float | None, timestamp: datetime
    ) -> Trade | None:
        """Fill an order and return the trade."""
        if fill_price is None or math.isnan(fill_price):
            # No price means no fill.
            logger.warning("No price for %s at %s; order skipped", order.instrument, timestamp)
            return None

        quantity = self._permitted_quantity(order)
        if quantity <= 0:
            return None

        trade = Trade(timestamp, order.instrument, order.side, float(fill_price), quantity)
        lot_size = self._config.lot_size(order.instrument.underlying)
        self._portfolio.apply_trade(trade, lot_size)
        return trade

    def _permitted_quantity(self, order: Order) -> int:
        """Clamp to limits and holdings."""
        current = self._portfolio.net_quantity(order.instrument)
        if order.side is Side.BUY:
            headroom = self._config.max_position_per_instrument - current
            if headroom <= 0:
                logger.debug("Buy skipped for %s; limit reached", order.instrument)
                return 0
            return min(order.quantity, headroom)

        # Long-only sells.
        if current <= 0:
            logger.debug("Sell skipped for %s; nothing held", order.instrument)
            return 0
        return min(order.quantity, current)
