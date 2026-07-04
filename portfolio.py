"""Portfolio holds positions, PnL, and trade history."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Callable

from instruments import Instrument, InstrumentType
from utils import get_logger

if TYPE_CHECKING:  # avoid a circular import
    from execution import Trade

logger = get_logger(__name__)

PriceFn = Callable[[Instrument], "float | None"]
LotSizeFn = Callable[[str], int]


@dataclass
class Position:
    """Quantity and average price for one instrument."""

    quantity: int = 0
    avg_price: float = 0.0

    def apply(self, signed_quantity: int, price: float, lot_size: int) -> float:
        """Apply a fill and return realized PnL."""
        previous = self.quantity
        realized = 0.0

        opening_or_adding = previous == 0 or (previous > 0) == (signed_quantity > 0)
        if opening_or_adding:
            total_lots = abs(previous) + abs(signed_quantity)
            self.avg_price = (
                abs(previous) * self.avg_price + abs(signed_quantity) * price
            ) / total_lots
        else:
            # Closing or reducing a position.
            closed = min(abs(signed_quantity), abs(previous))
            direction = 1 if previous > 0 else -1
            realized = closed * (price - self.avg_price) * direction * lot_size
            if abs(signed_quantity) > abs(previous):
                self.avg_price = price  # flipped position

        self.quantity = previous + signed_quantity
        return realized


class Portfolio:
    """Holdings, realized PnL, trade history, and MTM snapshots."""

    def __init__(self) -> None:
        self._positions: dict[Instrument, Position] = {}
        self.realized_pnl: float = 0.0
        self.trades: list["Trade"] = []

    def net_quantity(self, instrument: Instrument) -> int:
        position = self._positions.get(instrument)
        return position.quantity if position else 0

    def apply_trade(self, trade: "Trade", lot_size: int) -> None:
        """Record a trade and update PnL."""
        position = self._positions.get(trade.instrument)
        if position is None:
            position = Position()
            self._positions[trade.instrument] = position

        self.realized_pnl += position.apply(trade.signed_quantity, trade.price, lot_size)
        self.trades.append(trade)

        if position.quantity == 0:  # remove empty positions
            del self._positions[trade.instrument]

    def open_positions(self) -> dict[Instrument, Position]:
        return dict(self._positions)

    def open_options(self, underlying: str) -> list[Instrument]:
        """Option positions for one underlying."""
        return [
            inst
            for inst, pos in self._positions.items()
            if inst.instrument_type is InstrumentType.OPTION
            and inst.underlying == underlying
            and pos.quantity != 0
        ]

    def unrealized_pnl(self, price_fn: PriceFn, lot_size_fn: LotSizeFn) -> float:
        """Mark open positions to market."""
        total = 0.0
        for inst, pos in self._positions.items():
            price = price_fn(inst)
            if price is None:
                continue
            total += (price - pos.avg_price) * pos.quantity * lot_size_fn(inst.underlying)
        return total

    def snapshot(self, timestamp: datetime, price_fn: PriceFn, lot_size_fn: LotSizeFn) -> dict:
        """One MTM row with PnL and holdings."""
        unrealized = self.unrealized_pnl(price_fn, lot_size_fn)
        return {
            "timestamp": timestamp,
            "realized_pnl": self.realized_pnl,
            "unrealized_pnl": unrealized,
            "total_pnl": self.realized_pnl + unrealized,
            "num_open_positions": len(self._positions),
            "holdings": ",".join(sorted(inst.symbol for inst in self._positions)),
        }


class PortfolioView:
    """Read-only view for strategies."""

    def __init__(self, portfolio: Portfolio) -> None:
        self._portfolio = portfolio

    def net_quantity(self, instrument: Instrument) -> int:
        return self._portfolio.net_quantity(instrument)

    def open_options(self, underlying: str) -> list[Instrument]:
        return self._portfolio.open_options(underlying)
