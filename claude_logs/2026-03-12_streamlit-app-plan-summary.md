# Streamlit Web App -- Plan Summary

## Three Milestones

### Milestone 1: Bare-Bones Skeleton
- Create `app/` directory structure (`__init__.py`, `pages/__init__.py`)
- `app/discovery.py` -- strategy auto-discovery from `strategies/`
- `app/main.py` -- entry point with sidebar branding
- Placeholder pages for Strategy Dashboard and Data Explorer
- Verify: `streamlit run app/main.py` loads, sidebar shows both pages

### Milestone 2: Strategy Dashboard
- Add Sortino, Calmar, VaR, CVaR to `strategies/backtest.py`
- Create `strategies/analytics.py` -- rolling Sharpe, win rate, monthly returns, drawdown periods
- Create `app/charts.py` -- Plotly chart builders (equity curve, drawdown, heatmap, etc.)
- Full `1_Strategy_Dashboard.py` -- sidebar controls, summary stats, 7 chart types, trade log
- Verify: run Weather Precipitation backtest, all metrics and charts render interactively

### Milestone 3: Data Explorer + Deployment
- Add price chart and feature time series chart builders to `app/charts.py`
- Full `2_Data_Explorer.py` -- price data, feature explorer, weather data sections
- Deploy to Streamlit Community Cloud
- Verify: public URL works, app sleeps/wakes correctly

## Files Touched (10 total)
- Modified: `strategies/backtest.py`, `CLAUDE.md`
- Created: `strategies/analytics.py`, `app/__init__.py`, `app/pages/__init__.py`, `app/discovery.py`, `app/charts.py`, `app/main.py`, `app/pages/1_Strategy_Dashboard.py`, `app/pages/2_Data_Explorer.py`
