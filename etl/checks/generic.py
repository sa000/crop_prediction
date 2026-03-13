"""Generic validation checks that work on any DataFrame and column.

Each function takes a DataFrame (and relevant parameters) and returns
a boolean Series where True means the row passes the check.
"""

import pandas as pd


def check_nulls(df: pd.DataFrame, columns: list[str]) -> pd.Series:
    """True for rows where none of the specified columns are null.

    Args:
        df: DataFrame to validate.
        columns: Column names to check for nulls.

    Returns:
        Boolean Series aligned with df.index.
    """
    return df[columns].notna().all(axis=1)


def check_stddev_outlier(
    df: pd.DataFrame, column: str, historical_values: pd.Series, sigma: float
) -> pd.Series:
    """True for rows where the column value is within N sigma of the historical mean.

    Args:
        df: Incoming data to validate.
        column: Column name to check.
        historical_values: All prior clean values for this column (from warehouse.db).
        sigma: Number of standard deviations to allow.

    Returns:
        Boolean Series aligned with df.index.
    """
    mean = historical_values.mean()
    std = historical_values.std()
    if std == 0 or pd.isna(std):
        return pd.Series(True, index=df.index)
    return (df[column] - mean).abs() <= sigma * std


def check_date_not_future(df: pd.DataFrame, column: str) -> pd.Series:
    """True for rows where the date is not in the future.

    Args:
        df: DataFrame to validate.
        column: Date column name.

    Returns:
        Boolean Series aligned with df.index.
    """
    today = pd.Timestamp.now().normalize()
    return pd.to_datetime(df[column]) <= today


def check_non_negative(df: pd.DataFrame, column: str) -> pd.Series:
    """True for rows where the column value is >= 0.

    Args:
        df: DataFrame to validate.
        column: Column name to check.

    Returns:
        Boolean Series aligned with df.index.
    """
    return df[column] >= 0


def check_positive(df: pd.DataFrame, column: str) -> pd.Series:
    """True for rows where the column value is > 0.

    Args:
        df: DataFrame to validate.
        column: Column name to check.

    Returns:
        Boolean Series aligned with df.index.
    """
    return df[column] > 0
