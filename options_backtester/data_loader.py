"""Data loading and option-chain building."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime

import pandas as pd

from config import BacktestConfig
from instruments import Instrument, InstrumentType, OptionChain, OptionType
from parser import InstrumentParser
from utils import get_logger

logger = get_logger(__name__)


class DataError(Exception):
    """Base data error."""


class MissingDataError(DataError):
    """Required data is missing."""


class EmptyDataError(DataError):
    """A file has no usable rows."""


class SchemaError(DataError):
    """A file has the wrong columns."""


class DataLoader:
    """Load and cache market data."""

    def __init__(self, config: BacktestConfig, parser: InstrumentParser) -> None:
        self._config = config
        self._parser = parser
        self._frame_cache: dict[str, pd.DataFrame] = {}
        self._option_index_cache: dict[date, list[Instrument]] = {}

    # ------------------------------------------------------------------ days
    def trading_days(self) -> list[date]:
        """Return trading days."""
        prefix = self._config.date_folder_prefix
        days: list[date] = []
        if not self._config.data_dir.is_dir():
            raise MissingDataError(f"Data directory not found: {self._config.data_dir}")
        for entry in self._config.data_dir.iterdir():
            if not (entry.is_dir() and entry.name.startswith(prefix)):
                continue
            stamp = entry.name[len(prefix):]
            try:
                days.append(datetime.strptime(stamp, self._config.date_folder_format).date())
            except ValueError:
                logger.warning("Ignoring unrecognised folder: %s", entry.name)
        return sorted(days)

    def _date_folder(self, day: date):
        name = f"{self._config.date_folder_prefix}{day.strftime(self._config.date_folder_format)}"
        return self._config.data_dir / name

    # ----------------------------------------------------------------- frames
    def _read_price_frame(self, path) -> pd.DataFrame:
        """Read one CSV into a cached price frame."""
        key = str(path)
        cached = self._frame_cache.get(key)
        if cached is not None:
            return cached
        if not path.exists():
            raise MissingDataError(f"File not found: {path}")

        raw = pd.read_csv(path)
        cfg = self._config
        required = {cfg.date_column, cfg.time_column, cfg.price_column}
        missing = required - set(raw.columns)
        if missing:
            raise SchemaError(f"{path.name} missing columns: {sorted(missing)}")

        # Build timestamps from Date and Time.
        timestamp = pd.to_datetime(
            raw[cfg.date_column].astype(str) + " " + raw[cfg.time_column].astype(str),
            errors="coerce",
        )
        frame = pd.DataFrame(
            {"price": pd.to_numeric(raw[cfg.price_column], errors="coerce")}
        )
        frame.index = timestamp
        frame = frame[frame.index.notna() & frame["price"].notna()]
        # Keep the last duplicate timestamp.
        frame = frame[~frame.index.duplicated(keep="last")].sort_index()
        if frame.empty:
            raise EmptyDataError(f"No usable rows in {path.name}")

        self._frame_cache[key] = frame
        return frame

    def load_futures(self, underlying: str, day: date) -> pd.DataFrame:
        path = self._date_folder(day) / self._config.futures_subdir / self._config.futures_filename(underlying)
        return self._read_price_frame(path)

    def load_option(self, instrument: Instrument, day: date) -> pd.DataFrame:
        # Symbol matches the filename stem.
        path = self._date_folder(day) / self._config.options_subdir / f"{instrument.symbol}.csv"
        return self._read_price_frame(path)

    # ------------------------------------------------------------------ chain
    def available_options(self, day: date) -> list[Instrument]:
        """Return option instruments for one day."""
        cached = self._option_index_cache.get(day)
        if cached is not None:
            return cached

        options_dir = self._date_folder(day) / self._config.options_subdir
        if not options_dir.is_dir():
            raise MissingDataError(f"Options folder not found: {options_dir}")

        instruments: list[Instrument] = []
        for file in options_dir.iterdir():
            if file.suffix != ".csv":
                continue
            instrument = self._parser.try_parse_option(file.name)
            if instrument and instrument.underlying in self._config.underlyings:
                instruments.append(instrument)

        self._option_index_cache[day] = instruments
        return instruments

    def nearest_expiry(self, day: date, underlying: str) -> date | None:
        """Return the nearest expiry."""
        expiries = {
            inst.expiry
            for inst in self.available_options(day)
            if inst.underlying == underlying and inst.expiry is not None
        }
        if not expiries:
            return None
        upcoming = sorted(e for e in expiries if e >= day)
        return upcoming[0] if upcoming else min(expiries)

    def option_chain(self, day: date, underlying: str) -> OptionChain | None:
        """Build the nearest-expiry chain."""
        expiry = self.nearest_expiry(day, underlying)
        if expiry is None:
            return None

        legs: dict[float, set[OptionType]] = defaultdict(set)
        for inst in self.available_options(day):
            if inst.underlying == underlying and inst.expiry == expiry:
                legs[inst.strike].add(inst.option_type)

        # Keep strikes with both legs.
        strikes = tuple(sorted(s for s, types in legs.items() if {OptionType.CALL, OptionType.PUT} <= types))
        if not strikes:
            return None
        return OptionChain(underlying=underlying, expiry=expiry, strikes=strikes)
