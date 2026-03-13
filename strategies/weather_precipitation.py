"""Weather precipitation strategy for corn futures.

Both drought and flood conditions are bullish for corn prices — they threaten
supply. Asymmetric thresholds: drought is tighter (-1 sigma) because corn is
more drought-sensitive; only extreme excess precipitation (>1.5 sigma) is
damaging. When precipitation is normal (z-score near zero), there is no supply
threat and corn prices tend to drift down or stay flat — a natural short signal.

Signal zones (by precipitation z-score):
    z < -1.0          -> +1 (long)   Drought — supply threat, bullish
    -1.0 <= z <= -0.3 ->  0 (flat)   Ambiguous — could be drying out or recovering
    -0.3 <  z <  0.3  -> -1 (short)  Normal weather — no supply threat, bearish
     0.3 <= z <=  1.5 ->  0 (flat)   Ambiguous — wetter than normal but not damaging
    z > 1.5           -> +1 (long)   Flood — supply threat, bullish
"""

DROUGHT_THRESHOLD = -1.0   # z < -1.0 -> long  (supply threat)
FLOOD_THRESHOLD = 1.5      # z > +1.5 -> long  (supply threat)
NORMAL_LOW = -0.3          # -0.3 < z < 0.3 -> short (no supply threat)
NORMAL_HIGH = 0.3

FEATURES = {
    "categories": None,
    "weather_states": ["corn_belt"],
    "ticker_specific": False,
}

SUMMARY = (
    "Goes long when Corn Belt precipitation is abnormally low (drought) "
    "or abnormally high (flooding), as both threaten crop supply and push "
    "prices higher. Goes short during normal weather when there is no "
    "supply threat."
)


def generate_signal(df):
    """Generate long/short/flat signal from precipitation anomaly z-scores.

    Args:
        df: DataFrame with 'precip_anomaly_30d' column (z-score) and 'Close'.

    Returns:
        DataFrame with added 'signal' column (+1, -1, or 0).
    """
    df = df.copy()
    anomaly = df["precip_anomaly_30d"]
    df["signal"] = 0
    df.loc[anomaly < DROUGHT_THRESHOLD, "signal"] = 1      # drought -> long
    df.loc[anomaly > FLOOD_THRESHOLD, "signal"] = 1         # flood -> long
    df.loc[(anomaly > NORMAL_LOW) & (anomaly < NORMAL_HIGH), "signal"] = -1  # normal -> short
    df.loc[anomaly.isna(), "signal"] = 0
    return df
