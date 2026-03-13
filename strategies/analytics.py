"""Time-series analytics for backtest visualization.

Pure functions that take backtest outputs and return DataFrames or Series
for rolling performance, monthly return matrices, and drawdown period tables."""

import numpy as np
import pandas as pd

ROLLING_SHARPE_WINDOW = 60
ROLLING_WIN_RATE_WINDOW = 20


def rolling_sharpe(backtest_df: pd.DataFrame, window: int = ROLLING_SHARPE_WINDOW) -> pd.Series:
    """Compute rolling annualized Sharpe ratio over daily P&L.

    Args:
        backtest_df: Backtest DataFrame with net_daily_pnl column.
        window: Number of trading days in the rolling window.

    Returns:
        Series of rolling Sharpe values, NaN for the first (window-1) days.
    """
    pnl = backtest_df["net_daily_pnl"]
    rolling_mean = pnl.rolling(window).mean()
    rolling_std = pnl.rolling(window).std()
    return (rolling_mean / rolling_std) * np.sqrt(252)


def rolling_win_rate(
    trade_log: pd.DataFrame, backtest_df: pd.DataFrame, window: int = ROLLING_WIN_RATE_WINDOW
) -> pd.Series:
    """Compute rolling win rate over the last N completed trades.

    For each date in the backtest, finds trades exited on or before that date,
    takes the last `window` trades, and computes the fraction with positive P&L.

    Args:
        trade_log: DataFrame with exit_date and pnl columns.
        backtest_df: Backtest DataFrame (used for date index).
        window: Number of recent trades to consider.

    Returns:
        Series indexed like backtest_df, NaN until `window` trades complete.
    """
    if trade_log.empty:
        return pd.Series(np.nan, index=backtest_df.index, name="rolling_win_rate")

    trades = trade_log.sort_values("exit_date").reset_index(drop=True)
    exit_dates = pd.to_datetime(trades["exit_date"]).values
    wins = (trades["pnl"] > 0).astype(float).values
    cum_wins = np.cumsum(wins)

    result = pd.Series(np.nan, index=backtest_df.index, name="rolling_win_rate")

    for date in backtest_df.index:
        n_exited = np.searchsorted(exit_dates, np.datetime64(date), side="right")
        if n_exited < window:
            continue
        start = n_exited - window
        win_count = cum_wins[n_exited - 1] - (cum_wins[start - 1] if start > 0 else 0)
        result[date] = win_count / window

    return result


def monthly_returns(backtest_df: pd.DataFrame, capital: float) -> pd.DataFrame:
    """Compute monthly return percentages as a year x month matrix.

    Args:
        backtest_df: Backtest DataFrame with net_daily_pnl and equity columns.
        capital: Starting capital for the first month's denominator.

    Returns:
        DataFrame with year index, month columns (1-12), percentage values.
    """
    pnl = backtest_df["net_daily_pnl"].copy()
    pnl.index = pd.to_datetime(pnl.index)

    monthly_pnl = pnl.groupby([pnl.index.year, pnl.index.month]).sum()
    monthly_pnl.index.names = ["year", "month"]

    equity = backtest_df["equity"].copy()
    equity.index = pd.to_datetime(equity.index)
    month_start_equity = equity.groupby([equity.index.year, equity.index.month]).first()
    month_start_equity.index.names = ["year", "month"]

    # First month uses starting capital
    first_idx = month_start_equity.index[0]
    month_start_equity[first_idx] = capital

    monthly_ret = (monthly_pnl / month_start_equity) * 100
    matrix = monthly_ret.unstack(level="month")
    if isinstance(matrix.columns, pd.MultiIndex):
        matrix.columns = matrix.columns.droplevel(0)

    return matrix


def drawdown_periods(backtest_df: pd.DataFrame) -> pd.DataFrame:
    """Identify distinct drawdown periods from the equity curve.

    Args:
        backtest_df: Backtest DataFrame with equity column.

    Returns:
        DataFrame with start, trough_date, recovery_date, duration_days,
        max_dd_dollars, max_dd_pct per drawdown period.
    """
    equity = backtest_df["equity"]
    running_max = equity.cummax()
    dd = equity - running_max

    periods = []
    in_drawdown = False
    start = None
    trough_date = None
    trough_val = 0.0
    peak_val = 0.0

    for date, val in dd.items():
        if val < 0 and not in_drawdown:
            in_drawdown = True
            start = date
            peak_val = running_max[date]
            trough_date = date
            trough_val = val
        elif val < 0 and in_drawdown:
            if val < trough_val:
                trough_date = date
                trough_val = val
        elif val >= 0 and in_drawdown:
            in_drawdown = False
            periods.append({
                "start": start,
                "trough_date": trough_date,
                "recovery_date": date,
                "duration_days": (date - start).days,
                "max_dd_dollars": trough_val,
                "max_dd_pct": (trough_val / peak_val) * 100 if peak_val > 0 else 0.0,
            })

    if in_drawdown:
        periods.append({
            "start": start,
            "trough_date": trough_date,
            "recovery_date": None,
            "duration_days": (equity.index[-1] - start).days,
            "max_dd_dollars": trough_val,
            "max_dd_pct": (trough_val / peak_val) * 100 if peak_val > 0 else 0.0,
        })

    return pd.DataFrame(periods)
