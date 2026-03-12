"""Scrape daily futures OHLCV data from Yahoo Finance for all configured tickers.

Downloads data incrementally (only fetches days after the last known date in
the database), writes immutable Parquet files to the landing zone, and loads
rows into the SQLite warehouse.
"""

import logging
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import yaml
import yfinance as yf

from etl import db

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "etl" / "scrapers" / "config.yaml"


def load_config() -> dict:
    """Read config.yaml and return yahoo_finance scraper settings.

    Returns:
        Dict with keys: historical_start_date (str), tickers (list of dicts),
        landing_dir (Path).
    """
    with open(CONFIG_PATH) as f:
        cfg = yaml.safe_load(f)
    return {
        "historical_start_date": cfg["scraper_defaults"]["historical_start_date"],
        "tickers": cfg["yahoo_finance"]["tickers"],
        "landing_dir": PROJECT_ROOT / cfg["yahoo_finance"]["landing_dir"],
    }


def get_fetch_start(conn, ticker_symbol: str, historical_start: str) -> date | None:
    """Determine the start date for the next download.

    Args:
        conn: SQLite connection.
        ticker_symbol: Yahoo Finance ticker (e.g. 'ZC=F').
        historical_start: Fallback start date if no data exists.

    Returns:
        The date to start fetching from, or None if already up to date.
    """
    max_date_str = db.query_max_date(conn, "futures_daily", "ticker", ticker_symbol)
    if max_date_str is None:
        return datetime.strptime(historical_start, "%Y-%m-%d").date()

    max_date = datetime.strptime(max_date_str, "%Y-%m-%d").date()
    next_date = max_date + timedelta(days=1)
    yesterday = date.today() - timedelta(days=1)
    if next_date > yesterday:
        return None
    return next_date


def download_ticker(symbol: str, start: date, end: date) -> pd.DataFrame:
    """Download OHLCV data from Yahoo Finance.

    Args:
        symbol: Yahoo Finance ticker symbol.
        start: Start date (inclusive).
        end: End date (exclusive, per yfinance convention).

    Returns:
        DataFrame indexed by date with Open, High, Low, Close, Volume columns.

    Raises:
        ValueError: If no data is returned.
    """
    logger.info("Downloading %s from %s to %s", symbol, start, end)
    df = yf.download(symbol, start=str(start), end=str(end), auto_adjust=True)

    if df.empty:
        raise ValueError(f"No data returned for {symbol}.")

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [col[0] for col in df.columns]

    return df


def save_landing_files(df: pd.DataFrame, landing_dir: Path, ticker_name: str) -> list[Path]:
    """Write immutable Parquet files to the landing zone, split by year.

    Historical backfills produce one file per year. Incremental runs that
    span a single day produce a single dated file.

    Args:
        df: DataFrame indexed by DatetimeIndex.
        landing_dir: Base landing directory.
        ticker_name: Subdirectory name (e.g. 'corn').

    Returns:
        List of paths written.
    """
    ticker_dir = landing_dir / ticker_name
    ticker_dir.mkdir(parents=True, exist_ok=True)

    written = []
    current_year = date.today().year

    for year, group in df.groupby(df.index.year):
        if year == current_year:
            for day_date, day_group in group.groupby(group.index.date):
                path = ticker_dir / f"{day_date}.parquet"
                day_group.to_parquet(path)
                written.append(path)
        else:
            path = ticker_dir / f"{year}.parquet"
            group.to_parquet(path)
            written.append(path)

    logger.info("Wrote %d landing file(s) for %s", len(written), ticker_name)
    return written


def load_to_db(conn, df: pd.DataFrame, ticker_symbol: str) -> None:
    """Add ticker column and insert rows into the futures_daily table.

    Args:
        conn: SQLite connection.
        df: DataFrame indexed by DatetimeIndex with OHLCV columns.
        ticker_symbol: Ticker value to populate the ticker column.
    """
    flat = df.reset_index()
    flat.columns = [c.lower() for c in flat.columns]
    flat = flat.rename(columns={"price": "date"})
    if "date" not in flat.columns:
        date_col = [c for c in flat.columns if "date" in c.lower()]
        if date_col:
            flat = flat.rename(columns={date_col[0]: "date"})
    flat["date"] = pd.to_datetime(flat["date"]).dt.strftime("%Y-%m-%d")
    flat["ticker"] = ticker_symbol
    db.insert_futures(conn, flat)


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )

    cfg = load_config()
    conn = db.get_connection()
    db.init_tables(conn)

    today = date.today()

    for ticker in cfg["tickers"]:
        symbol = ticker["symbol"]
        name = ticker["name"]

        start = get_fetch_start(conn, symbol, cfg["historical_start_date"])
        if start is None:
            logger.info("%s (%s) is up to date", name, symbol)
            continue

        df = download_ticker(symbol, start, today)
        save_landing_files(df, cfg["landing_dir"], name)
        load_to_db(conn, df, symbol)

        logger.info(
            "%s (%s): loaded %d rows (%s to %s)",
            name, symbol, len(df), df.index[0].date(), df.index[-1].date(),
        )

    conn.close()


if __name__ == "__main__":
    main()
