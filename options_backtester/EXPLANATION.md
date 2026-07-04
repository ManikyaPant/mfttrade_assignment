# EXPLANATION — Architecture & Design Rationale

This document is the "why" behind the code. It walks through the architecture,
justifies every major design decision, explains where the engine is vectorized
and where it deliberately is not, traces one full execution flow, and finishes
with the questions an interviewer is likely to ask (and how to answer them).

---

## 1. The problem, restated

Given one month of tick data for NIFTY / BANKNIFTY futures and their options,
simulate an intraday strategy that, every second:

1. reads the futures price,
2. selects the option strike closest to it (nearest expiry only),
3. holds a long straddle (call + put) at that strike,
4. rebalances when the nearest strike changes,
5. closes everything at the end of the day,

and then reports the trade history, mark-to-market PnL through time, and summary
performance metrics — with the framework built so that a *different* strategy can
be dropped in without touching the engine.

---

## 2. Architecture at a glance

The system is a pipeline of small, single-responsibility components wired
together by dependency injection in `main.py`:

```
              ┌───────────┐
              │  config   │  immutable settings, injected everywhere
              └─────┬─────┘
                    │
   ┌────────────────┼───────────────────────────────┐
   │                │                                │
┌──▼──────────┐  ┌──▼──────────┐               ┌─────▼──────┐
│ data_loader │  │   parser    │               │  strategy  │  emits Orders
│  CSV -> DF  │  │ name <->    │               │  (pluggable)│
│  + caching  │  │ Instrument  │               └─────┬──────┘
└──┬──────────┘  └─────────────┘                     │ Orders
   │ prices                                          │
   │                                            ┌────▼────────┐
   │                                            │  execution  │ Order -> Trade
   │                                            │  + limits   │
   │                                            └────┬────────┘
   │                                                 │ Trade
   │            ┌───────────────┐              ┌─────▼──────┐
   └───────────►│  backtester   │◄─────────────┤ portfolio  │ positions, PnL,
      prices    │  event loop   │  reads/writes│  history   │ trade blotter
                └──────┬────────┘              └────────────┘
                       │ BacktestResult
              ┌────────▼────────┐   ┌─────────────────┐
              │     metrics     │──►│  visualization  │
              │ (vectorized)    │   │   (matplotlib)  │
              └─────────────────┘   └─────────────────┘
```

Data flows one way: **prices in → orders → fills → PnL → metrics → plots**. No
component reaches backwards or holds a global; each is handed exactly what it
needs.

---

## 3. Why each module exists

**`config.py` — one immutable, injected source of truth.**
A frozen dataclass holding every tunable: data paths, the traded underlyings,
folder/column naming conventions, lot sizes, the position limit, and the option
filename regex. It is *frozen* (can't be mutated mid-run) and *injected* (passed
to the objects that need it) rather than being a module of global constants.
That removes hidden state and makes tests trivial — you construct a config with
`tmp_path` and nothing leaks between runs.

**`utils.py` — cross-cutting logging only.**
Deliberately tiny. A "utils" module is a magnet for junk; keeping it to logging
setup avoids that anti-pattern.

**`instruments.py` — the domain model.**
`Instrument` is the *identity* of a contract, separate from its price data. It is
a frozen dataclass, which gives it value semantics: two instruments with the same
fields are equal and hashable, so an `Instrument` can be a dictionary key in the
portfolio. Its `symbol` property round-trips exactly to the CSV filename stem,
which is what lets the loader find an option's file without a lookup table.
`OptionChain` is a price-free view of the strikes available for one
underlying/expiry, built from filenames — cheap to construct, and the object the
strategy queries for the nearest strike.

**`parser.py` — filename ⇄ instrument.**
The option filename *is* the instrument spec, so parsing it correctly is
critical. The regex uses a fixed-width `\d{6}` expiry field to disambiguate the
expiry digits from the strike digits (otherwise `...22110314550...` is
ambiguous). It offers a strict `parse_option` (raises on bad input) and a lenient
`try_parse_option` (logs and returns `None`) for bulk directory scans where one
stray file shouldn't abort the run.

**`data_loader.py` — all filesystem and pandas I/O, contained.**
The only module that touches disk. It discovers trading days from the
`NSE_YYYYMMDD` folders, loads each CSV into a *canonical* frame (a `DatetimeIndex`
built from `Date`+`Time`, and a single `price` column) so nothing downstream
depends on raw column names, caches every load by path, and builds the
nearest-expiry chain. All the ugly edge cases live here (missing files, empty
data, duplicate/missing timestamps), exposed as typed exceptions so callers can
distinguish "skip this underlying today" from "the data is malformed."

**`portfolio.py` — the source of truth for holdings and PnL.**
`Position` does weighted-average-cost accounting and books realized PnL when a
fill reduces it. `Portfolio` aggregates positions, realized PnL, and the full
trade blotter, and can mark everything to market for the unrealized figure. A
read-only `PortfolioView` is what strategies receive — they can *read* current
holdings but cannot mutate state, which enforces the "strategy only emits orders"
contract at the type level.

**`execution.py` — the single place intent becomes a fill.**
`Order` (intent) and `Trade` (fact) are separate types. The `ExecutionEngine` is
the only thing that applies fills, and it enforces the invariants — the
per-instrument position limit on buys and long-only closing on sells — so those
guarantees hold no matter what a strategy requests.

**`strategy.py` — the pluggable brain.**
An abstract `Strategy` plus concrete strategies. Explained in depth in §5.

**`backtester.py` — orchestration and the event loop.**
Walks days, merges both underlyings' ticks into one time-ordered stream, drives
the strategy → execution → portfolio cycle, and snapshots MTM after every event.
`PriceBook` centralizes "price of any instrument at any instant" via `asof`.

**`metrics.py` / `visualization.py` — reporting, kept separate.**
Turning the blotter and MTM series into numbers (metrics) is a different concern
from drawing them (visualization), so they are different modules. Metrics is
vectorized; visualization uses the headless matplotlib backend.

**`main.py` — composition root.**
The one place the object graph is assembled. Everything else receives its
collaborators; nothing constructs its own dependencies from globals.

---

## 4. Why object-oriented here (and where it *isn't*)

OOP earns its place wherever there is a stable *interface* with interchangeable
*implementations*, or a bundle of state with invariants:

- `Strategy` is a genuine polymorphic interface — the whole point is to swap
  implementations. This is the textbook case for inheritance.
- `Portfolio`, `ExecutionEngine`, `DataLoader` each own state plus the invariants
  that protect it; encapsulating them as objects keeps that state from leaking.
- `Instrument` / `Trade` / `Order` are value objects — dataclasses with behaviour
  attached (e.g. `signed_quantity`), which reads better than passing tuples.

But not everything is a class. The numeric heavy lifting in `metrics.py` is plain
functions over pandas/numpy, because there is no state to protect there — forcing
it into objects would be ceremony. Good design is knowing where OOP helps and
where it's overhead.

**Composition over inheritance.** The `Backtester` *has-a* strategy, portfolio,
and execution engine (composition); it is not built by subclassing anything.
Inheritance appears only for `Strategy`, where substitutability (Liskov) is real:
any `Strategy` can stand in for any other.

**SOLID, concretely:**
- *S* — each module has one reason to change (loading vs. accounting vs. plotting).
- *O* — a new strategy is added without editing the backtester (see §5).
- *L* — every `Strategy` subclass is a drop-in for the base.
- *I* — strategies depend on the narrow `PortfolioView`, not the full `Portfolio`.
- *D* — the backtester depends on the `Strategy` *abstraction*, not a concrete one.

---

## 5. The pluggable strategy design (the core idea)

The key decision: **strategies are stateless and declarative.** A strategy never
remembers "which strike am I holding" — that fact already lives in the portfolio.
Each tick it computes the *desired* set of instruments and lets a shared base-class
helper diff that against what is actually held:

```python
def _orders_to_reach(self, desired, context):
    held = set(context.portfolio.open_options(context.underlying))
    orders = []
    for inst in held - desired:      # held but no longer wanted -> sell
        orders.append(Order(inst, Side.SELL, abs(context.portfolio.net_quantity(inst))))
    for inst in desired - held:      # wanted but not held -> buy
        orders.append(Order(inst, Side.BUY, 1))
    return orders
```

Given that helper, the entire straddle strategy is:

```python
class NearestStrikeLongStraddleStrategy(Strategy):
    def generate_signals(self, context):
        strike = context.option_chain.nearest_strike(context.futures_price)
        desired = {context.option_chain.option(strike, OptionType.CALL),
                   context.option_chain.option(strike, OptionType.PUT)}
        return self._orders_to_reach(desired, context)
```

Everything the assignment asks for falls out of this one idea:

- **Rebalancing** is automatic: when the futures price moves the nearest strike,
  `desired` changes, and the diff produces exactly the sell-old / buy-new orders.
- **End of day** reuses the same helper with an empty target, so `on_day_end`
  closes everything with no special-case code.
- **A new strategy is a few lines** — the demo `NearestStrikeLongCallStrategy`
  changes only the desired set to a single call. No change to the backtester,
  execution, or portfolio. That is the Open/Closed principle in practice, and it
  is why the design is "flexible enough that different strategies plug in."

This also honours "the backtest only needs orders as input": strategies emit
`Order`s; the loop is agnostic to which strategy produced them.

---

## 6. Vectorization vs. iteration — the important trade-off

A common interview probe: *"pandas is vectorized; why is there a Python loop over
seconds?"*

The engine **is** vectorized wherever the work is independent per row:

- Data cleaning — building the timestamp, dropping bad rows, de-duplicating,
  sorting — is all vectorized pandas in `data_loader`.
- Price lookups use `Series.asof`, an O(log n) binary search on a sorted index,
  not a manual scan.
- Metrics are vectorized: the drawdown is `equity - equity.cummax()`, and daily
  PnL is `groupby(day).last().diff()`.

But the event loop itself **cannot** be vectorized, and this is a property of the
problem, not a shortcoming. The strategy is *path dependent*: the decision at
second *t* depends on the position that was opened at second *t-1*. Whether we
trade at *t* depends on whether the nearest strike differs from the strike we are
*currently holding* — and what we hold is the cumulative result of every prior
decision. Vectorization requires each row to be computable independently of the
others; a feedback loop where each action changes the state that drives future
actions violates that by construction. So we iterate over events, but keep the
per-event cost tiny.

The clean split — *vectorize the data-parallel parts, iterate only the
inherently sequential part* — is the right answer, and being able to articulate
*why* the loop is unavoidable is more valuable than pretending it can be removed.

---

## 7. One full execution flow

Tracing `main.py` on the assignment's data:

1. **Wiring.** `main` builds the config, then the object graph: `DataLoader`,
   `Portfolio`, `ExecutionEngine(portfolio)`, the chosen `Strategy`, and the
   `Backtester` that composes them.
2. **Day loop.** `Backtester.run` iterates `loader.trading_days()`.
3. **Day setup.** For each day and each underlying, it loads the `-I` futures
   frame and builds the nearest-expiry `OptionChain` (strikes that have *both*
   legs). It collects every `(timestamp, underlying, futures_price)` event.
4. **Merged timeline.** Events from both underlyings are merged and sorted, so
   the day is replayed in true chronological order and the combined MTM curve is
   correct.
5. **Per event.** A `StrategyContext` (timestamp, underlying, futures price,
   chain, read-only portfolio) is handed to `strategy.generate_signals`, which
   returns the orders needed to reach its desired holding. For each order the
   backtester looks up the fill price via `PriceBook.price(...).asof(ts)` and
   calls `execution.execute`, which enforces limits and books the `Trade` into
   the portfolio. Then it snapshots MTM.
6. **End of day.** `strategy.on_day_end` targets an empty book, so the helper
   emits sells that flatten every position; a final snapshot is taken.
7. **Reporting.** `run` returns a `BacktestResult` (blotter + MTM frame).
   `compute_metrics` reduces it to summary numbers and the equity/drawdown/daily
   series; `render_all` writes the four plots; `main` writes `trades.csv` and
   `mtm.csv` and logs the summary.

---

## 8. Data-model details worth calling out

- **Filename as identity.** `Instrument.symbol` reconstructs the exact filename
  stem, so `load_option` builds the path directly from the instrument — no
  mapping to maintain.
- **Fixed-width expiry regex.** `\d{6}` for the expiry cleanly separates it from
  the variable-length strike digits.
- **Canonical frames.** Every loaded CSV becomes a `DatetimeIndex` + `price`
  frame, decoupling all downstream code from the raw `Date/Time/Price` schema.
- **`asof` price semantics.** Option ticks can be sparse; using the last price at
  or before the futures timestamp is both realistic (you trade at the last known
  price) and robust to gaps, with no explicit reindex/fill needed.
- **Both-legs-only chain.** A strike enters the chain only if both its CE and PE
  files exist, so a straddle can always be formed and we never try to trade a
  missing leg.

---

## 9. Complexity

Let `D` = trading days, `T` = ticks per day, `U` = underlyings, `S` = strikes.

- Building a day's chain: O(number of option files) filename parses — cheap.
- Each event: nearest strike is O(S); the price lookup is O(log T); MTM marks the
  (≤ 2·U) open positions. So each event is effectively O(S + log T).
- A full run is O(D · U · T · (S + log T)) — linear in the number of ticks, which
  is the floor for a path-dependent simulation.
- Memory is bounded by the cached frames actually touched (lazy option loading),
  not the entire month at once.

---

## 10. Interview Q&A

**Q: How do I add a new strategy?**
Subclass `Strategy`, implement `generate_signals` to return the desired
instruments via `_orders_to_reach`, and register it in `STRATEGIES`. Nothing else
changes.

**Q: Why separate `Order` and `Trade`?**
An order is an intention; a trade is what actually happened after the engine
applied limits and a fill price. Keeping them distinct makes the boundary between
"what the strategy wanted" and "what the market gave" explicit.

**Q: Where would slippage / fees go?**
In `ExecutionEngine.execute` — adjust the fill price or subtract a cost before
constructing the `Trade`. Nothing else needs to know.

**Q: Why is the config frozen?**
To eliminate hidden mutable global state. A run's parameters can't drift, and
tests are isolated because each builds its own config.

**Q: What if an option has no tick at a given second?**
`asof` returns the last known price at or before that instant. If there is none
at all (before the first tick), the order is skipped and logged rather than
filled at a fabricated price.

**Q: How is the combined PnL of two underlyings kept correct?**
Both underlyings' ticks are merged into one time-ordered stream, and each MTM
snapshot marks *all* open positions (across both) at that instant, so the equity
curve is a true combined view.

**Q: Why not multiprocess the days?**
Days are independent, so day-level parallelism is a clean future win. It was left
out to keep the reference implementation simple and deterministic; the module
boundaries make it easy to add.

---

## 11. Known limitations & future work

- **MTM granularity.** Snapshotting every event yields a very fine (large) MTM
  series over a full month. For scale, downsample snapshots (e.g. per minute) or
  store them columnar — a small change isolated to `Backtester._snapshot`.
- **Costs & slippage.** Not modelled; the single natural insertion point is the
  execution engine.
- **Config-driven underlyings in the regex.** The parser currently accepts any
  alphabetic underlying and filters afterward; the regex could be generated from
  `config.underlyings` for a stricter match.
- **Expiry-format variants.** Weekly vs. monthly expiry encodings differ across
  exchanges/segments; the parser assumes the `YYMMDD` form seen in the data.
- **Parallelism.** Per-day parallel execution is an easy throughput win given the
  independence of days.

These are deliberately *not* built, to keep the core clear — but each has an
obvious, localized home in the current design, which is the point of the module
boundaries.
