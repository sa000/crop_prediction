"""Parquet I/O layer for the feature store.

Handles reading, writing, and appending feature DataFrames as Parquet files.
All feature Parquet files are sorted by date and stored one per entity per
category (e.g. features/momentum/corn.parquet).
"""

import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

FEATURES_DIR = Path(__file__).resolve().parent


def get_parquet_path(category: str, entity_name: str) -> Path:
    """Build the path for a feature Parquet file.

    Args:
        category: Feature category (momentum, mean_reversion, weather).
        entity_name: Entity name (corn, iowa, etc.).

    Returns:
        Path to the Parquet file.
    """
    return FEATURES_DIR / category / f"{entity_name}.parquet"


def read_features(category: str, entity_name: str) -> pd.DataFrame | None:
    """Read an existing feature Parquet file.

    Args:
        category: Feature category.
        entity_name: Entity name.

    Returns:
        DataFrame if the file exists, None otherwise.
    """
    path = get_parquet_path(category, entity_name)
    if not path.exists():
        return None
    df = pd.read_parquet(path)
    logger.debug("Read %d rows from %s", len(df), path)
    return df


def get_max_date(category: str, entity_name: str) -> str | None:
    """Get the maximum date in an existing feature file.

    Args:
        category: Feature category.
        entity_name: Entity name.

    Returns:
        Max date as YYYY-MM-DD string, or None if file does not exist.
    """
    df = read_features(category, entity_name)
    if df is None or df.empty:
        return None
    return str(df["date"].max())


def write_features(df: pd.DataFrame, category: str, entity_name: str) -> Path:
    """Write a feature DataFrame to Parquet, sorted by date.

    Creates parent directories if needed.

    Args:
        df: Feature DataFrame with a 'date' column.
        category: Feature category.
        entity_name: Entity name.

    Returns:
        Path to the written file.
    """
    path = get_parquet_path(category, entity_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    df = df.sort_values("date").reset_index(drop=True)
    df.to_parquet(path, index=False)
    logger.info("Wrote %d rows to %s", len(df), path)
    return path


def append_features(
    existing: pd.DataFrame, new_rows: pd.DataFrame, category: str, entity_name: str
) -> Path:
    """Append new rows to an existing feature file.

    Concatenates, deduplicates on date, sorts, and rewrites.

    Args:
        existing: Existing feature DataFrame.
        new_rows: New rows to append.
        category: Feature category.
        entity_name: Entity name.

    Returns:
        Path to the rewritten file.
    """
    combined = pd.concat([existing, new_rows], ignore_index=True)
    combined = combined.drop_duplicates(subset=["date"], keep="last")
    return write_features(combined, category, entity_name)
