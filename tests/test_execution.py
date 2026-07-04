"""Execution tests."""
from datetime import date, datetime
from pathlib import Path

from config import BacktestConfig
from execution import ExecutionEngine, Order, Side
from instruments import Instrument, InstrumentType, OptionType
from portfolio import Portfolio

CE = Instrument("NIFTY", InstrumentType.OPTION, date(2022, 11, 3), 18000.0, OptionType.CALL)
TS = datetime(2022, 11, 1, 9, 15)


def _engine():
    cfg = BacktestConfig(data_dir=Path("/tmp"), output_dir=Path("/tmp"))
    pf = Portfolio()
    return ExecutionEngine(cfg, pf), pf


def test_position_limit_blocks_second_buy():
    engine, pf = _engine()
    assert engine.execute(Order(CE, Side.BUY, 1), 100.0, TS) is not None
    # Max position per instrument is 1, so a second buy is rejected.
    assert engine.execute(Order(CE, Side.BUY, 1), 100.0, TS) is None
    assert pf.net_quantity(CE) == 1


def test_cannot_sell_without_a_position():
    engine, pf = _engine()
    assert engine.execute(Order(CE, Side.SELL, 1), 100.0, TS) is None
    assert pf.net_quantity(CE) == 0


def test_missing_price_skips_order():
    engine, pf = _engine()
    assert engine.execute(Order(CE, Side.BUY, 1), None, TS) is None
    assert pf.net_quantity(CE) == 0
