"""Futures-specific validation checks.

Each function takes a DataFrame and returns a boolean Series where
True means the row passes the check.
"""

import pandas as pd


def check_high_gte_low(df: pd.DataFrame) -> pd.Series:
    """True for rows where high >= low.

    Args:
        df: DataFrame with 'high' and 'low' columns.

    Returns:
        Boolean Series aligned with df.index.
    """
    return df["high"] >= df["low"]


def check_close_within_range(df: pd.DataFrame) -> pd.Series:
    """True for rows where low <= close <= high.

    Args:
        df: DataFrame with 'low', 'close', and 'high' columns.

    Returns:
        Boolean Series aligned with df.index.
    """
    return (df["close"] >= df["low"]) & (df["close"] <= df["high"])
