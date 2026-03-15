# Crop Yield Trading Strategy Platform

## Overview
Backtesting agricultural commodity futures strategies driven by weather and market data. Currently focused on corn futures with Corn Belt precipitation signals. See [TODO.md](TODO.md) for the phased development plan.

## Project Structure
```
crop_prediction/
  README.md                    -- project overview and quick start
  CLAUDE.md                    -- coding rules and project conventions
  TODO.md                      -- phased development roadmap
  docs/
    coding_guidelines.md       -- coding standards (MUST follow for all code changes)
    planning_guidelines.md     -- plan file workflow (MUST follow for all plans)
  etl/
    db.py                      -- SQLite manager (DB_PATH constant, tables, inserts, queries)
    validate.py                -- validation orchestrator (runs checks, splits clean/rejected)
    pipeline.yaml              -- validation thresholds and check config
    run_pipeline.py            -- pipeline runner (--rebuild for full backfill)
    checks/
      generic.py               -- universal checks (nulls, std dev, dates, non-negative)
      futures.py               -- futures-specific checks (high >= low, close in range)
      weather.py               -- weather-specific checks (temp_max >= temp_min)
    scrapers/
      config.yaml              -- scraper config (tickers, API settings, landing dirs)
      yahoo_finance.py         -- Yahoo Finance multi-ticker futures OHLCV
      open_meteo.py            -- Open-Meteo daily temp/precip for Corn Belt
  warehouse/
    warehouse.db               -- data + catalog DB (rebuildable: data, ETL, catalogs)
    app.db                     -- app state DB (permanent: runs, shares, AI usage)
    landing/                   -- immutable CSV files (audit trail)
      yahoo_finance/           -- one folder per ticker
      open_meteo/
        corn_belt/             -- one folder per location group
  eda/
    signal_gen.py              -- feature engineering and signal generation
    scratch.ipynb              -- scratch notebook for ad-hoc exploration
  features/
    config.yaml                -- feature definitions (windows, entities, parameters)
    registry.yaml              -- auto-generated metadata (tickers, features, mappings)
    metadata.parquet           -- auto-generated feature metadata (one row per feature per entity)
    pipeline.py                -- orchestrator CLI (incremental + --rebuild)
    store.py                   -- Parquet I/O (read, write, append, metadata)
    query.py                   -- DuckDB query layer for consumers
    compute/
      momentum.py              -- SMA, EMA, MACD, RSI
      mean_reversion.py        -- Bollinger bands, z-score, percentile rank
      weather.py               -- rolling sum, mean, z-score
    momentum/                  -- Parquet output per ticker
    mean_reversion/            -- Parquet output per ticker
    weather/                   -- Parquet output per state
  strategies/                  -- one file per strategy, standard interface
    backtest.py                -- backtest engine (dollar P&L, position sizing, stats)
    weather_precipitation.py   -- drought/flood long-only strategy
    weather_strategy_2025.ipynb -- 2025 backtest notebook with visuals
    visuals/                   -- saved charts from strategy backtests
  app/                         -- Streamlit web application
    main.py                    -- entry point (streamlit run app/main.py)
    discovery.py               -- strategy auto-discovery from strategies/
    catalog_agent.py           -- AI feature catalog agent (Claude Haiku, structured JSON)
    trade_analyst.py           -- AI trade post-mortem agent (Claude Sonnet, web search)
    charts.py                  -- Plotly chart builders (pure functions, no Streamlit)
    paper_agent/               -- paper-to-strategy pipeline (extract, map, generate)
      extractor.py             -- PDF/text → strategy spec (DeepSeek)
      mapper.py                -- spec features → data catalog feasibility (DeepSeek)
      generator.py             -- spec + map → Python strategy code (DeepSeek)
      demos/                   -- built-in demo papers for POC
    pages/
      1_Strategy_Backtester.py  -- backtest results, risk metrics, charts
      2_Strategy_Leaderboard.py -- persistent backtest run leaderboard and comparison
      3_Data_Explorer.py       -- browse price, weather, and feature data (+ AI catalog)
      4_Paper_Upload.py        -- paper-to-strategy pipeline UI (5-step workflow)
      5_AI_Usage.py            -- AI API cost/token tracking dashboard
```

## Rules

### General
- Before writing or refactoring any code, read `docs/coding_guidelines.md` and follow every rule.
- Before implementing any plan, read `docs/planning_guidelines.md` and follow the workflow.
- All scraper configuration lives in `etl/scrapers/config.yaml`. Do not hardcode dates, tickers, URLs, or file paths in scripts.
- Python 3.11.7 via Anaconda (`/opt/anaconda3/bin/python`).
- Open-Meteo free tier: 600 calls/min, 10k/day, 300k/month. Always sleep between API calls per config.

### Data Format
- Two SQLite databases in `warehouse/`:
  - `warehouse.db` — data + catalogs (rebuildable): `futures_daily`, `weather_daily`, `validation_log`, `strategies`, `data_catalog`, `feature_catalog`.
  - `app.db` — application state (permanent, never rebuilt): `shared_analyses`, `backtest_runs`, `ai_usage`.
- Use `get_connection()` / `init_tables()` for warehouse.db; `get_app_connection()` / `init_app_tables()` for app.db.
- `--rebuild` deletes warehouse.db only; app.db is untouched.
- SQLite (`warehouse/warehouse.db`) contains only validated data. Downstream code reads from SQLite via `pd.read_sql()`.
- CSV landing zone (`warehouse/landing/`) stores raw, unvalidated CSV scraper output as an audit trail. Never modify landing CSV files.
- Validation runs between landing write and DB insert. Rows failing error-severity checks are rejected; warnings are logged but inserted.
- Validation checks are configured in `etl/pipeline.yaml`. Check code lives in `etl/checks/`.
- Use `python -m etl.run_pipeline --rebuild` to delete warehouse.db and rebuild from landing files with validation.
- Parquet is the primary format for the feature store. Engineered features go to `features/`.
- All database interactions go through `etl/db.py`. Do not create connections directly in scrapers or consumers.

### Feature Store
- Feature definitions live in `features/config.yaml`. To add features: add a compute function + config entry.
- Each entity gets one Parquet file per category (e.g. `features/momentum/corn.parquet`).
- `features/registry.yaml` is auto-generated by the pipeline. It contains: all tickers, all features with source/description/freshness/available_from, ticker-feature mappings, and unlinked (weather) features.
- Incremental updates: `python -m features.pipeline` appends new rows since last run.
- Full rebuild: `python -m features.pipeline --rebuild` recomputes everything from warehouse.db.
- Consumers query features via `features/query.py` (DuckDB SQL over Parquet) or read Parquet directly.
- Compute modules in `features/compute/` are pure functions with no I/O. Each exposes a `FUNCTIONS` dict for dispatch.
- All database interactions go through `etl/db.py`. Do not create connections directly in feature code.

### Strategies
- One file per strategy in `strategies/`.
- Every strategy must expose a `generate_signal` function that takes a feature DataFrame and returns a DataFrame with a `signal` column (+1, -1, or 0).
- Strategies read from the feature store, never directly from raw data.

### Streamlit App
- App code lives in `app/`.
- No hardcoded file paths or configuration in app code -- read from `etl/scrapers/config.yaml` or feature registry.
- Strategy selection should auto-discover available strategies from the `strategies/` directory.

### Backtest Engine
- Default allocation: $100M (user-configurable).
- Transaction cost: default 0% (user-configurable).
- Position sizing: default binary all-in (optional 1-2% risk per trade toggle).

### Testing
- Run `python -m pytest tests/ -v` after every code change to verify nothing is broken.
- Tests use the REAL warehouse.db and Parquet files. Do not mock data layer functions.
- Tests must pass before committing. If a test fails, fix the code, not the test (unless the test itself is wrong).
- When adding new strategies or features that touch the critical data flow, add corresponding tests.
- Test files live in `tests/` at the project root. Target: full suite under 30 seconds.
