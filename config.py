"""Configuration for the backtesting engine."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

# Option filename format.
DEFAULT_OPTION_FILENAME_REGEX: str = (
    r"^(?P<underlying>[A-Z]+?)"
    r"(?P<expiry>\d{6})"
    r"(?P<strike>\d+)"
    r"(?P<option_type>CE|PE)\.csv$"
)

# Expiry format.
EXPIRY_DATE_FORMAT: str = "%y%m%d"


@dataclass(frozen=True)
class BacktestConfig:
    """All run parameters."""

    data_dir: Path            # ``allData`` root
    output_dir: Path          # output folder

    # Traded underlyings.
    underlyings: tuple[str, ...] = ("NIFTY", "BANKNIFTY")

    # Filesystem layout.
    date_folder_prefix: str = "NSE_"
    date_folder_format: str = "%Y%m%d"
    options_subdir: str = "Options"
    futures_subdir: str = "Futures (Continuous)"
    futures_suffix: str = "-I"

    # Trading rules.
    max_position_per_instrument: int = 1
    lot_sizes: Mapping[str, int] = field(
        # Period-specific lot sizes.
        default_factory=lambda: {"NIFTY": 50, "BANKNIFTY": 25, "FINNIFTY": 40}
    )

    # CSV schema.
    csv_has_header: bool = False
    csv_columns: tuple[str, ...] = ("Date", "Time", "Price", "Volume", "Open Interest")
    date_column: str = "Date"
    time_column: str = "Time"
    price_column: str = "Price"
    volume_column: str = "Volume"
    open_interest_column: str = "Open Interest"

    option_filename_regex: str = DEFAULT_OPTION_FILENAME_REGEX
    log_level: str = "INFO"

    def futures_filename(self, underlying: str) -> str:
        """Return the futures filename."""
        return f"{underlying}{self.futures_suffix}.csv"

    def lot_size(self, underlying: str) -> int:
        # Fail loudly if a lot size is missing.
        try:
            return self.lot_sizes[underlying]
        except KeyError as exc:
            raise KeyError(f"No lot size configured for {underlying!r}") from exc

    @classmethod
    def from_json(cls, path: Path) -> "BacktestConfig":
        """Load config from JSON."""
        raw = json.loads(Path(path).read_text())
        raw["data_dir"] = Path(raw["data_dir"])
        raw["output_dir"] = Path(raw["output_dir"])
        if "underlyings" in raw:
            raw["underlyings"] = tuple(raw["underlyings"])
        return cls(**raw)
