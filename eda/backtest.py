"""Backtesting engine for a simple long/short signal on corn futures.

Takes a DataFrame with Close prices and a signal column, simulates trading,
and produces a trade log with P&L in price points (cents per bushel)."""

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


def compute_daily_pnl(df: pd.DataFrame, cost_per_trade: float = 0.0) -> pd.DataFrame:
    """Calculate daily and cumulative P&L in price points.

    Args:
        df: DataFrame with position and Close columns.
        cost_per_trade: Cost in price points deducted on each position change.
            Defaults to 0 (no costs).

    Returns:
        DataFrame with daily_pnl, trade_cost, net_daily_pnl, and cumulative_pnl columns.
    """
    df = df.copy()
    price_change = df["Close"].diff()
    df["daily_pnl"] = df["position"] * price_change

    position_changed = df["position"].diff().fillna(0) != 0
    df["trade_cost"] = 0.0
    df.loc[position_changed, "trade_cost"] = cost_per_trade

    df["net_daily_pnl"] = df["daily_pnl"] - df["trade_cost"]
    df["cumulative_pnl"] = df["net_daily_pnl"].cumsum()

    return df


def build_trade_log(df: pd.DataFrame) -> pd.DataFrame:
    """Build a log of completed trades from position changes.

    Each row represents a round-trip trade with entry date, exit date,
    direction, prices, P&L, and holding period.

    Args:
        df: DataFrame with position and Close columns.

    Returns:
        DataFrame with one row per completed trade.
    """
    trades = []
    current_position = 0
    entry_date = None
    entry_price = None

    for date, row in df.iterrows():
        pos = int(row["position"])

        if current_position == 0 and pos != 0:
            entry_date = date
            entry_price = row["Close"]
            current_position = pos

        elif current_position != 0 and pos != current_position:
            direction = "long" if current_position == 1 else "short"
            exit_price = row["Close"]
            pnl = (exit_price - entry_price) * current_position
            holding_days = (date - entry_date).days

            trades.append({
                "entry_date": entry_date,
                "exit_date": date,
                "direction": direction,
                "entry_price": entry_price,
                "exit_price": exit_price,
                "pnl": pnl,
                "holding_days": holding_days,
            })

            if pos != 0:
                entry_date = date
                entry_price = row["Close"]
                current_position = pos
            else:
                current_position = 0
                entry_date = None
                entry_price = None

    # Log open trade if one exists at the end
    if current_position != 0 and entry_date is not None:
        last_date = df.index[-1]
        last_price = df["Close"].iloc[-1]
        direction = "long" if current_position == 1 else "short"
        trades.append({
            "entry_date": entry_date,
            "exit_date": last_date,
            "direction": direction,
            "entry_price": entry_price,
            "exit_price": last_price,
            "pnl": (last_price - entry_price) * current_position,
            "holding_days": (last_date - entry_date).days,
        })

    trade_log = pd.DataFrame(trades)
    logger.info("Built trade log: %d completed trades", len(trade_log))
    return trade_log


def compute_stats(df: pd.DataFrame, trade_log: pd.DataFrame) -> dict:
    """Compute summary performance statistics.

    Args:
        df: Backtest DataFrame with net_daily_pnl and cumulative_pnl columns.
        trade_log: DataFrame of completed trades with pnl column.

    Returns:
        Dictionary of performance metrics.
    """
    stats = {}
    stats["total_pnl"] = df["cumulative_pnl"].iloc[-1] if len(df) > 0 else 0.0
    stats["num_trades"] = len(trade_log)

    if len(trade_log) > 0:
        wins = trade_log[trade_log["pnl"] > 0]
        losses = trade_log[trade_log["pnl"] <= 0]
        stats["win_rate"] = len(wins) / len(trade_log)
        stats["avg_win"] = wins["pnl"].mean() if len(wins) > 0 else 0.0
        stats["avg_loss"] = losses["pnl"].mean() if len(losses) > 0 else 0.0
        stats["avg_holding_days"] = trade_log["holding_days"].mean()
    else:
        stats["win_rate"] = 0.0
        stats["avg_win"] = 0.0
        stats["avg_loss"] = 0.0
        stats["avg_holding_days"] = 0.0

    daily_pnl = df["net_daily_pnl"].dropna()
    if daily_pnl.std() > 0:
        stats["sharpe_ratio"] = (daily_pnl.mean() / daily_pnl.std()) * np.sqrt(252)
    else:
        stats["sharpe_ratio"] = 0.0

    cumulative = df["cumulative_pnl"]
    running_max = cumulative.cummax()
    drawdown = cumulative - running_max
    stats["max_drawdown"] = drawdown.min()

    return stats


def run_backtest(df: pd.DataFrame, cost_per_trade: float = 0.0) -> tuple:
    """Run the full backtest pipeline.

    Args:
        df: DataFrame with Close and signal columns.
        cost_per_trade: Cost per position change in price points. Defaults to 0.

    Returns:
        Tuple of (backtest_df, trade_log, stats_dict).
    """
    df = compute_positions(df)
    df = compute_daily_pnl(df, cost_per_trade=cost_per_trade)
    trade_log = build_trade_log(df)
    stats = compute_stats(df, trade_log)

    logger.info(
        "Backtest complete: total_pnl=%.2f, trades=%d, win_rate=%.1f%%, sharpe=%.2f",
        stats["total_pnl"], stats["num_trades"],
        stats["win_rate"] * 100, stats["sharpe_ratio"],
    )

    return df, trade_log, stats
