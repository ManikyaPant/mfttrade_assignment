"""Portfolio tests."""
from datetime import date, datetime

from execution import Side, Trade
from instruments import Instrument, InstrumentType, OptionType
from portfolio import Portfolio

CE = Instrument("NIFTY", InstrumentType.OPTION, date(2022, 11, 3), 18000.0, OptionType.CALL)
LOT = 50


def _trade(side, price):
    return Trade(datetime(2022, 11, 1, 9, 15), CE, side, price, 1)


def test_buy_then_sell_realizes_pnl():
    pf = Portfolio()
    pf.apply_trade(_trade(Side.BUY, 100.0), LOT)
    assert pf.net_quantity(CE) == 1

    pf.apply_trade(_trade(Side.SELL, 110.0), LOT)
    # Realized PnL after the close.
    assert pf.realized_pnl == 500.0
    assert pf.net_quantity(CE) == 0
    assert CE not in pf.open_positions()
    assert len(pf.trades) == 2


def test_unrealized_marks_open_position_to_market():
    pf = Portfolio()
    pf.apply_trade(_trade(Side.BUY, 100.0), LOT)
    # Mark at 105 -> (105 - 100) * 1 * 50 = 250.
    unreal = pf.unrealized_pnl(price_fn=lambda inst: 105.0, lot_size_fn=lambda u: LOT)
    assert unreal == 250.0


def test_missing_price_is_skipped_in_mtm():
    pf = Portfolio()
    pf.apply_trade(_trade(Side.BUY, 100.0), LOT)
    unreal = pf.unrealized_pnl(price_fn=lambda inst: None, lot_size_fn=lambda u: LOT)
    assert unreal == 0.0
