"""Metrics tests."""
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from backtester import BacktestResult
from config import BacktestConfig
from execution import Side, Trade
from instruments import Instrument, InstrumentType, OptionType
from metrics import compute_metrics

CE = Instrument("NIFTY", InstrumentType.OPTION, date(2022, 11, 3), 18000.0, OptionType.CALL)
CFG = BacktestConfig(data_dir=Path("/tmp"), output_dir=Path("/tmp"))  # NIFTY lot.


def _t(second, side, price):
    return Trade(datetime(2022, 11, 1, 9, 15, second), CE, side, price, 1)


def test_round_trips_win_ratio_and_holding_time():
    # One win and one loss.
    trades = [
        _t(0, Side.BUY, 100.0), _t(2, Side.SELL, 110.0),
        _t(4, Side.BUY, 110.0), _t(6, Side.SELL, 105.0),
    ]
    mtm = pd.DataFrame(
        {"timestamp": [datetime(2022, 11, 1, 9, 15, s) for s in (0, 2, 6)],
         "realized_pnl": [0.0, 500.0, 250.0],
         "unrealized_pnl": [0.0, 0.0, 0.0],
         "total_pnl": [0.0, 500.0, 250.0]}
    ).set_index("timestamp")

    result = compute_metrics(BacktestResult(trades, mtm), CFG)
    assert result.round_trips == 2
    assert result.win_ratio == 0.5
    assert result.avg_holding_seconds == 2.0
    # Equity went 0 -> 500 -> 250, so the worst drawdown is -250.
    assert result.max_drawdown == -250.0
    assert result.total_pnl == 250.0
