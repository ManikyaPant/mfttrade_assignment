"""Run the backtest.

    python main.py --data-dir /path/to/allData --output-dir ./results --strategy straddle
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from backtester import Backtester
from config import BacktestConfig
from data_loader import DataLoader
from execution import ExecutionEngine
from metrics import compute_metrics
from parser import InstrumentParser
from portfolio import Portfolio
from strategy import STRATEGIES
from utils import configure_logging, get_logger
from visualization import render_all

logger = get_logger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Options straddle backtester")
    parser.add_argument("--data-dir", type=Path, required=True, help="Path to allData root")
    parser.add_argument("--output-dir", type=Path, default=Path("./results"))
    parser.add_argument("--strategy", choices=sorted(STRATEGIES), default="straddle")
    return parser.parse_args()


def _write_outputs(result, metrics, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    trade_rows = [
        {
            "timestamp": trade.timestamp,
            "instrument": trade.instrument.symbol,
            "side": str(trade.side),
            "price": trade.price,
            "quantity": trade.quantity,
        }
        for trade in result.trades
    ]
    pd.DataFrame(trade_rows).to_csv(output_dir / "trades.csv", index=False)
    result.mtm_history.to_csv(output_dir / "mtm.csv")
    render_all(metrics, result.trades, output_dir)


def main() -> None:
    args = parse_args()
    config = BacktestConfig(data_dir=args.data_dir, output_dir=args.output_dir)
    configure_logging(config.log_level)

    # Build the object graph.
    loader = DataLoader(config, InstrumentParser(config))
    portfolio = Portfolio()
    execution = ExecutionEngine(config, portfolio)
    strategy = STRATEGIES[args.strategy]()
    backtester = Backtester(config, loader, strategy, portfolio, execution)

    result = backtester.run()
    metrics = compute_metrics(result, config)
    _write_outputs(result, metrics, config.output_dir)

    logger.info("Backtest complete. Summary:")
    for key, value in metrics.summary().items():
        logger.info("  %-22s %s", key, value)


if __name__ == "__main__":
    main()
