# Backtest Robustness Analysis (Stress Test) — Summary

## Goal

Add a Stress Test page that answers: "Is this backtest result robust, or did we get lucky?" Uses techniques from *Advances in Financial Machine Learning* (López de Prado, Ch 11-14).

## Phased Approach

Implement one technique at a time, review and iterate before moving on.

| Phase | Technique | Description |
|-------|-----------|-------------|
| **1** | Monte Carlo Noise Injection | Add noise to log returns, re-run strategy on 200 synthetic paths, show Sharpe distribution + equity fan chart |
| 2 | Trade Bootstrap | Reshuffle trade P&Ls, test if drawdown/P&L are path-dependent |
| 3 | Regime Analysis | Split performance by high-vol vs low-vol periods |
| 4 | Sharpe Significance (PSR/DSR) | Statistical test for Sharpe > 0, adjusted for multiple testing |

## Phase 1 Files

| File | Change |
|------|--------|
| `strategies/robustness.py` | **NEW** — `generate_noisy_prices()`, `run_monte_carlo()` |
| `app/pages/3_Stress_Test.py` | **NEW** — Streamlit page with MC controls + results |
| `app/charts.py` | 2 new charts: `sharpe_distribution_chart`, `equity_fan_chart` |
| `app/discovery.py` | Exclude robustness.py from strategy list |
| `app/main.py` | Add Stress Test card to landing page |
| `tests/test_data_pipeline.py` | 4 new tests for MC + charts |

## Performance

200 MC paths < 1 second. Full page load < 5 seconds.
