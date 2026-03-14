"""Tests for app modules: strategy discovery, chart builders, trade analyst, imports."""

import pandas as pd
import plotly.graph_objects as go

from app.discovery import discover_strategies, get_strategy_metadata, sync_strategies_to_db
from app.trade_analyst import select_notable_trades, build_trade_context
from etl.db import get_connection, init_tables, list_strategies
from strategies import analytics


CAPITAL = 100_000_000


class TestDiscovery:
    """Verify strategy auto-discovery."""

    def test_discover_strategies(self):
        """Returns a non-empty dict including Weather Precipitation."""
        strategies = discover_strategies()
        assert isinstance(strategies, dict)
        assert len(strategies) > 0
        assert "Weather Precipitation" in strategies

    def test_discovered_strategy_has_generate_signal(self):
        """Every discovered module has a callable generate_signal."""
        strategies = discover_strategies()
        for name, module in strategies.items():
            assert callable(getattr(module, "generate_signal", None)), (
                f"{name} missing callable generate_signal"
            )

    def test_discover_includes_new_strategies(self):
        """Sma Crossover and Momentum Rsi are discovered."""
        strategies = discover_strategies()
        assert "Sma Crossover" in strategies
        assert "Momentum Rsi" in strategies

    def test_strategy_metadata(self):
        """get_strategy_metadata returns dict with description, summary, parameters."""
        strategies = discover_strategies()
        for name, module in strategies.items():
            meta = get_strategy_metadata(module)
            assert isinstance(meta, dict)
            assert "description" in meta
            assert "summary" in meta
            assert "parameters" in meta

    def test_strategy_features_metadata(self):
        """Every strategy has ticker_categories and unlinked in FEATURES."""
        strategies = discover_strategies()
        for name, module in strategies.items():
            meta = get_strategy_metadata(module)
            assert "features" in meta
            features = meta["features"]
            assert features is not None, f"{name} missing FEATURES"
            assert "ticker_categories" in features, f"{name} missing ticker_categories"
            assert "unlinked" in features, f"{name} missing unlinked"

    def test_sync_strategies_to_db(self):
        """sync_strategies_to_db populates the strategies table with all 3 strategies."""
        conn = get_connection()
        init_tables(conn)
        strategies = sync_strategies_to_db(conn)
        rows = list_strategies(conn)
        conn.close()

        assert len(strategies) == 3
        assert len(rows) == 3
        db_names = {row["name"] for row in rows}
        assert "Weather Precipitation" in db_names
        assert "Sma Crossover" in db_names
        assert "Momentum Rsi" in db_names


class TestCharts:
    """Verify chart functions return Plotly Figures."""

    def test_chart_equity_curve(self, backtest_result):
        """equity_curve returns a Plotly Figure."""
        from app.charts import equity_curve
        result_df, _, _ = backtest_result
        fig = equity_curve(result_df, CAPITAL)
        assert isinstance(fig, go.Figure)

    def test_chart_price_with_signals(self, backtest_result):
        """price_with_signals returns a Plotly Figure."""
        from app.charts import price_with_signals
        result_df, trade_log, _ = backtest_result
        fig = price_with_signals(result_df, trade_log)
        assert isinstance(fig, go.Figure)

    def test_chart_drawdown(self, backtest_result):
        """drawdown_chart returns a Plotly Figure."""
        from app.charts import drawdown_chart
        result_df, _, _ = backtest_result
        fig = drawdown_chart(result_df)
        assert isinstance(fig, go.Figure)

    def test_chart_price_chart(self, corn_prices):
        """price_chart returns a Plotly Figure."""
        from app.charts import price_chart
        fig = price_chart(corn_prices, "Corn")
        assert isinstance(fig, go.Figure)

    def test_chart_return_distribution(self, backtest_result):
        """return_distribution returns a Plotly Figure."""
        from app.charts import return_distribution
        result_df, _, stats = backtest_result
        fig = return_distribution(result_df, stats["var_95"])
        assert isinstance(fig, go.Figure)

    def test_chart_monthly_heatmap(self, backtest_result):
        """monthly_return_heatmap returns a Plotly Figure."""
        from app.charts import monthly_return_heatmap
        result_df, _, _ = backtest_result
        mr = analytics.monthly_returns(result_df, CAPITAL)
        fig = monthly_return_heatmap(mr)
        assert isinstance(fig, go.Figure)

    def test_chart_rolling_sharpe(self, backtest_result):
        """rolling_sharpe_chart returns a Plotly Figure."""
        from app.charts import rolling_sharpe_chart
        result_df, _, _ = backtest_result
        rs = analytics.rolling_sharpe(result_df)
        fig = rolling_sharpe_chart(rs)
        assert isinstance(fig, go.Figure)


class TestTradeAnalyst:
    """Verify trade analyst helper functions."""

    def _make_trade_log(self, pnls):
        """Build a minimal trade log DataFrame from a list of P&L values."""
        rows = []
        for i, pnl in enumerate(pnls):
            entry_price = 400.0
            exit_price = entry_price + pnl / 100.0
            rows.append({
                "entry_date": pd.Timestamp("2025-01-01") + pd.Timedelta(days=i * 10),
                "exit_date": pd.Timestamp("2025-01-01") + pd.Timedelta(days=i * 10 + 5),
                "direction": "long",
                "entry_price": entry_price,
                "exit_price": exit_price,
                "units": 100.0,
                "pnl": pnl,
                "pnl_per_unit": pnl / 100.0,
                "holding_days": 5,
            })
        return pd.DataFrame(rows)

    def test_select_notable_trades(self):
        """Returns 4 trades (2 best, 2 worst) with labels and pct_change."""
        trade_log = self._make_trade_log([100, -200, 300, -50, 150, -100])
        notable = select_notable_trades(trade_log, n=2)

        assert len(notable) == 4
        assert "label" in notable.columns
        assert "pct_change" in notable.columns

        labels = notable["label"].tolist()
        assert "Best Trade #1" in labels
        assert "Best Trade #2" in labels
        assert "Worst Trade #1" in labels
        assert "Worst Trade #2" in labels

        # Best trades should have highest P&L
        best1 = notable[notable["label"] == "Best Trade #1"].iloc[0]
        assert best1["pnl"] == 300

        # Worst trades should have lowest P&L
        worst1 = notable[notable["label"] == "Worst Trade #1"].iloc[0]
        assert worst1["pnl"] == -200

    def test_select_notable_trades_few(self):
        """Handles fewer than 4 trades without duplicates."""
        trade_log = self._make_trade_log([100, -50])
        notable = select_notable_trades(trade_log, n=2)

        assert len(notable) == 2
        labels = notable["label"].tolist()
        assert "Best Trade #1" in labels

    def test_select_notable_trades_empty(self):
        """Returns empty DataFrame for empty trade log."""
        trade_log = pd.DataFrame()
        notable = select_notable_trades(trade_log)

        assert notable.empty

    def test_build_trade_context(self):
        """Context string includes ticker, commodity, buy/sell language, and trade details."""
        trade_log = self._make_trade_log([500, -300, 200, -100])
        notable = select_notable_trades(trade_log, n=2)
        context = build_trade_context(notable, "ZC=F", "Corn")

        assert "ZC=F" in context
        assert "Corn" in context
        assert "Best Trade #1" in context
        assert "Worst Trade #1" in context
        assert "Bought" in context
        assert "Sold" in context
        assert "$" in context


class TestModuleImports:
    """Verify app dependency modules import without error."""

    def test_app_modules_importable(self):
        """app.discovery, app.charts, app.catalog_agent, app.trade_analyst import cleanly."""
        import app.discovery
        import app.charts
        import app.catalog_agent
        import app.trade_analyst

        assert app.discovery is not None
        assert app.charts is not None
        assert app.catalog_agent is not None
        assert app.trade_analyst is not None
