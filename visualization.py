"""Plot backtest results."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # Headless backend.
import matplotlib.pyplot as plt  # noqa: E402  (backend set above)
import pandas as pd  # noqa: E402

from metrics import MetricsResult
from utils import get_logger

logger = get_logger(__name__)


def _finish(fig, path: Path) -> Path:
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path


def plot_cumulative_pnl(equity: pd.Series, output_dir: Path) -> Path:
    fig, ax = plt.subplots(figsize=(10, 4))
    equity.plot(ax=ax, color="tab:blue")
    ax.axhline(0, color="grey", linewidth=0.8)
    ax.set_title("Cumulative PnL (mark-to-market)")
    ax.set_ylabel("PnL")
    return _finish(fig, output_dir / "cumulative_pnl.png")


def plot_daily_pnl(daily_pnl: pd.Series, output_dir: Path) -> Path:
    fig, ax = plt.subplots(figsize=(10, 4))
    colors = ["tab:green" if v >= 0 else "tab:red" for v in daily_pnl]
    ax.bar([d.strftime("%Y-%m-%d") for d in daily_pnl.index], daily_pnl.values, color=colors)
    ax.axhline(0, color="grey", linewidth=0.8)
    ax.set_title("Daily PnL")
    ax.set_ylabel("PnL")
    ax.tick_params(axis="x", rotation=45)
    return _finish(fig, output_dir / "daily_pnl.png")


def plot_drawdown(drawdown: pd.Series, output_dir: Path) -> Path:
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.fill_between(drawdown.index, drawdown.values, 0, color="tab:red", alpha=0.4)
    ax.set_title("Drawdown")
    ax.set_ylabel("PnL below peak")
    return _finish(fig, output_dir / "drawdown.png")


def plot_trades_per_day(trades, output_dir: Path) -> Path:
    counts = Counter(trade.timestamp.date() for trade in trades)
    ordered = sorted(counts.items())
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.bar([d.strftime("%Y-%m-%d") for d, _ in ordered], [c for _, c in ordered], color="tab:purple")
    ax.set_title("Trades per day")
    ax.set_ylabel("Number of trades")
    ax.tick_params(axis="x", rotation=45)
    return _finish(fig, output_dir / "trades_per_day.png")


def render_all(metrics: MetricsResult, trades, output_dir: Path) -> list[Path]:
    """Render all plots."""
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = [
        plot_cumulative_pnl(metrics.equity_curve, output_dir),
        plot_daily_pnl(metrics.daily_pnl, output_dir),
        plot_drawdown(metrics.drawdown, output_dir),
        plot_trades_per_day(trades, output_dir),
    ]
    logger.info("Wrote %d plots to %s", len(paths), output_dir)
    return paths
