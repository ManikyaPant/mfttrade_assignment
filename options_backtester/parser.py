"""Parse filenames into instruments."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from config import EXPIRY_DATE_FORMAT, BacktestConfig
from instruments import Instrument, InstrumentType, OptionType
from utils import get_logger

logger = get_logger(__name__)


class InvalidInstrumentName(ValueError):
    """Invalid filename."""


class InstrumentParser:
    """Parse option and future names."""

    def __init__(self, config: BacktestConfig) -> None:
        self._config = config
        # Compile once.
        self._pattern = re.compile(config.option_filename_regex)

    def parse_option(self, filename: str) -> Instrument:
        """Parse one option name."""
        name = Path(filename).name  # Accept a path or a filename.
        match = self._pattern.match(name)
        if match is None:
            raise InvalidInstrumentName(f"Unrecognised option filename: {name!r}")

        fields = match.groupdict()
        try:
            expiry = datetime.strptime(fields["expiry"], EXPIRY_DATE_FORMAT).date()
        except ValueError as exc:
            raise InvalidInstrumentName(
                f"Bad expiry {fields['expiry']!r} in {name!r}"
            ) from exc

        return Instrument(
            underlying=fields["underlying"],
            instrument_type=InstrumentType.OPTION,
            expiry=expiry,
            strike=float(fields["strike"]),
            option_type=OptionType(fields["option_type"]),
        )

    def try_parse_option(self, filename: str) -> Instrument | None:
        """Parse one option name, or return None."""
        try:
            return self.parse_option(filename)
        except InvalidInstrumentName as exc:
            logger.warning("Skipping file (%s)", exc)
            return None

    def parse_future(self, underlying: str) -> Instrument:
        """Build a future instrument."""
        return Instrument(
            underlying=underlying, instrument_type=InstrumentType.FUTURE
        )
