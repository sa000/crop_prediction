"""Weather precipitation strategy for corn futures.

Both drought and flood conditions are bullish for corn prices — they threaten
supply. Asymmetric thresholds: drought is tighter (-1 sigma) because corn is
more drought-sensitive; only extreme excess precipitation (>1.5 sigma) is
damaging.

Long-only strategy: signal is +1 (long) or 0 (flat), never short.
"""

DROUGHT_THRESHOLD = -1.0
FLOOD_THRESHOLD = 1.5


def generate_signal(df):
    """Generate long/flat signal from precipitation anomaly z-scores.

    Args:
        df: DataFrame with 'precip_anomaly_30d' column (z-score) and 'Close'.

    Returns:
        DataFrame with added 'signal' column (+1 or 0).
    """
    df = df.copy()
    anomaly = df["precip_anomaly_30d"]
    df["signal"] = 0
    df.loc[anomaly < DROUGHT_THRESHOLD, "signal"] = 1
    df.loc[anomaly > FLOOD_THRESHOLD, "signal"] = 1
    df.loc[anomaly.isna(), "signal"] = 0
    return df
