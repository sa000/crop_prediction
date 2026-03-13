"""Tests for app modules: strategy discovery, chart builders, imports."""

import plotly.graph_objects as go

from app.discovery import discover_strategies, get_strategy_metadata
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
        """Every strategy's metadata has a features key."""
        strategies = discover_strategies()
        for name, module in strategies.items():
            meta = get_strategy_metadata(module)
            assert "features" in meta


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


class TestModuleImports:
    """Verify app dependency modules import without error."""

    def test_app_modules_importable(self):
        """app.discovery, app.charts, app.catalog_agent import cleanly."""
        import app.discovery
        import app.charts
        import app.catalog_agent

        assert app.discovery is not None
        assert app.charts is not None
        assert app.catalog_agent is not None
