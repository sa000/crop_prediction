"""DuckDB query layer over the feature store Parquet files.

Provides both low-level SQL access and high-level convenience functions
for discovering and reading features. All connections are in-memory --
no persistent database file.
"""

import logging
from pathlib import Path

import duckdb
import pandas as pd
import yaml

from features import store

logger = logging.getLogger(__name__)

FEATURES_DIR = Path(__file__).resolve().parent
REGISTRY_PATH = FEATURES_DIR / "registry.yaml"


def get_connection() -> duckdb.DuckDBPyConnection:
    """Create an in-memory DuckDB connection.

    Returns:
        A DuckDB connection.
    """
    return duckdb.connect()


def load_registry() -> dict:
    """Load the feature registry.

    Returns:
        Registry dict, or empty dict if file does not exist.
    """
    if not REGISTRY_PATH.exists():
        logger.warning("Registry not found at %s", REGISTRY_PATH)
        return {}
    with open(REGISTRY_PATH) as f:
        return yaml.safe_load(f)


def list_tickers() -> list[dict]:
    """List all available tickers from the registry.

    Returns:
        List of ticker dicts with symbol, name, source, description.
    """
    registry = load_registry()
    return registry.get("tickers", [])


def list_features(category: str | None = None) -> list[dict]:
    """List available features with metadata from Parquet.

    Reads from metadata.parquet (one row per feature per entity).
    Falls back to registry.yaml if metadata Parquet does not exist.

    Args:
        category: Optional category filter.

    Returns:
        List of feature dicts.
    """
    metadata = store.read_metadata()
    if not metadata.empty:
        if category:
            metadata = metadata[metadata["category"] == category]
        return metadata.to_dict("records")

    # Fallback to YAML
    registry = load_registry()
    features = registry.get("features", [])
    if category:
        features = [f for f in features if f["category"] == category]
    return features


def get_ticker_features(ticker_name: str) -> dict:
    """Get all features mapped to a specific ticker.

    Args:
        ticker_name: Ticker name (e.g. 'corn').

    Returns:
        Dict of category -> feature name list.
    """
    registry = load_registry()
    mapping = registry.get("ticker_feature_map", {})
    return mapping.get(ticker_name, {})


def get_unlinked_features() -> dict:
    """Get features not linked to any ticker (e.g. weather).

    Returns:
        Dict of category -> entity -> feature name list.
    """
    registry = load_registry()
    return registry.get("unlinked_features", {})


def _resolve_paths(sql: str) -> str:
    """Replace relative features/ paths with absolute paths in SQL.

    Allows queries to work regardless of the caller's working directory.

    Args:
        sql: SQL string potentially containing relative Parquet paths.

    Returns:
        SQL string with absolute paths.
    """
    import re
    project_root = FEATURES_DIR.parent
    return re.sub(
        r"'features/([^']+\.parquet)'",
        lambda m: f"'{project_root / 'features' / m.group(1)}'",
        sql,
    )


def query(sql: str) -> pd.DataFrame:
    """Run arbitrary SQL over Parquet files.

    Parquet files can be referenced by path in the SQL string, e.g.:
        SELECT * FROM 'features/momentum/corn.parquet' LIMIT 5

    Relative paths starting with 'features/' are resolved automatically.

    Args:
        sql: SQL query string.

    Returns:
        Query result as a DataFrame.
    """
    conn = get_connection()
    result = conn.execute(_resolve_paths(sql)).fetchdf()
    conn.close()
    return result


def read_parquet(
    category: str,
    entity_name: str,
    columns: list[str] | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pd.DataFrame:
    """Read a single feature Parquet file with optional filters.

    Args:
        category: Feature category.
        entity_name: Entity name.
        columns: Optional list of columns to select.
        start_date: Optional start date filter (inclusive).
        end_date: Optional end date filter (inclusive).

    Returns:
        Filtered DataFrame.
    """
    path = FEATURES_DIR / category / f"{entity_name}.parquet"
    if not path.exists():
        logger.warning("File not found: %s", path)
        return pd.DataFrame()

    col_str = ", ".join(columns) if columns else "*"
    sql = f"SELECT {col_str} FROM '{path}'"

    conditions = []
    if start_date:
        conditions.append(f"date >= '{start_date}'")
    if end_date:
        conditions.append(f"date <= '{end_date}'")
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)

    sql += " ORDER BY date"
    return query(sql)


def read_strategy_features(
    ticker: str,
    categories: list[str] | None = None,
    unlinked: list[dict] | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pd.DataFrame:
    """Read and join features for strategy consumption.

    Joins price-based feature files for the given ticker with optional
    unlinked feature files (weather, consumer, etc.), all on the date column.

    Args:
        ticker: Ticker name (e.g. 'corn').
        categories: Price feature categories to include (default: all).
        unlinked: List of {category, entity} dicts for non-ticker features.
        start_date: Optional start date filter.
        end_date: Optional end date filter.

    Returns:
        Joined DataFrame with all requested features.
    """
    if categories is None:
        categories = ["momentum", "mean_reversion"]

    result = None

    for cat in categories:
        df = read_parquet(cat, ticker, start_date=start_date, end_date=end_date)
        if df.empty:
            continue
        if result is None:
            result = df
        else:
            merge_cols = [c for c in df.columns if c not in result.columns]
            merge_cols.append("date")
            result = result.merge(df[merge_cols], on="date", how="inner")

    if unlinked:
        for item in unlinked:
            category = item["category"]
            entity = item["entity"]
            udf = read_parquet(
                category, entity, start_date=start_date, end_date=end_date
            )
            if udf.empty:
                continue
            udf = udf.rename(
                columns={c: f"{entity}_{c}" for c in udf.columns if c != "date"}
            )
            if result is None:
                result = udf
            else:
                result = result.merge(udf, on="date", how="inner")

    return result if result is not None else pd.DataFrame()
