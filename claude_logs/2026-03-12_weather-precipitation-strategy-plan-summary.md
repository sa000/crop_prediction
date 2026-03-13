# Weather Precipitation Strategy — Summary

## Goal
Build a long-only weather-driven corn futures strategy using Corn Belt precipitation anomalies, with a proper dollar P&L backtest engine.

## What was built

1. **Corn Belt aggregate feature** — averages weather features across Iowa, Illinois, Nebraska into `features/weather/corn_belt.parquet` (5,913 rows). Config-driven via `aggregations` block in `features/config.yaml`.

2. **Backtest engine** (`strategies/backtest.py`) — moved from `eda/`, upgraded with equity-based position sizing (1% risk per trade), dollar P&L tracking, and comprehensive stats (Sharpe, drawdown, profit factor, streaks, etc.).

3. **Weather precipitation strategy** (`strategies/weather_precipitation.py`) — goes long on drought (z < -1.0) or flood (z > +1.5) precipitation anomalies. Both extremes threaten corn supply.

4. **Verification notebook** (`strategies/weather_strategy_2025.ipynb`) — full pipeline with stats summary, transaction log, equity curve, price+signal overlay, and drawdown chart. Visuals saved to `strategies/visuals/`.

## 2025 Backtest Results
- 297 trading days, 14 trades, 50% win rate
- Total P&L: -$36K (-0.04% return on $100M)
- Sharpe: -0.62, max drawdown: -$83K (-0.08%)
- Signal fires ~5% of the time (mostly flat)

## Cleanup
- Removed `eda/backtest.py`, `eda/backtest_walkthrough.ipynb`, `eda/backtest_visuals/`
- Updated CLAUDE.md project structure
