# TODO -- Crop Yield Trading Strategy Platform

## Phase 1: ETL Foundation
- [x] Refactor corn_futures.py -> yahoo_finance.py (multi-ticker from config)
- [x] Refactor weather.py -> open_meteo.py (multi-location from config)
- [x] Update config.yaml to list multiple tickers (ZC=F corn, ZS=F soybeans, ZW=F wheat)
- [x] Switch raw storage: SQLite warehouse + immutable CSV landing zone
- [x] Incremental scraping: only fetch new days since last DB entry
- [x] Create etl/db.py centralized database manager
- [x] Update signal_gen.py to read from SQLite instead of CSV
- [x] Add data validation step: null checks, range checks, anomaly detection

## Phase 2: Feature Store
- [x] Design feature store schema (name, ticker, source, category, frequency, description, staleness)
- [x] Create features/ directory with Parquet files per feature set
- [x] Build feature registry (YAML manifest with tickers, features, ticker-feature map, unlinked features)
- [x] Implement compute modules (momentum, mean_reversion, weather) with config-driven dispatch
- [x] Implement incremental pipeline (append new rows) and full rebuild
- [x] Add DuckDB query layer over Parquet files
- [ ] Move signal_gen.py feature engineering into feature store pipeline
- [ ] Add feature quality checks (staleness, coverage, drift detection)

## Phase 3: Strategy Framework
- [x] Define standard strategy interface (generate_signal function signature)
- [x] Create strategies/ directory
- [x] Implement weather-based strategy (refactor existing signal_gen.py)
- [ ] Implement momentum strategy (e.g., moving average crossover)
- [ ] Implement mean reversion strategy (e.g., Bollinger band breakout)
- [ ] Each strategy reads from feature store, outputs signal DataFrame

## Phase 4: Backtest Engine Enhancements
- [x] Add configurable transaction cost parameter (default 0, user-settable %)
- [x] Add optional position sizing (toggle: binary all-in vs 1-2% risk per trade)
- [x] Add best/worst trade to summary stats
- [x] Ensure backtest works with any strategy that follows the standard interface
- [x] Keep $100M as default allocation, make it user-configurable

## Phase 5a: Streamlit Skeleton (Deploy Locally)
- [x] Create app/ directory structure (app/__init__.py, app/pages/__init__.py)
- [x] Build strategy auto-discovery module (app/discovery.py)
- [x] Create app entry point with sidebar branding (app/main.py)
- [x] Add placeholder Strategy Dashboard page (app/pages/1_Strategy_Dashboard.py)
- [x] Add placeholder Data Explorer page (app/pages/2_Data_Explorer.py)
- [x] Update CLAUDE.md project structure with app/ entries
- [x] Verify: `streamlit run app/main.py` loads, sidebar shows both pages

## Phase 5b: Strategy Dashboard
- [x] Add Sortino, Calmar, VaR 95%, CVaR 95% to backtest compute_stats()
- [x] Create strategies/analytics.py (rolling Sharpe, rolling win rate, monthly returns, drawdown periods)
- [x] Create app/charts.py with Plotly chart builders (equity curve, drawdown, price+signals, heatmap, histogram, rolling metrics)
- [x] Build full Strategy Dashboard page (sidebar controls, summary stats, 7 chart types, trade log table)
- [ ] Verify: run Weather Precipitation backtest, all metrics and charts render interactively

## Phase 5c: Data Explorer + Cloud Deployment
- [ ] Add price_chart and feature_time_series to app/charts.py
- [ ] Build full Data Explorer page (price data, feature explorer, weather data sections)
- [ ] Deploy to Streamlit Community Cloud (free, from GitHub repo)
- [ ] Add secrets management for any API keys (future AI features)
- [ ] Verify public URL works, app sleeps/wakes correctly

## Future Enhancements (not in current scope)
- [ ] Multi-strategy comparison (side-by-side backtest results)
- [ ] AI strategy extraction from research papers
- [ ] Cross-asset backtesting (strategies spanning multiple tickers)
- [ ] Intraday data support
- [ ] Walk-forward optimization
- [ ] Scenario analysis (inflation shock, drought, etc.)
