"""Backtester event loop."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

import pandas as pd

from config import BacktestConfig
from data_loader import DataError, DataLoader
from execution import ExecutionEngine, Order
from instruments import Instrument, InstrumentType
from portfolio import Portfolio, PortfolioView
from strategy import Strategy, StrategyContext
from utils import get_logger

logger = get_logger(__name__)


class PriceBook:
    """Prices for one day."""

    def __init__(self, loader: DataLoader, day: date) -> None:
        self._loader = loader
        self._day = day

    def _asof(self, frame: pd.DataFrame, timestamp: datetime) -> float | None:
        value = frame["price"].asof(timestamp)
        return None if pd.isna(value) else float(value)

    def price(self, instrument: Instrument, timestamp: datetime) -> float | None:
        try:
            if instrument.instrument_type is InstrumentType.FUTURE:
                frame = self._loader.load_futures(instrument.underlying, self._day)
            else:
                frame = self._loader.load_option(instrument, self._day)
        except DataError:
            return None
        return self._asof(frame, timestamp)


@dataclass
class BacktestResult:
    """Backtest output."""

    trades: list
    mtm_history: pd.DataFrame


class Backtester:
    """Runs a strategy over the data."""

    def __init__(
        self,
        config: BacktestConfig,
        loader: DataLoader,
        strategy: Strategy,
        portfolio: Portfolio,
        execution: ExecutionEngine,
    ) -> None:
        self._config = config
        self._loader = loader
        self._strategy = strategy
        self._portfolio = portfolio
        self._execution = execution
        self._snapshots: list[dict] = []

    def run(self) -> BacktestResult:
        days = self._loader.trading_days()
        logger.info("Running %s over %d day(s)", self._strategy.name, len(days))
        for day in days:
            self._run_day(day)

        history = pd.DataFrame(self._snapshots)
        if not history.empty:
            history = history.set_index("timestamp").sort_index()
        return BacktestResult(trades=self._portfolio.trades, mtm_history=history)

    def _run_day(self, day: date) -> None:
        book = PriceBook(self._loader, day)
        chains, events = self._prepare_day(day)
        if not events:
            logger.warning("No tradable data on %s", day)
            return

        # Process events in time order.
        events.sort(key=lambda event: (event[0], event[1]))
        for timestamp, underlying, futures_price in events:
            context = StrategyContext(
                timestamp, underlying, futures_price, chains[underlying],
                PortfolioView(self._portfolio),
            )
            self._process(self._strategy.generate_signals(context), timestamp, book)
            self._snapshot(timestamp, book)

        self._close_day(events[-1][0], chains, book)

    def _prepare_day(self, day: date):
        """Load futures, chains, and events for one day."""
        chains: dict[str, object] = {}
        events: list[tuple[datetime, str, float]] = []
        for underlying in self._config.underlyings:
            try:
                futures = self._loader.load_futures(underlying, day)
            except DataError as exc:
                logger.warning("Skipping %s on %s: %s", underlying, day, exc)
                continue
            chain = self._loader.option_chain(day, underlying)
            if not chain:
                logger.warning("No option chain for %s on %s", underlying, day)
                continue

            chains[underlying] = chain
            self._strategy.on_day_start(underlying, day)
            for timestamp, price in futures["price"].items():
                events.append((timestamp.to_pydatetime(), underlying, float(price)))
        return chains, events

    def _close_day(self, last_timestamp: datetime, chains: dict, book: PriceBook) -> None:
        """Flatten positions and take a final snapshot."""
        for underlying, chain in chains.items():
            context = StrategyContext(
                last_timestamp, underlying, 0.0, chain, PortfolioView(self._portfolio)
            )
            self._process(self._strategy.on_day_end(context), last_timestamp, book)
        self._snapshot(last_timestamp, book)

    def _process(self, orders: list[Order], timestamp: datetime, book: PriceBook) -> None:
        for order in orders:
            fill_price = book.price(order.instrument, timestamp)
            self._execution.execute(order, fill_price, timestamp)

    def _snapshot(self, timestamp: datetime, book: PriceBook) -> None:
        snapshot = self._portfolio.snapshot(
            timestamp,
            price_fn=lambda inst: book.price(inst, timestamp),
            lot_size_fn=self._config.lot_size,
        )
        self._snapshots.append(snapshot)
