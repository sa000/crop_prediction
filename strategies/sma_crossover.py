"""SMA crossover strategy for agricultural commodity futures.

Goes long when the 20-day simple moving average crosses above the 50-day
SMA (bullish trend), and short when it crosses below (bearish trend).
When either SMA is unavailable (NaN), the signal is flat.

Signal logic:
    SMA_20 > SMA_50 -> +1 (long)   Bullish crossover
    SMA_20 < SMA_50 -> -1 (short)  Bearish crossover
    NaN in either   ->  0 (flat)   Insufficient data
"""

FEATURES = {
    "categories": ["momentum"],
    "weather_states": None,
    "ticker_specific": True,
}

SUMMARY = (
    "Goes long when the 20-day SMA crosses above the 50-day SMA "
    "(bullish trend) and short when it crosses below (bearish trend)."
)


def generate_signal(df):
    """Generate long/short/flat signal from SMA crossover.

    Args:
        df: DataFrame with 'sma_20', 'sma_50', and 'Close' columns.

    Returns:
        DataFrame with added 'signal' column (+1, -1, or 0).
    """
    df = df.copy()
    df["signal"] = 0
    has_both = df["sma_20"].notna() & df["sma_50"].notna()
    df.loc[has_both & (df["sma_20"] > df["sma_50"]), "signal"] = 1
    df.loc[has_both & (df["sma_20"] < df["sma_50"]), "signal"] = -1
    return df
