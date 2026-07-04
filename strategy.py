"""Trading strategies."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime

from execution import Order, Side
from instruments import Instrument, OptionChain, OptionType
from portfolio import PortfolioView


@dataclass(frozen=True)
class StrategyContext:
    """Inputs for one strategy step."""

    timestamp: datetime
    underlying: str
    futures_price: float
    option_chain: OptionChain
    portfolio: PortfolioView


class Strategy(ABC):
    """Base strategy class."""

    @property
    def name(self) -> str:
        return type(self).__name__

    def on_day_start(self, underlying: str, day: date) -> None:
        """Per-day hook."""

    @abstractmethod
    def generate_signals(self, context: StrategyContext) -> list[Order]:
        """Return orders for this step."""

    def on_day_end(self, context: StrategyContext) -> list[Order]:
        """Default end-of-day exit."""
        return self._orders_to_reach(set(), context)

    def _orders_to_reach(
        self, desired: set[Instrument], context: StrategyContext
    ) -> list[Order]:
        """Convert desired holdings into orders."""
        held = set(context.portfolio.open_options(context.underlying))

        orders: list[Order] = []
        for instrument in held - desired:  # Close no-longer-needed positions.
            quantity = context.portfolio.net_quantity(instrument)
            orders.append(Order(instrument, Side.SELL, abs(quantity)))
        for instrument in desired - held:  # Open missing positions.
            orders.append(Order(instrument, Side.BUY, 1))
        return orders


class NearestStrikeLongStraddleStrategy(Strategy):
    """Hold the nearest-strike straddle."""

    def generate_signals(self, context: StrategyContext) -> list[Order]:
        chain = context.option_chain
        strike = chain.nearest_strike(context.futures_price)
        desired = {
            chain.option(strike, OptionType.CALL),
            chain.option(strike, OptionType.PUT),
        }
        return self._orders_to_reach(desired, context)


class NearestStrikeLongCallStrategy(Strategy):
    """Hold only the nearest-strike call."""

    def generate_signals(self, context: StrategyContext) -> list[Order]:
        chain = context.option_chain
        strike = chain.nearest_strike(context.futures_price)
        desired = {chain.option(strike, OptionType.CALL)}
        return self._orders_to_reach(desired, context)


# Strategy registry.
STRATEGIES: dict[str, type[Strategy]] = {
    "straddle": NearestStrikeLongStraddleStrategy,
    "call": NearestStrikeLongCallStrategy,
}
