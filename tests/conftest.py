"""Session-scoped fixtures for the test suite.

Loads real data from warehouse.db and Parquet files once per session.
Individual tests assert shape, type, and invariant properties."""

import pandas as pd
import pytest

from etl.db import get_connection, init_tables, load_prices
from features import store
from features.query import load_registry, read_parquet, read_strategy_features
from strategies.backtest import run_backtest
from strategies.weather_precipitation import generate_signal
from strategies.sma_crossover import generate_signal as sma_generate_signal
from strategies.momentum_rsi import generate_signal as rsi_generate_signal


@pytest.fixture(scope="session")
def db_connection():
    """Open a connection to the SQLite warehouse database."""
    conn = get_connection()
    init_tables(conn)
    yield conn
    conn.close()


@pytest.fixture(scope="session")
def corn_prices():
    """Load corn futures OHLCV data from SQLite."""
    return load_prices("ZC=F")


@pytest.fixture(scope="session")
def weather_features():
    """Load weather features for corn_belt from Parquet."""
    return store.read_features("weather", "corn_belt")


@pytest.fixture(scope="session")
def registry():
    """Load the feature registry."""
    return load_registry()


@pytest.fixture(scope="session")
def backtest_result(corn_prices):
    """Run the full backtest pipeline matching the Strategy Dashboard flow.

    Uses read_strategy_features with the new unlinked protocol to load
    weather features, joins with prices, generates signal, runs backtest.
    """
    feat_df = read_strategy_features(
        "corn",
        categories=None,
        unlinked=[{"category": "weather", "entity": "corn_belt"}],
    )
    feat_df = feat_df.set_index(pd.to_datetime(feat_df["date"]))
    feat_df = feat_df.drop(columns=["date"], errors="ignore")

    df = corn_prices.join(feat_df, how="inner")
    df = df.loc["2025-01-01":]

    df = generate_signal(df)
    result_df, trade_log, stats = run_backtest(df, capital=100_000_000)
    return result_df, trade_log, stats


@pytest.fixture(scope="session")
def momentum_features():
    """Load momentum features for corn from Parquet."""
    return store.read_features("momentum", "corn")


@pytest.fixture(scope="session")
def sma_backtest_result(corn_prices, momentum_features):
    """Run SMA crossover backtest on corn.

    Loads momentum features, joins with corn prices, generates signals,
    and runs the backtest engine.
    """
    feat = momentum_features.copy()
    feat = feat.set_index(pd.to_datetime(feat["date"]))
    feat = feat.drop(columns=["date"], errors="ignore")

    df = corn_prices.join(feat[["sma_20", "sma_50"]], how="inner")
    df = df.loc["2025-01-01":]

    df = sma_generate_signal(df)
    result_df, trade_log, stats = run_backtest(df, capital=100_000_000)
    return result_df, trade_log, stats


@pytest.fixture(scope="session")
def rsi_backtest_result(corn_prices, momentum_features):
    """Run momentum RSI backtest on corn.

    Loads momentum features, joins with corn prices, generates signals,
    and runs the backtest engine.
    """
    feat = momentum_features.copy()
    feat = feat.set_index(pd.to_datetime(feat["date"]))
    feat = feat.drop(columns=["date"], errors="ignore")

    df = corn_prices.join(feat[["rsi_14"]], how="inner")
    df = df.loc["2025-01-01":]

    df = rsi_generate_signal(df)
    result_df, trade_log, stats = run_backtest(df, capital=100_000_000)
    return result_df, trade_log, stats
