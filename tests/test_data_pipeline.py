"""Tests for the data pipeline: DB tables, price loading, feature store, registry, robustness."""

import json

import pandas as pd
import plotly.graph_objects as go

from etl.db import (
    get_connection, init_tables,
    upsert_strategy, list_strategies, get_strategy,
    get_app_connection, init_app_tables,
    save_shared_analysis, load_shared_analysis,
    populate_data_catalog, list_data_catalog,
    populate_feature_catalog, list_feature_catalog,
)
from features import store
from features.query import read_parquet
from strategies.robustness import generate_noisy_prices, run_monte_carlo, run_bootstrap, compute_regime_stats


class TestDatabase:
    """Verify SQLite warehouse tables and data integrity."""

    def test_db_tables_exist(self, db_connection):
        """All expected warehouse tables exist in SQLite."""
        cursor = db_connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        tables = {row[0] for row in cursor.fetchall()}
        assert "futures_daily" in tables
        assert "weather_daily" in tables
        assert "validation_log" in tables
        assert "strategies" in tables
        assert "data_catalog" in tables
        assert "feature_catalog" in tables

    def test_load_prices_shape(self, corn_prices):
        """Corn prices are non-empty with expected columns and 1000+ rows."""
        assert not corn_prices.empty
        assert len(corn_prices) >= 1000
        for col in ["Open", "High", "Low", "Close", "Volume"]:
            assert col in corn_prices.columns
        assert isinstance(corn_prices.index, pd.DatetimeIndex)

    def test_load_prices_types(self, corn_prices):
        """OHLCV columns are numeric with no NaN in Close."""
        for col in ["Open", "High", "Low", "Close", "Volume"]:
            assert pd.api.types.is_numeric_dtype(corn_prices[col])
        assert corn_prices["Close"].notna().all()

    def test_load_prices_ohlc_invariant(self, corn_prices):
        """High >= Low for all rows; Close within [Low, High] for 99%+.

        Continuous futures can have minor OHLC violations at contract
        roll boundaries, so we allow up to 1% of rows to violate.
        """
        df = corn_prices.dropna(subset=["High", "Low", "Close"])
        assert (df["High"] >= df["Low"]).all()
        close_in_range = (df["Close"] >= df["Low"]) & (df["Close"] <= df["High"])
        violation_pct = (~close_in_range).sum() / len(df)
        assert violation_pct < 0.01, f"{violation_pct:.1%} of rows violate Close in [Low, High]"


class TestWeatherFeatures:
    """Verify weather feature store reads."""

    def test_weather_features_shape(self, weather_features):
        """Weather features are non-empty with 1000+ rows."""
        assert weather_features is not None
        assert not weather_features.empty
        assert len(weather_features) >= 1000

    def test_weather_features_columns(self, weather_features):
        """Expected columns are present."""
        assert "date" in weather_features.columns
        assert "precip_anomaly_30d" in weather_features.columns


class TestFeatureStore:
    """Verify feature store reads across categories."""

    def test_feature_store_read_momentum(self):
        """Momentum features for corn include sma_20 and rsi_14."""
        df = store.read_features("momentum", "corn")
        assert df is not None
        assert not df.empty
        assert "sma_20" in df.columns
        assert "rsi_14" in df.columns

    def test_feature_store_read_mean_reversion(self):
        """Mean reversion features for corn include bollinger_upper and zscore_20."""
        df = store.read_features("mean_reversion", "corn")
        assert df is not None
        assert not df.empty
        assert "bollinger_upper" in df.columns
        assert "zscore_20" in df.columns

    def test_feature_store_metadata(self):
        """Metadata has name, category, entity, description columns."""
        meta = store.read_metadata()
        assert not meta.empty
        for col in ["name", "category", "entity", "description"]:
            assert col in meta.columns


class TestRegistry:
    """Verify the feature registry structure."""

    def test_registry_structure(self, registry):
        """Registry is a populated dict with tickers, features, and files-related keys."""
        assert isinstance(registry, dict)
        assert "tickers" in registry
        assert "features" in registry
        assert len(registry["tickers"]) > 0
        assert len(registry["features"]) > 0


class TestQueryLayer:
    """Verify the DuckDB query layer over Parquet."""

    def test_query_read_parquet(self):
        """read_parquet returns the requested columns."""
        df = read_parquet("momentum", "corn", columns=["date", "sma_20"])
        assert not df.empty
        assert "date" in df.columns
        assert "sma_20" in df.columns

    def test_query_read_parquet_date_filter(self):
        """Date filtering returns a subset of the data."""
        df_all = read_parquet("momentum", "corn", columns=["date", "sma_20"])
        df_filtered = read_parquet(
            "momentum", "corn",
            columns=["date", "sma_20"],
            start_date="2020-01-01",
            end_date="2020-12-31",
        )
        assert not df_filtered.empty
        assert len(df_filtered) < len(df_all)


class TestStrategiesTable:
    """Verify the strategies table CRUD operations."""

    def test_strategies_table_exists(self, db_connection):
        """strategies table is in sqlite_master."""
        cursor = db_connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='strategies'"
        )
        assert cursor.fetchone() is not None

    def test_upsert_and_list_strategies(self, db_connection):
        """Round-trip insert and query of a strategy row."""
        upsert_strategy(
            db_connection,
            name="Test Strategy",
            module_name="strategies.test_strategy",
            description="A test strategy.",
            summary="Test summary.",
            features_config={"ticker_categories": ["momentum"], "unlinked": []},
            parameters={"THRESHOLD": 0.5},
        )
        row = get_strategy(db_connection, "Test Strategy")
        assert row is not None
        assert row["module_name"] == "strategies.test_strategy"
        assert row["summary"] == "Test summary."

        rows = list_strategies(db_connection)
        names = [r["name"] for r in rows]
        assert "Test Strategy" in names

        # Clean up
        db_connection.execute("DELETE FROM strategies WHERE name = 'Test Strategy'")
        db_connection.commit()


class TestSharedAnalyses:
    """Verify shared analyses save/load operations in app.db."""

    def test_shared_analyses_table_exists(self):
        """shared_analyses table exists in app.db."""
        conn = get_app_connection()
        init_app_tables(conn)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='shared_analyses'"
        )
        assert cursor.fetchone() is not None
        conn.close()

    def test_save_and_load_shared_analysis(self, backtest_result):
        """Round-trip save and load of a shared analysis."""
        conn = get_app_connection()
        init_app_tables(conn)
        result_df, trade_log, stats = backtest_result

        result_json = result_df.reset_index().to_json(orient="records", date_format="iso")
        trade_log_json = trade_log.to_json(orient="records", date_format="iso")
        safe_stats = {
            k: (1e18 if v == float("inf") else v)
            for k, v in stats.items()
        }
        stats_json = json.dumps(safe_stats)

        share_id = "test_abc12345"
        save_shared_analysis(
            conn, share_id,
            strategy_name="Weather Precipitation",
            ticker_symbol="ZC=F",
            ticker_name="Corn",
            capital=100_000_000,
            risk_pct=0.01,
            cost_per_trade=0.0,
            result_data=result_json,
            trade_log_data=trade_log_json,
            stats_data=stats_json,
        )

        row = load_shared_analysis(conn, share_id)
        assert row is not None
        assert row["strategy_name"] == "Weather Precipitation"
        assert row["ticker_symbol"] == "ZC=F"
        assert row["ticker_name"] == "Corn"
        assert row["capital"] == 100_000_000

        loaded_stats = json.loads(row["stats_data"])
        assert loaded_stats["num_trades"] == stats["num_trades"]

        # Clean up
        conn.execute("DELETE FROM shared_analyses WHERE id = ?", (share_id,))
        conn.commit()
        conn.close()

    def test_load_nonexistent_share(self):
        """Querying a fake share ID returns None."""
        conn = get_app_connection()
        init_app_tables(conn)
        result = load_shared_analysis(conn, "nonexistent_id")
        assert result is None
        conn.close()


class TestDataCatalog:
    """Verify data_catalog populate and list operations."""

    def test_populate_and_list(self, db_connection):
        """populate_data_catalog inserts entries that list_data_catalog returns."""
        count = populate_data_catalog(db_connection)
        assert count >= 3  # at least 3 futures tickers

        rows = list_data_catalog(db_connection)
        assert len(rows) >= 3
        # Check a futures entry exists
        futures_entries = [r for r in rows if r["source_type"] == "futures"]
        assert len(futures_entries) >= 1
        assert futures_entries[0]["provider"] == "Yahoo Finance"
        assert futures_entries[0]["row_count"] > 0

        # Check a weather entry exists
        weather_entries = [r for r in rows if r["source_type"] == "weather"]
        assert len(weather_entries) >= 1
        assert weather_entries[0]["provider"] == "Open-Meteo"


class TestFeatureCatalog:
    """Verify feature_catalog populate and list operations."""

    def test_populate_and_list(self, db_connection):
        """populate_feature_catalog round-trips metadata into the table."""
        from features import store
        metadata_df = store.read_metadata()
        assert not metadata_df.empty

        count = populate_feature_catalog(db_connection, metadata_df)
        assert count > 0

        rows = list_feature_catalog(db_connection)
        assert len(rows) == count

        # Filter by category
        momentum = list_feature_catalog(db_connection, category="momentum")
        assert len(momentum) > 0
        assert all(r["category"] == "momentum" for r in momentum)

        # Filter by entity
        corn = list_feature_catalog(db_connection, entity="corn")
        assert len(corn) > 0
        assert all(r["entity"] == "corn" for r in corn)


class TestRobustness:
    """Verify Monte Carlo robustness analysis and related charts."""

    def test_generate_noisy_prices(self, corn_prices):
        """Noisy prices are a Series, all positive, and differ from original."""
        close = corn_prices.loc["2025-01-01":]["Close"]
        noisy = generate_noisy_prices(close, noise_scale=0.5)

        assert isinstance(noisy, pd.Series)
        assert len(noisy) > 0
        assert len(noisy) <= len(close)
        assert (noisy > 0).all()
        # Noisy prices should differ from original on at least some days
        original_aligned = close.reindex(noisy.index)
        assert not noisy.equals(original_aligned)

    def test_run_monte_carlo(self, backtest_result):
        """MC result has expected keys, correct sharpe_ratios length, pct_profitable in [0,1]."""
        result_df, _, _ = backtest_result
        # Use a trivial signal function that preserves existing signal column
        mc = run_monte_carlo(
            result_df,
            generate_signal_fn=lambda df: df,
            n_paths=10,
            noise_scale=0.5,
            seed=42,
        )

        assert "sharpe_ratios" in mc
        assert "total_returns" in mc
        assert "equity_curves" in mc
        assert "pct_profitable" in mc
        assert "original_sharpe" in mc
        assert "original_sharpe_percentile" in mc
        assert "original_equity" in mc

        assert len(mc["sharpe_ratios"]) == 10
        assert 0.0 <= mc["pct_profitable"] <= 1.0

    def test_sharpe_distribution_chart(self):
        """sharpe_distribution_chart returns a Plotly Figure."""
        from app.charts import sharpe_distribution_chart

        fig = sharpe_distribution_chart([0.5, 1.0, 1.5, 0.8, -0.2], 1.0)
        assert isinstance(fig, go.Figure)

    def test_equity_fan_chart(self, backtest_result):
        """equity_fan_chart returns a Plotly Figure."""
        from app.charts import equity_fan_chart

        result_df, _, _ = backtest_result
        equity = result_df["equity"]
        # Create a couple of fake MC equity curves
        curves = [equity * 1.01, equity * 0.99]
        fig = equity_fan_chart(curves, equity, 100_000_000)
        assert isinstance(fig, go.Figure)

    def test_compute_regime_stats(self, backtest_result):
        """Regime stats dict has expected keys and sub-keys."""
        result_df, trade_log, _ = backtest_result
        regime = compute_regime_stats(result_df, trade_log)

        assert "vol_threshold" in regime
        assert regime["vol_threshold"] > 0
        for key in ("high_vol", "low_vol"):
            assert key in regime
            sub = regime[key]
            for metric in ("sharpe_ratio", "total_return_pct", "max_drawdown_pct",
                           "num_trades", "win_rate", "num_days"):
                assert metric in sub, f"{key} missing {metric}"

    def test_regime_stats_days_partition(self, backtest_result):
        """High + low num_days ≈ total days minus vol warm-up period."""
        result_df, trade_log, _ = backtest_result
        regime = compute_regime_stats(result_df, trade_log, vol_window=21)

        total = regime["high_vol"]["num_days"] + regime["low_vol"]["num_days"]
        # Warm-up removes vol_window days, so total should be close to len - 20
        expected = len(result_df) - 20
        assert abs(total - expected) <= 2

    def test_regime_stats_win_rate_bounds(self, backtest_result):
        """Both regime win rates are in [0.0, 1.0]."""
        result_df, trade_log, _ = backtest_result
        regime = compute_regime_stats(result_df, trade_log)

        assert 0.0 <= regime["high_vol"]["win_rate"] <= 1.0
        assert 0.0 <= regime["low_vol"]["win_rate"] <= 1.0

    def test_run_bootstrap(self, backtest_result):
        """Bootstrap result has expected keys, correct length, all drawdowns <= 0."""
        _, trade_log, _ = backtest_result
        bs = run_bootstrap(trade_log, n_paths=50, seed=42)

        for key in ("max_drawdowns", "original_max_drawdown", "median_drawdown",
                     "pct_worse_drawdown", "n_paths"):
            assert key in bs, f"Missing key: {key}"
        assert len(bs["max_drawdowns"]) == 50
        assert all(d <= 0 for d in bs["max_drawdowns"])

    def test_bootstrap_original_drawdown(self, backtest_result):
        """Original max drawdown is negative (real backtest has drawdown)."""
        _, trade_log, _ = backtest_result
        bs = run_bootstrap(trade_log, n_paths=10, seed=42)
        assert bs["original_max_drawdown"] < 0

    def test_bootstrap_empty_trades(self):
        """Empty trade log returns empty max_drawdowns and zero drawdowns."""
        bs = run_bootstrap(pd.DataFrame(), n_paths=100)
        assert bs["max_drawdowns"] == []
        assert bs["original_max_drawdown"] == 0.0
        assert bs["median_drawdown"] == 0.0
