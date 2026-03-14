"""Backtesting engine with dollar P&L and position sizing.

Takes a DataFrame with Close prices and a signal column, simulates trading
with equity-based position sizing, and produces a trade log with dollar P&L
and comprehensive performance statistics."""

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def compute_positions(df: pd.DataFrame) -> pd.DataFrame:
    """Derive held positions from the signal column.

    Position on day T is determined by the signal generated at close of day T-1.
    This one-day delay reflects realistic execution.

    Args:
        df: DataFrame with a signal column.

    Returns:
        DataFrame with additional position column.
    """
    df = df.copy()
    df["position"] = df["signal"].shift(1).fillna(0).astype(int)
    return df


def compute_daily_pnl(
    df: pd.DataFrame,
    capital: float = 100_000_000,
    risk_pct: float = 0.01,
    cost_per_trade: float = 0.0,
) -> pd.DataFrame:
    """Calculate daily and cumulative P&L in dollars with position sizing.

    On trade entry, allocates risk_pct of current equity. Units = allocation / price.
    Daily P&L = units * price_change. No pyramiding on consecutive same-direction
    signals.

    Args:
        df: DataFrame with position and Close columns.
        capital: Starting capital in dollars.
        risk_pct: Fraction of equity to allocate per trade.
        cost_per_trade: Dollar cost deducted on each position change. Defaults to 0.

    Returns:
        DataFrame with units, daily_pnl, trade_cost, net_daily_pnl,
        cumulative_pnl, and equity columns.
    """
    df = df.copy()
    n = len(df)
    units = np.zeros(n)
    daily_pnl = np.zeros(n)
    trade_cost = np.zeros(n)
    equity_arr = np.full(n, float(capital))

    positions = df["position"].values
    closes = df["Close"].values
    current_units = 0.0
    current_equity = float(capital)
    prev_position = 0

    for i in range(n):
        pos = int(positions[i])
        price_change = closes[i] - closes[i - 1] if i > 0 else 0.0

        if pos != prev_position:
            # Position changed — compute P&L on old position first
            pnl = current_units * price_change * prev_position
            daily_pnl[i] = pnl

            # Size new position from current equity
            if pos != 0:
                allocation = current_equity * risk_pct
                current_units = int(allocation / closes[i]) if closes[i] > 0 else 0
            else:
                current_units = 0.0

            trade_cost[i] = cost_per_trade
        else:
            # Holding same position
            pnl = current_units * price_change * pos
            daily_pnl[i] = pnl

        units[i] = current_units
        net = daily_pnl[i] - trade_cost[i]
        current_equity += net
        equity_arr[i] = current_equity
        prev_position = pos

    df["units"] = units
    df["daily_pnl"] = daily_pnl
    df["trade_cost"] = trade_cost
    df["net_daily_pnl"] = df["daily_pnl"] - df["trade_cost"]
    df["cumulative_pnl"] = df["net_daily_pnl"].cumsum()
    df["equity"] = equity_arr

    return df


def build_trade_log(df: pd.DataFrame) -> pd.DataFrame:
    """Build a log of completed trades from position changes.

    Each row represents a round-trip trade with entry date, exit date,
    direction, prices, units, dollar P&L, and holding period.

    Args:
        df: DataFrame with position, Close, units, and net_daily_pnl columns.

    Returns:
        DataFrame with one row per completed trade.
    """
    trades = []
    current_position = 0
    entry_date = None
    entry_price = None
    entry_units = None
    trade_pnl = 0.0

    for date, row in df.iterrows():
        pos = int(row["position"])

        if current_position == 0 and pos != 0:
            # Enter new position
            entry_date = date
            entry_price = row["Close"]
            entry_units = row["units"]
            current_position = pos
            trade_pnl = row["net_daily_pnl"]

        elif current_position != 0 and pos != current_position:
            # Position changed — close current trade
            trade_pnl += row["net_daily_pnl"]
            direction = "long" if current_position == 1 else "short"
            exit_price = row["Close"]
            pnl_per_unit = (exit_price - entry_price) * current_position
            holding_days = (date - entry_date).days

            trades.append({
                "entry_date": entry_date,
                "exit_date": date,
                "direction": direction,
                "entry_price": entry_price,
                "exit_price": exit_price,
                "units": entry_units,
                "pnl": trade_pnl,
                "pnl_per_unit": pnl_per_unit,
                "holding_days": holding_days,
            })

            if pos != 0:
                # Immediately enter opposite position
                entry_date = date
                entry_price = row["Close"]
                entry_units = row["units"]
                current_position = pos
                trade_pnl = 0.0
            else:
                current_position = 0
                entry_date = None
                entry_price = None
                entry_units = None
                trade_pnl = 0.0

        elif current_position != 0:
            # Holding same position
            trade_pnl += row["net_daily_pnl"]

    # Log open trade if one exists at the end
    if current_position != 0 and entry_date is not None:
        last_date = df.index[-1]
        last_price = df["Close"].iloc[-1]
        direction = "long" if current_position == 1 else "short"
        pnl_per_unit = (last_price - entry_price) * current_position
        holding_days = (last_date - entry_date).days

        trades.append({
            "entry_date": entry_date,
            "exit_date": last_date,
            "direction": direction,
            "entry_price": entry_price,
            "exit_price": last_price,
            "units": entry_units,
            "pnl": trade_pnl,
            "pnl_per_unit": pnl_per_unit,
            "holding_days": holding_days,
        })

    trade_log = pd.DataFrame(trades)
    logger.info("Built trade log: %d trades", len(trade_log))
    return trade_log


def compute_stats(
    df: pd.DataFrame, trade_log: pd.DataFrame, capital: float = 100_000_000
) -> dict:
    """Compute comprehensive dollar-denominated performance statistics.

    Args:
        df: Backtest DataFrame with net_daily_pnl, cumulative_pnl, equity columns.
        trade_log: DataFrame of completed trades with pnl column.
        capital: Starting capital for return calculations.

    Returns:
        Dictionary of performance metrics.
    """
    stats = {}
    stats["total_pnl"] = df["cumulative_pnl"].iloc[-1] if len(df) > 0 else 0.0
    stats["total_return_pct"] = (stats["total_pnl"] / capital) * 100 if capital > 0 else 0.0
    stats["starting_equity"] = capital
    stats["ending_equity"] = df["equity"].iloc[-1] if len(df) > 0 else capital
    stats["num_trades"] = len(trade_log)

    if len(trade_log) > 0:
        wins = trade_log[trade_log["pnl"] > 0]
        losses = trade_log[trade_log["pnl"] <= 0]
        stats["win_rate"] = len(wins) / len(trade_log)
        stats["avg_win"] = wins["pnl"].mean() if len(wins) > 0 else 0.0
        stats["avg_loss"] = losses["pnl"].mean() if len(losses) > 0 else 0.0
        stats["best_trade"] = trade_log["pnl"].max()
        stats["worst_trade"] = trade_log["pnl"].min()
        stats["avg_holding_days"] = trade_log["holding_days"].mean()

        # Profit factor
        gross_wins = wins["pnl"].sum() if len(wins) > 0 else 0.0
        gross_losses = abs(losses["pnl"].sum()) if len(losses) > 0 else 0.0
        stats["profit_factor"] = (
            gross_wins / gross_losses if gross_losses > 0 else float("inf")
        )

        # Streaks
        outcomes = (trade_log["pnl"] > 0).astype(int).values
        longest_win = 0
        longest_lose = 0
        current_streak = 0
        current_type = None
        for outcome in outcomes:
            if outcome == current_type:
                current_streak += 1
            else:
                current_type = outcome
                current_streak = 1
            if outcome == 1:
                longest_win = max(longest_win, current_streak)
            else:
                longest_lose = max(longest_lose, current_streak)
        stats["longest_win_streak"] = longest_win
        stats["longest_lose_streak"] = longest_lose
    else:
        stats["win_rate"] = 0.0
        stats["avg_win"] = 0.0
        stats["avg_loss"] = 0.0
        stats["best_trade"] = 0.0
        stats["worst_trade"] = 0.0
        stats["avg_holding_days"] = 0.0
        stats["profit_factor"] = 0.0
        stats["longest_win_streak"] = 0
        stats["longest_lose_streak"] = 0

    # Sharpe ratio (annualized from daily P&L)
    daily_pnl = df["net_daily_pnl"].dropna()
    if daily_pnl.std() > 0:
        stats["sharpe_ratio"] = (daily_pnl.mean() / daily_pnl.std()) * np.sqrt(252)
    else:
        stats["sharpe_ratio"] = 0.0

    # Sortino ratio (annualized, downside deviation only)
    daily_returns = daily_pnl / capital
    downside = daily_returns[daily_returns < 0]
    downside_std = downside.std() if len(downside) > 0 else 0.0
    ann_return = daily_returns.mean() * 252
    stats["sortino_ratio"] = (
        ann_return / (downside_std * np.sqrt(252)) if downside_std > 0 else 0.0
    )

    # Max drawdown from equity curve
    equity = df["equity"]
    running_max = equity.cummax()
    drawdown = equity - running_max
    stats["max_drawdown"] = drawdown.min()
    peak_at_trough = running_max[drawdown.idxmin()] if len(drawdown) > 0 else capital
    stats["max_drawdown_pct"] = (
        (stats["max_drawdown"] / peak_at_trough) * 100 if peak_at_trough > 0 else 0.0
    )

    # Calmar ratio (annualized return / max drawdown %)
    stats["calmar_ratio"] = (
        (ann_return * 100) / abs(stats["max_drawdown_pct"])
        if stats["max_drawdown_pct"] != 0 else 0.0
    )

    # VaR 95% and CVaR 95% (in dollars, from daily P&L)
    stats["var_95"] = float(np.percentile(daily_pnl, 5)) if len(daily_pnl) > 0 else 0.0
    tail = daily_pnl[daily_pnl <= stats["var_95"]]
    stats["cvar_95"] = float(tail.mean()) if len(tail) > 0 else 0.0

    return stats


def run_backtest(
    df: pd.DataFrame,
    capital: float = 100_000_000,
    risk_pct: float = 0.01,
    cost_per_trade: float = 0.0,
) -> tuple:
    """Run the full backtest pipeline with dollar P&L and position sizing.

    Args:
        df: DataFrame with Close and signal columns, datetime index.
        capital: Starting capital in dollars. Defaults to $100M.
        risk_pct: Fraction of equity to allocate per trade. Defaults to 1%.
        cost_per_trade: Dollar cost per position change. Defaults to 0.

    Returns:
        Tuple of (backtest_df, trade_log, stats_dict).
    """
    df = compute_positions(df)
    df = compute_daily_pnl(df, capital=capital, risk_pct=risk_pct, cost_per_trade=cost_per_trade)
    trade_log = build_trade_log(df)
    stats = compute_stats(df, trade_log, capital=capital)

    logger.info(
        "Backtest complete: total_pnl=$%.0f, trades=%d, win_rate=%.1f%%, sharpe=%.2f",
        stats["total_pnl"], stats["num_trades"],
        stats["win_rate"] * 100, stats["sharpe_ratio"],
    )

    return df, trade_log, stats
