"""Validation orchestrator for incoming data.

Runs configured checks against DataFrames, splits rows into clean
(passes all error-severity checks) and rejected, and collects issues
for logging.
"""

import logging
from datetime import datetime

import pandas as pd

from etl.checks import futures as futures_checks
from etl.checks import generic
from etl.checks import weather as weather_checks

logger = logging.getLogger(__name__)

# Maps check names to callables for futures-specific checks.
FUTURES_SPECIFIC = {
    "high_gte_low": futures_checks.check_high_gte_low,
    "close_within_range": futures_checks.check_close_within_range,
}

# Maps check names to callables for weather-specific checks.
WEATHER_SPECIFIC = {
    "temp_max_gte_min": weather_checks.check_temp_max_gte_min,
}


def _run_check(check_cfg: dict, df: pd.DataFrame, specific_map: dict,
               historical: dict[str, pd.Series], sigma: float) -> pd.Series:
    """Run a single check and return a boolean mask (True = pass).

    Args:
        check_cfg: Check definition dict from pipeline.yaml.
        df: Incoming data.
        specific_map: Dict mapping check names to dataset-specific callables.
        historical: Dict mapping column names to historical value Series.
        sigma: Standard deviation threshold for outlier checks.

    Returns:
        Boolean Series aligned with df.index.
    """
    name = check_cfg["name"]

    if check_cfg["type"] == "specific":
        return specific_map[name](df)

    # Generic checks
    if name == "null_check":
        return generic.check_nulls(df, check_cfg["columns"])

    if name == "date_not_future":
        return generic.check_date_not_future(df, "date")

    if name in ("positive_prices",):
        # Run check_positive on each column, combine with AND.
        mask = pd.Series(True, index=df.index)
        for col in check_cfg["columns"]:
            mask = mask & generic.check_positive(df, col)
        return mask

    if name.startswith("non_negative"):
        return generic.check_non_negative(df, check_cfg["column"])

    if name.startswith("stddev_"):
        col = check_cfg["column"]
        hist = historical.get(col, pd.Series(dtype=float))
        return generic.check_stddev_outlier(df, col, hist, sigma)

    logger.warning("Unknown check '%s', passing all rows", name)
    return pd.Series(True, index=df.index)


def _validate(df: pd.DataFrame, checks: list[dict], specific_map: dict,
              historical: dict[str, pd.Series], sigma: float,
              source_table: str, entity_key_col: str) -> tuple[pd.DataFrame, list[dict]]:
    """Core validation loop shared by futures and weather validators.

    Args:
        df: Incoming data to validate.
        checks: List of check config dicts from pipeline.yaml.
        specific_map: Dataset-specific check callables.
        historical: Column name -> historical values for std dev checks.
        sigma: Outlier sigma threshold.
        source_table: Table name for issue logging (e.g. 'futures_daily').
        entity_key_col: Column name used as entity key in issue logs.

    Returns:
        Tuple of (clean_df, issues_list).
    """
    error_mask = pd.Series(True, index=df.index)
    issues: list[dict] = []
    now = datetime.now().isoformat(timespec="seconds")

    for check_cfg in checks:
        passed = _run_check(check_cfg, df, specific_map, historical, sigma)
        failed_rows = df[~passed]

        severity = check_cfg["severity"]
        check_name = check_cfg["name"]

        for _, row in failed_rows.iterrows():
            issues.append({
                "checked_at": now,
                "source_table": source_table,
                "date": str(row.get("date", "")),
                "entity_key": str(row.get(entity_key_col, "")),
                "check_name": check_name,
                "severity": severity,
                "details": _build_details(check_cfg, row),
            })

        if severity == "error":
            error_mask = error_mask & passed

    clean_df = df[error_mask].copy()
    rejected_count = len(df) - len(clean_df)
    if rejected_count > 0:
        logger.info("Rejected %d rows from %s (error-severity failures)", rejected_count, source_table)
    if issues:
        logger.info("Logged %d validation issues for %s", len(issues), source_table)

    return clean_df, issues


def _build_details(check_cfg: dict, row: pd.Series) -> str:
    """Build a human-readable details string for a failed check.

    Args:
        check_cfg: The check definition dict.
        row: The failing row.

    Returns:
        Descriptive string about the failure.
    """
    name = check_cfg["name"]

    if name == "null_check":
        null_cols = [c for c in check_cfg["columns"] if pd.isna(row.get(c))]
        return f"{', '.join(null_cols)} is NULL"

    if name == "date_not_future":
        return f"date={row.get('date')} is in the future"

    if name in ("high_gte_low", "close_within_range"):
        return f"open={row.get('open')}, high={row.get('high')}, low={row.get('low')}, close={row.get('close')}"

    if name == "temp_max_gte_min":
        return f"temp_max_f={row.get('temp_max_f')}, temp_min_f={row.get('temp_min_f')}"

    if name in ("positive_prices",):
        bad_cols = [c for c in check_cfg["columns"] if row.get(c, 1) <= 0]
        return f"{', '.join(bad_cols)} <= 0"

    if name.startswith("non_negative"):
        col = check_cfg["column"]
        return f"{col}={row.get(col)} is negative"

    if name.startswith("stddev_"):
        col = check_cfg["column"]
        return f"{col}={row.get(col)} is an outlier"

    return ""


def _load_historical(conn, table: str, columns: list[str],
                     filter_col: str, filter_val: str) -> dict[str, pd.Series]:
    """Load historical column values from the warehouse for std dev checks.

    Args:
        conn: SQLite connection.
        table: Table name.
        columns: Column names to fetch.
        filter_col: Column to filter on.
        filter_val: Value to filter for.

    Returns:
        Dict mapping column name to Series of historical values.
    """
    cols_str = ", ".join(columns)
    query = f"SELECT {cols_str} FROM {table} WHERE {filter_col} = ?"  # noqa: S608
    df = pd.read_sql(query, conn, params=(filter_val,))
    return {col: df[col].dropna() for col in columns}


def validate_futures(df: pd.DataFrame, conn, cfg: dict) -> tuple[pd.DataFrame, list[dict]]:
    """Run all configured validation checks on futures data.

    Args:
        df: Incoming futures data with columns: date, ticker, open, high, low,
            close, volume.
        conn: SQLite connection to warehouse.db (for historical queries).
        cfg: Validation config dict (the 'validation' section from pipeline.yaml).

    Returns:
        Tuple of (clean_df, issues_list).
    """
    sigma = cfg["anomaly_sigma"]
    checks = cfg["futures"]["checks"]

    all_clean = []
    all_issues: list[dict] = []

    for ticker, group in df.groupby("ticker"):
        historical = _load_historical(
            conn, "futures_daily", ["close", "volume"], "ticker", ticker,
        )
        clean, issues = _validate(
            group, checks, FUTURES_SPECIFIC, historical, sigma,
            source_table="futures_daily", entity_key_col="ticker",
        )
        all_clean.append(clean)
        all_issues.extend(issues)

    clean_df = pd.concat(all_clean, ignore_index=True) if all_clean else pd.DataFrame()
    return clean_df, all_issues


def validate_weather(df: pd.DataFrame, conn, cfg: dict) -> tuple[pd.DataFrame, list[dict]]:
    """Run all configured validation checks on weather data.

    Args:
        df: Incoming weather data with columns: date, state, temp_max_f,
            temp_min_f, precip_in.
        conn: SQLite connection to warehouse.db (for historical queries).
        cfg: Validation config dict (the 'validation' section from pipeline.yaml).

    Returns:
        Tuple of (clean_df, issues_list).
    """
    sigma = cfg["anomaly_sigma"]
    checks = cfg["weather"]["checks"]

    all_clean = []
    all_issues: list[dict] = []

    for state, group in df.groupby("state"):
        historical = _load_historical(
            conn, "weather_daily", ["temp_max_f", "precip_in"], "state", state,
        )
        clean, issues = _validate(
            group, checks, WEATHER_SPECIFIC, historical, sigma,
            source_table="weather_daily", entity_key_col="state",
        )
        all_clean.append(clean)
        all_issues.extend(issues)

    clean_df = pd.concat(all_clean, ignore_index=True) if all_clean else pd.DataFrame()
    return clean_df, all_issues
