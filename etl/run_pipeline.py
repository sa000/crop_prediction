"""Pipeline runner with support for rebuilding the warehouse from landing files.

Usage:
    python -m etl.run_pipeline --rebuild
    python -m etl.run_pipeline --rebuild --rebuild-features
"""

import argparse
import logging
from pathlib import Path

import pandas as pd
import yaml

from etl import db, validate

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LANDING_DIR = PROJECT_ROOT / "warehouse" / "landing"
PIPELINE_PATH = PROJECT_ROOT / "etl" / "pipeline.yaml"


def load_validation_config() -> dict:
    """Load the validation section from pipeline.yaml.

    Returns:
        Validation config dict.
    """
    with open(PIPELINE_PATH) as f:
        return yaml.safe_load(f)["validation"]


def _classify_landing_file(path: Path) -> str | None:
    """Determine the data source type from a landing file path.

    Args:
        path: Path to a landing CSV file.

    Returns:
        'futures' or 'weather', or None if unrecognized.
    """
    parts = path.parts
    if "yahoo_finance" in parts:
        return "futures"
    if "open_meteo" in parts:
        return "weather"
    return None


def _add_ticker_column(df: pd.DataFrame, path: Path) -> pd.DataFrame:
    """Add a ticker column to a futures DataFrame based on the landing file path.

    Yahoo Finance landing files are stored as:
    landing/yahoo_finance/<ticker_name>/<file>.csv

    The ticker_name directory maps to a symbol via config, but for backfill
    we need to infer from the data or path. The ticker column may already
    exist if the data was saved with it.

    Args:
        df: Futures DataFrame.
        path: Path to the source landing file.

    Returns:
        DataFrame with a 'ticker' column.
    """
    if "ticker" in df.columns:
        return df

    # The parent directory name is the ticker name (e.g. 'corn').
    # Load config to map name -> symbol.
    config_path = PROJECT_ROOT / "etl" / "scrapers" / "config.yaml"
    with open(config_path) as f:
        cfg = yaml.safe_load(f)

    name_to_symbol = {t["name"]: t["symbol"] for t in cfg["yahoo_finance"]["tickers"]}
    ticker_name = path.parent.name
    symbol = name_to_symbol.get(ticker_name)

    if symbol is None:
        logger.warning("Unknown ticker directory '%s', skipping", ticker_name)
        return df

    df = df.copy()
    df["ticker"] = symbol
    return df


def _normalize_futures_df(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize column names and date format for a futures DataFrame.

    Args:
        df: Raw futures DataFrame from a landing CSV file.

    Returns:
        DataFrame with lowercase columns and string dates.
    """
    df = df.reset_index() if df.index.name or isinstance(df.index, pd.DatetimeIndex) else df.copy()
    df.columns = [c.lower() for c in df.columns]
    df = df.rename(columns={"price": "date"})
    if "date" not in df.columns:
        date_col = [c for c in df.columns if "date" in c.lower()]
        if date_col:
            df = df.rename(columns={date_col[0]: "date"})
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    return df


def rebuild():
    """Delete warehouse.db and rebuild it by revalidating all landing files."""
    logger.info("Rebuilding warehouse from landing files")

    db.DB_PATH.unlink(missing_ok=True)
    conn = db.get_connection()
    db.init_tables(conn)

    val_cfg = load_validation_config()

    landing_files = sorted(LANDING_DIR.glob("**/*.csv"))
    if not landing_files:
        logger.warning("No landing files found in %s", LANDING_DIR)
        conn.close()
        return

    logger.info("Processing %d landing files", len(landing_files))

    for path in landing_files:
        source = _classify_landing_file(path)
        if source is None:
            logger.warning("Skipping unrecognized file: %s", path)
            continue

        df = pd.read_csv(path)

        if source == "futures":
            df = _normalize_futures_df(df)
            df = _add_ticker_column(df, path)
            if "ticker" not in df.columns:
                continue
            clean_df, issues = validate.validate_futures(df, conn, val_cfg)
            if not clean_df.empty:
                db.insert_futures(conn, clean_df)
        else:
            clean_df, issues = validate.validate_weather(df, conn, val_cfg)
            if not clean_df.empty:
                db.insert_weather(conn, clean_df)

        if issues:
            db.log_validation(conn, issues)

    # Back-adjust futures prices to remove contract roll gaps
    from etl.adjust import adjust_futures
    roll_results = adjust_futures(conn)
    for ticker, n_rolls in roll_results.items():
        logger.info("Back-adjust %s: %d rolls corrected", ticker, n_rolls)

    # Log summary
    for table in ["futures_daily", "weather_daily"]:
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        logger.info("%s: %d rows after rebuild", table, count)

    issue_count = conn.execute("SELECT COUNT(*) FROM validation_log").fetchone()[0]
    logger.info("validation_log: %d issues recorded", issue_count)

    conn.close()
    logger.info("Rebuild complete")


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )

    parser = argparse.ArgumentParser(description="ETL pipeline runner")
    parser.add_argument(
        "--rebuild", action="store_true",
        help="Delete warehouse.db and rebuild from landing files with validation",
    )
    parser.add_argument(
        "--rebuild-features", action="store_true",
        help="Rebuild the feature store after warehouse rebuild",
    )
    args = parser.parse_args()

    if args.rebuild:
        rebuild()
        if args.rebuild_features:
            from features.pipeline import run as run_features
            logger.info("Rebuilding feature store")
            run_features(rebuild=True)
    else:
        logger.info("No action specified. Use --rebuild to rebuild the warehouse.")


if __name__ == "__main__":
    main()
