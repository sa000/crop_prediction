"""Back-adjust continuous futures prices to remove contract roll gaps.

Walks through each ticker's price series, detects overnight gaps that
exceed a volatility threshold, and shifts all prior prices so that
day-to-day returns reflect real market moves only."""

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

ROLL_SIGMA_THRESHOLD = 5.0
VOLATILITY_WINDOW = 30


def detect_rolls(closes: np.ndarray, highs: np.ndarray, lows: np.ndarray,
                 window: int = VOLATILITY_WINDOW,
                 threshold: float = ROLL_SIGMA_THRESHOLD) -> list[tuple[int, float]]:
    """Find indices where a contract roll likely occurred.

    A roll is flagged when:
    1. The overnight gap (prev close to current open approximated by close)
       exceeds `threshold` times the trailing rolling std of daily changes.
    2. The current day's intraday range (high - low) is NOT abnormally large,
       distinguishing rolls from real market shocks (e.g. war spikes) which
       show both large gaps AND large intraday ranges.

    Args:
        closes: Array of close prices sorted by date.
        highs: Array of high prices sorted by date.
        lows: Array of low prices sorted by date.
        window: Lookback window for rolling volatility estimate.
        threshold: Number of standard deviations to flag as a roll.

    Returns:
        List of (index, gap_amount) tuples for each detected roll.
    """
    daily_changes = np.diff(closes)
    intraday_ranges = highs - lows
    rolls = []

    for i in range(window, len(daily_changes)):
        lookback = daily_changes[max(0, i - window):i]
        rolling_std = np.std(lookback)

        if rolling_std == 0:
            continue

        change = daily_changes[i]
        if abs(change) <= threshold * rolling_std:
            continue

        # Check intraday range on the gap day — rolls have normal ranges,
        # real shocks have huge ranges
        day_idx = i + 1  # index in the original arrays (diff shifts by 1)
        day_range = intraday_ranges[day_idx]
        avg_range = np.mean(intraday_ranges[max(0, day_idx - window):day_idx])

        if avg_range > 0 and day_range < 3 * avg_range:
            rolls.append((day_idx, change))

    return rolls


def back_adjust(df: pd.DataFrame) -> pd.DataFrame:
    """Apply back-adjustment to a single ticker's price series.

    Walks forward through the series, accumulates roll adjustments, then
    subtracts the cumulative adjustment from all prices before each roll
    so that daily returns are preserved.

    Args:
        df: DataFrame with date index and open/high/low/close columns,
            sorted by date ascending.

    Returns:
        DataFrame with adjusted price columns. Original structure preserved.
    """
    df = df.copy()
    closes = df["close"].values.astype(float)
    rolls = detect_rolls(closes)

    if not rolls:
        logger.info("No rolls detected")
        return df

    # Accumulate adjustments from the end backwards
    # Each roll's gap is subtracted from all prices before that roll
    price_cols = ["open", "high", "low", "close"]
    adjustment = 0.0

    # Process rolls from latest to earliest
    for idx, gap in sorted(rolls, reverse=True):
        adjustment += gap
        # Shift all prices before this roll
        for col in price_cols:
            df.loc[df.index[:idx], col] += gap

    logger.info(
        "Applied %d roll adjustments, total cumulative shift: $%.2f",
        len(rolls), adjustment,
    )

    return df


def adjust_futures(conn) -> dict:
    """Back-adjust all futures tickers in the warehouse in-place.

    Reads each ticker's full history, detects and adjusts roll gaps,
    then updates the rows in the database.

    Args:
        conn: Open SQLite connection to the warehouse.

    Returns:
        Dict of ticker -> number of rolls detected.
    """
    tickers = pd.read_sql(
        "SELECT DISTINCT ticker FROM futures_daily", conn
    )["ticker"].tolist()

    results = {}

    for ticker in tickers:
        df = pd.read_sql(
            "SELECT rowid, date, open, high, low, close, volume "
            "FROM futures_daily WHERE ticker = ? ORDER BY date",
            conn,
            params=(ticker,),
        )

        if df.empty:
            results[ticker] = 0
            continue

        closes = df["close"].values.astype(float)
        highs = df["high"].values.astype(float)
        lows = df["low"].values.astype(float)
        rolls = detect_rolls(closes, highs, lows)
        results[ticker] = len(rolls)

        if not rolls:
            logger.info("%s: no rolls detected", ticker)
            continue

        # Apply adjustment — add the gap (which is negative when new contract
        # is cheaper) to shift pre-roll prices down for continuity
        price_cols = ["open", "high", "low", "close"]
        for idx, gap in sorted(rolls, reverse=True):
            for col in price_cols:
                df.loc[:idx - 1, col] += gap

        # Update rows in database
        for _, row in df.iterrows():
            conn.execute(
                "UPDATE futures_daily SET open=?, high=?, low=?, close=? "
                "WHERE date=? AND ticker=?",
                (row["open"], row["high"], row["low"], row["close"],
                 row["date"], ticker),
            )

        conn.commit()

        roll_dates = [df.iloc[idx]["date"] for idx, _ in rolls]
        total_adj = sum(gap for _, gap in rolls)
        logger.info(
            "%s: %d rolls adjusted (total shift: $%.2f), dates: %s",
            ticker, len(rolls), total_adj, roll_dates,
        )

    return results
