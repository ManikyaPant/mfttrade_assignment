"""Performance metrics."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime

import pandas as pd

from backtester import BacktestResult
from config import BacktestConfig
from execution import Side


@dataclass(frozen=True)
class RoundTrip:
    symbol: str
    entry_time: datetime
    exit_time: datetime
    pnl: float
    holding_seconds: float


@dataclass
class MetricsResult:
    total_trades: int
    round_trips: int
    win_ratio: float
    avg_holding_seconds: float
    realized_pnl: float
    final_unrealized_pnl: float
    total_pnl: float
    max_drawdown: float
    equity_curve: pd.Series
    daily_pnl: pd.Series
    drawdown: pd.Series

    def summary(self) -> dict[str, float | int]:
        return {
            "total_trades": self.total_trades,
            "round_trips": self.round_trips,
            "win_ratio": round(self.win_ratio, 4),
            "avg_holding_seconds": round(self.avg_holding_seconds, 2),
            "realized_pnl": round(self.realized_pnl, 2),
            "final_unrealized_pnl": round(self.final_unrealized_pnl, 2),
            "total_pnl": round(self.total_pnl, 2),
            "max_drawdown": round(self.max_drawdown, 2),
        }


def _round_trips(trades, lot_size_fn) -> list[RoundTrip]:
    """Pair sells with earlier buys."""
    open_lots: dict = defaultdict(deque)
    result: list[RoundTrip] = []
    for trade in trades:
        if trade.side is Side.BUY:
            for _ in range(trade.quantity):
                open_lots[trade.instrument].append((trade.timestamp, trade.price))
            continue
        lot_size = lot_size_fn(trade.instrument.underlying)
        for _ in range(trade.quantity):
            if not open_lots[trade.instrument]:
                break
            entry_time, entry_price = open_lots[trade.instrument].popleft()
            result.append(
                RoundTrip(
                    symbol=trade.instrument.symbol,
                    entry_time=entry_time,
                    exit_time=trade.timestamp,
                    pnl=(trade.price - entry_price) * lot_size,
                    holding_seconds=(trade.timestamp - entry_time).total_seconds(),
                )
            )
    return result


def compute_metrics(result: BacktestResult, config: BacktestConfig) -> MetricsResult:
    trips = _round_trips(result.trades, config.lot_size)
    wins = sum(1 for trip in trips if trip.pnl > 0)
    win_ratio = wins / len(trips) if trips else 0.0
    avg_hold = sum(t.holding_seconds for t in trips) / len(trips) if trips else 0.0

    mtm = result.mtm_history
    if mtm.empty:
        empty = pd.Series(dtype=float)
        return MetricsResult(
            len(result.trades), len(trips), win_ratio, avg_hold,
            0.0, 0.0, 0.0, 0.0, empty, empty, empty,
        )

    mtm = mtm[~mtm.index.duplicated(keep="last")]
    equity = mtm["total_pnl"]
    drawdown = equity - equity.cummax()  # Below the running peak.
    daily = equity.groupby(equity.index.normalize()).last()
    daily_pnl = daily.diff()
    if not daily_pnl.empty:
        daily_pnl.iloc[0] = daily.iloc[0]  # First day starts from zero.

    return MetricsResult(
        total_trades=len(result.trades),
        round_trips=len(trips),
        win_ratio=win_ratio,
        avg_holding_seconds=avg_hold,
        realized_pnl=float(mtm["realized_pnl"].iloc[-1]),
        final_unrealized_pnl=float(mtm["unrealized_pnl"].iloc[-1]),
        total_pnl=float(equity.iloc[-1]),
        max_drawdown=float(drawdown.min()),
        equity_curve=equity,
        daily_pnl=daily_pnl,
        drawdown=drawdown,
    )
