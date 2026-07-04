# Options Straddle Backtester

A modular, object-oriented backtesting engine for intraday options strategies on
NIFTY and BANKNIFTY, built around a pluggable strategy interface. The default
strategy is a **nearest-strike long straddle**: at every second it reads the
futures price, picks the strike closest to it, and holds a long call + long put
at that strike, rebalancing whenever the nearest strike changes and flattening
at the end of each day.

The engine is deliberately split into small single-responsibility modules so the
trading logic, the data handling, the accounting, and the reporting can each be
understood, tested, and swapped in isolation.

---

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Python 3.11+ is recommended.

---

## Data layout

The engine expects the dataset in the structure provided with the assignment:

```
allData/
  NSE_20221101/
    futures/
      NIFTY-I.csv        # nearest-month future (the "-I" file is the one used)
      BANKNIFTY-I.csv
    options/
      NIFTY22110318000CE.csv     # <UNDERLYING><YYMMDD expiry><STRIKE><CE|PE>
      NIFTY22110318000PE.csv
      ...
  NSE_20221102/
    ...
```

Each CSV has the columns: `Date, Time, Price, Volume, Open Interest`.
The **option filename is the instrument name** and is parsed into
underlying / expiry / strike / option-type.

---

## Running

```bash
python main.py --data-dir /path/to/allData --output-dir ./results --strategy straddle
```

Arguments:

| Flag | Default | Meaning |
|------|---------|---------|
| `--data-dir`   | *(required)* | Path to the `allData` root |
| `--output-dir` | `./results`  | Where CSVs and plots are written |
| `--strategy`   | `straddle`   | `straddle` or `call` (the demo strategy) |

### Outputs

Written to the output directory:

- `trades.csv` — full trade blotter (timestamp, instrument, side, price, quantity)
- `mtm.csv` — mark-to-market history (realized / unrealized / total PnL and the
  instruments held at each instant)
- `cumulative_pnl.png`, `daily_pnl.png`, `drawdown.png`, `trades_per_day.png`

A summary (total trades, round trips, win ratio, average holding time, realized /
unrealized / total PnL, max drawdown) is printed to the log.

---

## Project structure

```
options_backtester/
  config.py         # immutable, injected configuration (no globals)
  utils.py          # logging setup
  instruments.py    # Instrument + OptionChain domain model
  parser.py         # filename <-> Instrument
  data_loader.py    # load/validate/cache CSVs; build the option chain
  portfolio.py      # positions, realized/unrealized PnL, trade history
  execution.py      # Order/Trade + ExecutionEngine (fills, position limits)
  strategy.py       # Strategy base + straddle + demo call strategy
  backtester.py     # the day/second event loop (orchestration)
  metrics.py        # win ratio, drawdown, daily PnL (vectorized)
  visualization.py  # matplotlib plots
  main.py           # CLI entry point / dependency wiring
  tests/            # pytest unit tests
```

---

## Running the tests

```bash
python -m pytest tests/ -v
```

---

## Key assumptions

- Only the nearest-month future (`-I`) is used for the reference price.
- Only NIFTY and BANKNIFTY are traded; other underlyings present in the data
  (e.g. FINNIFTY) are ignored.
- "Nearest expiry" is the closest expiry on or after the trading day.
- The futures tick series is the master clock; option prices are looked up
  *as-of* each futures timestamp (last known price at or before that instant),
  which absorbs missing/sparse option ticks.
- Fills happen at the traded price with no slippage or transaction cost (these
  are natural extension points — see `EXPLANATION.md`).
- `max_position_per_instrument = 1` and the engine is long-only.

See `EXPLANATION.md` for the full architecture, design rationale, and the
reasoning behind every component.
