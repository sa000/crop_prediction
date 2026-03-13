"""Scrape daily temperature and precipitation data from Open-Meteo for
configured Corn Belt locations.

Downloads data incrementally, writes immutable CSV files to the landing
zone, and loads validated rows into the SQLite warehouse in normalized
long format (one row per date + state).
"""

import logging
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import requests
import yaml

from etl import db
from etl import validate

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "etl" / "scrapers" / "config.yaml"
PIPELINE_PATH = PROJECT_ROOT / "etl" / "pipeline.yaml"


def load_config() -> dict:
    """Read config.yaml and pipeline.yaml, return open_meteo scraper settings.

    Returns:
        Dict with API settings, locations, landing_dir, historical_start_date,
        and validation config.
    """
    with open(CONFIG_PATH) as f:
        cfg = yaml.safe_load(f)
    with open(PIPELINE_PATH) as f:
        pipeline_cfg = yaml.safe_load(f)
    return {
        "historical_start_date": cfg["scraper_defaults"]["historical_start_date"],
        "base_url": cfg["open_meteo"]["base_url"],
        "timezone": cfg["open_meteo"]["timezone"],
        "request_delay": cfg["open_meteo"]["request_delay_seconds"],
        "request_timeout": cfg["open_meteo"]["request_timeout_seconds"],
        "daily_variables": cfg["open_meteo"]["daily_variables"],
        "locations": cfg["open_meteo"]["locations"],
        "landing_dir": PROJECT_ROOT / cfg["open_meteo"]["landing_dir"],
        "validation": pipeline_cfg["validation"],
    }


def get_fetch_start(conn, historical_start: str, locations: list[dict]) -> date | None:
    """Determine the start date for the next download.

    Uses the minimum of the max dates across all states so that no
    state falls behind.

    Args:
        conn: SQLite connection.
        historical_start: Fallback start date if no data exists.
        locations: List of location dicts with 'state' key.

    Returns:
        The date to start fetching from, or None if already up to date.
    """
    max_dates = []
    for loc in locations:
        max_date_str = db.query_max_date(conn, "weather_daily", "state", loc["state"])
        if max_date_str is None:
            return datetime.strptime(historical_start, "%Y-%m-%d").date()
        max_dates.append(datetime.strptime(max_date_str, "%Y-%m-%d").date())

    earliest_max = min(max_dates)
    next_date = earliest_max + timedelta(days=1)
    yesterday = date.today() - timedelta(days=1)
    if next_date > yesterday:
        return None
    return next_date


def fetch_location(loc: dict, cfg: dict, start: date, end: date) -> pd.DataFrame:
    """Fetch daily weather data for a single location from Open-Meteo.

    Converts temperatures from Celsius to Fahrenheit and precipitation
    from millimeters to inches.

    Args:
        loc: Dict with 'state', 'lat', 'lon' keys.
        cfg: Scraper config dict with API settings.
        start: Start date (inclusive).
        end: End date (inclusive).

    Returns:
        DataFrame with columns: date, state, temp_max_f, temp_min_f, precip_in.
    """
    params = {
        "latitude": loc["lat"],
        "longitude": loc["lon"],
        "start_date": str(start),
        "end_date": str(end),
        "daily": cfg["daily_variables"],
        "timezone": cfg["timezone"],
    }

    logger.info("Fetching %s (%.2f, %.2f) from %s to %s", loc["state"], loc["lat"], loc["lon"], start, end)
    response = requests.get(cfg["base_url"], params=params, timeout=cfg["request_timeout"])
    response.raise_for_status()
    daily = response.json()["daily"]

    df = pd.DataFrame({
        "date": pd.to_datetime(daily["time"]).strftime("%Y-%m-%d"),
        "state": loc["state"],
        "temp_max_f": [t * 9 / 5 + 32 if t is not None else None for t in daily["temperature_2m_max"]],
        "temp_min_f": [t * 9 / 5 + 32 if t is not None else None for t in daily["temperature_2m_min"]],
        "precip_in": [p / 25.4 if p is not None else None for p in daily["precipitation_sum"]],
    })
    return df


def fetch_all_locations(cfg: dict, start: date, end: date) -> pd.DataFrame:
    """Fetch weather data for all configured locations with rate limiting.

    Args:
        cfg: Scraper config dict.
        start: Start date (inclusive).
        end: End date (inclusive).

    Returns:
        Concatenated DataFrame in long format (one row per date + state).
    """
    all_dfs = []
    locations = cfg["locations"]
    for i, loc in enumerate(locations):
        all_dfs.append(fetch_location(loc, cfg, start, end))
        if i < len(locations) - 1:
            logger.debug("Sleeping %ds between requests", cfg["request_delay"])
            time.sleep(cfg["request_delay"])

    return pd.concat(all_dfs, ignore_index=True)


def save_landing_files(df: pd.DataFrame, landing_dir: Path) -> list[Path]:
    """Write immutable CSV files to the landing zone, split by year.

    Historical backfills produce one file per year. Current-year data
    produces one file per day.

    Args:
        df: DataFrame with a 'date' column (string YYYY-MM-DD).
        landing_dir: Landing zone directory for this data source.

    Returns:
        List of paths written.
    """
    landing_dir.mkdir(parents=True, exist_ok=True)

    written = []
    current_year = date.today().year
    df["_year"] = pd.to_datetime(df["date"]).dt.year

    for year, group in df.groupby("_year"):
        group = group.drop(columns=["_year"])
        if year == current_year:
            for day_str, day_group in group.groupby("date"):
                path = landing_dir / f"{day_str}.csv"
                day_group.to_csv(path, index=False)
                written.append(path)
        else:
            path = landing_dir / f"{year}.csv"
            group.to_csv(path, index=False)
            written.append(path)

    logger.info("Wrote %d landing file(s) to %s", len(written), landing_dir)
    return written


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )

    cfg = load_config()
    conn = db.get_connection()
    db.init_tables(conn)

    start = get_fetch_start(conn, cfg["historical_start_date"], cfg["locations"])
    if start is None:
        logger.info("Weather data is up to date")
        conn.close()
        return

    yesterday = date.today() - timedelta(days=1)
    df = fetch_all_locations(cfg, start, yesterday)
    save_landing_files(df, cfg["landing_dir"])

    val_cfg = cfg["validation"]
    clean_df, issues = validate.validate_weather(df, conn, val_cfg)

    if issues:
        db.log_validation(conn, issues)

    if not clean_df.empty:
        db.insert_weather(conn, clean_df)

    logger.info(
        "Weather: %d rows fetched, %d passed validation (%s to %s)",
        len(df), len(clean_df), df["date"].min(), df["date"].max(),
    )
    conn.close()


if __name__ == "__main__":
    main()
