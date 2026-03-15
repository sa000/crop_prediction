# Crop Yield Trading Strategy Platform — Project Overview

## Purpose

This is a proof-of-concept platform for backtesting agricultural commodity futures trading strategies driven by weather and market data. The core hypothesis: **anomalous precipitation in the US Corn Belt creates supply shocks that move corn futures prices in predictable ways**. Both drought and flood conditions threaten crop yields and are bullish for prices; normal weather means no supply threat and prices drift or fall.

The broader vision is a multi-asset, multi-strategy platform where trading signals — including AI-extracted signals from research papers — can be rapidly prototyped, backtested, and compared through a web dashboard called **Cortex**.

## Architecture — The Five Layers

Data flows through five distinct layers, each building on the previous one:

```
[1. Scrapers] → [2. Landing Zone] → [3. Validated Warehouse] → [4. Feature Store] → [5. Strategies + Backtest]
                                                                                            ↓
                                                                                    [Streamlit Web App]
```

### Layer 1: Data Ingestion (Scrapers)

Two scrapers pull raw data daily:

- **Yahoo Finance** (`etl/scrapers/yahoo_finance.py`): Daily OHLCV futures prices for corn (ZC=F), soybeans (ZS=F), and wheat (ZW=F). Uses the `yfinance` library. Data goes back to 2010.
- **Open-Meteo** (`etl/scrapers/open_meteo.py`): Daily temperature (max/min) and precipitation for three Corn Belt locations — Iowa (41.59°N, 93.62°W), Illinois (39.80°N, 89.64°W), and Nebraska (40.81°N, 96.70°W). Free API tier with rate limits (600 calls/min).

Both scrapers are incremental: they only fetch new days since the last entry. All configuration (tickers, locations, API URLs, date ranges) lives in `etl/scrapers/config.yaml` — nothing is hardcoded.

### Layer 2: Landing Zone (Immutable Audit Trail)

Raw scraper output is written to CSV files in `warehouse/landing/`. These files are **never modified or deleted** — they serve as a permanent audit trail. Directory structure:

```
warehouse/landing/
  yahoo_finance/
    corn/          ← one CSV per scrape run
    soybeans/
    wheat/
  open_meteo/
    corn_belt/
      iowa/
      illinois/
      nebraska/
```

### Layer 3: Validated Warehouse (SQLite)

Between landing and consumption, data passes through a **validation pipeline** (`etl/validate.py`) with configurable checks defined in `etl/pipeline.yaml`:

- **Generic checks**: null detection, standard deviation outliers, date continuity, non-negative values
- **Futures-specific**: high >= low, close within daily range
- **Weather-specific**: temp_max >= temp_min

Rows failing error-severity checks are **rejected**; warnings are logged but the data is inserted. Only validated data enters the SQLite warehouse.

There are **two SQLite databases** in `warehouse/`:

| Database | Purpose | Rebuildable? |
|----------|---------|-------------|
| `warehouse.db` | Data + catalogs: `futures_daily`, `weather_daily`, `validation_log`, `strategies`, `data_catalog`, `feature_catalog` | Yes — `--rebuild` deletes and recreates from landing CSVs |
| `app.db` | Application state: `shared_analyses`, `backtest_runs`, `ai_usage` | No — permanent, never rebuilt |

All database access goes through a centralized module (`etl/db.py`). No other code creates SQLite connections directly.

### Layer 4: Feature Store (Parquet + DuckDB)

The feature store transforms raw warehouse data into engineered features for strategy consumption. It uses **Parquet** as its storage format and **DuckDB** for queries.

**Feature categories and what they compute:**

| Category | Source | Entity | Features |
|----------|--------|--------|----------|
| **Momentum** | `futures_daily` | Per ticker (corn, soybeans, wheat) | SMA-20, SMA-50, EMA-12, EMA-26, MACD, MACD Signal, RSI-14 |
| **Mean Reversion** | `futures_daily` | Per ticker | Bollinger Upper/Lower, Z-Score (20d, 50d), Percentile Rank (20d) |
| **Weather** | `weather_daily` | Per state (Iowa, Illinois, Nebraska) + aggregated `corn_belt` | Precip 7d/30d rolling sum, temp rolling means, temp range, **precip anomaly z-score (30d)** |

Key design decisions:
- Feature definitions live in `features/config.yaml` — add a compute function + config entry to add a feature.
- Compute modules (`features/compute/`) are **pure functions with no I/O**. Each exposes a `FUNCTIONS` dict for dispatch.
- Each entity gets one Parquet file per category (e.g., `features/momentum/corn.parquet`).
- `features/registry.yaml` is auto-generated and contains all tickers, all features with metadata, and ticker-feature mappings.
- Supports incremental updates (append new rows) and full rebuilds.
- Consumers query via `features/query.py` (DuckDB SQL over Parquet) or read Parquet directly.

### Layer 5: Strategies + Backtest Engine

**Strategy Interface:**
Every strategy is a single Python file in `strategies/` that exposes:
- `generate_signal(df)` → returns DataFrame with a `signal` column: +1 (long), -1 (short), or 0 (flat)
- `FEATURES` dict declaring which feature store categories/entities it needs
- `SUMMARY` string describing the strategy logic

Strategies read **only from the feature store**, never from raw data.

**Implemented Strategy — Weather Precipitation (`strategies/weather_precipitation.py`):**

Uses the 30-day precipitation anomaly z-score for the Corn Belt aggregate:
- z < -1.0 → **Long** (drought = supply threat = bullish)
- -0.3 < z < 0.3 → **Short** (normal weather = no supply threat = bearish)
- z > 1.5 → **Long** (flood = supply threat = bullish)
- Everything else → **Flat** (ambiguous zones)

The asymmetry is intentional: corn is more drought-sensitive, so the drought threshold is tighter (-1σ) than the flood threshold (+1.5σ).

**Backtest Engine (`strategies/backtest.py`):**
- Default starting capital: $100M (user-configurable)
- Position sizing: allocates `risk_pct` (default 1%) of current equity per trade
- Transaction costs: configurable dollar cost per position change (default $0)
- Outputs: daily P&L, cumulative P&L, equity curve, trade log
- **Risk metrics**: Sharpe ratio, Sortino ratio, Calmar ratio, max drawdown, VaR 95%, CVaR 95%, profit factor, win rate, best/worst trade, win/loss streaks, average holding period

## Web Application (Streamlit — "Cortex")

The platform has a Streamlit web app deployed to **Streamlit Community Cloud** (trexquant-sakibul.streamlit.app). Five pages:

1. **Strategy Backtester** — Run backtests with configurable parameters, view equity curves, drawdown charts, price overlays with signal markers, monthly return heatmaps, P&L histograms, rolling metrics, and a full trade log table.

2. **Strategy Leaderboard** — Persistent record of all backtest runs. Filter, sort, compare, and star top performers. Results are saved to `app.db`.

3. **Data Explorer** — Browse raw price data, weather data, and engineered features. Includes an **AI-powered feature catalog agent** (Claude Haiku) that answers natural-language questions about available features.

4. **Paper Upload** — A 5-step pipeline to extract trading strategies from research papers:
   - Upload PDF/text
   - AI extracts a strategy specification (using DeepSeek)
   - AI maps required features to the available data catalog
   - AI generates runnable Python strategy code
   - User reviews and saves the strategy

5. **AI Usage** — Dashboard tracking API costs, token consumption, and call history across Claude and DeepSeek models.

Strategy selection in the app uses **auto-discovery** — it scans the `strategies/` directory at runtime, so adding a new strategy file automatically makes it available in the UI.

## AI Integrations

The platform uses three AI models for different purposes:

| Model | Purpose | Module |
|-------|---------|--------|
| **Claude Haiku** | Feature catalog Q&A agent (structured JSON responses) | `app/catalog_agent.py` |
| **Claude Sonnet** | Trade post-mortem analysis with web search | `app/trade_analyst.py` |
| **DeepSeek** | Paper-to-strategy pipeline (extraction, mapping, code generation) | `app/paper_agent/` |

All AI API usage is tracked in `app.db` for cost monitoring.

## Tech Stack

| Component | Technology |
|-----------|------------|
| Language | Python 3.11.7 (Anaconda) |
| Data manipulation | pandas, NumPy |
| Databases | SQLite (warehouse + app state), DuckDB (feature queries) |
| Feature storage | Parquet |
| Market data | yfinance |
| Weather data | Open-Meteo API (free tier) |
| Visualization | Plotly (app), matplotlib (notebooks) |
| Web app | Streamlit |
| AI models | Claude (Haiku, Sonnet), DeepSeek |
| Deployment | Streamlit Community Cloud |
| Testing | pytest (real data, no mocks) |

## Current State

**Completed:**
- Full ETL pipeline with validation (Phase 1)
- Feature store with momentum, mean reversion, and weather features (Phase 2)
- Strategy framework with weather precipitation strategy (Phase 3)
- Backtest engine with comprehensive risk metrics (Phase 4)
- Complete Streamlit app with all 5 pages (Phase 5)
- AI integrations (catalog agent, trade analyst, paper-to-strategy pipeline)
- Cloud deployment

**Remaining / Planned:**
- Momentum strategy (moving average crossover)
- Mean reversion strategy (Bollinger band breakout)
- Feature quality checks (staleness, coverage, drift detection)
- Multi-strategy comparison (side-by-side backtest results)
- Cross-asset backtesting (strategies spanning multiple tickers)
- Walk-forward optimization
- Scenario analysis (drought, inflation shocks)
- Intraday data support

## How to Run

```bash
# Scrape latest data
python -m etl.scrapers.yahoo_finance
python -m etl.scrapers.open_meteo

# Rebuild warehouse from landing files
python -m etl.run_pipeline --rebuild

# Rebuild feature store
python -m features.pipeline --rebuild

# Launch the web app
streamlit run app/main.py

# Run tests
python -m pytest tests/ -v
```

## Key Design Principles

1. **Config-driven**: All tickers, locations, features, and validation rules are defined in YAML configs, not hardcoded.
2. **Immutable audit trail**: Raw data is never modified. Landing CSVs are permanent.
3. **Separation of concerns**: Scrapers → Validation → Warehouse → Features → Strategies → Backtest. Each layer has a clear boundary.
4. **Pure compute**: Feature compute modules have no I/O side effects. They take DataFrames in and return DataFrames out.
5. **Standard interfaces**: Every strategy exposes the same `generate_signal()` signature, making them pluggable.
6. **Two-database split**: Rebuildable data (warehouse.db) is separate from permanent app state (app.db).
7. **Real data testing**: Tests run against the actual warehouse and Parquet files, not mocks.
