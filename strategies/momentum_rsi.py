"""Momentum RSI strategy for agricultural commodity futures.

Uses the 14-day Relative Strength Index to identify oversold and overbought
conditions. Goes long when RSI dips below the oversold threshold (mean
reversion buy), short when it exceeds the overbought threshold (mean
reversion sell), and stays flat in between.

Signal zones (by RSI value):
    RSI < 30  -> +1 (long)   Oversold -- expect bounce
    RSI > 70  -> -1 (short)  Overbought -- expect pullback
    otherwise ->  0 (flat)   Neutral zone
"""

RSI_OVERSOLD = 30
RSI_OVERBOUGHT = 70

FEATURES = {
    "categories": ["momentum"],
    "weather_states": None,
    "ticker_specific": True,
}

SUMMARY = (
    "Goes long when RSI drops below 30 (oversold) and short when RSI "
    "rises above 70 (overbought), staying flat in the neutral zone."
)


def generate_signal(df):
    """Generate long/short/flat signal from RSI levels.

    Args:
        df: DataFrame with 'rsi_14' and 'Close' columns.

    Returns:
        DataFrame with added 'signal' column (+1, -1, or 0).
    """
    df = df.copy()
    rsi = df["rsi_14"]
    df["signal"] = 0
    df.loc[rsi < RSI_OVERSOLD, "signal"] = 1
    df.loc[rsi > RSI_OVERBOUGHT, "signal"] = -1
    df.loc[rsi.isna(), "signal"] = 0
    return df
