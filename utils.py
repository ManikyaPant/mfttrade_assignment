"""Shared helpers."""

from __future__ import annotations

import logging

# Shared log format.
_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def configure_logging(level: str = "INFO") -> None:
    """Set up logging."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format=_LOG_FORMAT,
        datefmt=_DATE_FORMAT,
    )


def get_logger(name: str) -> logging.Logger:
    """Return a logger."""
    return logging.getLogger(name)
