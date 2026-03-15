"""Feature pipeline orchestrator.

Reads raw data from warehouse.db, computes features via compute modules,
writes Parquet files, and generates the feature registry.

Usage:
    python -m features.pipeline                  # incremental update
    python -m features.pipeline --rebuild        # full recompute
    python -m features.pipeline --category momentum  # single category
"""

import argparse
import importlib
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import yaml

from etl import db
from features import store

logger = logging.getLogger(__name__)

FEATURES_DIR = Path(__file__).resolve().parent
CONFIG_PATH = FEATURES_DIR / "config.yaml"
REGISTRY_PATH = FEATURES_DIR / "registry.yaml"

CALENDAR_BUFFER_MULTIPLIER = 2


def load_feature_config() -> dict:
    """Load feature definitions from config.yaml.

    Returns:
        Dict keyed by category name.
    """
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def load_source_data(
    category_cfg: dict, entity_key: str, start_date: str | None = None
) -> pd.DataFrame:
    """Query warehouse.db for source data.

    Args:
        category_cfg: Category config section from config.yaml.
        entity_key: Entity filter value (e.g. 'ZC=F' or 'Iowa').
        start_date: Optional earliest date to query from.

    Returns:
        DataFrame with date column and source columns, sorted by date.
    """
    table = category_cfg["source_table"]
    entity_col = category_cfg["entity_column"]

    conn = db.get_connection()
    where = f"WHERE {entity_col} = ?"
    params: list = [entity_key]

    if start_date:
        where += " AND date >= ?"
        params.append(start_date)

    df = pd.read_sql(
        f"SELECT * FROM {table} {where} ORDER BY date",  # noqa: S608
        conn,
        params=params,
    )
    conn.close()
    return df


def _get_compute_module(category: str):
    """Dynamically import the compute module for a category.

    Args:
        category: Category name (momentum, mean_reversion, weather).

    Returns:
        The compute module with a FUNCTIONS dict.
    """
    return importlib.import_module(f"features.compute.{category}")


def compute_entity_features(
    source_df: pd.DataFrame, category_cfg: dict, compute_module
) -> pd.DataFrame:
    """Compute all features for a single entity, lagged by 1 day.

    All feature values are shifted forward by 1 row so that on date T,
    the feature reflects data through T-1. This prevents lookahead bias:
    a strategy making a decision on day T only sees information available
    before the market opens on T.

    Args:
        source_df: Raw data from warehouse.db, sorted by date.
        category_cfg: Category config section.
        compute_module: Module with FUNCTIONS dict.

    Returns:
        DataFrame with date and all computed features (point-in-time safe).
    """
    result = pd.DataFrame({"date": source_df["date"]})

    for col in category_cfg.get("include_columns", []):
        result[col] = source_df[col].values

    functions = compute_module.FUNCTIONS

    for feat_cfg in category_cfg["features"]:
        func = functions[feat_cfg["function"]]
        params = dict(feat_cfg["params"])

        if "column" in params:
            col_name = params.pop("column")
            series = source_df[col_name]
            raw = func(series, **params)
        elif "col_a" in params:
            raw = func(source_df, **params)
        else:
            close = source_df["close"]
            raw = func(close, **params)

        # Shift by 1 so date T's feature uses data through T-1
        result[feat_cfg["name"]] = raw.shift(1).values

    return result


def compute_rebuild(category: str, category_cfg: dict) -> None:
    """Full rebuild for a category: load all data, compute, write.

    Args:
        category: Category name.
        category_cfg: Category config section.
    """
    compute_module = _get_compute_module(category)

    for entity in category_cfg["entities"]:
        entity_key = entity["key"]
        entity_name = entity["name"]

        source_df = load_source_data(category_cfg, entity_key)
        if source_df.empty:
            logger.warning("No data for %s/%s, skipping", category, entity_name)
            continue

        features_df = compute_entity_features(source_df, category_cfg, compute_module)
        store.write_features(features_df, category, entity_name)
        logger.info(
            "Rebuilt %s/%s: %d rows", category, entity_name, len(features_df)
        )


def compute_incremental(category: str, category_cfg: dict) -> None:
    """Incremental update for a category: append only new rows.

    Args:
        category: Category name.
        category_cfg: Category config section.
    """
    compute_module = _get_compute_module(category)
    max_lookback = category_cfg.get("max_lookback", 50)

    for entity in category_cfg["entities"]:
        entity_key = entity["key"]
        entity_name = entity["name"]

        existing_max = store.get_max_date(category, entity_name)

        if existing_max is None:
            logger.info(
                "No existing data for %s/%s, doing full build",
                category, entity_name,
            )
            source_df = load_source_data(category_cfg, entity_key)
            if source_df.empty:
                logger.warning("No data for %s/%s, skipping", category, entity_name)
                continue
            features_df = compute_entity_features(
                source_df, category_cfg, compute_module
            )
            store.write_features(features_df, category, entity_name)
            logger.info(
                "Built %s/%s: %d rows", category, entity_name, len(features_df)
            )
            continue

        lookback_days = max_lookback * CALENDAR_BUFFER_MULTIPLIER
        start_date = (
            datetime.strptime(existing_max, "%Y-%m-%d") - timedelta(days=lookback_days)
        ).strftime("%Y-%m-%d")

        source_df = load_source_data(category_cfg, entity_key, start_date)
        if source_df.empty:
            logger.info("No new data for %s/%s", category, entity_name)
            continue

        features_df = compute_entity_features(source_df, category_cfg, compute_module)
        new_rows = features_df[features_df["date"] > existing_max]

        if new_rows.empty:
            logger.info("No new rows for %s/%s", category, entity_name)
            continue

        existing_df = store.read_features(category, entity_name)
        store.append_features(existing_df, new_rows, category, entity_name)
        logger.info(
            "Appended %d rows to %s/%s", len(new_rows), category, entity_name
        )


def compute_aggregations(category: str, category_cfg: dict, rebuild: bool) -> None:
    """Compute aggregated features by averaging across source entities.

    Args:
        category: Category name.
        category_cfg: Category config section.
        rebuild: If True, do full write; otherwise append new rows only.
    """
    aggregations = category_cfg.get("aggregations", [])
    if not aggregations:
        return

    for agg in aggregations:
        agg_name = agg["name"]
        method = agg["method"]
        source_entities = agg["source_entities"]

        dfs = []
        for entity_name in source_entities:
            df = store.read_features(category, entity_name)
            if df is None:
                logger.warning(
                    "Missing %s/%s for aggregation %s, skipping",
                    category, entity_name, agg_name,
                )
                return
            dfs.append(df)

        # Concat all frames, group by date, and average feature columns
        feature_cols = [c for c in dfs[0].columns if c != "date"]
        combined = pd.concat(dfs, ignore_index=True)
        agg_df = combined.groupby("date")[feature_cols].mean().reset_index()
        agg_df = agg_df.sort_values("date").reset_index(drop=True)

        if rebuild:
            store.write_features(agg_df, category, agg_name)
            logger.info(
                "Built aggregation %s/%s: %d rows", category, agg_name, len(agg_df)
            )
        else:
            existing_max = store.get_max_date(category, agg_name)
            if existing_max is None:
                store.write_features(agg_df, category, agg_name)
                logger.info(
                    "Built aggregation %s/%s: %d rows",
                    category, agg_name, len(agg_df),
                )
            else:
                new_rows = agg_df[agg_df["date"] > existing_max]
                if new_rows.empty:
                    logger.info("No new rows for aggregation %s/%s", category, agg_name)
                else:
                    existing_df = store.read_features(category, agg_name)
                    store.append_features(existing_df, new_rows, category, agg_name)
                    logger.info(
                        "Appended %d rows to aggregation %s/%s",
                        len(new_rows), category, agg_name,
                    )


def _build_ticker_descriptions() -> list[dict]:
    """Build ticker metadata from scraper config.

    Returns:
        List of ticker dicts with symbol, name, source, asset_class, description.
    """
    config_path = FEATURES_DIR.parent / "etl" / "scrapers" / "config.yaml"
    with open(config_path) as f:
        scraper_cfg = yaml.safe_load(f)

    descriptions = {
        "ZC=F": "CBOT Corn Futures continuous contract",
        "ZS=F": "CBOT Soybean Futures continuous contract",
        "ZW=F": "CBOT Wheat Futures continuous contract",
    }

    tickers = []
    for t in scraper_cfg["yahoo_finance"]["tickers"]:
        tickers.append({
            "symbol": t["symbol"],
            "name": t["name"],
            "source": "yahoo_finance",
            "asset_class": "agricultural_futures",
            "description": descriptions.get(t["symbol"], t["name"]),
        })
    return tickers


def update_registry(config: dict) -> None:
    """Scan Parquet files and write registry.yaml with full metadata.

    Args:
        config: The full feature config dict.
    """
    tickers = _build_ticker_descriptions()
    ticker_names = [t["name"] for t in tickers]

    features_list = []
    ticker_feature_map: dict[str, dict[str, list[str]]] = {
        name: {} for name in ticker_names
    }
    unlinked_features: dict[str, dict[str, list[str]]] = {}
    files_meta: dict[str, dict] = {}

    for category, cat_cfg in config.items():
        is_ticker_based = cat_cfg["entity_column"] == "ticker"
        files_meta[category] = {}

        for entity in cat_cfg["entities"]:
            entity_name = entity["name"]
            entity_key = entity["key"]

            df = store.read_features(category, entity_name)
            if df is None:
                continue

            path = store.get_parquet_path(category, entity_name)
            date_min = str(df["date"].min())
            date_max = str(df["date"].max())
            row_count = len(df)

            files_meta[category][entity_name] = {
                "path": str(path.relative_to(FEATURES_DIR.parent)),
                "date_range": [date_min, date_max],
                "row_count": row_count,
                "entity_key": entity_key,
            }

            feature_names = [f["name"] for f in cat_cfg["features"]]

            if is_ticker_based:
                ticker_feature_map[entity_name][category] = feature_names
            else:
                if category not in unlinked_features:
                    unlinked_features[category] = {}
                unlinked_features[category][entity_name] = feature_names

            for feat_cfg in cat_cfg["features"]:
                feat_col = feat_cfg["name"]
                non_null = df[feat_col].dropna()
                available_from = str(non_null.iloc[0]) if not non_null.empty else None
                # Get the date corresponding to the first non-null feature value
                if not non_null.empty:
                    first_valid_idx = df[feat_col].first_valid_index()
                    available_from = str(df.loc[first_valid_idx, "date"])

                entry = {
                    "name": feat_cfg["name"],
                    "category": category,
                    "source_table": cat_cfg["source_table"],
                    "description": feat_cfg.get("description", ""),
                    "freshness": date_max,
                    "available_from": available_from,
                    "frequency": "daily",
                }

                if is_ticker_based:
                    existing = next(
                        (f for f in features_list if f["name"] == feat_cfg["name"]
                         and f["category"] == category),
                        None,
                    )
                    if existing:
                        existing["tickers"].append(entity_name)
                    else:
                        entry["tickers"] = [entity_name]
                        features_list.append(entry)
                else:
                    existing = next(
                        (f for f in features_list if f["name"] == feat_cfg["name"]
                         and f["category"] == category),
                        None,
                    )
                    if existing:
                        existing["states"].append(entity_name)
                    else:
                        entry["tickers"] = []
                        entry["states"] = [entity_name]
                        features_list.append(entry)

        # Include aggregation entities in the registry
        for agg in cat_cfg.get("aggregations", []):
            agg_name = agg["name"]
            df = store.read_features(category, agg_name)
            if df is None:
                continue

            path = store.get_parquet_path(category, agg_name)
            date_min = str(df["date"].min())
            date_max = str(df["date"].max())
            row_count = len(df)

            files_meta[category][agg_name] = {
                "path": str(path.relative_to(FEATURES_DIR.parent)),
                "date_range": [date_min, date_max],
                "row_count": row_count,
                "entity_key": agg_name,
            }

            if not is_ticker_based:
                if category not in unlinked_features:
                    unlinked_features[category] = {}
                feature_names = [f["name"] for f in cat_cfg["features"]]
                unlinked_features[category][agg_name] = feature_names

                # Add aggregation entity to each feature's states list
                for feat in features_list:
                    if feat["category"] == category and "states" in feat:
                        if agg_name not in feat["states"]:
                            feat["states"].append(agg_name)

    # Build metadata.parquet (one row per feature per entity)
    metadata_rows = []
    for category, cat_cfg in config.items():
        entity_col = cat_cfg["entity_column"]
        entity_type = "ticker" if entity_col == "ticker" else "region"

        all_entities = [e["name"] for e in cat_cfg["entities"]]
        for agg in cat_cfg.get("aggregations", []):
            all_entities.append(agg["name"])

        for entity_name in all_entities:
            df = store.read_features(category, entity_name)
            if df is None:
                continue

            parquet_path = str(
                store.get_parquet_path(category, entity_name)
                .relative_to(FEATURES_DIR.parent)
            )
            date_max = str(df["date"].max())

            for feat_cfg in cat_cfg["features"]:
                feat_name = feat_cfg["name"]
                if feat_name not in df.columns:
                    continue

                col = df[feat_name]
                non_null = col.dropna()

                available_from = None
                if not non_null.empty:
                    first_idx = col.first_valid_index()
                    available_from = str(df.loc[first_idx, "date"])

                metadata_rows.append({
                    "name": feat_name,
                    "category": category,
                    "entity": entity_name,
                    "entity_type": entity_type,
                    "source_table": cat_cfg["source_table"],
                    "description": feat_cfg.get("description", ""),
                    "params": json.dumps(dict(feat_cfg["params"])),
                    "available_from": available_from,
                    "freshness": date_max,
                    "row_count": len(df),
                    "stat_min": float(non_null.min()) if not non_null.empty else None,
                    "stat_max": float(non_null.max()) if not non_null.empty else None,
                    "stat_mean": float(non_null.mean()) if not non_null.empty else None,
                    "stat_std": float(non_null.std()) if not non_null.empty else None,
                    "null_pct": round(col.isna().mean() * 100, 2),
                    "parquet_path": parquet_path,
                })

    if metadata_rows:
        metadata_df = pd.DataFrame(metadata_rows)
        store.write_metadata(metadata_df)
        logger.info("Metadata written: %d rows", len(metadata_df))

        # Sync feature catalog table
        conn = db.get_connection()
        db.init_tables(conn)
        db.populate_feature_catalog(conn, metadata_df)
        conn.close()

    # Clean up empty ticker maps
    ticker_feature_map = {k: v for k, v in ticker_feature_map.items() if v}

    registry = {
        "generated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "tickers": tickers,
        "features": features_list,
        "ticker_feature_map": ticker_feature_map,
        "unlinked_features": unlinked_features,
        "files": files_meta,
    }

    with open(REGISTRY_PATH, "w") as f:
        yaml.dump(registry, f, default_flow_style=False, sort_keys=False)

    logger.info("Registry written to %s", REGISTRY_PATH)


def run(rebuild: bool = False, category_filter: str | None = None) -> None:
    """Run the feature pipeline.

    Args:
        rebuild: If True, delete existing Parquet files and recompute.
        category_filter: If set, only process this category.
    """
    config = load_feature_config()

    if category_filter:
        if category_filter not in config:
            logger.error("Unknown category: %s", category_filter)
            return
        config = {category_filter: config[category_filter]}

    if rebuild:
        for category in config:
            output_dir = FEATURES_DIR / category
            if output_dir.exists():
                for f in output_dir.glob("*.parquet"):
                    f.unlink()
                    logger.info("Deleted %s", f)

    for category, cat_cfg in config.items():
        logger.info("Processing category: %s", category)
        if rebuild:
            compute_rebuild(category, cat_cfg)
        else:
            compute_incremental(category, cat_cfg)

    # Compute aggregations after all per-entity features are done
    full_config = load_feature_config()
    for category, cat_cfg in full_config.items():
        compute_aggregations(category, cat_cfg, rebuild)

    update_registry(full_config)


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )

    parser = argparse.ArgumentParser(description="Feature store pipeline")
    parser.add_argument(
        "--rebuild", action="store_true",
        help="Delete existing Parquet files and recompute from warehouse.db",
    )
    parser.add_argument(
        "--category", type=str, default=None,
        help="Only process a single category (momentum, mean_reversion, weather)",
    )
    args = parser.parse_args()

    run(rebuild=args.rebuild, category_filter=args.category)


if __name__ == "__main__":
    main()
