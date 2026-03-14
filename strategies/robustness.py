"""Robustness analysis for backtested strategies.

Includes Monte Carlo noise injection (Ch 13) and volatility regime
analysis (split backtest into high-vol / low-vol periods)."""

import logging
from math import sqrt

import numpy as np
import pandas as pd

from strategies.backtest import run_backtest

logger = logging.getLogger(__name__)


def generate_noisy_prices(close: pd.Series, noise_scale: float = 0.5,
                          rng: np.random.Generator | None = None) -> pd.Series:
    """Generate one synthetic price path by adding noise to log returns.

    Args:
        close: Original close price series with datetime index.
        noise_scale: Fraction of daily return std used as noise amplitude.
        rng: NumPy random generator for reproducibility.

    Returns:
        Series of synthetic prices with same index as close (excluding first row).
    """
    if rng is None:
        rng = np.random.default_rng()

    log_returns = np.log(close / close.shift(1)).dropna()
    # Drop inf values from zero/negative prices
    log_returns = log_returns[np.isfinite(log_returns)]
    noise = rng.normal(0, noise_scale * log_returns.std(), len(log_returns))
    noisy_returns = log_returns.values + noise
    noisy_prices = close.iloc[0] * np.exp(np.cumsum(noisy_returns))
    return pd.Series(noisy_prices, index=log_returns.index, name="Close")


def run_monte_carlo(df: pd.DataFrame, generate_signal_fn, n_paths: int = 200,
                    noise_scale: float = 0.5, capital: float = 100_000_000,
                    risk_pct: float = 0.01, cost_per_trade: float = 0.0,
                    seed: int = 42) -> dict:
    """Run strategy on n_paths synthetic price series.

    For each path:
    1. Generate noisy prices from Close column
    2. Replace Close in feature df, re-run generate_signal
    3. Run backtest, collect Sharpe and equity curve

    Args:
        df: DataFrame with Close column and any feature columns needed by
            generate_signal_fn. Must have datetime index.
        generate_signal_fn: Strategy's generate_signal callable.
        n_paths: Number of Monte Carlo paths to simulate.
        noise_scale: Fraction of daily return std used as noise amplitude.
        capital: Starting capital in dollars.
        risk_pct: Fraction of equity to allocate per trade.
        cost_per_trade: Dollar cost per position change.
        seed: Random seed for reproducibility.

    Returns:
        Dict with:
        - sharpe_ratios: list of Sharpe ratios across paths
        - total_returns: list of total return percentages
        - equity_curves: list of equity Series (capped at 50 for rendering)
        - pct_profitable: fraction of paths with positive total P&L
        - original_sharpe: Sharpe ratio from the original (unperturbed) data
        - original_sharpe_percentile: percentile rank of original Sharpe
        - original_equity: equity Series from the original backtest
    """
    rng = np.random.default_rng(seed)

    # Run original backtest first
    original_df = generate_signal_fn(df.copy())
    orig_result, _, orig_stats = run_backtest(
        original_df, capital=capital, risk_pct=risk_pct,
        cost_per_trade=cost_per_trade,
    )
    original_sharpe = orig_stats["sharpe_ratio"]
    original_equity = orig_result["equity"]

    sharpe_ratios = []
    total_returns = []
    equity_curves = []
    max_curves = 50

    for i in range(n_paths):
        noisy_close = generate_noisy_prices(df["Close"], noise_scale=noise_scale, rng=rng)

        # Build a copy with the noisy prices, aligned to the shorter index
        sim_df = df.loc[noisy_close.index].copy()
        sim_df["Close"] = noisy_close.values

        try:
            sim_df = generate_signal_fn(sim_df)
            result_df, _, stats = run_backtest(
                sim_df, capital=capital, risk_pct=risk_pct,
                cost_per_trade=cost_per_trade,
            )
            sharpe_ratios.append(stats["sharpe_ratio"])
            total_returns.append(stats["total_return_pct"])
            if len(equity_curves) < max_curves:
                equity_curves.append(result_df["equity"])
        except Exception:
            logger.debug("MC path %d failed, skipping", i)
            continue

    original_sharpe_percentile = (
        np.mean([s <= original_sharpe for s in sharpe_ratios]) * 100
        if sharpe_ratios else 50.0
    )

    profitable_count = sum(1 for r in total_returns if r > 0)
    pct_profitable = profitable_count / len(total_returns) if total_returns else 0.0

    logger.info(
        "Monte Carlo complete: %d/%d paths succeeded, median Sharpe=%.2f, "
        "pct_profitable=%.1f%%",
        len(sharpe_ratios), n_paths,
        float(np.median(sharpe_ratios)) if sharpe_ratios else 0.0,
        pct_profitable * 100,
    )

    return {
        "sharpe_ratios": sharpe_ratios,
        "total_returns": total_returns,
        "equity_curves": equity_curves,
        "pct_profitable": pct_profitable,
        "original_sharpe": original_sharpe,
        "original_sharpe_percentile": original_sharpe_percentile,
        "original_equity": original_equity,
    }


def run_bootstrap(
    trade_log: pd.DataFrame,
    capital: float = 100_000_000,
    n_paths: int = 500,
    seed: int = 42,
) -> dict:
    """Reshuffle realized trade P&Ls and reconstruct equity curves.

    Answers whether the observed max drawdown was driven by the specific
    ordering of trades (unlucky streak) or is inherent to the strategy's
    P&L distribution. Based on Ch 13 of Advances in Financial ML.

    Args:
        trade_log: Trade log DataFrame with a pnl column.
        capital: Starting capital in dollars.
        n_paths: Number of bootstrap reshuffles.
        seed: Random seed for reproducibility.

    Returns:
        Dict with max_drawdowns (one per path), original_max_drawdown,
        median_drawdown, pct_worse_drawdown, and n_paths.
    """
    if trade_log.empty or "pnl" not in trade_log.columns:
        return {
            "max_drawdowns": [],
            "original_max_drawdown": 0.0,
            "median_drawdown": 0.0,
            "pct_worse_drawdown": 0.0,
            "n_paths": n_paths,
        }

    pnls = trade_log["pnl"].values

    def _max_drawdown(pnl_array):
        equity = capital + np.cumsum(pnl_array)
        peak = np.maximum.accumulate(equity)
        dd = equity - peak
        return float(dd.min())

    original_dd = _max_drawdown(pnls)

    rng = np.random.default_rng(seed)
    max_drawdowns = []
    for _ in range(n_paths):
        shuffled = rng.permutation(pnls)
        max_drawdowns.append(_max_drawdown(shuffled))

    worse_count = sum(1 for d in max_drawdowns if d < original_dd)
    pct_worse = worse_count / len(max_drawdowns) if max_drawdowns else 0.0

    return {
        "max_drawdowns": max_drawdowns,
        "original_max_drawdown": original_dd,
        "median_drawdown": float(np.median(max_drawdowns)),
        "pct_worse_drawdown": pct_worse,
        "n_paths": n_paths,
    }


def compute_regime_stats(
    result_df: pd.DataFrame,
    trade_log: pd.DataFrame,
    capital: float = 100_000_000,
    vol_window: int = 21,
) -> dict:
    """Split backtest into high-vol and low-vol regimes and report per-regime stats.

    Args:
        result_df: Backtest DataFrame with Close, net_daily_pnl, equity columns.
        trade_log: Trade log DataFrame with entry_date and pnl columns.
        capital: Starting capital in dollars.
        vol_window: Rolling window for realized vol (trading days).

    Returns:
        Dict with vol_threshold, high_vol, and low_vol sub-dicts containing
        sharpe_ratio, total_return_pct, max_drawdown_pct, num_trades, win_rate,
        and num_days.
    """
    close = result_df["Close"]
    log_returns = np.log(close / close.shift(1))
    rolling_vol = log_returns.rolling(vol_window).std() * sqrt(252)

    vol_clean = rolling_vol.dropna()
    if vol_clean.empty:
        empty = {"sharpe_ratio": 0.0, "total_return_pct": 0.0,
                 "max_drawdown_pct": 0.0, "num_trades": 0, "win_rate": 0.0,
                 "num_days": 0}
        return {"vol_threshold": 0.0, "high_vol": empty, "low_vol": empty.copy()}

    vol_threshold = float(vol_clean.median())

    # Label each day (only where vol is available)
    regime = pd.Series(index=result_df.index, dtype="object")
    regime[rolling_vol >= vol_threshold] = "high_vol"
    regime[rolling_vol < vol_threshold] = "low_vol"
    # Warm-up days (NaN vol) are excluded

    out = {"vol_threshold": vol_threshold}

    for label in ("high_vol", "low_vol"):
        mask = regime == label
        pnl = result_df.loc[mask, "net_daily_pnl"]
        num_days = int(mask.sum())

        # Sharpe
        if len(pnl) > 1 and pnl.std() > 0:
            sharpe = (pnl.mean() / pnl.std()) * sqrt(252)
        else:
            sharpe = 0.0

        # Total return %
        total_return_pct = float(pnl.sum() / capital * 100) if capital > 0 else 0.0

        # Max drawdown %: reconstruct regime-only equity curve
        regime_equity = capital + pnl.cumsum()
        if len(regime_equity) > 0:
            peak = regime_equity.cummax()
            dd = regime_equity - peak
            max_dd = dd.min()
            peak_at_trough = peak[dd.idxmin()] if len(dd) > 0 else capital
            max_dd_pct = float(max_dd / peak_at_trough * 100) if peak_at_trough > 0 else 0.0
        else:
            max_dd_pct = 0.0

        # Trade-level: assign by entry_date vol
        if not trade_log.empty and "entry_date" in trade_log.columns:
            trade_dates = pd.to_datetime(trade_log["entry_date"])
            trade_regime = regime.reindex(trade_dates).values
            regime_trades = trade_log[trade_regime == label]
            num_trades = len(regime_trades)
            if num_trades > 0:
                win_rate = float((regime_trades["pnl"] > 0).sum() / num_trades)
            else:
                win_rate = 0.0
        else:
            num_trades = 0
            win_rate = 0.0

        out[label] = {
            "sharpe_ratio": float(sharpe),
            "total_return_pct": total_return_pct,
            "max_drawdown_pct": max_dd_pct,
            "num_trades": num_trades,
            "win_rate": win_rate,
            "num_days": num_days,
        }

    return out
