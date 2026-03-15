"""Precipitation Stress Signals in Corn Futures.

Strategy based on Mitchell, Vasquez & Chen (2024). Uses extreme deviations in
short-horizon precipitation metrics (30-day anomaly z-score and 8-day rolling
total) to forecast moves in corn futures.

Long positions during confirmed drought or flood stress, short during normal
precipitation. The 8-day rolling precipitation total is derived inline from
raw weather data in the warehouse.

Point-in-time: all weather features are lagged by 1 day because weather data
for day T is not available until after day T ends. On the morning of day T,
the most recent complete weather observation is for day T-1.
"""

import pandas as pd
from etl.db import load_raw_data

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
    "Goes long when Corn Belt precipitation shows extreme dry (drought) or wet "
    "(flood) stress confirmed by 8-day totals, short during normal precipitation."
)


def _derive_corn_belt_precip_8d():
    """Derive 8-day rolling precipitation total for Corn Belt.

    Loads raw daily precipitation for Iowa, Illinois, and Nebraska,
    averages across states, then computes the 8-day rolling sum.

    Returns:
        Series indexed by date with the 8-day rolling precipitation total.
    """
    frames = []
    for state in ["Iowa", "Illinois", "Nebraska"]:
        raw = load_raw_data("weather_daily", "state", state)
        raw = raw.set_index(pd.to_datetime(raw["date"]))
        frames.append(raw["precip_in"])

    corn_belt_precip = pd.concat(frames, axis=1).mean(axis=1)
    return corn_belt_precip.rolling(window=8, min_periods=8).sum()


def generate_signal(df):
    """Generate long/short/flat signal from precipitation metrics.

    All weather features are shifted by 1 day to be point-in-time: on day T,
    we only use weather data through day T-1.

    Args:
        df: DataFrame indexed by date with 'corn_belt_precip_anomaly_30d'
            and 'Close' columns.

    Returns:
        DataFrame with added 'signal' column (+1, -1, or 0).
    """
    df = df.copy()

    # Derive 8-day precipitation total and lag by 1 day for point-in-time
    precip_8d = _derive_corn_belt_precip_8d()
    df["corn_belt_precip_8d"] = precip_8d.shift(1)

    # Store feature is already point-in-time (shifted by the feature pipeline)
    anomaly = df["corn_belt_precip_anomaly_30d"]
    p8d = df["corn_belt_precip_8d"]

    df["signal"] = 0

    # Drought stress: z-score below threshold AND sustained dry conditions
    drought = (anomaly < DROUGHT_Z_THRESHOLD) & (p8d < DRY_CONFIRMATION_INCHES)
    df.loc[drought, "signal"] = 1

    # Flood stress: z-score above threshold AND sustained wet conditions
    flood = (anomaly > FLOOD_Z_THRESHOLD) & (p8d > WET_CONFIRMATION_INCHES)
    df.loc[flood, "signal"] = 1

    # Normal precipitation: no supply threat, bearish
    normal = (anomaly > NORMAL_Z_LOWER) & (anomaly < NORMAL_Z_UPPER)
    df.loc[normal, "signal"] = -1

    # NaN safety
    df.loc[anomaly.isna() | p8d.isna(), "signal"] = 0

    return df
