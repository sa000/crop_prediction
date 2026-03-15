"""Precipitation Stress Signals in Corn Futures.

Strategy based on "Precipitation Stress Signals in Corn Futures" paper.
Extreme deviations in precipitation, measured by a 30-day anomaly z-score
and confirmed by an 8-day rolling precipitation total, forecast significant
moves in corn futures. The strategy goes long during drought or flood stress
conditions and short during normal precipitation periods.

This implementation derives the 8-day rolling precipitation total inline from
raw warehouse data, applying a 1-day lag for point-in-time correctness.
"""

import pandas as pd
import numpy as np
from etl.db import load_raw_data

# Signal thresholds
DROUGHT_Z_THRESHOLD = -1.5
FLOOD_Z_THRESHOLD = 2.0
NORMAL_Z_LOWER = -0.3
NORMAL_Z_UPPER = 0.3
DRY_CONFIRMATION_INCHES = 0.2
WET_CONFIRMATION_INCHES = 3.0

FEATURES = {
    "ticker_categories": [],
    "unlinked": [{"category": "weather", "entity": "corn_belt"}],
}

SUMMARY = (
    "Goes long when Corn Belt precipitation shows extreme drought or flood "
    "conditions confirmed by sustained dry/wet patterns, and short during "
    "normal precipitation periods when there is no supply threat."
)


def _compute_8d_precipitation():
    """Compute 8-day rolling precipitation total for Corn Belt.
    
    Loads raw precipitation data for Iowa, Illinois, and Nebraska,
    computes Corn Belt aggregate by averaging across states, then
    calculates 8-day rolling sum.
    
    Returns:
        Series with DatetimeIndex and 'precip_8d' values.
    """
    states = ["Iowa", "Illinois", "Nebraska"]
    state_series = []
    
    for state in states:
        # Load raw precipitation data for each state
        df_state = load_raw_data("weather_daily", "state", state)
        df_state = df_state[["date", "precip_in"]].copy()
        df_state.set_index("date", inplace=True)
        state_series.append(df_state["precip_in"].rename(state))
    
    # Combine states into DataFrame
    precip_df = pd.concat(state_series, axis=1)
    
    # Compute Corn Belt aggregate (mean across states)
    corn_belt_precip = precip_df.mean(axis=1).rename("corn_belt_precip_in")
    
    # Calculate 8-day rolling sum with min_periods=8 (default)
    # Apply 1-day lag for point-in-time correctness
    # On date T, we only have data through T-1
    precip_8d = corn_belt_precip.rolling(8).sum().shift(1).rename("precip_8d")
    
    return precip_8d


def generate_signal(df):
    """Generate long/short/flat signal from precipitation features.
    
    Args:
        df: DataFrame with DatetimeIndex, 'Close' column, and
            'corn_belt_precip_anomaly_30d' column from feature store.
    
    Returns:
        DataFrame with added 'signal' column (+1, -1, or 0).
    """
    df = df.copy()
    
    # Derive 8-day precipitation total inline
    precip_8d = _compute_8d_precipitation()
    
    # Join derived feature (pandas aligns on DatetimeIndex)
    df["precip_8d"] = precip_8d
    
    # Get feature store columns
    anomaly = df["corn_belt_precip_anomaly_30d"]
    
    # Initialize signal column
    df["signal"] = 0
    
    # Long drought: extreme negative z-score AND sustained dry conditions
    drought_mask = (anomaly < DROUGHT_Z_THRESHOLD) & (df["precip_8d"] < DRY_CONFIRMATION_INCHES)
    df.loc[drought_mask, "signal"] = 1
    
    # Long flood: extreme positive z-score AND sustained wet conditions
    flood_mask = (anomaly > FLOOD_Z_THRESHOLD) & (df["precip_8d"] > WET_CONFIRMATION_INCHES)
    df.loc[flood_mask, "signal"] = 1
    
    # Short normal: z-score within normal range
    normal_mask = (anomaly > NORMAL_Z_LOWER) & (anomaly < NORMAL_Z_UPPER)
    df.loc[normal_mask, "signal"] = -1
    
    # Handle NaN values
    df.loc[anomaly.isna() | df["precip_8d"].isna(), "signal"] = 0
    
    return df