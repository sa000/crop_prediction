"""Tests for the data pipeline: DB tables, price loading, feature store, registry."""

import json

import pandas as pd

from etl.db import (
    upsert_strategy, list_strategies, get_strategy,
    save_shared_analysis, load_shared_analysis,
)
from features import store
from features.query import read_parquet


class TestDatabase:
    """Verify SQLite warehouse tables and data integrity."""

    def test_db_tables_exist(self, db_connection):
        """All expected tables exist in SQLite."""
        cursor = db_connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        tables = {row[0] for row in cursor.fetchall()}
        assert "futures_daily" in tables
        assert "weather_daily" in tables
        assert "validation_log" in tables
        assert "strategies" in tables
        assert "shared_analyses" in tables

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

        Back-adjusted continuous futures can have minor OHLC violations
        from roll adjustments, so we allow up to 1% of rows to violate.
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
    """Verify shared analyses save/load operations."""

    def test_shared_analyses_table_exists(self, db_connection):
        """shared_analyses table is in sqlite_master."""
        cursor = db_connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='shared_analyses'"
        )
        assert cursor.fetchone() is not None

    def test_save_and_load_shared_analysis(self, db_connection, backtest_result):
        """Round-trip save and load of a shared analysis."""
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
            db_connection, share_id,
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

        row = load_shared_analysis(db_connection, share_id)
        assert row is not None
        assert row["strategy_name"] == "Weather Precipitation"
        assert row["ticker_symbol"] == "ZC=F"
        assert row["ticker_name"] == "Corn"
        assert row["capital"] == 100_000_000

        loaded_stats = json.loads(row["stats_data"])
        assert loaded_stats["num_trades"] == stats["num_trades"]

        # Clean up
        db_connection.execute("DELETE FROM shared_analyses WHERE id = ?", (share_id,))
        db_connection.commit()

    def test_load_nonexistent_share(self, db_connection):
        """Querying a fake share ID returns None."""
        result = load_shared_analysis(db_connection, "nonexistent_id")
        assert result is None
