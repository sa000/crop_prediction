"""Scrape daily corn futures OHLCV data from Yahoo Finance."""

import logging
from pathlib import Path

import pandas as pd
import yaml
import yfinance as yf

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "etl" / "config.yaml"


def load_config() -> dict:
    """Read the shared ETL config and return settings for this scraper."""
    with open(CONFIG_PATH) as f:
        cfg = yaml.safe_load(f)
    return {
        "ticker": cfg["corn_futures"]["ticker"],
        "start_date": cfg["shared"]["start_date"],
        "end_date": cfg["shared"]["end_date"],
        "output_file": PROJECT_ROOT / cfg["corn_futures"]["output_file"],
    }


def download_futures(ticker: str, start: str, end: str) -> pd.DataFrame:
    """Download raw OHLCV futures data from Yahoo Finance.

    Args:
        ticker: Yahoo Finance ticker symbol.
        start: Start date string (YYYY-MM-DD).
        end: End date string (YYYY-MM-DD).

    Returns:
        DataFrame indexed by date with Open, High, Low, Close, Volume columns.
    """
    logger.info("Downloading %s from %s to %s", ticker, start, end)
    df = yf.download(ticker, start=start, end=end, auto_adjust=True)

    if df.empty:
        raise ValueError(f"No data returned for {ticker}.")

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [col[0] for col in df.columns]

    return df


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )

    cfg = load_config()
    df = download_futures(cfg["ticker"], cfg["start_date"], cfg["end_date"])

    output_path = cfg["output_file"]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path)

    logger.info(
        "Saved %d rows to %s | Date range: %s to %s",
        len(df), output_path, df.index[0].date(), df.index[-1].date(),
    )


if __name__ == "__main__":
    main()
