"""Reusable SQL queries for loading data from the warehouse.

Import query strings directly or use ``run(query_name)`` for quick
interactive use in notebooks.
"""

import pandas as pd

from etl import db

# -- Futures ------------------------------------------------------------------

FUTURES_ALL = """
SELECT date, ticker, open, high, low, close, volume
FROM futures_daily
ORDER BY ticker, date
"""

FUTURES_BY_TICKER = """
SELECT date, open, high, low, close, volume
FROM futures_daily
WHERE ticker = :ticker
ORDER BY date
"""

FUTURES_LATEST = """
SELECT ticker, MAX(date) AS latest_date, COUNT(*) AS row_count
FROM futures_daily
GROUP BY ticker
"""

# -- Weather ------------------------------------------------------------------

WEATHER_ALL = """
SELECT date, state, temp_max_f, temp_min_f, precip_in
FROM weather_daily
ORDER BY state, date
"""

WEATHER_BY_STATE = """
SELECT date, temp_max_f, temp_min_f, precip_in
FROM weather_daily
WHERE state = :state
ORDER BY date
"""

WEATHER_LATEST = """
SELECT state, MAX(date) AS latest_date, COUNT(*) AS row_count
FROM weather_daily
GROUP BY state
"""

# -- Joined -------------------------------------------------------------------

FUTURES_WEATHER_JOINED = """
SELECT f.date, f.close,
       w.state, w.temp_max_f, w.temp_min_f, w.precip_in
FROM futures_daily f
JOIN weather_daily w ON f.date = w.date
WHERE f.ticker = :ticker
ORDER BY f.date, w.state
"""

# -- Helpers ------------------------------------------------------------------

# All named queries, for discovery.
ALL_QUERIES = {
    "futures_all": FUTURES_ALL,
    "futures_by_ticker": FUTURES_BY_TICKER,
    "futures_latest": FUTURES_LATEST,
    "weather_all": WEATHER_ALL,
    "weather_by_state": WEATHER_BY_STATE,
    "weather_latest": WEATHER_LATEST,
    "futures_weather_joined": FUTURES_WEATHER_JOINED,
}


def run(query_name: str, params: dict | None = None) -> pd.DataFrame:
    """Execute a named query and return the result as a DataFrame.

    Args:
        query_name: Key in ALL_QUERIES.
        params: Optional dict of bind parameters (e.g. {"ticker": "ZC=F"}).

    Returns:
        Query results as a DataFrame.
    """
    sql = ALL_QUERIES[query_name]
    conn = db.get_connection()
    df = pd.read_sql(sql, conn, params=params or {}, parse_dates=["date"])
    conn.close()
    return df
