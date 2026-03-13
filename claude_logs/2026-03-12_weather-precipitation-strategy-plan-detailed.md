# Weather Precipitation Strategy — Full Implementation Plan

## Context

Feature store has point-in-time safety (`.shift(1)`) with 16 years of corn futures (2010-2026) and Corn Belt weather features for Iowa, Illinois, Nebraska. Three things to build:
1. Corn Belt aggregate feature in the feature store (average of 3 states)
2. Upgrade backtest engine with dollar P&L and position sizing
3. Weather precipitation strategy

**Key constraints**:
- Treat futures prices like stock prices. No bushels, no contract multipliers. Price = price.
- 1% of current equity per trade. No transaction costs by default.
- **Backtest period**: 2025 year (Jan 1 - present) for initial testing.
- Move backtest engine out of `eda/` into `strategies/` for clean, modular structure.

---

## Part 1: Corn Belt Aggregate Feature

### What
Average all weather features across Iowa, Illinois, Nebraska -> write `features/weather/corn_belt.parquet`.

### Files modified

**`features/config.yaml`** — Added `aggregations` block under `weather`:
```yaml
weather:
  aggregations:
    - name: corn_belt
      method: mean
      source_entities: [iowa, illinois, nebraska]
```

**`features/pipeline.py`** — Three changes:

1. **New function** `compute_aggregations(category, category_cfg, rebuild)`:
   - Read iowa, illinois, nebraska parquets via `store.read_features()`
   - `pd.concat` all feature columns, `groupby("date").mean()` -> single averaged row per date
   - Write to `features/weather/corn_belt.parquet` via `store.write_features()`
   - Supports both rebuild (full write) and incremental (append new rows)

2. **Hook into `run()`** — after the per-entity compute loop, before `update_registry()`:
   ```python
   for category, cat_cfg in full_config.items():
       compute_aggregations(category, cat_cfg, rebuild)
   ```

3. **Update `update_registry()`** — after the entity loop, added a block that:
   - Iterates `cat_cfg.get("aggregations", [])`
   - Reads the corn_belt parquet, records metadata in `files_meta`
   - Adds `corn_belt` to `unlinked_features["weather"]`
   - Appends `corn_belt` to each weather feature's `states` list

### Output
`features/weather/corn_belt.parquet` with columns: `date, precip_7d, precip_30d, temp_max_7d, temp_min_7d, temp_range_7d, precip_anomaly_30d` — all averaged across 3 states.

---

## Part 2: Backtest Engine — Move & Upgrade

### What
Moved `eda/backtest.py` -> `strategies/backtest.py` and upgraded with dollar P&L, position sizing, equity tracking, and comprehensive metrics.

### New `run_backtest()` signature
```python
def run_backtest(df, capital=100_000_000, risk_pct=0.01, cost_per_trade=0.0)
```

### Position sizing model
- **On trade entry**: `allocation = current_equity * risk_pct`, `units = allocation / entry_price`
- **While holding**: `daily_pnl = units * price_change` (in dollars)
- **On exit**: units go to 0, equity updated
- **Consecutive same-direction signals**: hold, don't add (no pyramiding)
- **Equity tracks continuously**: `equity = capital + cumulative_net_pnl`

### Functions in `strategies/backtest.py`

1. **`compute_daily_pnl(df, capital, risk_pct, cost_per_trade)`** — iterative loop. Adds columns: `units`, `daily_pnl`, `trade_cost`, `net_daily_pnl`, `cumulative_pnl`, `equity`.

2. **`build_trade_log(df)`** — includes `units`, `pnl` (dollars), `pnl_per_unit` (raw price move).

3. **`compute_stats(df, trade_log, capital)`** — comprehensive dollar-denominated metrics:
   - `total_pnl`, `total_return_pct`, `starting_equity`, `ending_equity`
   - `num_trades`, `win_rate`, `avg_win`, `avg_loss`, `best_trade`, `worst_trade`
   - `avg_holding_days`, `sharpe_ratio`, `max_drawdown`, `max_drawdown_pct`
   - `profit_factor`, `longest_win_streak`, `longest_lose_streak`

4. **`run_backtest(df, capital, risk_pct, cost_per_trade)`** — orchestrator.

5. **`compute_positions(df)`** — unchanged (`signal.shift(1)`).

---

## Part 3: Weather Precipitation Strategy

### What
Created `strategies/weather_precipitation.py` with `generate_signal(df)`.

### Signal logic
```python
DROUGHT_THRESHOLD = -1.0  # z-score below -> drought -> long
FLOOD_THRESHOLD = 1.5     # z-score above -> flood -> long
```

- Long-only (+1 or 0, never -1)
- Both drought and flood are bullish (threaten corn supply)
- Asymmetric thresholds: drought tighter (-1σ) because corn is more drought-sensitive
- NaN -> flat

---

## Part 4: Verification Notebook

### What
Created `strategies/weather_strategy_2025.ipynb` — runs the full pipeline with charts.

### Notebook sections
1. Setup — imports, load corn_belt features + futures, join, filter to 2025
2. Signal generation — call `generate_signal(df)`, print distribution
3. Run backtest — `run_backtest(df, capital=100_000_000, risk_pct=0.01)`
4. Stats summary — formatted display of all metrics
5. Transaction log — styled trade_log DataFrame
6. Equity curve chart
7. Price + signal overlay with entry/exit markers
8. Drawdown chart

Charts saved to `strategies/visuals/`.

---

## Cleanup

- Moved backtest notebook and visuals from `eda/` to `strategies/`
- Deleted `eda/backtest_walkthrough.ipynb`, `eda/backtest.py`, `eda/backtest_visuals/`
- Updated CLAUDE.md project structure

---

## Files Summary

### Created
| File | Purpose |
|------|---------|
| `strategies/__init__.py` | Package init (empty) |
| `strategies/backtest.py` | Backtest engine with dollar P&L and position sizing |
| `strategies/weather_precipitation.py` | Weather precipitation strategy |
| `strategies/weather_strategy_2025.ipynb` | 2025 backtest notebook with visuals |
| `strategies/visuals/` | Chart output directory |

### Modified
| File | Changes |
|------|---------|
| `features/config.yaml` | Added `aggregations` block under `weather` |
| `features/pipeline.py` | Added `compute_aggregations()`, hooked into `run()`, updated `update_registry()` |
| `CLAUDE.md` | Updated project structure |

### Deleted
| File | Reason |
|------|--------|
| `eda/backtest.py` | Moved to `strategies/backtest.py` |
| `eda/backtest_walkthrough.ipynb` | Replaced by `strategies/weather_strategy_2025.ipynb` |
| `eda/backtest_visuals/` | Replaced by `strategies/visuals/` |

---

## Verification Results

- `python -m features.pipeline --rebuild` -> `features/weather/corn_belt.parquet` created (5,913 rows)
- `features/registry.yaml` includes `corn_belt` under `unlinked_features.weather` and in all weather feature `states` lists
- 2025 backtest: 297 trading days, 14 trades, 50% win rate, -$36K P&L (-0.04%), Sharpe -0.62
- Signal distribution: 282 flat (94.9%), 15 long (5.1%)
- No pyramiding confirmed — consecutive same-direction signals held without adding
- Trade log shows multi-day holds (1-4 days), not daily flipping
