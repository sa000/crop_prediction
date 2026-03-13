"""Tests for the data pipeline: DB tables, price loading, feature store, registry."""

import pandas as pd

from features import store
from features.query import read_parquet


class TestDatabase:
    """Verify SQLite warehouse tables and data integrity."""

    def test_db_tables_exist(self, db_connection):
        """futures_daily, weather_daily, and validation_log exist in SQLite."""
        cursor = db_connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        tables = {row[0] for row in cursor.fetchall()}
        assert "futures_daily" in tables
        assert "weather_daily" in tables
        assert "validation_log" in tables

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
