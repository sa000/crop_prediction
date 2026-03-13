"""Momentum feature computations: moving averages, MACD, RSI.

All functions are pure -- they take pandas Series/DataFrames and return
Series. No I/O. The FUNCTIONS dict maps config names to callables for
dispatch by the pipeline.
"""

import pandas as pd


def sma(series: pd.Series, window: int, **_kwargs) -> pd.Series:
    """Simple moving average.

    Args:
        series: Price series.
        window: Number of periods.

    Returns:
        Rolling mean series.
    """
    return series.rolling(window=window).mean()


def ema(series: pd.Series, span: int, **_kwargs) -> pd.Series:
    """Exponential moving average.

    Args:
        series: Price series.
        span: EMA span (decay factor).

    Returns:
        EWM mean series.
    """
    return series.ewm(span=span, adjust=False).mean()


def macd(close: pd.Series, fast_span: int, slow_span: int, **_kwargs) -> pd.Series:
    """MACD line: fast EMA minus slow EMA.

    Args:
        close: Closing price series.
        fast_span: Span for the fast EMA.
        slow_span: Span for the slow EMA.

    Returns:
        MACD line series.
    """
    fast = close.ewm(span=fast_span, adjust=False).mean()
    slow = close.ewm(span=slow_span, adjust=False).mean()
    return fast - slow


def macd_signal(
    close: pd.Series, fast_span: int, slow_span: int, signal_span: int, **_kwargs
) -> pd.Series:
    """MACD signal line: EMA of the MACD line.

    Args:
        close: Closing price series.
        fast_span: Span for the fast EMA.
        slow_span: Span for the slow EMA.
        signal_span: Span for the signal EMA.

    Returns:
        Signal line series.
    """
    macd_line = macd(close, fast_span, slow_span)
    return macd_line.ewm(span=signal_span, adjust=False).mean()


def rsi(series: pd.Series, window: int, **_kwargs) -> pd.Series:
    """Relative Strength Index (0-100).

    Uses the standard Wilder smoothing (EWM with alpha=1/window).

    Args:
        series: Price series.
        window: Lookback window.

    Returns:
        RSI series.
    """
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1.0 / window, min_periods=window, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / window, min_periods=window, adjust=False).mean()
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


FUNCTIONS = {
    "sma": sma,
    "ema": ema,
    "macd": macd,
    "macd_signal": macd_signal,
    "rsi": rsi,
}
