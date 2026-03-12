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
    config.yaml                -- shared configuration for all scrapers
    scrapers/
      corn_futures.py          -- Yahoo Finance corn futures OHLCV
      weather.py               -- Open-Meteo daily temp/precip for Corn Belt
    warehouse/
      raw/                     -- raw scraper output (CSV, migrating to Parquet)
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
- All scraper configuration lives in `etl/config.yaml`. Do not hardcode dates, tickers, URLs, or file paths in scripts.
- Python 3.11.7 via Anaconda (`/opt/anaconda3/bin/python`).
- Open-Meteo free tier: 600 calls/min, 10k/day, 300k/month. Always sleep between API calls per config.

### Data Format
- Parquet is the primary storage format for warehouse and feature store data. Use it for all new data files.
- Keep CSV export as a convenience option, not the primary format.
- Raw scraper output goes to `etl/warehouse/raw/`. Engineered features go to `features/`.

### Feature Store
- Each feature set is a Parquet file in `features/`.
- Feature registry (YAML or JSON) lists all features with metadata: name, ticker, source, date range, description, category (weather/price/fundamental), frequency, staleness.

### Strategies
- One file per strategy in `strategies/`.
- Every strategy must expose a `generate_signal` function that takes a feature DataFrame and returns a DataFrame with a `signal` column (+1, -1, or 0).
- Strategies read from the feature store, never directly from raw data.

### Streamlit App
- App code lives in `app/`.
- No hardcoded file paths or configuration in app code -- read from `etl/config.yaml` or feature registry.
- Strategy selection should auto-discover available strategies from the `strategies/` directory.

### Backtest Engine
- Default allocation: $100M (user-configurable).
- Transaction cost: default 0% (user-configurable).
- Position sizing: default binary all-in (optional 1-2% risk per trade toggle).
