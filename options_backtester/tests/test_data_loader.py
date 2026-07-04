"""DataLoader tests."""
from datetime import date

import pandas as pd
import pytest

from config import BacktestConfig
from data_loader import DataLoader, EmptyDataError, MissingDataError
from instruments import Instrument, InstrumentType, OptionType
from parser import InstrumentParser


def _write(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)


@pytest.fixture
def dataset(tmp_path):
    """A one-day dataset with a duplicate timestamp and a later expiry."""
    day = tmp_path / "NSE_20221101"
    _write(
        day / "futures" / "NIFTY-I.csv",
        {"Date": ["20221101"] * 3, "Time": ["09:15:00", "09:15:01", "09:15:01"],
         "Price": [18000, 18010, 18011], "Volume": [1, 1, 1], "Open Interest": [1, 1, 1]},
    )
    # Nearest expiry and a later one.
    for name in ("NIFTY22110318000CE", "NIFTY22110318000PE", "NIFTY22111018000CE", "NIFTY22111018000PE"):
        _write(day / "options" / f"{name}.csv",
               {"Date": ["20221101"], "Time": ["09:15:00"], "Price": [100],
                "Volume": [1], "Open Interest": [1]})
    # FINNIFTY is present but ignored.
    _write(day / "options" / "FINNIFTY22110318000CE.csv",
           {"Date": ["20221101"], "Time": ["09:15:00"], "Price": [1], "Volume": [1], "Open Interest": [1]})
    cfg = BacktestConfig(data_dir=tmp_path, output_dir=tmp_path)
    return cfg, DataLoader(cfg, InstrumentParser(cfg))


def test_trading_days_discovered(dataset):
    _, loader = dataset
    assert loader.trading_days() == [date(2022, 11, 1)]


def test_duplicate_timestamp_keeps_last(dataset):
    _, loader = dataset
    fut = loader.load_futures("NIFTY", date(2022, 11, 1))
    assert len(fut) == 2  # Two timestamps.
    assert fut["price"].iloc[-1] == 18011  # last value for the duplicated second


def test_nearest_expiry_chain_ignores_later_expiry_and_finnifty(dataset):
    _, loader = dataset
    chain = loader.option_chain(date(2022, 11, 1), "NIFTY")
    assert chain.expiry == date(2022, 11, 3)   # nearest, not 2022-11-10
    assert chain.strikes == (18000.0,)


def test_missing_futures_raises(dataset):
    _, loader = dataset
    with pytest.raises(MissingDataError):
        loader.load_futures("BANKNIFTY", date(2022, 11, 1))


def test_empty_file_raises(tmp_path):
    day = tmp_path / "NSE_20221101"
    _write(day / "futures" / "NIFTY-I.csv",
           {"Date": [], "Time": [], "Price": [], "Volume": [], "Open Interest": []})
    cfg = BacktestConfig(data_dir=tmp_path, output_dir=tmp_path)
    loader = DataLoader(cfg, InstrumentParser(cfg))
    with pytest.raises(EmptyDataError):
        loader.load_futures("NIFTY", date(2022, 11, 1))
