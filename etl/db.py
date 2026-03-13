"""SQLite database manager for the ETL warehouse.

Centralizes all database interactions: connection management, table
creation, bulk inserts, and helper queries. Scrapers and downstream
consumers import from here instead of managing connections directly.
"""

import logging
import sqlite3
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "warehouse" / "warehouse.db"

CREATE_FUTURES_DAILY = """
CREATE TABLE IF NOT EXISTS futures_daily (
    date     TEXT NOT NULL,
    ticker   TEXT NOT NULL,
    open     REAL,
    high     REAL,
    low      REAL,
    close    REAL,
    volume   INTEGER,
    PRIMARY KEY (date, ticker)
);
"""

CREATE_WEATHER_DAILY = """
CREATE TABLE IF NOT EXISTS weather_daily (
    date       TEXT NOT NULL,
    state      TEXT NOT NULL,
    temp_max_f REAL,
    temp_min_f REAL,
    precip_in  REAL,
    PRIMARY KEY (date, state)
);
"""

CREATE_VALIDATION_LOG = """
CREATE TABLE IF NOT EXISTS validation_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    checked_at   TEXT NOT NULL,
    source_table TEXT NOT NULL,
    date         TEXT NOT NULL,
    entity_key   TEXT NOT NULL,
    check_name   TEXT NOT NULL,
    severity     TEXT NOT NULL,
    details      TEXT
);
"""


def get_connection() -> sqlite3.Connection:
    """Open a connection to the SQLite warehouse database.

    Returns:
        An open sqlite3.Connection.
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    logger.debug("Connected to %s", DB_PATH)
    return conn


def init_tables(conn: sqlite3.Connection) -> None:
    """Create all warehouse tables if they do not exist.

    Args:
        conn: An open SQLite connection.
    """
    conn.execute(CREATE_FUTURES_DAILY)
    conn.execute(CREATE_WEATHER_DAILY)
    conn.execute(CREATE_VALIDATION_LOG)
    conn.commit()
    logger.debug("Tables initialized")


def insert_futures(conn: sqlite3.Connection, df: pd.DataFrame) -> int:
    """Bulk-insert futures rows, ignoring duplicates on (date, ticker).

    Args:
        conn: An open SQLite connection.
        df: DataFrame with columns: date, ticker, open, high, low, close, volume.

    Returns:
        Number of rows inserted (excluding ignored duplicates).
    """
    rows = list(df[["date", "ticker", "open", "high", "low", "close", "volume"]].itertuples(index=False, name=None))
    cursor = conn.executemany(
        "INSERT OR IGNORE INTO futures_daily (date, ticker, open, high, low, close, volume) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    inserted = cursor.rowcount
    logger.info("Inserted %d rows into futures_daily (%d total submitted)", inserted, len(rows))
    return inserted


def insert_weather(conn: sqlite3.Connection, df: pd.DataFrame) -> int:
    """Bulk-insert weather rows, ignoring duplicates on (date, state).

    Args:
        conn: An open SQLite connection.
        df: DataFrame with columns: date, state, temp_max_f, temp_min_f, precip_in.

    Returns:
        Number of rows inserted (excluding ignored duplicates).
    """
    rows = list(df[["date", "state", "temp_max_f", "temp_min_f", "precip_in"]].itertuples(index=False, name=None))
    cursor = conn.executemany(
        "INSERT OR IGNORE INTO weather_daily (date, state, temp_max_f, temp_min_f, precip_in) "
        "VALUES (?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    inserted = cursor.rowcount
    logger.info("Inserted %d rows into weather_daily (%d total submitted)", inserted, len(rows))
    return inserted


def query_max_date(conn: sqlite3.Connection, table: str, filter_col: str, filter_val: str) -> str | None:
    """Return the maximum date for a given filter value, or None if no rows match.

    Args:
        conn: An open SQLite connection.
        table: Table name (futures_daily or weather_daily).
        filter_col: Column to filter on (e.g. 'ticker' or 'state').
        filter_val: Value to filter for (e.g. 'ZC=F' or 'Iowa').

    Returns:
        The max date as a string (YYYY-MM-DD), or None if no data exists.
    """
    cursor = conn.execute(
        f"SELECT MAX(date) FROM {table} WHERE {filter_col} = ?",  # noqa: S608
        (filter_val,),
    )
    result = cursor.fetchone()[0]
    return result


def log_validation(conn: sqlite3.Connection, issues: list[dict]) -> int:
    """Bulk-insert validation issues into the validation_log table.

    Args:
        conn: An open SQLite connection.
        issues: List of dicts with keys: checked_at, source_table, date,
            entity_key, check_name, severity, details.

    Returns:
        Number of rows inserted.
    """
    if not issues:
        return 0
    rows = [
        (i["checked_at"], i["source_table"], i["date"], i["entity_key"],
         i["check_name"], i["severity"], i["details"])
        for i in issues
    ]
    conn.executemany(
        "INSERT INTO validation_log "
        "(checked_at, source_table, date, entity_key, check_name, severity, details) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    logger.info("Logged %d validation issues", len(rows))
    return len(rows)
