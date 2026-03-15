# Data Pipeline Architecture

## 1. Overview

The platform ingests agricultural commodity futures and weather data through a multi-stage pipeline designed around three principles: **immutable audit trail**, **incremental ingestion**, and **point-in-time safety**.

```
Sources          Scrapers          Landing Zone        Validation         Warehouse          Feature Store       Consumers
─────────       ──────────        ──────────────      ────────────       ───────────        ───────────────     ──────────
Yahoo Finance → yahoo_finance.py → warehouse/landing/ → validate.py    → warehouse.db     → Parquet files    → Strategies
Open-Meteo    → open_meteo.py    → (immutable CSVs)   (pipeline.yaml)   (rebuildable)      (features/)        → Streamlit App
                                                       ↓                                    ↓                  → AI Agents
                                                       validation_log                       registry.yaml
                                                                                            metadata.parquet
```

**Two databases** separate rebuildable data from permanent application state:

| Database | Purpose | Rebuild behavior |
|---|---|---|
| `warehouse/warehouse.db` | Data + catalogs (futures, weather, validation log, catalogs) | Deleted and rebuilt from landing CSVs via `--rebuild` |
| `warehouse/app.db` | Application state (backtest runs, shared analyses, AI usage) | Never touched by any rebuild |

All database access flows through a single module: `etl/db.py`.

---

## 2. Data Sources

### Yahoo Finance — Commodity Futures

| Ticker | Name | Exchange |
|---|---|---|
| `ZC=F` | Corn | CBOT |
| `ZS=F` | Soybeans | CBOT |
| `ZW=F` | Wheat | CBOT |

- **Fields**: date, open, high, low, close, volume (OHLCV daily bars)
- **History**: 2010-01-01 to present
- **Provider**: yfinance Python library

### Open-Meteo — Corn Belt Weather

| State | Latitude | Longitude |
|---|---|---|
| Iowa | 41.59 | -93.62 |
| Illinois | 39.80 | -89.64 |
| Nebraska | 40.81 | -96.70 |

- **Fields**: date, temp_max_f (°F), temp_min_f (°F), precip_in (inches)
- **History**: 2010-01-01 to present
- **Provider**: Open-Meteo Archive API (`archive-api.open-meteo.com/v1/archive`)
- **Rate limiting**: 1 second delay between calls (free tier: 600/min, 10k/day, 300k/month)

### Configuration

All tickers, locations, API settings, and landing directories are defined in `etl/scrapers/config.yaml`. Nothing is hardcoded in scraper scripts.

```yaml
scraper_defaults:
  historical_start_date: "2010-01-01"

yahoo_finance:
  tickers:
    - symbol: "ZC=F"
      name: "corn"
    # ...
  landing_dir: "warehouse/landing/yahoo_finance"

open_meteo:
  base_url: "https://archive-api.open-meteo.com/v1/archive"
  timezone: "America/Chicago"
  request_delay_seconds: 1
  request_timeout_seconds: 30
  daily_variables: [temperature_2m_max, temperature_2m_min, precipitation_sum]
  landing_dir: "warehouse/landing/open_meteo/corn_belt"
  locations:
    - state: "Iowa"
      lat: 41.59
      lon: -93.62
    # ...
```

---

## 3. Scrapers & Landing Zone

### Scrapers

**`etl/scrapers/yahoo_finance.py`** — Fetches OHLCV data via yfinance. Incremental: queries `MAX(date)` from warehouse.db and only fetches newer data.

**`etl/scrapers/open_meteo.py`** — Fetches daily weather via REST API. Handles unit conversion (Celsius → Fahrenheit, millimeters → inches) before writing to the landing zone.

### Landing Zone

The landing zone (`warehouse/landing/`) is an **immutable CSV audit trail**. Files are never modified or deleted after creation.

```
warehouse/landing/
├── yahoo_finance/
│   ├── corn/        (~65 CSV files)
│   ├── soybeans/    (~65 CSV files)
│   └── wheat/       (~65 CSV files)
└── open_meteo/
    └── corn_belt/   (~79 CSV files)
```

- **File partitioning**: one CSV per year (historical backfill) + one CSV per day (current year incremental)
- **~274 CSV files** across 4 subdirectories
- Landing files are the source of truth for `--rebuild` operations

---

## 4. Validation Pipeline

Validation sits between the landing zone and the warehouse, ensuring only clean data enters the database.

### Orchestrator

`etl/validate.py` runs checks per entity (ticker or state), splits rows into clean and rejected sets:

1. Load landing CSV, normalize columns, add entity key (ticker/state)
2. Load historical data from warehouse.db for statistical checks (σ-outlier detection)
3. Run each configured check, accumulate issues
4. **Error-severity failures** → row rejected (not inserted)
5. **Warning-severity failures** → row inserted, issue logged
6. Log all issues to `validation_log` table

### Check Types

Checks are configured in `etl/pipeline.yaml` and implemented in `etl/checks/`:

**Generic checks** (`etl/checks/generic.py`) — apply to any data source:
| Check | Severity | Description |
|---|---|---|
| `null_check` | error | Required columns must not be NULL |
| `date_not_future` | error | Date must not be in the future |
| `positive_prices` | error | Price columns must be > 0 |
| `non_negative_volume` | warning | Volume must be ≥ 0 |
| `non_negative_precip` | error | Precipitation must be ≥ 0 |
| `stddev_*` | warning | Value outside ±3σ from historical mean |

**Futures-specific checks** (`etl/checks/futures.py`):
| Check | Severity | Description |
|---|---|---|
| `high_gte_low` | error | High price must be ≥ low price |
| `close_within_range` | warning | Close should be within [low, high] |

**Weather-specific checks** (`etl/checks/weather.py`):
| Check | Severity | Description |
|---|---|---|
| `temp_max_gte_min` | error | Max temperature must be ≥ min temperature |

### Severity Model

| Severity | Action | Example |
|---|---|---|
| `error` | Row **rejected** — not inserted into warehouse | NULL close price, high < low |
| `warning` | Row **inserted** — issue logged for review | Close outside [low, high], 3σ outlier |

All issues are recorded in the `validation_log` table with: timestamp, source table, date, entity key, check name, severity, and details.

---

## 5. Warehouse (SQLite)

### warehouse.db — Rebuildable Data + Catalogs

Rebuilt from scratch via `python -m etl.run_pipeline --rebuild`.

#### Data Tables

**`futures_daily`** — ~12,210 rows (3 tickers × ~4,070 days)

```sql
CREATE TABLE futures_daily (
    date     TEXT NOT NULL,
    ticker   TEXT NOT NULL,
    open     REAL,
    high     REAL,
    low      REAL,
    close    REAL,
    volume   INTEGER,
    PRIMARY KEY (date, ticker)
);
```

**`weather_daily`** — ~17,739 rows (3 states × ~5,913 days)

```sql
CREATE TABLE weather_daily (
    date       TEXT NOT NULL,
    state      TEXT NOT NULL,
    temp_max_f REAL,
    temp_min_f REAL,
    precip_in  REAL,
    PRIMARY KEY (date, state)
);
```

#### ETL Tables

**`validation_log`** — audit trail of all check failures

```sql
CREATE TABLE validation_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    checked_at   TEXT NOT NULL,
    source_table TEXT NOT NULL,
    date         TEXT NOT NULL,
    entity_key   TEXT NOT NULL,
    check_name   TEXT NOT NULL,
    severity     TEXT NOT NULL,
    details      TEXT
);
```

#### Catalog Tables

**`data_catalog`** — 6 entries (3 futures + 3 weather) with live statistics

```sql
CREATE TABLE data_catalog (
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

**`feature_catalog`** — mirrors `metadata.parquet` in SQLite for app queries

```sql
CREATE TABLE feature_catalog (
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

**`strategies`** — registered strategy modules

```sql
CREATE TABLE strategies (
    name             TEXT PRIMARY KEY,
    module_name      TEXT NOT NULL,
    description      TEXT,
    summary          TEXT,
    features_config  TEXT,
    parameters       TEXT,
    registered_at    TEXT NOT NULL,
    updated_at       TEXT NOT NULL
);
```

#### Duplicate Handling

All inserts use `INSERT OR IGNORE` on composite primary keys, making re-ingestion of overlapping date ranges safe.

### app.db — Permanent Application State

Never touched by any rebuild operation.

**`backtest_runs`** — full backtest results with strategy config, metrics (Sharpe, Sortino, Calmar, drawdown, win rate, profit factor), serialized result/trade/stats data, user notes, and star flags.

**`shared_analyses`** — shareable backtest snapshots with unique IDs.

**`ai_usage`** — API cost/token tracking per provider, model, and feature (catalog agent, trade analyst, paper pipeline).

### Database Access

All connections flow through `etl/db.py`:
- `get_connection()` / `init_tables()` → warehouse.db
- `get_app_connection()` / `init_app_tables()` → app.db
- No other module creates direct database connections

---

## 6. Feature Store

### Configuration

All feature definitions live in `features/config.yaml`. To add a new feature: add a compute function in the appropriate module + add a config entry.

### Feature Categories

**Momentum** (7 features per ticker, source: `futures_daily`):

| Feature | Description | Parameters |
|---|---|---|
| `sma_20` | Simple moving average | window=20 |
| `sma_50` | Simple moving average | window=50 |
| `ema_12` | Exponential moving average | span=12 |
| `ema_26` | Exponential moving average | span=26 |
| `macd` | MACD line (EMA12 − EMA26) | fast=12, slow=26 |
| `macd_signal` | MACD signal line | fast=12, slow=26, signal=9 |
| `rsi_14` | Relative Strength Index | window=14 |

Entities: corn (`ZC=F`), soybeans (`ZS=F`), wheat (`ZW=F`). Max lookback: 50 days.

**Mean Reversion** (5 features per ticker, source: `futures_daily`):

| Feature | Description | Parameters |
|---|---|---|
| `bollinger_upper` | Upper Bollinger band | window=20, num_std=2 |
| `bollinger_lower` | Lower Bollinger band | window=20, num_std=2 |
| `zscore_20` | Z-score of close | window=20 |
| `zscore_50` | Z-score of close | window=50 |
| `pct_rank_20` | Percentile rank of close | window=20 |

Entities: corn (`ZC=F`), soybeans (`ZS=F`), wheat (`ZW=F`). Max lookback: 50 days.

**Weather** (6 features per state, source: `weather_daily`):

| Feature | Description | Parameters |
|---|---|---|
| `precip_7d` | 7-day rolling precipitation sum | window=7 |
| `precip_30d` | 30-day rolling precipitation sum | window=30 |
| `temp_max_7d` | 7-day rolling mean max temp | window=7 |
| `temp_min_7d` | 7-day rolling mean min temp | window=7 |
| `temp_range_7d` | 7-day rolling mean temp range | window=7 |
| `precip_anomaly_30d` | 30-day precipitation z-score | window=30 |

Entities: Iowa, Illinois, Nebraska + `corn_belt` (mean aggregate). Max lookback: 30 days.

### Storage

One Parquet file per entity per category:

```
features/
├── momentum/
│   ├── corn.parquet       (~4,070 rows)
│   ├── soybeans.parquet
│   └── wheat.parquet
├── mean_reversion/
│   ├── corn.parquet
│   ├── soybeans.parquet
│   └── wheat.parquet
├── weather/
│   ├── iowa.parquet       (~5,913 rows)
│   ├── illinois.parquet
│   ├── nebraska.parquet
│   └── corn_belt.parquet  (aggregated)
├── registry.yaml          (auto-generated)
└── metadata.parquet       (auto-generated)
```

Parquet I/O is handled by `features/store.py`: write, append (dedup on date), read, and max-date queries.

### Point-in-Time Safety

All features are **lagged by 1 day** (`shift(1)`) to prevent lookahead bias. A feature value on date T is computed from data available up to date T−1. This ensures strategies cannot peek at same-day information.

### Compute Modules

Compute modules in `features/compute/` are **pure functions with no I/O**. Each module exposes a `FUNCTIONS` dict for dispatch:

- `features/compute/momentum.py` — SMA, EMA, MACD, RSI
- `features/compute/mean_reversion.py` — Bollinger bands, z-score, percentile rank
- `features/compute/weather.py` — rolling sum, mean, z-score

### Pipeline Execution

**Incremental** (`python -m features.pipeline`):
1. For each category and entity, check existing max date in Parquet
2. Load source data from `max_date − 2 × max_lookback` onwards (buffer for rolling windows)
3. Compute features, apply 1-day lag
4. Append only rows where date > existing max date
5. Compute aggregations (e.g., corn_belt = mean of state features)
6. Update registry.yaml and metadata.parquet

**Full rebuild** (`python -m features.pipeline --rebuild`):
1. Delete all Parquet files in each category directory
2. Load all source data from warehouse.db
3. Compute all features from scratch, apply 1-day lag
4. Write full Parquet files
5. Regenerate registry and metadata

---

## 7. Metadata & Catalogs

### Feature Registry (`features/registry.yaml`)

Auto-generated every pipeline run. Contains:

- **tickers**: all 3 futures with symbols and descriptions
- **features**: all 18 features with category, source table, description, freshness date, available_from date
- **ticker_feature_map**: maps each ticker → categories → feature names
- **unlinked_features**: maps weather category → states → feature names
- **files**: metadata per Parquet file (path, date range, row count, entity key)

### Feature Metadata (`features/metadata.parquet`)

Auto-generated. One row per feature per entity with statistics: min, max, mean, std, null_pct, available_from, freshness.

### Data Catalog (`data_catalog` table)

6 entries (3 futures + 3 weather sources) with live statistics: row count, date range, null percentage per column. Populated by `populate_data_catalog()` during pipeline runs.

### Feature Catalog (`feature_catalog` table)

Mirrors metadata.parquet in SQLite for app-layer queries. Populated every pipeline run.

### AI Catalog Agent (`app/catalog_agent.py`)

Natural language feature discovery powered by DeepSeek. Queries metadata.parquet to answer questions like "what momentum features are available for corn?" with structured JSON responses.

---

## 8. Consumer Interface

### Strategy Feature Access

Strategies read features via `features/query.py`, which provides a DuckDB SQL layer over Parquet files.

**`read_strategy_features()`** — primary consumer interface:

```python
read_strategy_features(
    ticker="ZC=F",
    categories=["momentum", "mean_reversion"],
    unlinked=[{"category": "weather", "entity": "corn_belt"}],
    start_date="2015-01-01",
    end_date="2025-12-31",
)
```

1. Reads Parquet files for each requested ticker category (joins on date)
2. For each unlinked feature set (e.g., weather), reads separate Parquet and renames columns with entity prefix
3. Joins everything into a single DataFrame aligned on date
4. Returns a ready-to-use DataFrame for signal generation

### Other Query Functions

- `query()` — arbitrary DuckDB SQL over Parquet files
- `read_parquet()` — single file read with date/column filters
- `list_features()` — enumerate available features from metadata
- `get_ticker_features()` — map a ticker to its available categories and features

### Strategy Contract

Every strategy in `strategies/` must expose:
- `generate_signal(df)` → DataFrame with a `signal` column (+1, −1, or 0)
- `FEATURES` config dict declaring feature dependencies

Strategies read from the feature store, never directly from raw data.

### Raw Price Data

For OHLCV data (used by the backtest engine), consumers call `etl/db.py:load_prices()` which queries `futures_daily` directly.

---

## 9. Rebuild & Recovery

### Full Data Rebuild

```bash
python -m etl.run_pipeline --rebuild
```

1. Deletes `warehouse/warehouse.db`
2. Creates fresh database, initializes all tables
3. Scans all landing CSV files (~274 files)
4. Classifies by path (yahoo_finance → futures, open_meteo → weather)
5. Normalizes columns, adds entity keys from config
6. Validates each batch (split clean/rejected)
7. Inserts clean rows, logs validation issues
8. Back-adjusts futures prices (contract roll corrections)
9. Populates data_catalog with live statistics

### Full Feature Rebuild

```bash
python -m features.pipeline --rebuild
```

1. Deletes all Parquet files in category directories
2. Recomputes all features from warehouse.db
3. Regenerates registry.yaml and metadata.parquet

### Combined Rebuild

```bash
python -m etl.run_pipeline --rebuild --rebuild-features
```

Chains both rebuilds: warehouse first, then feature store.

### What Is Preserved

`warehouse/app.db` is **never touched** by any rebuild operation. Backtest history, shared analyses, and AI usage tracking persist across all rebuilds.

### Recovery Scenarios

| Scenario | Command | Data Lost |
|---|---|---|
| Corrupted warehouse.db | `python -m etl.run_pipeline --rebuild` | None (rebuilt from landing CSVs) |
| Stale features | `python -m features.pipeline --rebuild` | None (recomputed from warehouse) |
| Full reset | `--rebuild --rebuild-features` | None (landing + app.db preserved) |
| Lost landing files | Re-run scrapers with full date range | Download time only |

---

## Key Files Reference

| File | Purpose |
|---|---|
| `etl/scrapers/config.yaml` | Scraper configuration (tickers, locations, API settings) |
| `etl/scrapers/yahoo_finance.py` | Yahoo Finance futures scraper |
| `etl/scrapers/open_meteo.py` | Open-Meteo weather scraper |
| `etl/validate.py` | Validation orchestrator |
| `etl/pipeline.yaml` | Validation check config and thresholds |
| `etl/checks/generic.py` | Universal validation checks |
| `etl/checks/futures.py` | Futures-specific validation checks |
| `etl/checks/weather.py` | Weather-specific validation checks |
| `etl/run_pipeline.py` | Pipeline runner (scrape + validate + insert) |
| `etl/db.py` | All database access (single module) |
| `features/config.yaml` | Feature definitions (windows, entities, parameters) |
| `features/pipeline.py` | Feature pipeline orchestrator |
| `features/store.py` | Parquet I/O (read, write, append, metadata) |
| `features/query.py` | DuckDB query layer for consumers |
| `features/compute/momentum.py` | SMA, EMA, MACD, RSI compute functions |
| `features/compute/mean_reversion.py` | Bollinger, z-score, percentile rank |
| `features/compute/weather.py` | Rolling sum, mean, z-score for weather |
| `app/catalog_agent.py` | AI feature catalog (natural language queries) |
