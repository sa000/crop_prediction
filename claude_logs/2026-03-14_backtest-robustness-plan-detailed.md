# Backtest Robustness Analysis (Stress Test) — Detailed Plan

## Context

After running a backtest on historical data, there's no way to know if the results are robust or just an artifact of the specific price path. A Sharpe ratio of 1.5 on one historical series could be noise. This feature adds a **Stress Test** page that applies techniques from *Advances in Financial Machine Learning* (Ch 11-14) to stress-test any strategy's backtest results under synthetic conditions, bootstrapped trade orderings, volatility regimes, and statistical significance tests.

The goal: give users confidence (or healthy skepticism) about whether their strategy's performance is real or luck.

## What Changes

### New files (2)

| File | Change |
|------|--------|
| `strategies/robustness.py` | Pure computation: Monte Carlo noise injection, trade bootstrap, regime analysis, Probabilistic/Deflated Sharpe Ratio |
| `app/pages/3_Stress_Test.py` | Streamlit page: strategy/ticker selection, run stress test, display results in 5 sections |

### Modified files (4)

| File | Change |
|------|--------|
| `app/charts.py` | Add 4 chart functions: `sharpe_distribution_chart`, `equity_fan_chart`, `bootstrap_pnl_chart`, `regime_comparison_chart` |
| `app/discovery.py` | Add `"robustness.py"` to `EXCLUDED_FILES` so it doesn't appear as a tradeable strategy |
| `app/main.py` | Add 3rd navigation card for "Stress Test" on the landing page |
| `tests/test_data_pipeline.py` | Add `TestRobustness` class with 7 tests covering all computation functions |

---

## 1. `strategies/robustness.py` — Pure Computation

All functions are pure (data in, data out). No Streamlit or I/O imports.

### 1a. Monte Carlo Noise Injection (Ch 13)

**Concept**: Add Gaussian noise to log returns, reconstruct synthetic price paths, re-run the strategy on each. If the strategy is robust, it should perform similarly across many noisy paths.

```python
def generate_noisy_prices(close: pd.Series, noise_scale: float = 0.5) -> pd.Series:
    """Generate one synthetic price path by adding noise to log returns.

    noise_scale: fraction of the daily return std dev used as noise amplitude.
    E.g., 0.5 means noise std = 0.5 * historical return std.
    """
    log_returns = np.log(close / close.shift(1)).dropna()
    noise = np.random.normal(0, noise_scale * log_returns.std(), len(log_returns))
    noisy_returns = log_returns.values + noise
    noisy_prices = close.iloc[0] * np.exp(np.cumsum(noisy_returns))
    return pd.Series(noisy_prices, index=close.index[1:], name="Close")


def run_monte_carlo(df: pd.DataFrame, generate_signal_fn, n_paths: int = 200,
                    noise_scale: float = 0.5, capital: float = 100_000_000,
                    risk_pct: float = 0.01, cost_per_trade: float = 0.0) -> dict:
    """Run strategy on n_paths synthetic price series.

    Args:
        df: Original feature DataFrame with Close + feature columns.
        generate_signal_fn: Strategy's generate_signal function.
        n_paths: Number of Monte Carlo iterations.
        noise_scale: Noise amplitude as fraction of return std.
        capital, risk_pct, cost_per_trade: Backtest parameters.

    Returns:
        dict with keys:
        - sharpe_ratios: list of floats (one per path)
        - total_returns: list of floats (one per path)
        - equity_curves: list of pd.Series (for fan chart, capped at 50 for perf)
        - pct_profitable: float (fraction of paths with positive return)
        - original_sharpe_percentile: float (where the real Sharpe falls in distribution)
    """
```

**Key design decisions**:
- Noise is applied to **log returns**, not prices directly — preserves statistical properties
- Features are recomputed on the noisy prices where applicable (e.g., SMA crossover recalculates SMAs on noisy Close). For weather strategies, weather features are untouched (noise only on prices)
- Signal is regenerated per path — this tests the full strategy, not just the equity math
- Each path takes ~1-2ms, so 200 paths = ~0.4s. Very fast.

### 1b. Trade Reshuffling / Bootstrap (Ch 13)

**Concept**: Take the realized trade P&Ls, randomly reshuffle their order, reconstruct equity curves. Tests whether the strategy's path-dependent outcomes (max drawdown, final equity) are sensitive to trade timing.

```python
def run_bootstrap(trade_log: pd.DataFrame, capital: float = 100_000_000,
                  n_paths: int = 500) -> dict:
    """Bootstrap equity curves by reshuffling trade P&L order.

    Returns:
        dict with keys:
        - max_drawdowns: list of floats (one per path)
        - final_pnls: list of floats (one per path)
        - median_drawdown: float
        - pct_worse_drawdown: float (paths with worse DD than original)
    """
```

### 1c. Regime Analysis

**Concept**: Split the backtest period into high-vol and low-vol regimes using realized volatility, then report performance stats for each. A robust strategy should perform acceptably in both regimes.

```python
def compute_regime_stats(result_df: pd.DataFrame, trade_log: pd.DataFrame,
                         capital: float = 100_000_000,
                         vol_window: int = 21) -> dict:
    """Split performance by volatility regime.

    Uses rolling vol_window-day realized volatility, splits at median.

    Returns:
        dict with keys:
        - high_vol: {sharpe, total_return, max_dd, num_trades, win_rate, avg_pnl_per_trade}
        - low_vol: same structure
        - vol_threshold: the median volatility used as cutoff
    """
```

### 1d. Sharpe Ratio Significance (Ch 14)

**Concept**: The Probabilistic Sharpe Ratio (PSR) tests whether the observed Sharpe is statistically > a benchmark (e.g., 0) given skewness, kurtosis, and sample size. The Deflated Sharpe Ratio (DSR) further adjusts for multiple testing — if you tried N strategies and picked the best, DSR tells you if it's still significant.

```python
def probabilistic_sharpe_ratio(observed_sharpe: float, benchmark_sharpe: float,
                                n_obs: int, skewness: float,
                                kurtosis: float) -> float:
    """PSR: probability that true Sharpe exceeds benchmark.

    From López de Prado Ch 14, Eq. 14.1:
    PSR = CDF((SR - SR*) * sqrt(n-1) / sqrt(1 - skew*SR + (kurtosis-1)/4 * SR^2))

    Returns: probability [0, 1]
    """


def deflated_sharpe_ratio(observed_sharpe: float, n_obs: int,
                          skewness: float, kurtosis: float,
                          n_trials: int) -> float:
    """DSR: PSR where benchmark is the expected max Sharpe from n_trials.

    Uses the Euler-Mascheroni approximation for E[max(SR)] from independent trials:
    E[max] ≈ (1 - gamma) * Z_inv(1 - 1/n_trials) + gamma * Z_inv(1 - 1/(n_trials * e))
    where gamma ≈ 0.5772.

    Returns: probability [0, 1]
    """


def compute_sharpe_stats(result_df: pd.DataFrame, n_trials: int = 1) -> dict:
    """Compute all Sharpe significance metrics from backtest results.

    Returns:
        dict with keys:
        - observed_sharpe: float
        - psr: float (probability Sharpe > 0)
        - dsr: float (probability Sharpe > expected max from n_trials)
        - skewness, kurtosis: float
        - n_obs: int
    """
```

---

## 2. `app/charts.py` — 4 New Chart Functions

### 2a. `sharpe_distribution_chart(sharpe_ratios, original_sharpe)`
Histogram of Monte Carlo Sharpe ratios with vertical line at the original Sharpe. Shows where the real performance falls in the distribution. Template: existing `distribution_chart()`.

### 2b. `equity_fan_chart(equity_curves, original_equity, capital)`
Fan chart showing Monte Carlo equity paths as semi-transparent gray lines with the original equity curve highlighted in blue. Capped at 50 paths for rendering performance. Y-axis in $M.

### 2c. `bootstrap_pnl_chart(final_pnls, original_pnl)`
Histogram of bootstrapped final P&Ls with vertical line at the original. Shows how likely the observed cumulative P&L is under random trade ordering.

### 2d. `regime_comparison_chart(regime_stats)`
Grouped bar chart comparing high-vol vs low-vol regime stats (Sharpe, return %, win rate, max DD %). Side-by-side bars with green (low-vol) and red (high-vol) color coding.

All charts follow the existing pattern: `go.Figure()` → add traces → `_apply_layout()`. Use existing `COLORS`, `LAYOUT_DEFAULTS`, `BG_DARK`, `BG_CARD`.

---

## 3. `app/pages/3_Stress_Test.py` — Streamlit Page

### Layout

**Sidebar**:
- Strategy selector (reuse `app/discovery.py` auto-discovery)
- Ticker selector (from feature registry)
- Noise scale slider: 0.1 to 2.0, default 0.5
- Monte Carlo paths: 100 to 1000, default 200
- Bootstrap paths: 100 to 2000, default 500
- Volatility window: 10 to 63, default 21
- Number of trials (for DSR): 1 to 50, default 1
- "Run Stress Test" button

**Main area** (after run):

1. **Summary Verdict** — Color-coded card:
   - Median MC Sharpe, % profitable paths, PSR, regime spread
   - Overall verdict: "Robust", "Moderate", or "Fragile" based on thresholds:
     - Robust: PSR > 0.95 AND >70% MC paths profitable AND regime spread < 0.5
     - Fragile: PSR < 0.80 OR <50% MC paths profitable
     - Moderate: everything else

2. **Monte Carlo Analysis** — 2-column layout:
   - Left: Sharpe distribution histogram
   - Right: Equity fan chart
   - Below: Key stats (median Sharpe, 5th/95th percentile, % profitable, original percentile rank)

3. **Trade Bootstrap** — 2-column layout:
   - Left: Final P&L distribution histogram
   - Right: Key stats (median DD, % paths with worse DD than original, confidence interval)

4. **Regime Analysis** — Full-width:
   - Regime comparison bar chart
   - Table with high-vol vs low-vol stats side by side

5. **Sharpe Significance** — Metric cards:
   - PSR value with interpretation ("95% confident Sharpe > 0")
   - DSR value (if n_trials > 1) with interpretation
   - Skewness and kurtosis values

### Execution flow

```python
if st.button("Run Stress Test"):
    # 1. Load features, generate signal, run original backtest
    # 2. Progress bar with 4 stages
    with st.spinner("Running Monte Carlo simulations..."):
        mc_results = run_monte_carlo(...)      # ~0.5s for 200 paths
    with st.spinner("Bootstrapping trades..."):
        bs_results = run_bootstrap(...)         # ~0.2s for 500 paths
    with st.spinner("Analyzing regimes..."):
        regime_stats = compute_regime_stats(...)  # ~instant
    with st.spinner("Computing Sharpe statistics..."):
        sharpe_stats = compute_sharpe_stats(...)  # ~instant
    # 3. Render all sections
```

### Feature recomputation for Monte Carlo

For each noisy price path, features must be recomputed because strategies depend on features derived from prices. The approach:

1. Get the strategy module's `generate_signal` function
2. For each MC path, replace the `Close` column in the feature DataFrame with the noisy prices
3. Re-run `generate_signal` on the modified DataFrame — this naturally recomputes any price-dependent features internally
4. Run backtest on the resulting signal + noisy prices

This works because `generate_signal` takes a feature DataFrame and returns one with a `signal` column. Strategies that use weather features (which don't depend on price) will correctly keep those unchanged.

---

## 4. `app/discovery.py` — Exclude robustness module

Add `"robustness.py"` to the `EXCLUDED_FILES` set so it doesn't appear as a selectable strategy.

---

## 5. `app/main.py` — Landing page card

Add a 3rd column with a "Stress Test" card linking to the new page. Brief description: "Test strategy robustness with Monte Carlo simulation, trade bootstrapping, and regime analysis."

---

## 6. Tests (`tests/test_data_pipeline.py`)

### `TestRobustness` class

Uses existing `backtest_result` fixture (which provides `result_df`, `trade_log`, `stats`).

| Test | What it verifies |
|------|-----------------|
| `test_generate_noisy_prices` | Output is a Series, same length as input minus 1, all positive, different from original |
| `test_run_monte_carlo` | Returns dict with expected keys, `sharpe_ratios` has `n_paths` elements, `pct_profitable` is 0-1 |
| `test_run_bootstrap` | Returns dict with expected keys, `max_drawdowns` has `n_paths` elements, all negative |
| `test_compute_regime_stats` | Returns dict with `high_vol` and `low_vol` keys, each containing expected stat keys |
| `test_probabilistic_sharpe_ratio` | PSR of a known high Sharpe (e.g., 2.0, n=252, skew=0, kurt=3) returns > 0.95 |
| `test_deflated_sharpe_ratio` | DSR < PSR when n_trials > 1 (multiple testing penalty) |
| `test_compute_sharpe_stats` | Returns dict with all expected keys, PSR is 0-1 |

### Chart tests

Add tests for the 4 new chart functions (return `go.Figure`, correct trace count).

---

## Verification

```bash
python -m pytest tests/ -v --tb=short
# All tests pass, < 30 seconds
```

Manual testing:
1. `streamlit run app/main.py`
2. Navigate to Stress Test page
3. Select SMA Crossover strategy + Corn ticker
4. Run with defaults (200 MC paths, 500 bootstrap, noise 0.5)
5. Verify all 5 sections render correctly
6. Check summary verdict appears with color coding
7. Try Weather Precipitation strategy — verify weather features unchanged in MC
8. Try n_trials=10 — verify DSR < PSR
9. Check total execution time < 5 seconds

---

## Key Files to Reuse

| Existing code | Where | What to reuse |
|---|---|---|
| `strategies/backtest.run_backtest()` | `strategies/backtest.py` | Core backtest engine for each MC path |
| `app/discovery.discover_strategies()` | `app/discovery.py` | Strategy auto-discovery for sidebar |
| `features/query.get_features()` | `features/query.py` | Load feature data for selected ticker |
| `app/charts.distribution_chart()` | `app/charts.py` | Template for histogram charts |
| `app/charts.equity_curve()` | `app/charts.py` | Template for equity fan chart |
| `app/charts.COLORS`, `LAYOUT_DEFAULTS` | `app/charts.py` | Consistent styling |
| `tests/conftest.backtest_result` | `tests/conftest.py` | Fixture for robustness tests |
