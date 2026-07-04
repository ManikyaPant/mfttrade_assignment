"""Strategy tests."""
from datetime import date, datetime

from execution import Side, Trade
from instruments import Instrument, InstrumentType, OptionChain, OptionType
from portfolio import Portfolio, PortfolioView
from strategy import NearestStrikeLongStraddleStrategy, StrategyContext

EXPIRY = date(2022, 11, 3)
CHAIN = OptionChain("NIFTY", EXPIRY, (17950.0, 18000.0, 18050.0, 18100.0))


def _context(futures_price, portfolio):
    return StrategyContext(
        timestamp=datetime(2022, 11, 1, 9, 15),
        underlying="NIFTY",
        futures_price=futures_price,
        option_chain=CHAIN,
        portfolio=PortfolioView(portfolio),
    )


def _hold(pf, strike):
    for opt in (OptionType.CALL, OptionType.PUT):
        inst = CHAIN.option(strike, opt)
        pf.apply_trade(Trade(datetime(2022, 11, 1, 9, 15), inst, Side.BUY, 100.0, 1), 50)


def test_opens_straddle_when_flat():
    strat = NearestStrikeLongStraddleStrategy()
    orders = strat.generate_signals(_context(18000, Portfolio()))
    assert {o.side for o in orders} == {Side.BUY}
    assert {o.instrument.strike for o in orders} == {18000.0}
    assert {o.instrument.option_type for o in orders} == {OptionType.CALL, OptionType.PUT}


def test_no_orders_when_already_holding_nearest():
    pf = Portfolio()
    _hold(pf, 18000.0)
    strat = NearestStrikeLongStraddleStrategy()
    assert strat.generate_signals(_context(18010, pf)) == []  # 18000 stays nearest.


def test_rebalances_when_nearest_strike_changes():
    pf = Portfolio()
    _hold(pf, 18000.0)
    strat = NearestStrikeLongStraddleStrategy()
    orders = strat.generate_signals(_context(18049, pf))  # nearest is now 18050
    sells = {o.instrument.strike for o in orders if o.side is Side.SELL}
    buys = {o.instrument.strike for o in orders if o.side is Side.BUY}
    assert sells == {18000.0}
    assert buys == {18050.0}


def test_day_end_flattens_everything():
    pf = Portfolio()
    _hold(pf, 18000.0)
    strat = NearestStrikeLongStraddleStrategy()
    orders = strat.on_day_end(_context(18000, pf))
    assert all(o.side is Side.SELL for o in orders)
    assert len(orders) == 2
