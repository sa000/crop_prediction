"""Load futures and weather data from the SQLite warehouse, merge on
trading days, engineer lagged precipitation features, and generate a
long/short trading signal."""

import logging
import sys
from pathlib import Path

import pandas as pd

# Allow imports from the project root so `etl.db` resolves.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from etl import db

logger = logging.getLogger(__name__)

PRECIP_COLS = ["Iowa_precip_in", "Illinois_precip_in", "Nebraska_precip_in"]
ROLLING_WINDOW = 30
LAG_DAYS = 1


def load_futures() -> pd.DataFrame:
    """Load corn futures OHLCV data from the SQLite warehouse.

    Returns:
        DataFrame indexed by date with Open, High, Low, Close, Volume columns.
    """
    conn = db.get_connection()
    df = pd.read_sql(
        "SELECT date, open, high, low, close, volume "
        "FROM futures_daily WHERE ticker = 'ZC=F' ORDER BY date",
        conn,
        parse_dates=["date"],
        index_col="date",
    )
    conn.close()
    df.columns = [c.capitalize() for c in df.columns]
    df.sort_index(inplace=True)
    logger.info("Loaded futures: %d rows (%s to %s)", len(df), df.index[0].date(), df.index[-1].date())
    return df


def load_weather() -> pd.DataFrame:
    """Load Corn Belt weather data from the SQLite warehouse.

    The database stores long format (one row per date + state). This
    function pivots to wide format for compatibility with the existing
    feature engineering pipeline.

    Returns:
        DataFrame indexed by date with temp and precip columns per state.
    """
    conn = db.get_connection()
    df = pd.read_sql(
        "SELECT date, state, temp_max_f, temp_min_f, precip_in "
        "FROM weather_daily ORDER BY date",
        conn,
        parse_dates=["date"],
    )
    conn.close()

    df_wide = df.pivot(index="date", columns="state", values=["temp_max_f", "temp_min_f", "precip_in"])
    df_wide.columns = [f"{state}_{metric}" for metric, state in df_wide.columns]
    df_wide.sort_index(inplace=True)
    logger.info("Loaded weather: %d rows (%s to %s)", len(df_wide), df_wide.index[0].date(), df_wide.index[-1].date())
    return df_wide


def merge_on_trading_days(futures: pd.DataFrame, weather: pd.DataFrame) -> pd.DataFrame:
    """Inner-join futures and weather on date index.

    Weather contains all calendar days; futures only trading days. The inner
    join naturally filters to trading days where both datasets have data.

    Args:
        futures: OHLCV DataFrame indexed by date.
        weather: Weather DataFrame indexed by date.

    Returns:
        Merged DataFrame on trading-day dates.
    """
    df = futures.join(weather, how="inner")
    logger.info("Merged dataset: %d rows", len(df))
    return df


def add_avg_precip(df: pd.DataFrame) -> pd.DataFrame:
    """Add a column averaging precipitation across all tracked states.

    Args:
        df: Merged DataFrame with per-state precip columns.

    Returns:
        DataFrame with additional avg_precip_in column.
    """
    df = df.copy()
    df["avg_precip_in"] = df[PRECIP_COLS].mean(axis=1)
    return df


def add_rolling_precip_lag(df: pd.DataFrame, window: int = ROLLING_WINDOW,
                           lag: int = LAG_DAYS) -> pd.DataFrame:
    """Compute rolling sum of average precipitation with a lag to prevent lookahead.

    On trading day T, the value reflects precipitation from days T-(window+lag-1)
    through T-lag. This ensures no future data leaks into the signal.

    Args:
        df: DataFrame with avg_precip_in column.
        window: Number of trading days in the rolling window.
        lag: Number of days to shift forward (1 = use only data through yesterday).

    Returns:
        DataFrame with additional rolling_precip column.
    """
    df = df.copy()
    df["rolling_precip"] = df["avg_precip_in"].rolling(window=window).sum().shift(lag)
    return df


def generate_signal(df: pd.DataFrame, threshold_long: float,
                    threshold_short: float) -> pd.DataFrame:
    """Generate a long/short/flat signal based on rolling precipitation.

    High recent precipitation suggests crop damage, which is bullish for
    corn prices (supply reduction). Low precipitation suggests normal
    conditions with no supply shock.

    Args:
        df: DataFrame with rolling_precip column.
        threshold_long: Go long (+1) when rolling precip is at or above this value.
        threshold_short: Go short (-1) when rolling precip is at or below this value.

    Returns:
        DataFrame with additional signal column (+1, -1, or 0).
    """
    df = df.copy()
    df["signal"] = 0
    df.loc[df["rolling_precip"] >= threshold_long, "signal"] = 1
    df.loc[df["rolling_precip"] <= threshold_short, "signal"] = -1
    # Rows without enough history for rolling calc stay NaN -> set to 0
    df.loc[df["rolling_precip"].isna(), "signal"] = 0

    long_pct = (df["signal"] == 1).mean() * 100
    short_pct = (df["signal"] == -1).mean() * 100
    flat_pct = (df["signal"] == 0).mean() * 100
    logger.info("Signal distribution: long=%.1f%% short=%.1f%% flat=%.1f%%", long_pct, short_pct, flat_pct)

    return df


def build_signal_dataframe(threshold_long: float, threshold_short: float,
                           window: int = ROLLING_WINDOW,
                           lag: int = LAG_DAYS) -> pd.DataFrame:
    """End-to-end pipeline: load data, merge, engineer features, generate signal.

    Args:
        threshold_long: Rolling precip threshold to go long.
        threshold_short: Rolling precip threshold to go short.
        window: Rolling window size in trading days.
        lag: Lag days to avoid lookahead bias.

    Returns:
        Complete DataFrame with OHLCV, weather, features, and signal columns.
    """
    futures = load_futures()
    weather = load_weather()
    df = merge_on_trading_days(futures, weather)
    df = add_avg_precip(df)
    df = add_rolling_precip_lag(df, window=window, lag=lag)
    df = generate_signal(df, threshold_long, threshold_short)
    return df
