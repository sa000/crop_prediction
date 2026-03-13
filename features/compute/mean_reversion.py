"""Mean-reversion feature computations: Bollinger bands, z-score, percentile rank.

All functions are pure -- no I/O. The FUNCTIONS dict maps config names to
callables for dispatch by the pipeline.
"""

import pandas as pd


def bollinger_upper(
    series: pd.Series, window: int, num_std: float, **_kwargs
) -> pd.Series:
    """Upper Bollinger Band: SMA + num_std * rolling std.

    Args:
        series: Price series.
        window: Rolling window size.
        num_std: Number of standard deviations.

    Returns:
        Upper band series.
    """
    mid = series.rolling(window=window).mean()
    std = series.rolling(window=window).std()
    return mid + num_std * std


def bollinger_lower(
    series: pd.Series, window: int, num_std: float, **_kwargs
) -> pd.Series:
    """Lower Bollinger Band: SMA - num_std * rolling std.

    Args:
        series: Price series.
        window: Rolling window size.
        num_std: Number of standard deviations.

    Returns:
        Lower band series.
    """
    mid = series.rolling(window=window).mean()
    std = series.rolling(window=window).std()
    return mid - num_std * std


def zscore(series: pd.Series, window: int, **_kwargs) -> pd.Series:
    """Rolling z-score: (value - rolling_mean) / rolling_std.

    Args:
        series: Price series.
        window: Rolling window size.

    Returns:
        Z-score series.
    """
    mean = series.rolling(window=window).mean()
    std = series.rolling(window=window).std()
    return (series - mean) / std


def pct_rank(series: pd.Series, window: int, **_kwargs) -> pd.Series:
    """Rolling percentile rank (0-1).

    For each value, computes the fraction of values in the trailing window
    that are less than or equal to the current value.

    Args:
        series: Price series.
        window: Rolling window size.

    Returns:
        Percentile rank series (0 to 1).
    """
    def _rank_in_window(arr):
        if len(arr) < window:
            return float("nan")
        current = arr[-1]
        return (arr <= current).sum() / len(arr)

    return series.rolling(window=window).apply(_rank_in_window, raw=True)


FUNCTIONS = {
    "bollinger_upper": bollinger_upper,
    "bollinger_lower": bollinger_lower,
    "zscore": zscore,
    "pct_rank": pct_rank,
}
