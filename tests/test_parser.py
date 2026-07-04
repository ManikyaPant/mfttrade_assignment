"""Parser tests."""
from datetime import date
from pathlib import Path

import pytest

from config import BacktestConfig
from instruments import OptionType
from parser import InstrumentParser, InvalidInstrumentName


@pytest.fixture
def parser() -> InstrumentParser:
    cfg = BacktestConfig(data_dir=Path("/tmp"), output_dir=Path("/tmp"))
    return InstrumentParser(cfg)


@pytest.mark.parametrize(
    "filename, underlying, expiry, strike, opt_type",
    [
        ("NIFTY22110314550PE.csv", "NIFTY", date(2022, 11, 3), 14550, OptionType.PUT),
        ("BANKNIFTY22112443200CE.csv", "BANKNIFTY", date(2022, 11, 24), 43200, OptionType.CALL),
        ("FINNIFTY22110719500CE.csv", "FINNIFTY", date(2022, 11, 7), 19500, OptionType.CALL),
    ],
)
def test_parses_real_examples(parser, filename, underlying, expiry, strike, opt_type):
    inst = parser.parse_option(filename)
    assert inst.underlying == underlying
    assert inst.expiry == expiry
    assert inst.strike == strike
    assert inst.option_type is opt_type
    # The symbol should match the filename stem.
    assert f"{inst.symbol}.csv" == filename


def test_rejects_garbage_name(parser):
    with pytest.raises(InvalidInstrumentName):
        parser.parse_option("not_an_option.csv")


def test_rejects_impossible_expiry(parser):
    with pytest.raises(InvalidInstrumentName):
        parser.parse_option("NIFTY22139914550PE.csv")  # month 13, day 99


def test_try_parse_returns_none_instead_of_raising(parser):
    assert parser.try_parse_option("garbage.csv") is None


def test_future_symbol(parser):
    assert parser.parse_future("NIFTY").symbol == "NIFTY-I"
