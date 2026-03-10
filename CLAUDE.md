# Crop Prediction Project

## Overview
Predicting corn futures prices using historical market data and weather patterns from the US Corn Belt.

## Project Structure
```
crop_prediction/
  docs/
    coding_guidelines.md   -- coding standards (MUST follow for all code changes)
  etl/
    config.yaml            -- shared configuration for all scrapers
    scrapers/
      corn_futures.py      -- Yahoo Finance corn futures raw OHLCV
      weather.py           -- Open-Meteo daily temp/precip for Corn Belt states
    warehouse/
      raw/                 -- raw scraper output, no transformations
        futures_corn_daily.csv
        weather_corn_belt_daily.csv
```

## Rules
- Before writing or refactoring any code, read `docs/coding_guidelines.md` and follow every rule.
- All scraper configuration lives in `etl/config.yaml`. Do not hardcode dates, tickers, URLs, or file paths in scripts.
- Python 3.11.7 via Anaconda (`/opt/anaconda3/bin/python`).
- Open-Meteo free tier: 600 calls/min, 10k/day, 300k/month. Always sleep between API calls per config.
