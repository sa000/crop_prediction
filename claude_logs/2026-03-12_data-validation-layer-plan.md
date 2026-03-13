# Plan: Data Validation and Clean Warehouse

**Date**: 2026-03-12
**Type**: Plan (pre-implementation)
**Status**: Implemented (see `2026-03-12_data-validation-layer.md` for results)

---

## Context

Scrapers fetch data -> landing Parquet (audit trail) -> `warehouse/warehouse.db`. No validation exists -- nulls, anomalies, and bad data flow straight into the database. We need a validation layer that:

1. Checks incoming data before inserting into the database
2. Keeps the raw landing Parquet files as-is (unvalidated safety net)
3. Logs all validation issues for auditing
4. Supports a clean backfill (delete DB, revalidate everything from landing files)

No clean folder or separate database needed -- landing Parquet is the raw record, `warehouse.db` only gets validated data.

**Out of scope for now**: Feature store, feature registry, metadata tables, feature computation.

---

## Part 1: How Data Flows After This Change

```
API fetch -> DataFrame (in memory)
  |
  v
Landing Parquet (raw, unvalidated, immutable -- already exists)
  |
  v
Validation checks run on the DataFrame
  |
  +-- Rows that pass -> Insert into warehouse.db
  +-- Rows that flag (warning) -> Insert into warehouse.db + log to validation_log
  +-- Rows that fail (error) -> NOT inserted, logged to validation_log
```

Validation sits between the landing write and the DB insert. Landing files capture everything the API returned. warehouse.db only gets validated data.

### Naming change: `raw.db` -> `warehouse.db`

`warehouse/landing/` = raw, unvalidated files from APIs. `warehouse/warehouse.db` = validated, queryable data. The DB name reflects that it's the warehouse -- clean and ready for consumption.

This means updating `DB_PATH` in `etl/db.py` and the `.gitignore` entry.

### Folder structure

```
warehouse/
  warehouse.db                        -- SQLite, only validated data
  landing/                            -- raw unvalidated Parquet (exists today)
    yahoo_finance/corn/2026-03-11.parquet
    open_meteo/corn_belt/2026-03-11.parquet
```

### Backfill strategy

For the initial migration (existing data was never validated):

1. Delete warehouse.db entirely
2. Read all landing Parquet files chronologically
3. Run validation on each file
4. Insert passing rows into a fresh warehouse.db
5. Log any issues found in the historical data

This is a `--rebuild` flag on the pipeline script.

---

## Part 2: Check Organization

### Two categories of checks

**Generic checks** -- work on any DataFrame, any column. Reusable across any dataset:

- `check_nulls(df, columns)` -- are any values null?
- `check_stddev_outlier(df, column, historical_values, sigma)` -- is the value outside N standard deviations from the historical mean?
- `check_date_not_future(df, column)` -- is the date <= today?
- `check_non_negative(df, column)` -- are all values >= 0?
- `check_positive(df, column)` -- are all values > 0?

**Dataset-specific checks** -- only make sense for a particular data source:

- Futures: `check_high_gte_low(df)` -- high >= low
- Futures: `check_close_within_range(df)` -- low <= close <= high
- Weather: `check_temp_max_gte_min(df)` -- temp_max_f >= temp_min_f

### Module structure

```
etl/
  checks/
    __init__.py
    generic.py          -- check_nulls, check_stddev_outlier, check_date_not_future, etc.
    futures.py          -- check_high_gte_low, check_close_within_range
    weather.py          -- check_temp_max_gte_min
  validate.py           -- orchestrates checks, returns clean/failed splits
  pipeline.yaml         -- thresholds and check configuration
```

### How checks are defined

Each check function takes a DataFrame, returns a boolean Series (True = row passes):

```python
# etl/checks/generic.py

def check_nulls(df: pd.DataFrame, columns: list[str]) -> pd.Series:
    """True for rows where none of the specified columns are null."""
    return df[columns].notna().all(axis=1)

def check_stddev_outlier(df: pd.DataFrame, column: str,
                         historical_values: pd.Series, sigma: float) -> pd.Series:
    """True for rows where column value is within N sigma of historical mean.

    Args:
        df: Incoming data to validate.
        column: Column name to check.
        historical_values: All prior clean values for this column (from warehouse.db).
        sigma: Number of standard deviations to allow.
    """
    mean = historical_values.mean()
    std = historical_values.std()
    if std == 0 or pd.isna(std):
        return pd.Series(True, index=df.index)  # can't compute, pass all
    return (df[column] - mean).abs() <= sigma * std

def check_non_negative(df: pd.DataFrame, column: str) -> pd.Series:
    """True for rows where column >= 0."""
    return df[column] >= 0

def check_date_not_future(df: pd.DataFrame, column: str) -> pd.Series:
    """True for rows where date <= today."""
    today = pd.Timestamp.now().normalize()
    return pd.to_datetime(df[column]) <= today
```

```python
# etl/checks/futures.py

def check_high_gte_low(df: pd.DataFrame) -> pd.Series:
    """True for rows where high >= low."""
    return df["high"] >= df["low"]

def check_close_within_range(df: pd.DataFrame) -> pd.Series:
    """True for rows where low <= close <= high."""
    return (df["close"] >= df["low"]) & (df["close"] <= df["high"])
```

```python
# etl/checks/weather.py

def check_temp_max_gte_min(df: pd.DataFrame) -> pd.Series:
    """True for rows where temp_max_f >= temp_min_f."""
    return df["temp_max_f"] >= df["temp_min_f"]
```

### How the standard deviation check works with historical data

When a scraper fetches 1 new day of corn futures data, the std dev check asks: "Is this close price within 3 sigma of the historical distribution?"

The historical data comes from warehouse.db itself -- since it only contains previously validated data, it's a clean baseline:

```python
# In etl/validate.py:
historical = pd.read_sql(
    "SELECT close, volume FROM futures_daily WHERE ticker = ?",
    conn, params=(ticker,)
)
close_ok = generic.check_stddev_outlier(df, "close", historical["close"], sigma=3.0)
```

**Edge case -- first run (no history)**: With no historical data, std dev can't be computed. The check passes all rows. As data accumulates, outlier detection kicks in.

**Edge case -- backfill**: Landing files are processed chronologically. Each batch's "historical" data is everything already inserted, so the baseline grows as we process.

---

## Part 3: The Validation Orchestrator (`etl/validate.py`)

Ties checks together. For each dataset, defines which checks run and at what severity:

```python
def validate_futures(df: pd.DataFrame, conn, cfg: dict) -> tuple[pd.DataFrame, list[dict]]:
    """Run all futures validation checks.

    Args:
        df: Incoming futures data (columns: date, ticker, open, high, low, close, volume).
        conn: SQLite connection to warehouse.db (for historical std dev queries).
        cfg: Validation config from pipeline.yaml.

    Returns:
        clean_df: Rows that passed all error-severity checks.
        issues: List of dicts with check_name, severity, date, entity_key, details.
    """
```

The function:

1. Loads historical data from warehouse.db (for std dev checks)
2. Runs every configured check against the incoming DataFrame
3. Combines error-severity failures -> rows to reject
4. Combines warning-severity failures -> rows to flag but accept
5. Returns `(clean_df, issues_list)`

Same pattern for `validate_weather()`.

---

## Part 4: Validation Log Table

```sql
CREATE TABLE validation_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    checked_at   TEXT NOT NULL,      -- '2026-03-12T14:30:00'
    source_table TEXT NOT NULL,      -- 'futures_daily' or 'weather_daily'
    date         TEXT NOT NULL,      -- '2026-03-11'
    entity_key   TEXT NOT NULL,      -- 'ZC=F' or 'Iowa'
    check_name   TEXT NOT NULL,      -- 'null_check', 'high_gte_low', 'stddev_close'
    severity     TEXT NOT NULL,      -- 'error' or 'warning'
    details      TEXT                -- 'close=NULL', 'close=850.0 is 4.2 sigma from mean'
);
```

Example rows:
```
| checked_at          | source_table  | date       | entity_key | check_name    | severity | details                            |
|---------------------|---------------|------------|------------|---------------|----------|------------------------------------|
| 2026-03-12T14:30:00 | futures_daily | 2026-03-11 | ZC=F       | stddev_close  | warning  | close=850.0 is 4.2 sigma from mean |
| 2026-03-12T14:30:00 | weather_daily | 2026-03-11 | Iowa       | null_check    | error    | precip_in is NULL -- row rejected  |
```

---

## Part 5: Check Configuration (`etl/pipeline.yaml`)

```yaml
validation:
  anomaly_sigma: 3.0

  futures:
    checks:
      - name: "null_check"
        type: "generic"
        severity: "error"
        columns: ["open", "high", "low", "close", "volume"]
      - name: "date_not_future"
        type: "generic"
        severity: "error"
      - name: "high_gte_low"
        type: "specific"
        severity: "error"
      - name: "close_within_range"
        type: "specific"
        severity: "warning"
      - name: "positive_prices"
        type: "generic"
        severity: "error"
        columns: ["open", "high", "low", "close"]
      - name: "non_negative_volume"
        type: "generic"
        severity: "warning"
        column: "volume"
      - name: "stddev_close"
        type: "generic"
        severity: "warning"
        column: "close"
      - name: "stddev_volume"
        type: "generic"
        severity: "warning"
        column: "volume"

  weather:
    checks:
      - name: "null_check"
        type: "generic"
        severity: "error"
        columns: ["temp_max_f", "temp_min_f", "precip_in"]
      - name: "date_not_future"
        type: "generic"
        severity: "error"
      - name: "temp_max_gte_min"
        type: "specific"
        severity: "error"
      - name: "non_negative_precip"
        type: "generic"
        severity: "error"
        column: "precip_in"
      - name: "stddev_temp_max"
        type: "generic"
        severity: "warning"
        column: "temp_max_f"
      - name: "stddev_precip"
        type: "generic"
        severity: "warning"
        column: "precip_in"
```

Checks are in config so you can add/remove checks, change severity, or adjust columns without touching code.

---

## Part 6: How Scrapers Change

### `etl/scrapers/yahoo_finance.py`

Current: `fetch -> save landing -> insert into DB`

New:
```python
# For each ticker:
df = download_ticker(symbol, start, today)

# 1. Save raw landing (unvalidated -- what the API returned)
save_landing_files(df, cfg["landing_dir"], name)

# 2. Validate
clean_df, issues = validate.validate_futures(df_flat, conn, val_cfg)

# 3. Log issues
if issues:
    db.log_validation(conn, issues)

# 4. Insert only validated rows
if not clean_df.empty:
    db.insert_futures(conn, clean_df)
```

### `etl/scrapers/open_meteo.py` -- same pattern

---

## Part 7: Backfill (`etl/run_pipeline.py`)

```python
def rebuild():
    """Delete warehouse.db, revalidate all landing files."""
    # 1. Delete warehouse.db
    DB_PATH.unlink(missing_ok=True)

    # 2. Create fresh DB with tables
    conn = db.get_connection()
    db.init_tables(conn)

    # 3. Read all landing files chronologically
    for parquet_file in sorted(LANDING_DIR.glob("**/*.parquet")):
        df = pd.read_parquet(parquet_file)
        if "yahoo_finance" in str(parquet_file):
            clean_df, issues = validate.validate_futures(df, conn, cfg)
            db.insert_futures(conn, clean_df)
        elif "open_meteo" in str(parquet_file):
            clean_df, issues = validate.validate_weather(df, conn, cfg)
            db.insert_weather(conn, clean_df)
        db.log_validation(conn, issues)

    conn.close()
```

Run with: `python -m etl.run_pipeline --rebuild`

---

## Part 8: Complete Check Reference

### Generic checks (`etl/checks/generic.py`)

| Function | What it checks | Needs history? |
|----------|---------------|----------------|
| `check_nulls(df, columns)` | No nulls in specified columns | No |
| `check_stddev_outlier(df, column, historical, sigma)` | Value within N sigma | Yes |
| `check_date_not_future(df, column)` | Date <= today | No |
| `check_non_negative(df, column)` | Value >= 0 | No |
| `check_positive(df, column)` | Value > 0 | No |

### Futures-specific (`etl/checks/futures.py`)

| Function | What it checks |
|----------|---------------|
| `check_high_gte_low(df)` | high >= low |
| `check_close_within_range(df)` | low <= close <= high |

### Weather-specific (`etl/checks/weather.py`)

| Function | What it checks |
|----------|---------------|
| `check_temp_max_gte_min(df)` | temp_max_f >= temp_min_f |

---

## Implementation Steps

### Step 1: Rename `warehouse/raw.db` -> `warehouse/warehouse.db`
Update `DB_PATH` in `etl/db.py` and `.gitignore`.

### Step 2: Create `etl/pipeline.yaml`
Validation thresholds and check definitions.

### Step 3: Create `etl/checks/` package
- `__init__.py`
- `generic.py` -- universal check functions
- `futures.py` -- futures-specific checks
- `weather.py` -- weather-specific checks

### Step 4: Create `etl/validate.py`
Orchestrator: `validate_futures()` and `validate_weather()`.

### Step 5: Expand `etl/db.py`
- Add `validation_log` table DDL to `init_tables()`
- Add `log_validation(conn, issues)` -- bulk insert into validation_log

### Step 6: Modify `etl/scrapers/yahoo_finance.py`
Add validation between landing write and DB insert.

### Step 7: Modify `etl/scrapers/open_meteo.py`
Same pattern.

### Step 8: Create `etl/run_pipeline.py`
`--rebuild` flag for full backfill.

### Step 9: Update `.gitignore`, `CLAUDE.md`, `TODO.md`

---

## Files Summary

**New files:**

| File | Purpose |
|------|---------|
| `etl/pipeline.yaml` | Validation thresholds and check config |
| `etl/checks/__init__.py` | Package init |
| `etl/checks/generic.py` | Universal checks: nulls, std dev, dates, non-negative |
| `etl/checks/futures.py` | Futures-specific: high >= low, close in range |
| `etl/checks/weather.py` | Weather-specific: temp_max >= temp_min |
| `etl/validate.py` | Orchestrator: runs checks, splits clean/rejected |
| `etl/run_pipeline.py` | Rebuild script (--rebuild flag) |

**Modified files:**

| File | What changes |
|------|-------------|
| `etl/db.py` | Rename DB_PATH to warehouse.db, add validation_log DDL, log_validation() |
| `etl/scrapers/yahoo_finance.py` | Add validation between fetch and insert |
| `etl/scrapers/open_meteo.py` | Same validation pattern |
| `.gitignore` | `warehouse/raw.db` -> `warehouse/warehouse.db` |
| `CLAUDE.md` | Update structure, data format rules, DB name |
| `TODO.md` | Check off validation item |

---

## Verification

```bash
# 1. Rebuild from scratch (validates all historical data)
python -m etl.run_pipeline --rebuild

# 2. Check validation log for historical issues
python -c "
from etl import db
import pandas as pd
conn = db.get_connection()
log = pd.read_sql('SELECT severity, check_name, COUNT(*) as cnt FROM validation_log GROUP BY severity, check_name', conn)
print(log if len(log) else 'No issues found')
conn.close()
"

# 3. Run scrapers normally (now with validation)
python -m etl.scrapers.yahoo_finance
python -m etl.scrapers.open_meteo

# 4. Verify DB has data
python -c "
from etl import db
conn = db.get_connection()
for t in ['futures_daily', 'weather_daily']:
    r = conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
    print(f'{t}: {r} rows')
conn.close()
"
```
