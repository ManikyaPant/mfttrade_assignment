# Options Straddle Backtester

Modular backtesting engine for intraday options strategies on NIFTY and BANKNIFTY,
built around a pluggable strategy interface.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Requires Python 3.11+.

## Run

```bash
python main.py --data-dir allData --output-dir ./results --strategy straddle
```

| Flag | Default | Meaning |
|------|---------|---------|
| `--data-dir`   | required   | Path to the `allData` root |
| `--output-dir` | `./results`| Where CSVs and plots are written |
| `--strategy`   | `straddle` | `straddle` or `call` |

## Strategies

Two strategies are implemented against the same framework:

- **`straddle`** — `NearestStrikeLongStraddleStrategy`: holds a long call + long put
  at the strike nearest the futures price, rebalancing when the nearest strike
  changes and flattening at end of day.
- **`call`** — `NearestStrikeLongCallStrategy`: holds only the nearest-strike call.

Each strategy declares its desired holding; the base class diffs that against the
current portfolio and emits the required orders. A new strategy is added by
subclassing `Strategy`, implementing `generate_signals`, and registering it in the
`STRATEGIES` dict in `strategy.py` — no changes to the engine.

## Output

Written to the output directory:

- `trades.csv` — trade blotter (timestamp, instrument, side, price, quantity)
- `mtm.csv` — mark-to-market history (realized / unrealized / total PnL, positions held)
- `cumulative_pnl.png`, `daily_pnl.png`, `drawdown.png`, `trades_per_day.png`

A summary (trades, round trips, win ratio, avg holding time, realized/unrealized/total
PnL, max drawdown) is logged at the end.

## Project structure

```
config.py        immutable, injected configuration
instruments.py   Instrument + OptionChain
parser.py        option filename <-> Instrument
data_loader.py   load/validate/cache CSVs; build the option chain
portfolio.py     positions, realized/unrealized PnL, trade history
execution.py     Order/Trade + ExecutionEngine (fills, position limits, atomic legs)
strategy.py      Strategy base + straddle + call
backtester.py    day/second event loop
metrics.py       win ratio, drawdown, daily PnL (vectorized)
visualization.py matplotlib plots
main.py          CLI entry point
verify_output.py independent output verifier
tests/           pytest unit tests
```

## Verify

```bash
python -m pytest tests/ -q                                  # 26 unit tests
python verify_output.py --data-dir allData --results ./results   # re-derive invariants from the outputs
```

`verify_output.py` independently recomputes the key invariants from the output CSVs
(MTM identity, end-of-day flat, traded underlyings, realized-PnL reconciliation,
nearest-strike, nearest-expiry) and reports PASS/FAIL for each.


- Multi-leg execution is atomic (`config.atomic_execution`, default on): if a leg
  can't be priced at a given second, the whole batch is retried next tick so a
  straddle is never half-filled. The end-of-day close is exempt.
- See `EXPLANATION.md` for architecture and design rationale.
