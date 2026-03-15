# Database Reorganization — Summary

## Goal
Split the single `warehouse.db` into two databases, add persistent catalog tables, keep all table names as-is.

## Final Layout

**`warehouse/warehouse.db`** (data layer — rebuildable):
| Table | Group | Purpose |
|-------|-------|---------|
| `futures_daily` | Data | OHLCV price data |
| `weather_daily` | Data | Temperature/precipitation |
| `validation_log` | ETL | Data quality audit trail |
| `data_catalog` | Catalog (NEW) | Raw data source inventory |
| `feature_catalog` | Catalog (NEW) | Engineered feature inventory |
| `strategies` | Catalog | Strategy registry |

**`warehouse/app.db`** (app state — permanent, never rebuilt):
| Table | Purpose |
|-------|---------|
| `shared_analyses` | Shareable backtest links |
| `backtest_runs` | Leaderboard run history |
| `ai_usage` | AI token/cost tracking |

## Key Behaviors
- `--rebuild` deletes warehouse.db only; app.db untouched
- `data_catalog` auto-populated after ETL pipeline
- `feature_catalog` auto-populated after feature pipeline
- YAML/Parquet files kept as-is (catalogs are additive)
- All existing table names unchanged

## Files Affected

| File | Change |
|------|--------|
| `etl/db.py` | Add catalog DDLs, add app DB path/connection, move app table DDLs |
| `etl/run_pipeline.py` | Populate data_catalog after rebuild |
| `features/pipeline.py` | Populate feature_catalog after computing features |
| `app/pages/1_Strategy_Dashboard.py` | Use app DB for shares/runs |
| `app/pages/4_Strategy_Leaderboard.py` | Use app DB |
| `app/pages/2_Data_Explorer.py` | Read from catalog tables |
| `app/discovery.py` | Keep warehouse DB (strategies stays in warehouse) |
| `app/ai_usage.py` | Use app DB, remove local DDL |
| `tests/test_app.py` | Update connections, add catalog tests |
| `tests/test_data_pipeline.py` | Update connections, add catalog tests |

## Implementation Order
7 pieces: (1) catalog schemas in db.py, (2) app DB infrastructure, (3) ETL pipeline, (4) feature pipeline, (5) app consumers, (6) Data Explorer, (7) tests
