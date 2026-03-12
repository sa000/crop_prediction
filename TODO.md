# TODO -- Crop Yield Trading Strategy Platform

## Phase 1: ETL Foundation
- [x] Refactor corn_futures.py -> yahoo_finance.py (multi-ticker from config)
- [x] Refactor weather.py -> open_meteo.py (multi-location from config)
- [x] Update config.yaml to list multiple tickers (ZC=F corn, ZS=F soybeans, ZW=F wheat)
- [x] Switch raw storage: SQLite warehouse + immutable Parquet landing zone
- [x] Incremental scraping: only fetch new days since last DB entry
- [x] Create etl/db.py centralized database manager
- [x] Update signal_gen.py to read from SQLite instead of CSV
- [ ] Add data validation step: null checks, range checks, anomaly detection

## Phase 2: Feature Store
- [ ] Design feature store schema (name, ticker, source, category, frequency, description, staleness)
- [ ] Create features/ directory with Parquet files per feature set
- [ ] Build feature registry (YAML or JSON manifest listing all available features)
- [ ] Move signal_gen.py feature engineering into feature store pipeline
- [ ] Add feature quality checks (staleness, coverage, drift detection)

## Phase 3: Strategy Framework
- [ ] Define standard strategy interface (generate_signal function signature)
- [ ] Create strategies/ directory
- [ ] Implement weather-based strategy (refactor existing signal_gen.py)
- [ ] Implement momentum strategy (e.g., moving average crossover)
- [ ] Implement mean reversion strategy (e.g., Bollinger band breakout)
- [ ] Each strategy reads from feature store, outputs signal DataFrame

## Phase 4: Backtest Engine Enhancements
- [ ] Add configurable transaction cost parameter (default 0, user-settable %)
- [ ] Add optional position sizing (toggle: binary all-in vs 1-2% risk per trade)
- [ ] Add best/worst trade to summary stats
- [ ] Ensure backtest works with any strategy that follows the standard interface
- [ ] Keep $100M as default allocation, make it user-configurable

## Phase 5: Streamlit Web App (Local)
- [ ] Create app/ directory with main Streamlit app
- [ ] Strategy selection dropdown (auto-discovers strategies from strategies/)
- [ ] Parameter inputs (allocation, transaction cost, position sizing toggle, date range)
- [ ] "Run Backtest" button that calls backtest engine
- [ ] Results dashboard: P&L chart, drawdown, daily P&L bars, trade log table
- [ ] Summary stats card (total P&L, Sharpe, max drawdown, win rate, best/worst trade)

## Phase 6: Deployment
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
