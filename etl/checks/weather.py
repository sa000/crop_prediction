"""Weather-specific validation checks.

Each function takes a DataFrame and returns a boolean Series where
True means the row passes the check.
"""

import pandas as pd


def check_temp_max_gte_min(df: pd.DataFrame) -> pd.Series:
    """True for rows where temp_max_f >= temp_min_f.

    Args:
        df: DataFrame with 'temp_max_f' and 'temp_min_f' columns.

    Returns:
        Boolean Series aligned with df.index.
    """
    return df["temp_max_f"] >= df["temp_min_f"]
