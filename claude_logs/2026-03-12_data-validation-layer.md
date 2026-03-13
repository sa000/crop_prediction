# Data Validation and Clean Warehouse

**Date**: 2026-03-12
**Status**: Completed

## Goal

Add a validation layer between landing Parquet files and warehouse.db so that only validated data enters the database. Landing files remain raw and unvalidated as an audit trail.

## What Changed

### New files

| File | Purpose |
|------|---------|
| `etl/pipeline.yaml` | Validation thresholds and check config (severity, columns, sigma) |
| `etl/checks/__init__.py` | Package init |
| `etl/checks/generic.py` | 5 universal checks: nulls, stddev outlier, date not future, non-negative, positive |
| `etl/checks/futures.py` | 2 futures checks: high >= low, close within range |
| `etl/checks/weather.py` | 1 weather check: temp_max >= temp_min |
| `etl/validate.py` | Orchestrator: runs checks per config, splits clean/rejected rows, builds issue logs |
| `etl/run_pipeline.py` | Pipeline runner with `--rebuild` flag for full backfill from landing files |

### Modified files

| File | What changed |
|------|-------------|
| `etl/db.py` | Renamed `DB_PATH` to `warehouse.db`, added `validation_log` table DDL, added `log_validation()` |
| `etl/scrapers/yahoo_finance.py` | Loads `pipeline.yaml`, validates between landing write and DB insert |
| `etl/scrapers/open_meteo.py` | Same validation pattern |
| `.gitignore` | `raw.db` -> `warehouse.db` |
| `CLAUDE.md` | Updated structure, data format rules, DB name |
| `README.md` | Updated structure and data description |
| `TODO.md` | Checked off "Add data validation step" |

### Naming change

`warehouse/raw.db` -> `warehouse/warehouse.db`. The DB now only contains validated data, so "raw" no longer applies. Landing Parquet files are the raw record.

## Data flow after this change

```
API fetch -> DataFrame (in memory)
  |
  v
Landing Parquet (raw, unvalidated, immutable)
  |
  v
Validation checks run on the DataFrame
  |
  +-- Rows that pass -> Insert into warehouse.db
  +-- Rows that flag (warning) -> Insert into warehouse.db + log to validation_log
  +-- Rows that fail (error) -> NOT inserted, logged to validation_log
```

## Check organization

**Generic checks** (any DataFrame, any column):
- `check_nulls(df, columns)` -- any values null?
- `check_stddev_outlier(df, column, historical_values, sigma)` -- value outside N sigma?
- `check_date_not_future(df, column)` -- date <= today?
- `check_non_negative(df, column)` -- value >= 0?
- `check_positive(df, column)` -- value > 0?

**Futures-specific**:
- `check_high_gte_low(df)` -- high >= low
- `check_close_within_range(df)` -- low <= close <= high

**Weather-specific**:
- `check_temp_max_gte_min(df)` -- temp_max_f >= temp_min_f

Checks are configured in `etl/pipeline.yaml` with severity (error/warning) and column mappings. Adding or removing checks requires no code changes.

## Stddev check details

Historical baseline comes from warehouse.db itself (previously validated data). On first run with no history, the check passes all rows. During backfill, the baseline grows as files are processed chronologically.

## Rebuild strategy

`python -m etl.run_pipeline --rebuild`:
1. Deletes warehouse.db
2. Creates fresh DB with all tables
3. Reads all landing Parquet files chronologically
4. Validates each file, inserts passing rows
5. Logs all issues to validation_log

## Verification results

After rebuild from 274 landing files:
- `futures_daily`: 12,208 rows
- `weather_daily`: 17,739 rows
- `validation_log`: 805 issues (all warnings, zero error rejections)

Breakdown of warnings:
- `stddev_precip`: 457 (precipitation outliers)
- `stddev_close`: 219 (price outliers)
- `stddev_volume`: 94 (volume outliers)
- `close_within_range`: 22 (close outside high/low)
- `stddev_temp_max`: 13 (temperature outliers)

## Related TODO items completed

- Phase 1: "Add data validation step: null checks, range checks, anomaly detection" -- checked off
