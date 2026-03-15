"""SQLite database manager for the warehouse and app databases.

Two databases:
  - warehouse.db: validated market data, ETL logs, and catalog metadata
  - app.db: application state (backtest runs, shared analyses, AI usage)

Centralizes all database interactions: connection management, table
creation, bulk inserts, and helper queries. Scrapers and downstream
consumers import from here instead of managing connections directly.
"""

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "warehouse" / "warehouse.db"
APP_DB_PATH = PROJECT_ROOT / "warehouse" / "app.db"

# ===========================================================================
# Warehouse DDL — data tables
# ===========================================================================

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

# ===========================================================================
# Warehouse DDL — ETL tables
# ===========================================================================

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

# ===========================================================================
# Warehouse DDL — catalog tables
# ===========================================================================

CREATE_STRATEGIES = """
CREATE TABLE IF NOT EXISTS strategies (
    name             TEXT PRIMARY KEY,
    module_name      TEXT NOT NULL,
    description      TEXT,
    summary          TEXT,
    features_config  TEXT,
    parameters       TEXT,
    registered_at    TEXT NOT NULL,
    updated_at       TEXT NOT NULL
);
"""

CREATE_DATA_CATALOG = """
CREATE TABLE IF NOT EXISTS data_catalog (
    table_name     TEXT NOT NULL,
    entity_key     TEXT NOT NULL,
    source_name    TEXT NOT NULL,
    source_type    TEXT NOT NULL,
    entity_column  TEXT NOT NULL,
    provider       TEXT NOT NULL,
    description    TEXT DEFAULT '',
    columns        TEXT NOT NULL,
    row_count      INTEGER,
    min_date       TEXT,
    max_date       TEXT,
    null_pct       TEXT,
    updated_at     TEXT NOT NULL,
    PRIMARY KEY (table_name, entity_key)
);
"""

CREATE_FEATURE_CATALOG = """
CREATE TABLE IF NOT EXISTS feature_catalog (
    name           TEXT NOT NULL,
    category       TEXT NOT NULL,
    entity         TEXT NOT NULL,
    description    TEXT DEFAULT '',
    params         TEXT,
    source_table   TEXT,
    stat_min       REAL,
    stat_max       REAL,
    stat_mean      REAL,
    stat_std       REAL,
    available_from TEXT,
    freshness      TEXT,
    updated_at     TEXT NOT NULL,
    PRIMARY KEY (name, category, entity)
);
"""

# ===========================================================================
# App DDL — application state tables
# ===========================================================================

CREATE_SHARED_ANALYSES = """
CREATE TABLE IF NOT EXISTS shared_analyses (
    id              TEXT PRIMARY KEY,
    strategy_name   TEXT NOT NULL,
    ticker_symbol   TEXT NOT NULL,
    ticker_name     TEXT NOT NULL,
    capital         REAL NOT NULL,
    risk_pct        REAL NOT NULL,
    cost_per_trade  REAL NOT NULL,
    result_data     TEXT NOT NULL,
    trade_log_data  TEXT NOT NULL,
    stats_data      TEXT NOT NULL,
    created_at      TEXT NOT NULL
);
"""

CREATE_BACKTEST_RUNS = """
CREATE TABLE IF NOT EXISTS backtest_runs (
    id               TEXT PRIMARY KEY,
    strategy_name    TEXT NOT NULL,
    strategy_module  TEXT NOT NULL,
    run_type         TEXT NOT NULL DEFAULT 'manual',
    ticker           TEXT NOT NULL,
    ticker_name      TEXT NOT NULL,
    date_range_start TEXT,
    date_range_end   TEXT,
    capital          REAL NOT NULL,
    risk_pct         REAL NOT NULL,
    cost_per_trade   REAL NOT NULL,
    total_pnl        REAL,
    sharpe_ratio     REAL,
    max_drawdown_pct REAL,
    win_rate         REAL,
    num_trades       INTEGER,
    sortino_ratio    REAL,
    calmar_ratio     REAL,
    profit_factor    REAL,
    result_data      TEXT NOT NULL,
    trade_log_data   TEXT NOT NULL,
    stats_data       TEXT NOT NULL,
    run_by           TEXT NOT NULL DEFAULT 'Sakib',
    notes            TEXT DEFAULT '',
    starred          INTEGER NOT NULL DEFAULT 0,
    created_at       TEXT NOT NULL
);
"""

CREATE_AI_USAGE = """
CREATE TABLE IF NOT EXISTS ai_usage (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp     TEXT NOT NULL,
    provider      TEXT NOT NULL,
    model         TEXT NOT NULL,
    feature       TEXT NOT NULL,
    input_tokens  INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd      REAL NOT NULL DEFAULT 0.0,
    duration_s    REAL
);
"""

# ===========================================================================
# Connection management
# ===========================================================================


def get_connection() -> sqlite3.Connection:
    """Open a connection to the warehouse database (data + catalogs).

    Returns:
        An open sqlite3.Connection to warehouse.db.
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    logger.debug("Connected to %s", DB_PATH)
    return conn


def get_app_connection() -> sqlite3.Connection:
    """Open a connection to the app database (application state).

    Returns:
        An open sqlite3.Connection to app.db.
    """
    APP_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(APP_DB_PATH))
    logger.debug("Connected to %s", APP_DB_PATH)
    return conn


def init_tables(conn: sqlite3.Connection) -> None:
    """Create all warehouse tables if they do not exist.

    Warehouse tables: data, ETL, and catalog tables.

    Args:
        conn: An open SQLite connection to warehouse.db.
    """
    # Data
    conn.execute(CREATE_FUTURES_DAILY)
    conn.execute(CREATE_WEATHER_DAILY)
    # ETL
    conn.execute(CREATE_VALIDATION_LOG)
    # Catalog
    conn.execute(CREATE_STRATEGIES)
    conn.execute(CREATE_DATA_CATALOG)
    conn.execute(CREATE_FEATURE_CATALOG)
    conn.commit()
    logger.debug("Warehouse tables initialized")


def init_app_tables(conn: sqlite3.Connection) -> None:
    """Create all app tables if they do not exist.

    App tables: shared analyses, backtest runs, AI usage.

    Args:
        conn: An open SQLite connection to app.db.
    """
    conn.execute(CREATE_SHARED_ANALYSES)
    conn.execute(CREATE_BACKTEST_RUNS)
    conn.execute(CREATE_AI_USAGE)

    # Migrations for existing databases
    cur = conn.execute("PRAGMA table_info(ai_usage)")
    columns = {row[1] for row in cur.fetchall()}
    if "duration_s" not in columns:
        conn.execute("ALTER TABLE ai_usage ADD COLUMN duration_s REAL")

    conn.commit()
    logger.debug("App tables initialized")


# ===========================================================================
# Data table operations
# ===========================================================================


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
    """Return the maximum date for a given filter value, or None if no rows match."""
    cursor = conn.execute(
        f"SELECT MAX(date) FROM {table} WHERE {filter_col} = ?",  # noqa: S608
        (filter_val,),
    )
    result = cursor.fetchone()[0]
    return result


def log_validation(conn: sqlite3.Connection, issues: list[dict]) -> int:
    """Bulk-insert validation issues into the validation_log table."""
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


def source_summary(table: str, entity_col: str, entity_val: str) -> dict:
    """Return summary statistics for a raw data source entity.

    Returns:
        Dict with keys: min_date, max_date, row_count, null_pct.
    """
    conn = get_connection()

    cursor = conn.execute(
        f"SELECT MIN(date), MAX(date), COUNT(*) FROM {table} "  # noqa: S608
        f"WHERE {entity_col} = ?",
        (entity_val,),
    )
    min_date, max_date, row_count = cursor.fetchone()

    cursor = conn.execute(f"PRAGMA table_info({table})")
    columns = [row[1] for row in cursor.fetchall()
               if row[1] not in ("date", entity_col)]

    null_pct = {}
    for col in columns:
        cursor = conn.execute(
            f"SELECT ROUND(100.0 * SUM(CASE WHEN {col} IS NULL THEN 1 ELSE 0 END) "  # noqa: S608
            f"/ COUNT(*), 2) FROM {table} WHERE {entity_col} = ?",
            (entity_val,),
        )
        null_pct[col] = cursor.fetchone()[0] or 0.0

    conn.close()
    return {
        "min_date": min_date,
        "max_date": max_date,
        "row_count": row_count,
        "null_pct": null_pct,
    }


def load_raw_data(table: str, entity_col: str, entity_val: str) -> pd.DataFrame:
    """Load raw data for a given table and entity."""
    conn = get_connection()
    df = pd.read_sql(
        f"SELECT * FROM {table} WHERE {entity_col} = ? ORDER BY date",  # noqa: S608
        conn,
        params=(entity_val,),
        parse_dates=["date"],
    )
    conn.close()
    return df


def load_prices(ticker: str = "ZC=F") -> pd.DataFrame:
    """Load OHLCV price data for a ticker."""
    conn = get_connection()
    df = pd.read_sql(
        "SELECT date, open, high, low, close, volume "
        "FROM futures_daily WHERE ticker = ? ORDER BY date",
        conn,
        params=(ticker,),
        parse_dates=["date"],
        index_col="date",
    )
    conn.close()
    df.columns = [c.capitalize() for c in df.columns]
    df.sort_index(inplace=True)
    return df


# ===========================================================================
# Catalog: strategies
# ===========================================================================


def upsert_strategy(
    conn: sqlite3.Connection,
    name: str,
    module_name: str,
    description: str,
    summary: str,
    features_config: dict | None,
    parameters: dict,
) -> None:
    """Insert or update a strategy row."""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT OR REPLACE INTO strategies "
        "(name, module_name, description, summary, features_config, parameters, "
        "registered_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, "
        "COALESCE((SELECT registered_at FROM strategies WHERE name = ?), ?), ?)",
        (
            name,
            module_name,
            description,
            summary,
            json.dumps(features_config) if features_config else None,
            json.dumps(parameters),
            name,
            now,
            now,
        ),
    )
    conn.commit()
    logger.debug("Upserted strategy: %s", name)


def list_strategies(conn: sqlite3.Connection) -> list[dict]:
    """Return all strategies as a list of dicts."""
    conn.row_factory = sqlite3.Row
    cursor = conn.execute("SELECT * FROM strategies ORDER BY name")
    rows = [dict(row) for row in cursor.fetchall()]
    conn.row_factory = None
    return rows


def get_strategy(conn: sqlite3.Connection, name: str) -> dict | None:
    """Return one strategy by name, or None if not found."""
    conn.row_factory = sqlite3.Row
    cursor = conn.execute("SELECT * FROM strategies WHERE name = ?", (name,))
    row = cursor.fetchone()
    conn.row_factory = None
    return dict(row) if row else None


def delete_strategy(conn: sqlite3.Connection, name: str) -> None:
    """Remove a strategy row."""
    conn.execute("DELETE FROM strategies WHERE name = ?", (name,))
    conn.commit()
    logger.debug("Deleted strategy: %s", name)


# ===========================================================================
# Catalog: data sources
# ===========================================================================


def populate_data_catalog(conn: sqlite3.Connection) -> int:
    """Populate the data_catalog table from scraper config and live DB stats.

    Reads etl/scrapers/config.yaml for source definitions, queries live
    row counts and date ranges from data tables, and inserts/replaces rows.

    Returns:
        Number of catalog entries written.
    """
    import yaml

    config_path = PROJECT_ROOT / "etl" / "scrapers" / "config.yaml"
    with open(config_path) as f:
        cfg = yaml.safe_load(f)

    now = datetime.now(timezone.utc).isoformat()
    count = 0

    # Futures sources
    for ticker in cfg.get("yahoo_finance", {}).get("tickers", []):
        symbol = ticker["symbol"]
        name = ticker["name"]

        cursor = conn.execute(
            "SELECT MIN(date), MAX(date), COUNT(*) FROM futures_daily WHERE ticker = ?",
            (symbol,),
        )
        min_date, max_date, row_count = cursor.fetchone()

        # Compute null percentages
        null_pct = {}
        for col in ("open", "high", "low", "close", "volume"):
            cursor = conn.execute(
                f"SELECT ROUND(100.0 * SUM(CASE WHEN {col} IS NULL THEN 1 ELSE 0 END) "
                f"/ COUNT(*), 2) FROM futures_daily WHERE ticker = ?",
                (symbol,),
            )
            null_pct[col] = cursor.fetchone()[0] or 0.0

        conn.execute(
            "INSERT OR REPLACE INTO data_catalog "
            "(table_name, entity_key, source_name, source_type, entity_column, "
            "provider, description, columns, row_count, min_date, max_date, "
            "null_pct, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "futures_daily", symbol, name, "futures", "ticker",
                "Yahoo Finance",
                f"CBOT {name.title()} Futures continuous contract",
                json.dumps(["date", "ticker", "open", "high", "low", "close", "volume"]),
                row_count, min_date, max_date,
                json.dumps(null_pct), now,
            ),
        )
        count += 1

    # Weather sources
    for loc in cfg.get("open_meteo", {}).get("locations", []):
        state = loc["state"]

        cursor = conn.execute(
            "SELECT MIN(date), MAX(date), COUNT(*) FROM weather_daily WHERE state = ?",
            (state,),
        )
        min_date, max_date, row_count = cursor.fetchone()

        null_pct = {}
        for col in ("temp_max_f", "temp_min_f", "precip_in"):
            cursor = conn.execute(
                f"SELECT ROUND(100.0 * SUM(CASE WHEN {col} IS NULL THEN 1 ELSE 0 END) "
                f"/ COUNT(*), 2) FROM weather_daily WHERE state = ?",
                (state,),
            )
            null_pct[col] = cursor.fetchone()[0] or 0.0

        conn.execute(
            "INSERT OR REPLACE INTO data_catalog "
            "(table_name, entity_key, source_name, source_type, entity_column, "
            "provider, description, columns, row_count, min_date, max_date, "
            "null_pct, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "weather_daily", state, state.lower(), "weather", "state",
                "Open-Meteo",
                f"Daily temperature and precipitation for {state} (Corn Belt)",
                json.dumps(["date", "state", "temp_max_f", "temp_min_f", "precip_in"]),
                row_count, min_date, max_date,
                json.dumps(null_pct), now,
            ),
        )
        count += 1

    conn.commit()
    logger.info("Populated data_catalog: %d entries", count)
    return count


def list_data_catalog(conn: sqlite3.Connection) -> list[dict]:
    """Return all data catalog entries."""
    conn.row_factory = sqlite3.Row
    cursor = conn.execute("SELECT * FROM data_catalog ORDER BY source_type, source_name")
    rows = [dict(row) for row in cursor.fetchall()]
    conn.row_factory = None
    return rows


# ===========================================================================
# Catalog: features
# ===========================================================================


def populate_feature_catalog(conn: sqlite3.Connection, metadata_df: pd.DataFrame) -> int:
    """Populate the feature_catalog table from a metadata DataFrame.

    Args:
        conn: An open warehouse connection.
        metadata_df: DataFrame with columns: name, category, entity,
            description, params, source_table, stat_min, stat_max,
            stat_mean, stat_std, available_from, freshness.

    Returns:
        Number of catalog entries written.
    """
    if metadata_df.empty:
        return 0

    now = datetime.now(timezone.utc).isoformat()

    # Clear and repopulate
    conn.execute("DELETE FROM feature_catalog")

    rows = []
    for _, row in metadata_df.iterrows():
        rows.append((
            row.get("name", ""),
            row.get("category", ""),
            row.get("entity", ""),
            row.get("description", ""),
            row.get("params"),
            row.get("source_table"),
            row.get("stat_min"),
            row.get("stat_max"),
            row.get("stat_mean"),
            row.get("stat_std"),
            row.get("available_from"),
            row.get("freshness"),
            now,
        ))

    conn.executemany(
        "INSERT INTO feature_catalog "
        "(name, category, entity, description, params, source_table, "
        "stat_min, stat_max, stat_mean, stat_std, available_from, freshness, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    logger.info("Populated feature_catalog: %d entries", len(rows))
    return len(rows)


def list_feature_catalog(
    conn: sqlite3.Connection,
    category: str | None = None,
    entity: str | None = None,
) -> list[dict]:
    """Return feature catalog entries with optional filters."""
    query = "SELECT * FROM feature_catalog"
    conditions = []
    params: list = []

    if category:
        conditions.append("category = ?")
        params.append(category)
    if entity:
        conditions.append("entity = ?")
        params.append(entity)

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " ORDER BY category, entity, name"

    conn.row_factory = sqlite3.Row
    cursor = conn.execute(query, params)
    rows = [dict(row) for row in cursor.fetchall()]
    conn.row_factory = None
    return rows


# ===========================================================================
# App: shared analyses
# ===========================================================================


def save_shared_analysis(
    conn: sqlite3.Connection,
    id: str,
    strategy_name: str,
    ticker_symbol: str,
    ticker_name: str,
    capital: float,
    risk_pct: float,
    cost_per_trade: float,
    result_data: str,
    trade_log_data: str,
    stats_data: str,
) -> None:
    """Persist a shared backtest analysis to the app database."""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO shared_analyses "
        "(id, strategy_name, ticker_symbol, ticker_name, capital, risk_pct, "
        "cost_per_trade, result_data, trade_log_data, stats_data, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (id, strategy_name, ticker_symbol, ticker_name, capital, risk_pct,
         cost_per_trade, result_data, trade_log_data, stats_data, now),
    )
    conn.commit()
    logger.info("Saved shared analysis: %s", id)


def load_shared_analysis(conn: sqlite3.Connection, share_id: str) -> dict | None:
    """Load a shared analysis by ID from the app database."""
    conn.row_factory = sqlite3.Row
    cursor = conn.execute(
        "SELECT * FROM shared_analyses WHERE id = ?", (share_id,),
    )
    row = cursor.fetchone()
    conn.row_factory = None
    return dict(row) if row else None


# ===========================================================================
# App: backtest runs
# ===========================================================================


def save_backtest_run(
    conn: sqlite3.Connection,
    id: str,
    strategy_name: str,
    strategy_module: str,
    run_type: str,
    ticker: str,
    ticker_name: str,
    date_range_start: str | None,
    date_range_end: str | None,
    capital: float,
    risk_pct: float,
    cost_per_trade: float,
    total_pnl: float | None,
    sharpe_ratio: float | None,
    max_drawdown_pct: float | None,
    win_rate: float | None,
    num_trades: int | None,
    sortino_ratio: float | None,
    calmar_ratio: float | None,
    profit_factor: float | None,
    result_data: str,
    trade_log_data: str,
    stats_data: str,
    run_by: str = "Sakib",
    notes: str = "",
    starred: int = 0,
) -> None:
    """Persist a backtest run to the app database."""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO backtest_runs "
        "(id, strategy_name, strategy_module, run_type, ticker, ticker_name, "
        "date_range_start, date_range_end, capital, risk_pct, cost_per_trade, "
        "total_pnl, sharpe_ratio, max_drawdown_pct, win_rate, num_trades, "
        "sortino_ratio, calmar_ratio, profit_factor, "
        "result_data, trade_log_data, stats_data, run_by, notes, starred, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (id, strategy_name, strategy_module, run_type, ticker, ticker_name,
         date_range_start, date_range_end, capital, risk_pct, cost_per_trade,
         total_pnl, sharpe_ratio, max_drawdown_pct, win_rate, num_trades,
         sortino_ratio, calmar_ratio, profit_factor,
         result_data, trade_log_data, stats_data, run_by, notes, starred, now),
    )
    conn.commit()
    logger.info("Saved backtest run: %s", id)


def load_backtest_run(conn: sqlite3.Connection, run_id: str) -> dict | None:
    """Load a backtest run by ID from the app database."""
    conn.row_factory = sqlite3.Row
    cursor = conn.execute(
        "SELECT * FROM backtest_runs WHERE id = ?", (run_id,),
    )
    row = cursor.fetchone()
    conn.row_factory = None
    return dict(row) if row else None


_LIST_SORT_ALLOWLIST = {
    "created_at", "total_pnl", "sharpe_ratio", "max_drawdown_pct",
    "win_rate", "num_trades", "sortino_ratio", "calmar_ratio", "profit_factor",
    "strategy_name", "ticker_name",
}


def list_backtest_runs(
    conn: sqlite3.Connection,
    strategy_name: str | None = None,
    ticker: str | None = None,
    run_type: str | None = None,
    starred_only: bool = False,
    sort_by: str = "created_at",
    sort_order: str = "DESC",
    limit: int = 100,
) -> list[dict]:
    """List backtest runs from the app database, excluding large JSON blobs."""
    if sort_by not in _LIST_SORT_ALLOWLIST:
        sort_by = "created_at"
    if sort_order.upper() not in ("ASC", "DESC"):
        sort_order = "DESC"

    cols = (
        "id, strategy_name, strategy_module, run_type, ticker, ticker_name, "
        "date_range_start, date_range_end, capital, risk_pct, cost_per_trade, "
        "total_pnl, sharpe_ratio, max_drawdown_pct, win_rate, num_trades, "
        "sortino_ratio, calmar_ratio, profit_factor, "
        "run_by, notes, starred, created_at"
    )
    query = f"SELECT {cols} FROM backtest_runs"  # noqa: S608
    conditions = []
    params: list = []

    if strategy_name:
        conditions.append("strategy_name = ?")
        params.append(strategy_name)
    if ticker:
        conditions.append("ticker = ?")
        params.append(ticker)
    if run_type:
        conditions.append("run_type = ?")
        params.append(run_type)
    if starred_only:
        conditions.append("starred = 1")

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += f" ORDER BY {sort_by} {sort_order} LIMIT ?"  # noqa: S608
    params.append(limit)

    conn.row_factory = sqlite3.Row
    cursor = conn.execute(query, params)
    rows = [dict(row) for row in cursor.fetchall()]
    conn.row_factory = None
    return rows


def update_backtest_run_star(conn: sqlite3.Connection, run_id: str, starred: int) -> None:
    """Toggle the starred flag on a backtest run."""
    conn.execute(
        "UPDATE backtest_runs SET starred = ? WHERE id = ?",
        (starred, run_id),
    )
    conn.commit()


def update_backtest_run_notes(conn: sqlite3.Connection, run_id: str, notes: str) -> None:
    """Update notes on a backtest run."""
    conn.execute(
        "UPDATE backtest_runs SET notes = ? WHERE id = ?",
        (notes, run_id),
    )
    conn.commit()


def delete_backtest_run(conn: sqlite3.Connection, run_id: str) -> None:
    """Delete a backtest run."""
    conn.execute("DELETE FROM backtest_runs WHERE id = ?", (run_id,))
    conn.commit()
    logger.debug("Deleted backtest run: %s", run_id)
