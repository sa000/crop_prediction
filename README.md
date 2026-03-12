# Crop Yield Trading Strategy Platform

## Overview

A proof-of-concept platform for backtesting agricultural commodity futures strategies driven by weather data. The core hypothesis: anomalous precipitation in the US Corn Belt creates supply shocks that move corn futures prices in predictable ways.

The platform currently supports corn futures with Corn Belt precipitation data, a weather-based trading signal, and a backtest engine that produces P&L curves, drawdown analysis, and trade-level statistics. The broader vision is a multi-asset, multi-strategy platform where strategies -- including AI-extracted signals from research papers -- can be rapidly prototyped, backtested, and compared through a web dashboard.

## Architecture

Data flows through four stages:

1. **ETL scrapers** pull raw market data (Yahoo Finance) and weather data (Open-Meteo) into the raw warehouse as Parquet files.
2. **Feature engineering** merges datasets, computes rolling/lagged features, and writes them to a feature store with metadata.
3. **Strategies** consume features and produce a signal DataFrame (long/short/flat per day).
4. **Backtest engine** takes signals, simulates trading with configurable costs and position sizing, and outputs P&L metrics.

A Streamlit web app will tie these together, letting users select strategies, tune parameters, run backtests, and view results interactively.

## Project Structure

```
crop_prediction/
  README.md
  CLAUDE.md
  TODO.md
  docs/
    coding_guidelines.md       -- coding standards for all code changes
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
    corn_weather_eda.ipynb     -- exploratory data analysis notebook
    backtest_walkthrough.ipynb -- full backtest walkthrough with visuals
    backtest_visuals/          -- saved charts from backtest analysis
  strategies/                  -- (planned) one file per strategy, standard interface
  features/                    -- (planned) feature store with Parquet files
  app/                         -- (planned) Streamlit web application
```

## Quick Start

**Prerequisites**: Python 3.11 (Anaconda), plus packages: `pandas`, `numpy`, `yfinance`, `requests`, `pyyaml`, `matplotlib`, `plotly`.

**Run the scrapers** to pull raw data:

```bash
python etl/scrapers/corn_futures.py
python etl/scrapers/weather.py
```

**Run a backtest** interactively via the walkthrough notebook:

```bash
jupyter notebook eda/backtest_walkthrough.ipynb
```

Or use the modules directly in Python:

```python
from eda.signal_gen import build_signal_dataframe
from eda.backtest import run_backtest

df = build_signal_dataframe(threshold_long=4.5, threshold_short=1.5)
results, trade_log, stats = run_backtest(df)
```

## Strategies

**Weather-based (implemented)**: Generates long/short signals from 30-day rolling precipitation across Iowa, Illinois, and Nebraska. High precipitation signals potential crop damage (bullish for corn prices); low precipitation signals normal supply conditions.

**Momentum (planned)**: Moving average crossover signals on corn futures prices.

**Mean reversion (planned)**: Bollinger band breakout signals for range-bound periods.

## Data

| Source | Dataset | Range | Frequency |
|--------|---------|-------|-----------|
| Yahoo Finance | Corn futures (ZC=F) OHLCV | 2010--present | Daily |
| Open-Meteo | Temp (max/min) + precipitation | 2010--present | Daily |

Weather data covers three Corn Belt states: Iowa, Illinois, and Nebraska. Date range and locations are configured in `etl/config.yaml`.

## Tech Stack

- **Language**: Python 3.11
- **Data**: pandas, NumPy, Parquet (planned primary format)
- **Visualization**: matplotlib, Plotly
- **Market data**: yfinance
- **Weather data**: Open-Meteo API (free tier)
- **Web app**: Streamlit (planned)
- **Notebooks**: Jupyter

## Deployment

**Local**:
```bash
streamlit run app/main.py
```

**Cloud**: Streamlit Community Cloud (free tier). Deploys directly from the GitHub repo, sleeps on inactivity, wakes on visit.

## Roadmap

See [TODO.md](TODO.md) for the phased development plan covering ETL improvements, feature store, strategy framework, backtest enhancements, Streamlit app, and cloud deployment.

## Future Vision

- AI-powered strategy extraction from agricultural research papers
- Cross-asset backtesting (soybeans, wheat, and other commodities)
- Walk-forward optimization and scenario analysis (drought, inflation shocks)
- Intraday data support
