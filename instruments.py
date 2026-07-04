"""Instrument and option-chain models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum


class InstrumentType(str, Enum):
    """Instrument kind."""

    OPTION = "OPTION"
    FUTURE = "FUTURE"


class OptionType(str, Enum):
    """Call or put."""

    CALL = "CE"
    PUT = "PE"


@dataclass(frozen=True)
class Instrument:
    """Immutable contract identity."""

    underlying: str
    instrument_type: InstrumentType
    expiry: date | None = None
    strike: float | None = None
    option_type: OptionType | None = None

    @property
    def symbol(self) -> str:
        """Return the canonical name."""
        if self.instrument_type is InstrumentType.FUTURE:
            return f"{self.underlying}-I"
        return (
            f"{self.underlying}{self.expiry:%y%m%d}"
            f"{int(self.strike)}{self.option_type.value}"
        )

    def __str__(self) -> str:
        return self.symbol


@dataclass(frozen=True)
class OptionChain:
    """Available strikes for one underlying and expiry."""

    underlying: str
    expiry: date
    strikes: tuple[float, ...]

    def nearest_strike(self, price: float) -> float:
        # Closest strike to price.
        return min(self.strikes, key=lambda strike: abs(strike - price))

    def option(self, strike: float, option_type: OptionType) -> Instrument:
        return Instrument(
            underlying=self.underlying,
            instrument_type=InstrumentType.OPTION,
            expiry=self.expiry,
            strike=strike,
            option_type=option_type,
        )

    def __bool__(self) -> bool:
        return bool(self.strikes)
