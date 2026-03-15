"""Precipitation Stress Signals Strategy for corn futures.

Based on "Precipitation Stress Signals Strategy" paper. Extreme deviations in
precipitation, measured by a 30-day anomaly z-score and confirmed by an 8-day
rolling precipitation total, forecast significant moves in corn futures. The
strategy goes long during drought or flood stress conditions and short during
normal precipitation periods.

Derived features:
- 8-day rolling precipitation total computed inline from raw weather data
  for Iowa, Illinois, and Nebraska (Corn Belt aggregate).
- Point-in-time lag applied to derived feature (shift(1)).
"""

import pandas as pd
from etl.db import load_raw_data

DROUGHT_Z_THRESHOLD = -1.5
FLOOD_Z_THRESHOLD = 2.0
NORMAL_Z_LOWER = -0.3
NORMAL_Z_UPPER = 0.3
DRY_CONFIRMATION_THRESHOLD = 0.2
WET_CONFIRMATION_THRESHOLD = 3.0

FEATURES = {
    "ticker_categories": [],
    "unlinked": [
        {"category": "weather", "entity": "corn_belt"}
    ],
}

SUMMARY = (
    "Goes long when Corn Belt precipitation shows extreme drought (z < -1.5 "
    "and 8-day total < 0.2) or flood (z > 2.0 and 8-day total > 3.0) "
    "conditions. Goes short during normal precipitation (-0.3 < z < 0.3)."
)


def _compute_precip_8d():
    """Compute 8-day rolling precipitation total for Corn Belt aggregate.
    
    Returns:
        Series with DatetimeIndex and derived precip_8d values.
    """
    # Load raw data for each state
    iowa = load_raw_data('weather_daily', 'state', 'Iowa')[['date', 'precip_in']]
    illinois = load_raw_data('weather_daily', 'state', 'Illinois')[['date', 'precip_in']]
    nebraska = load_raw_data('weather_daily', 'state', 'Nebraska')[['date', 'precip_in']]
    
    # Set date as index for alignment
    iowa = iowa.set_index('date')
    illinois = illinois.set_index('date')
    nebraska = nebraska.set_index('date')
    
    # Concatenate and compute Corn Belt aggregate (average across states)
    merged = pd.concat(
        [iowa['precip_in'], illinois['precip_in'], nebraska['precip_in']],
        axis=1,
        keys=['iowa', 'illinois', 'nebraska']
    )
    merged['corn_belt_precip'] = merged.mean(axis=1)
    
    # Compute 8-day rolling sum with point-in-time lag
    # Feature pipeline shifts features by 1 day, but derived features bypass pipeline
    # Must apply shift(1) to ensure point-in-time correctness
    merged['precip_8d'] = merged['corn_belt_precip'].rolling(8).sum().shift(1)
    
    return merged['precip_8d']


def generate_signal(df):
    """Generate long/short/flat signal from precipitation features.
    
    Args:
        df: DataFrame with DatetimeIndex, 'Close', and 
            'corn_belt_precip_anomaly_30d' column (z-score).
    
    Returns:
        DataFrame with added 'signal' column (+1, -1, or 0).
    """
    df = df.copy()
    
    # Compute derived 8-day precipitation total
    precip_8d_series = _compute_precip_8d()
    
    # Align derived feature with df index (pandas aligns on index automatically)
    df['precip_8d'] = precip_8d_series
    
    # Get feature values
    anomaly = df['corn_belt_precip_anomaly_30d']
    precip_8d = df['precip_8d']
    
    # Initialize signal column
    df['signal'] = 0
    
    # Long conditions
    drought_long = (anomaly < DROUGHT_Z_THRESHOLD) & (precip_8d < DRY_CONFIRMATION_THRESHOLD)
    flood_long = (anomaly > FLOOD_Z_THRESHOLD) & (precip_8d > WET_CONFIRMATION_THRESHOLD)
    df.loc[drought_long, 'signal'] = 1
    df.loc[flood_long, 'signal'] = 1
    
    # Short condition (normal precipitation)
    normal_short = (anomaly > NORMAL_Z_LOWER) & (anomaly < NORMAL_Z_UPPER)
    df.loc[normal_short, 'signal'] = -1
    
    # Handle NaN values
    df.loc[anomaly.isna() | precip_8d.isna(), 'signal'] = 0
    
    return df