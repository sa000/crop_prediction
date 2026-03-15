# Database Reorganization — Detailed Plan

## Context

The warehouse has 7 tables in a single `warehouse.db`, mixing validated market data with app-layer state (leaderboard runs, shared analyses, AI usage). The `--rebuild` flag deletes the entire DB file, which destroys app state. Additionally, the data catalog (raw source metadata) and feature catalog (engineered feature metadata) exist only as on-the-fly computations or YAML/Parquet files — not as queryable tables.

## Goals

1. **Split into two databases**: `warehouse.db` (data) and `app.db` (app state)
2. **Add `data_catalog` table**: persistent, queryable description of every raw data source
3. **Add `feature_catalog` table**: persistent, queryable description of every engineered feature
4. **Make `--rebuild` safe**: only touches warehouse.db, app state is untouched
5. **Keep YAML/Parquet files**: catalogs are additive, not replacements

## Final Table Layout

### warehouse/warehouse.db (data layer — rebuildable)
| Table | Purpose |
|-------|---------|
| `futures_daily` | Raw OHLCV price data |
| `weather_daily` | Raw temperature/precipitation |
| `validation_log` | ETL quality audit trail |
| `data_catalog` | **NEW** — raw data source inventory |
| `feature_catalog` | **NEW** — engineered feature inventory |

### warehouse/app.db (app layer — permanent)
| Table | Purpose |
|-------|---------|
| `strategies` | Strategy registry (synced from filesystem) |
| `shared_analyses` | Shareable backtest links |
| `backtest_runs` | Leaderboard run history |
| `ai_usage` | AI token/cost tracking |

---

## Implementation (7 pieces)

### Piece 1: Catalog table schemas + helpers in `etl/db.py`

**`data_catalog` DDL:**
```sql
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
```

**`feature_catalog` DDL:**
```sql
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
```

**New functions:**
- `populate_data_catalog(conn)` — reads `etl/scrapers/config.yaml`, queries live stats via existing `source_summary()` pattern, inserts/replaces rows
- `populate_feature_catalog(conn, metadata_df)` — takes the metadata DataFrame (from `features/pipeline.py`) and bulk-inserts rows
- `list_data_catalog(conn)` — SELECT * from data_catalog
- `list_feature_catalog(conn, category=None, entity=None)` — SELECT with optional filters

Register both in `init_tables()`.

### Piece 2: App database infrastructure in `etl/db.py`

**New constants:**
- `APP_DB_PATH = PROJECT_ROOT / "warehouse" / "app.db"`

**New functions:**
- `get_app_connection()` — same pattern as `get_connection()` but for app.db
- `init_app_tables(conn)` — creates strategies, shared_analyses, backtest_runs, ai_usage

**Move DDLs:**
- `CREATE_STRATEGIES` → stays in db.py but registered in `init_app_tables()`
- `CREATE_SHARED_ANALYSES` → same
- `CREATE_BACKTEST_RUNS` → same
- `CREATE_AI_USAGE` → move from `app/ai_usage.py` into db.py

**Remove from `init_tables()`:**
- `CREATE_STRATEGIES`, `CREATE_SHARED_ANALYSES`, `CREATE_BACKTEST_RUNS` — no longer in warehouse.db

### Piece 3: Update `etl/run_pipeline.py`

- `--rebuild` continues to delete `warehouse.db` only (already does this)
- After rebuilding data, call `populate_data_catalog(conn)` to populate the catalog from the freshly inserted data
- No changes to app.db

### Piece 4: Update `features/pipeline.py`

- After writing metadata.parquet, also call `populate_feature_catalog(conn, metadata_df)` to sync the feature catalog table
- This happens on both incremental and `--rebuild` runs

### Piece 5: Update app consumers

Files that use app-state tables need `get_app_connection()` instead of `get_connection()`:

| File | Tables used | Change |
|------|-------------|--------|
| `app/pages/1_Strategy_Dashboard.py` | shared_analyses, backtest_runs, strategies | Use `get_app_connection()` for save/load of shares and runs; `get_connection()` still for `load_prices()` |
| `app/pages/4_Strategy_Leaderboard.py` | backtest_runs | Switch to `get_app_connection()` |
| `app/pages/2_Data_Explorer.py` | (none directly, uses source_summary) | No change needed — data_catalog is in warehouse.db |
| `app/discovery.py` | strategies | Switch to `get_app_connection()` |
| `app/ai_usage.py` | ai_usage | Switch to `get_app_connection()`, remove local DDL |
| `app/catalog_agent.py` | (none) | No change |

### Piece 6: Update Data Explorer to read from catalog tables

- Data Catalog tab can read from `data_catalog` table instead of computing live via `source_summary()` per entity
- Keep `source_summary()` as a fallback / for the "Explore Raw Data" section
- Feature catalog agent can read from `feature_catalog` table as an alternative to metadata.parquet

### Piece 7: Update tests

- `tests/test_app.py`: `TestBacktestRunDB` needs `get_app_connection()` + `init_app_tables()`
- `tests/test_data_pipeline.py`:
  - `TestStrategiesTable` and `TestSharedAnalyses` need app DB connection
  - Add `TestDataCatalog` — verify populate + list round-trip
  - Add `TestFeatureCatalog` — verify populate + list round-trip

---

## Files Changed

| File | Change |
|------|--------|
| `etl/db.py` | Add catalog DDLs + helpers, add app DB path + connection, move app DDLs to init_app_tables |
| `etl/run_pipeline.py` | Call populate_data_catalog after rebuild |
| `features/pipeline.py` | Call populate_feature_catalog after metadata.parquet |
| `app/pages/1_Strategy_Dashboard.py` | Use get_app_connection for app tables |
| `app/pages/4_Strategy_Leaderboard.py` | Use get_app_connection |
| `app/pages/2_Data_Explorer.py` | Read from data_catalog table |
| `app/discovery.py` | Use get_app_connection |
| `app/ai_usage.py` | Use get_app_connection, remove local DDL |
| `tests/test_app.py` | Use get_app_connection, add catalog tests |
| `tests/test_data_pipeline.py` | Use get_app_connection for app tests, add catalog tests |

## Verification

1. `python -m pytest tests/ -v` — all tests pass
2. `python -m etl.run_pipeline --rebuild` — rebuilds warehouse.db, populates data_catalog, app.db untouched
3. `python -m features.pipeline --rebuild` — rebuilds features, populates feature_catalog
4. `streamlit run app/main.py` — all pages work, leaderboard reads from app.db, data explorer reads catalogs
5. Verify app.db exists separately with strategies, backtest_runs, shared_analyses, ai_usage
