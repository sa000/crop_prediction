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
  etl/
    db.py                      -- SQLite manager (DB_PATH constant, tables, inserts, queries)
    scrapers/
      config.yaml              -- scraper config (tickers, API settings, landing dirs)
      yahoo_finance.py         -- Yahoo Finance multi-ticker futures OHLCV
      open_meteo.py            -- Open-Meteo daily temp/precip for Corn Belt
  warehouse/
    raw.db                     -- SQLite database (source of truth)
    landing/                   -- immutable Parquet files (audit trail)
      yahoo_finance/           -- one folder per ticker
      open_meteo/
        corn_belt/             -- one folder per location group
  eda/
    signal_gen.py              -- feature engineering and signal generation
    backtest.py                -- backtesting engine (P&L, trade log, stats)
    corn_weather_eda.ipynb     -- exploratory data analysis
    backtest_walkthrough.ipynb -- backtest walkthrough with visuals
    backtest_visuals/          -- saved charts from backtest analysis
  strategies/                  -- one file per strategy, standard interface
  features/                    -- feature store (Parquet files + registry)
  app/                         -- Streamlit web application
```

## Rules

### General
- Before writing or refactoring any code, read `docs/coding_guidelines.md` and follow every rule.
- All scraper configuration lives in `etl/scrapers/config.yaml`. Do not hardcode dates, tickers, URLs, or file paths in scripts.
- Python 3.11.7 via Anaconda (`/opt/anaconda3/bin/python`).
- Open-Meteo free tier: 600 calls/min, 10k/day, 300k/month. Always sleep between API calls per config.

### Data Format
- SQLite (`warehouse/raw.db`) is the source of truth for all raw data. Downstream code reads from SQLite via `pd.read_sql()`.
- Parquet landing zone (`warehouse/landing/`) stores immutable scraper output as an audit trail. Never modify landing files.
- Parquet is the primary format for the feature store. Engineered features go to `features/`.
- All database interactions go through `etl/db.py`. Do not create connections directly in scrapers or consumers.

### Feature Store
- Each feature set is a Parquet file in `features/`.
- Feature registry (YAML or JSON) lists all features with metadata: name, ticker, source, date range, description, category (weather/price/fundamental), frequency, staleness.

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
