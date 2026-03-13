"""Weather feature computations: rolling aggregations and anomaly detection.

All functions are pure -- no I/O. The FUNCTIONS dict maps config names to
callables for dispatch by the pipeline.
"""

import pandas as pd


def rolling_sum(series: pd.Series, window: int, **_kwargs) -> pd.Series:
    """Rolling sum over a fixed window.

    Args:
        series: Daily measurement series.
        window: Number of periods.

    Returns:
        Rolling sum series.
    """
    return series.rolling(window=window).sum()


def rolling_mean(series: pd.Series, window: int, **_kwargs) -> pd.Series:
    """Rolling mean over a fixed window.

    Args:
        series: Daily measurement series.
        window: Number of periods.

    Returns:
        Rolling mean series.
    """
    return series.rolling(window=window).mean()


def rolling_mean_diff(
    df: pd.DataFrame, col_a: str, col_b: str, window: int, **_kwargs
) -> pd.Series:
    """Rolling mean of the difference between two columns.

    Args:
        df: DataFrame containing both columns.
        col_a: Name of the first column (e.g. temp_max_f).
        col_b: Name of the second column (e.g. temp_min_f).
        window: Number of periods.

    Returns:
        Rolling mean of (col_a - col_b).
    """
    diff = df[col_a] - df[col_b]
    return diff.rolling(window=window).mean()


def rolling_zscore(series: pd.Series, window: int, **_kwargs) -> pd.Series:
    """Rolling z-score for anomaly detection.

    Args:
        series: Daily measurement series.
        window: Number of periods.

    Returns:
        Z-score series: (value - rolling_mean) / rolling_std.
    """
    mean = series.rolling(window=window).mean()
    std = series.rolling(window=window).std()
    return (series - mean) / std


FUNCTIONS = {
    "rolling_sum": rolling_sum,
    "rolling_mean": rolling_mean,
    "rolling_mean_diff": rolling_mean_diff,
    "rolling_zscore": rolling_zscore,
}
