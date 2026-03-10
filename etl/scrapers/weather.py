"""Scrape daily temperature and precipitation data from Open-Meteo
for Corn Belt states."""

import logging
import time
from pathlib import Path

import pandas as pd
import requests
import yaml

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "etl" / "config.yaml"


def load_config() -> dict:
    """Read the shared ETL config and return the merged settings for this scraper."""
    with open(CONFIG_PATH) as f:
        cfg = yaml.safe_load(f)
    return {
        "start_date": cfg["shared"]["start_date"],
        "end_date": cfg["shared"]["end_date"],
        "base_url": cfg["weather"]["base_url"],
        "timezone": cfg["weather"]["timezone"],
        "request_delay": cfg["weather"]["request_delay_seconds"],
        "request_timeout": cfg["weather"]["request_timeout_seconds"],
        "locations": cfg["weather"]["locations"],
        "output_file": PROJECT_ROOT / cfg["weather"]["output_file"],
    }


def fetch_location(loc: dict, cfg: dict) -> pd.DataFrame:
    """Fetch daily temp and precipitation for a single location.

    Args:
        loc: Dict with 'state', 'lat', 'lon' keys.
        cfg: Scraper config dict with API settings.

    Returns:
        DataFrame indexed by date with temp max/min (F) and precip (in) columns.
    """
    params = {
        "latitude": loc["lat"],
        "longitude": loc["lon"],
        "start_date": cfg["start_date"],
        "end_date": cfg["end_date"],
        "daily": ["temperature_2m_max", "temperature_2m_min", "precipitation_sum"],
        "timezone": cfg["timezone"],
    }

    logger.info("Fetching %s (%.2f, %.2f)", loc["state"], loc["lat"], loc["lon"])
    response = requests.get(cfg["base_url"], params=params, timeout=cfg["request_timeout"])
    response.raise_for_status()
    daily = response.json()["daily"]

    state = loc["state"]
    df = pd.DataFrame({
        "date": pd.to_datetime(daily["time"]),
        f"{state}_temp_max_f": [t * 9 / 5 + 32 if t is not None else None for t in daily["temperature_2m_max"]],
        f"{state}_temp_min_f": [t * 9 / 5 + 32 if t is not None else None for t in daily["temperature_2m_min"]],
        f"{state}_precip_in":  [p / 25.4 if p is not None else None for p in daily["precipitation_sum"]],
    })
    df.set_index("date", inplace=True)
    return df


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )

    cfg = load_config()
    logger.info("Downloading weather: %s to %s", cfg["start_date"], cfg["end_date"])

    all_dfs = []
    locations = cfg["locations"]
    for i, loc in enumerate(locations):
        all_dfs.append(fetch_location(loc, cfg))
        if i < len(locations) - 1:
            logger.debug("Sleeping %ds between requests", cfg["request_delay"])
            time.sleep(cfg["request_delay"])

    combined = pd.concat(all_dfs, axis=1)
    combined.index.name = "date"

    output_path = cfg["output_file"]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(output_path)
    logger.info("Saved %d rows x %d columns to %s", len(combined), len(combined.columns), output_path)

    return combined


if __name__ == "__main__":
    main()
