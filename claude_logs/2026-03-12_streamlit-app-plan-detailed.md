# Streamlit Web App -- Strategy Dashboard + Data Explorer (Detailed Plan)

## Context

Phase 5 of the project roadmap: build a local Streamlit web app for hedge fund quants to analyze crop futures trading strategies. The infrastructure is ready -- backtest engine, feature store, query layer, and one strategy (weather precipitation) all work. The app surfaces this to a quant user: run a strategy, see how it performed, inspect the data.

Work is split into three milestones to keep each PR deployable and testable independently.

---

## Milestone 1: Bare-Bones Skeleton (Deploy Locally)

Goal: `streamlit run app/main.py` works, sidebar shows two pages, pages render placeholder content.

| Order | File | Action |
|-------|------|--------|
| 1 | `app/__init__.py` | Create -- empty |
| 2 | `app/pages/__init__.py` | Create -- empty |
| 3 | `app/discovery.py` | Create -- strategy auto-discovery |
| 4 | `app/main.py` | Create -- entry point with page config and sidebar branding |
| 5 | `app/pages/1_Strategy_Dashboard.py` | Create -- placeholder with title and "Run Backtest" button (no logic) |
| 6 | `app/pages/2_Data_Explorer.py` | Create -- placeholder with title and dropdowns (no logic) |
| 7 | `CLAUDE.md` | Modify -- add app/ entries to project structure |

### app/discovery.py

**`discover_strategies() -> dict[str, ModuleType]`**
Scan `strategies/` for `.py` files (excluding `__init__.py`, `backtest.py`, `analytics.py`). Import each via `importlib`, check for `generate_signal` callable. Return `{display_name: module}` where display name = `stem.replace("_", " ").title()`.

**`get_strategy_metadata(module) -> dict`**
Extract docstring and module-level threshold constants.

### app/main.py

- `st.set_page_config(page_title="Crop Yield Trading Platform", layout="wide")`
- Sidebar title and description
- Landing page with brief description of the two pages
- Run with: `streamlit run app/main.py`
- Pages auto-discovered from `app/pages/` directory

### Verification

1. `streamlit run app/main.py` -- app loads, sidebar shows both pages
2. Navigate to Strategy Dashboard -- placeholder renders
3. Navigate to Data Explorer -- placeholder renders

---

## Milestone 2: Strategy Dashboard (Full Backtest UI)

Goal: Select a strategy, run a backtest, see all charts and metrics interactively.

| Order | File | Action |
|-------|------|--------|
| 1 | `strategies/backtest.py` | Modify -- add Sortino, Calmar, VaR, CVaR to `compute_stats()` |
| 2 | `strategies/analytics.py` | Create -- rolling Sharpe, rolling win rate, monthly returns, drawdown periods |
| 3 | `app/charts.py` | Create -- Plotly chart builders (pure functions, no Streamlit) |
| 4 | `app/pages/1_Strategy_Dashboard.py` | Replace placeholder -- full backtest dashboard |

### strategies/backtest.py -- New Risk Metrics

Add 4 new keys to the dict returned by `compute_stats()`, after the existing Sharpe and max drawdown block (line ~270):

```python
# Sortino ratio (annualized, downside deviation only)
daily_returns = daily_pnl / capital
downside = daily_returns[daily_returns < 0]
downside_std = downside.std() if len(downside) > 0 else 0.0
ann_return = daily_returns.mean() * 252
stats["sortino_ratio"] = (
    ann_return / (downside_std * np.sqrt(252)) if downside_std > 0 else 0.0
)

# Calmar ratio (annualized return % / max drawdown %)
stats["calmar_ratio"] = (
    (ann_return * 100) / abs(stats["max_drawdown_pct"])
    if stats["max_drawdown_pct"] != 0 else 0.0
)

# VaR 95% and CVaR 95% (in dollars, from daily P&L)
stats["var_95"] = float(np.percentile(daily_pnl, 5)) if len(daily_pnl) > 0 else 0.0
tail = daily_pnl[daily_pnl <= stats["var_95"]]
stats["cvar_95"] = float(tail.mean()) if len(tail) > 0 else 0.0
```

### strategies/analytics.py (new)

Pure functions that take backtest outputs and return DataFrames/Series for visualization.

**Constants:**
- `ROLLING_SHARPE_WINDOW = 60` (trading days)
- `ROLLING_WIN_RATE_WINDOW = 20` (trades)

**Functions:**

- `rolling_sharpe(backtest_df, window=60) -> pd.Series` -- Rolling annualized Sharpe over a sliding window of `net_daily_pnl`. Formula: `(rolling_mean / rolling_std) * sqrt(252)`.
- `rolling_win_rate(trade_log, backtest_df, window=20) -> pd.Series` -- For each date, find trades exited on or before that date, take last `window` trades, compute `(pnl > 0).mean()`. Use vectorized approach with `searchsorted`.
- `monthly_returns(backtest_df, capital) -> pd.DataFrame` -- Group `net_daily_pnl` by year and month. Year-index x month-columns (1-12) matrix of percentage returns.
- `drawdown_periods(backtest_df) -> pd.DataFrame` -- Each period: `start`, `trough_date`, `recovery_date` (or None), `duration_days`, `max_dd_dollars`, `max_dd_pct`.

### app/charts.py (new)

All functions are pure: take data, return `plotly.graph_objects.Figure`. No Streamlit imports.

| Function | Input | Description |
|----------|-------|-------------|
| `equity_curve(backtest_df, capital)` | equity series | Line chart, $M y-axis, dashed starting capital line |
| `price_with_signals(backtest_df, trade_log)` | Close + positions + trades | Line + green up-triangle entries, red down-triangle exits, position shading |
| `drawdown_chart(backtest_df)` | equity series | Red filled area below zero |
| `rolling_sharpe_chart(series)` | rolling Sharpe series | Line with horizontal refs at 0, 1, 2 |
| `rolling_win_rate_chart(series)` | rolling win rate series | Line with horizontal ref at 50% |
| `monthly_return_heatmap(monthly_df)` | year x month matrix | RdYlGn heatmap with % annotations |
| `return_distribution(backtest_df)` | net_daily_pnl | Histogram with VaR 95% vertical line |

### app/pages/1_Strategy_Dashboard.py

**Sidebar Controls:**
- Strategy dropdown (auto-discovered via `discovery.discover_strategies()`)
- Run Backtest button
- Capital: $100M, Risk: 1%, Cost: $0 (hardcoded defaults)

**Data Loading (on button click):**
1. Load corn futures from SQLite via `etl/db.py` -> capitalize columns -> set date index
2. Load weather features via `features/store.read_features("weather", "corn_belt")` -> set date index
3. Inner join on date, filter to 2025+
4. Run `strategy.generate_signal(df)` then `run_backtest(df)`
5. Compute analytics
6. Store results in `st.session_state`

**Display Layout (top to bottom):**
- Row 1 -- Summary Stats (2 rows of `st.metric` in `st.columns(5)`)
- Equity Curve -- full width
- Price with Signals -- full width
- Drawdown -- full width + periods table
- Alpha Decay -- two columns (Rolling Sharpe left, Rolling Win Rate right)
- Monthly Returns -- full width heatmap
- Return Distribution -- histogram with VaR line
- Trade Log -- `st.dataframe`, scrollable

### Verification

1. Select "Weather Precipitation", click Run Backtest
2. Confirm summary stats show Sortino, Calmar, VaR, CVaR
3. All charts render and are interactive (zoom, pan, hover)
4. Trade log table shows both long and short trades

---

## Milestone 3: Data Explorer + Cloud Deployment

Goal: Data Explorer page is functional. App is deployed to Streamlit Community Cloud.

| Order | File | Action |
|-------|------|--------|
| 1 | `app/charts.py` | Add `price_chart` and `feature_time_series` functions |
| 2 | `app/pages/2_Data_Explorer.py` | Replace placeholder -- three sections with charts |
| 3 | Deploy to Streamlit Community Cloud |

### app/pages/2_Data_Explorer.py

Three sections, each with a dropdown:

- **Price Data**: Ticker dropdown (corn, soybeans, wheat) -> load from SQLite via `etl/db.py` -> candlestick chart
- **Feature Explorer**: Category + feature dropdown -> load from Parquet via `features/query.read_parquet` -> line chart
- **Weather Data**: Region dropdown -> load from Parquet -> summary table (date range, row count, columns)

### Cloud Deployment

- Deploy to Streamlit Community Cloud (free, from GitHub repo)
- Add secrets management for any API keys
- Verify public URL works, app sleeps/wakes correctly

---

## Key Design Decisions

1. **No `read_strategy_features` for dashboard data loading** -- the Parquet feature files don't contain raw Close prices. Load prices from SQLite and weather features from Parquet separately, join manually. Matches the working notebook pattern.
2. **Charts in pure module, not inline** -- `app/charts.py` contains all Plotly builders as pure functions. Keeps page files thin, charts testable.
3. **Analytics in `strategies/analytics.py`, not `strategies/backtest.py`** -- scalar risk metrics (Sortino, etc.) added to `compute_stats()` since they're summary stats. Time-series analytics (rolling Sharpe, monthly returns) go in a separate module since they return DataFrames and are presentation-oriented.
4. **Plotly, not Matplotlib** -- interactive zoom/pan on charts. Streamlit + Plotly supports this natively.
5. **`st.session_state` for results** -- avoids re-running the backtest on every Streamlit rerender. Results persist until the user clicks "Run Backtest" again.
