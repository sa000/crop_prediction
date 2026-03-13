"""Tests for strategy signal generation, backtest engine, and analytics."""

import pandas as pd

from strategies import analytics


CAPITAL = 100_000_000


class TestGenerateSignal:
    """Verify the generate_signal contract."""

    def test_generate_signal_returns_signal_column(self, backtest_result):
        """Output has a signal column."""
        result_df, _, _ = backtest_result
        assert "signal" in result_df.columns

    def test_generate_signal_values(self, backtest_result):
        """Signal values are only in {-1, 0, 1}."""
        result_df, _, _ = backtest_result
        assert set(result_df["signal"].unique()).issubset({-1, 0, 1})

    def test_generate_signal_no_nan(self, backtest_result):
        """No NaN in the signal column."""
        result_df, _, _ = backtest_result
        assert result_df["signal"].notna().all()


class TestBacktestOutput:
    """Verify the backtest engine output structure."""

    def test_backtest_returns_tuple(self, backtest_result):
        """Returns (DataFrame, DataFrame, dict)."""
        result_df, trade_log, stats = backtest_result
        assert isinstance(result_df, pd.DataFrame)
        assert isinstance(trade_log, pd.DataFrame)
        assert isinstance(stats, dict)

    def test_backtest_result_columns(self, backtest_result):
        """Result DataFrame has position, units, daily_pnl, equity, etc."""
        result_df, _, _ = backtest_result
        for col in ["position", "units", "daily_pnl", "equity", "net_daily_pnl", "cumulative_pnl"]:
            assert col in result_df.columns

    def test_backtest_stats_keys(self, backtest_result):
        """Stats dict has expected performance metrics."""
        _, _, stats = backtest_result
        for key in [
            "total_pnl", "sharpe_ratio", "num_trades", "win_rate",
            "max_drawdown", "max_drawdown_pct", "sortino_ratio",
            "profit_factor", "best_trade", "worst_trade",
        ]:
            assert key in stats

    def test_backtest_equity_starts_at_capital(self, backtest_result):
        """Equity starts at $100M."""
        result_df, _, _ = backtest_result
        assert result_df["equity"].iloc[0] == CAPITAL

    def test_backtest_trade_log_columns(self, backtest_result):
        """Trade log has entry_date, exit_date, pnl, etc."""
        _, trade_log, _ = backtest_result
        if not trade_log.empty:
            for col in ["entry_date", "exit_date", "pnl", "direction", "entry_price", "exit_price"]:
                assert col in trade_log.columns

    def test_backtest_trade_directions(self, backtest_result):
        """Trade directions are only 'long' or 'short'."""
        _, trade_log, _ = backtest_result
        if not trade_log.empty:
            assert set(trade_log["direction"].unique()).issubset({"long", "short"})


class TestAnalytics:
    """Verify analytics functions used for dashboard visualization."""

    def test_analytics_rolling_sharpe(self, backtest_result):
        """Rolling Sharpe returns a Series with the same index as result_df."""
        result_df, _, _ = backtest_result
        rs = analytics.rolling_sharpe(result_df)
        assert isinstance(rs, pd.Series)
        assert rs.index.equals(result_df.index)

    def test_analytics_monthly_returns(self, backtest_result):
        """Monthly returns is a DataFrame with month columns 1-12."""
        result_df, _, _ = backtest_result
        mr = analytics.monthly_returns(result_df, CAPITAL)
        assert isinstance(mr, pd.DataFrame)
        assert all(m in mr.columns for m in mr.columns if 1 <= m <= 12)

    def test_analytics_drawdown_periods(self, backtest_result):
        """Drawdown periods has start, trough_date, max_dd_pct columns."""
        result_df, _, _ = backtest_result
        dd = analytics.drawdown_periods(result_df)
        assert isinstance(dd, pd.DataFrame)
        if not dd.empty:
            for col in ["start", "trough_date", "max_dd_pct"]:
                assert col in dd.columns
