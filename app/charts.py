"""Plotly chart builders for the Streamlit app.

All functions are pure: take data in, return a plotly Figure out.
No Streamlit imports. Mirrors the notebook visualizations in interactive Plotly.

Date axes use explicit string dates (YYYY-MM-DD) to avoid serialization
issues between Plotly 6 and Streamlit."""

import numpy as np
import pandas as pd
import plotly.graph_objects as go

COLORS = {
    "equity": "#3B82F6",
    "price": "#e2e8f0",
    "long": "rgba(34, 197, 94, 0.13)",
    "short": "rgba(239, 68, 68, 0.13)",
    "entry": "#22c55e",
    "exit": "#ef4444",
    "drawdown": "rgba(239, 68, 68, 0.35)",
    "drawdown_line": "#ef4444",
    "reference": "rgba(148, 163, 184, 0.3)",
    "histogram": "#3B82F6",
    "var_line": "#ef4444",
    "grid": "rgba(148, 163, 184, 0.08)",
    "text": "#94a3b8",
}

BG_DARK = "#0f1117"
BG_CARD = "#1a1b2e"

LAYOUT_DEFAULTS = dict(
    template="plotly_dark",
    paper_bgcolor=BG_CARD,
    plot_bgcolor=BG_DARK,
    margin=dict(l=60, r=30, t=50, b=50),
    hovermode="x unified",
    font=dict(size=12, color=COLORS["text"]),
    xaxis=dict(gridcolor=COLORS["grid"], zeroline=False),
    yaxis=dict(gridcolor=COLORS["grid"], zeroline=False),
)


def _dates(index: pd.Index) -> list[str]:
    """Convert a datetime index to a list of date strings for Plotly."""
    return [d.strftime("%Y-%m-%d") for d in index]


def _apply_layout(fig: go.Figure, title: str, yaxis_title: str, height: int = 420) -> go.Figure:
    """Apply consistent layout defaults to a figure."""
    fig.update_layout(title=title, yaxis_title=yaxis_title, height=height, **LAYOUT_DEFAULTS)
    return fig


def equity_curve(backtest_df: pd.DataFrame, capital: float) -> go.Figure:
    """Line chart of portfolio equity over time.

    Matches the notebook: equity in $M, dashed starting capital reference.

    Args:
        backtest_df: Backtest DataFrame with equity column and datetime index.
        capital: Starting capital in dollars.

    Returns:
        Plotly Figure.
    """
    dates = _dates(backtest_df.index)
    equity_m = (backtest_df["equity"] / 1e6).tolist()

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=dates, y=equity_m,
        mode="lines", name="Portfolio Equity",
        line=dict(color=COLORS["equity"], width=2),
    ))
    fig.add_hline(
        y=capital / 1e6, line_dash="dash", line_color=COLORS["reference"],
        annotation_text=f"${capital / 1e6:.0f}M starting capital",
        annotation_position="bottom right",
        annotation_font_color=COLORS["text"],
    )
    return _apply_layout(fig, "Equity Curve", "Equity ($M)")


def price_with_signals(backtest_df: pd.DataFrame, trade_log: pd.DataFrame) -> go.Figure:
    """Price chart with position shading and entry/exit markers.

    Matches the notebook: close price line, green shaded regions for long,
    red for short, triangle markers at trade entries and exits.

    Args:
        backtest_df: Backtest DataFrame with Close and position columns.
        trade_log: Trade log DataFrame with entry/exit dates and prices.

    Returns:
        Plotly Figure.
    """
    dates = _dates(backtest_df.index)
    close = backtest_df["Close"].tolist()

    fig = go.Figure()

    # Close price line
    fig.add_trace(go.Scatter(
        x=dates, y=close,
        mode="lines", name="Close Price",
        line=dict(color=COLORS["price"], width=1.5),
    ))

    # Position shading using vertical rectangles
    positions = backtest_df["position"].values

    for pos_val, color, label in [(1, COLORS["long"], "Long"), (-1, COLORS["short"], "Short")]:
        in_block = False
        block_start = None
        added_legend = False

        for i in range(len(positions)):
            if positions[i] == pos_val and not in_block:
                in_block = True
                block_start = dates[i]
            elif positions[i] != pos_val and in_block:
                in_block = False
                fig.add_vrect(
                    x0=block_start, x1=dates[i - 1],
                    fillcolor=color, layer="below", line_width=0,
                    annotation_text=label if not added_legend else None,
                    annotation_position="top left" if not added_legend else None,
                )
                added_legend = True

        if in_block:
            fig.add_vrect(
                x0=block_start, x1=dates[-1],
                fillcolor=color, layer="below", line_width=0,
                annotation_text=label if not added_legend else None,
                annotation_position="top left" if not added_legend else None,
            )

    # Entry/exit markers
    if not trade_log.empty:
        entry_dates = [d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)[:10]
                       for d in trade_log["entry_date"]]
        exit_dates = [d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)[:10]
                      for d in trade_log["exit_date"]]
        fig.add_trace(go.Scatter(
            x=entry_dates, y=trade_log["entry_price"].tolist(),
            mode="markers", name="Entry",
            marker=dict(symbol="triangle-up", size=10, color=COLORS["entry"]),
        ))
        fig.add_trace(go.Scatter(
            x=exit_dates, y=trade_log["exit_price"].tolist(),
            mode="markers", name="Exit",
            marker=dict(symbol="triangle-down", size=10, color=COLORS["exit"]),
        ))

    return _apply_layout(fig, "Price with Trading Signals", "Price", height=450)


def drawdown_chart(backtest_df: pd.DataFrame) -> go.Figure:
    """Red filled area chart of equity drawdown from peak.

    Matches the notebook: fill between drawdown line and zero.

    Args:
        backtest_df: Backtest DataFrame with equity column.

    Returns:
        Plotly Figure.
    """
    dates = _dates(backtest_df.index)
    equity = backtest_df["equity"]
    running_max = equity.cummax()
    dd = (equity - running_max).tolist()

    fig = go.Figure()

    # Zero reference line (invisible, for fill target)
    fig.add_trace(go.Scatter(
        x=dates, y=[0] * len(dates),
        mode="lines", line=dict(color="rgba(0,0,0,0)", width=0),
        showlegend=False, hoverinfo="skip",
    ))

    # Drawdown area filled up to zero
    fig.add_trace(go.Scatter(
        x=dates, y=dd,
        mode="lines", fill="tonexty",
        fillcolor=COLORS["drawdown"],
        line=dict(color=COLORS["drawdown_line"], width=1),
        name="Drawdown",
    ))

    return _apply_layout(fig, "Drawdown from Peak Equity", "Drawdown ($)")


def rolling_sharpe_chart(series: pd.Series) -> go.Figure:
    """Line chart of rolling Sharpe ratio with reference lines at 0, 1, 2.

    Args:
        series: Rolling Sharpe Series with datetime index.

    Returns:
        Plotly Figure.
    """
    clean = series.dropna()
    dates = _dates(clean.index)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=dates, y=clean.tolist(),
        mode="lines", name="Rolling Sharpe",
        line=dict(color=COLORS["equity"], width=1.5),
    ))
    for level in [0, 1, 2]:
        fig.add_hline(y=level, line_dash="dot", line_color=COLORS["reference"],
                      annotation_text=str(level), annotation_position="bottom right",
                      annotation_font_color=COLORS["text"])
    return _apply_layout(fig, "Rolling Sharpe Ratio (60-day)", "Sharpe Ratio")


def rolling_win_rate_chart(series: pd.Series) -> go.Figure:
    """Line chart of rolling win rate with 50% reference line.

    Args:
        series: Rolling win rate Series (0 to 1 scale) with datetime index.

    Returns:
        Plotly Figure.
    """
    clean = series.dropna()
    dates = _dates(clean.index)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=dates, y=(clean * 100).tolist(),
        mode="lines", name="Rolling Win Rate",
        line=dict(color=COLORS["equity"], width=1.5),
    ))
    fig.add_hline(y=50, line_dash="dot", line_color=COLORS["reference"],
                  annotation_text="50%", annotation_position="bottom right",
                  annotation_font_color=COLORS["text"])
    fig.update_yaxes(range=[0, 100])
    return _apply_layout(fig, "Rolling Win Rate (last 20 trades)", "Win Rate (%)")


def monthly_return_heatmap(monthly_df: pd.DataFrame) -> go.Figure:
    """Heatmap of monthly returns by year and month.

    Args:
        monthly_df: DataFrame with year index, month columns (1-12), % values.

    Returns:
        Plotly Figure.
    """
    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                   "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

    monthly_df = monthly_df.reindex(columns=range(1, 13))
    z = monthly_df.values.tolist()
    text = [[f"{v:.3f}%" if not (isinstance(v, float) and np.isnan(v)) else ""
             for v in row] for row in monthly_df.values]

    fig = go.Figure(go.Heatmap(
        z=z,
        x=month_names,
        y=[str(y) for y in monthly_df.index],
        text=text,
        texttemplate="%{text}",
        colorscale="RdYlGn",
        zmid=0,
        colorbar=dict(title="%"),
    ))
    return _apply_layout(fig, "Monthly Returns (%)", "", height=max(220, 100 * len(monthly_df)))


def return_distribution(backtest_df: pd.DataFrame, var_95: float) -> go.Figure:
    """Histogram of daily P&L with VaR 95% vertical line.

    Args:
        backtest_df: Backtest DataFrame with net_daily_pnl column.
        var_95: VaR 95% value in dollars.

    Returns:
        Plotly Figure.
    """
    pnl = backtest_df["net_daily_pnl"].dropna().tolist()

    fig = go.Figure()
    fig.add_trace(go.Histogram(
        x=pnl, nbinsx=50, name="Daily P&L",
        marker_color=COLORS["histogram"], opacity=0.75,
    ))
    fig.add_vline(
        x=var_95, line_dash="dash", line_color=COLORS["var_line"], line_width=2,
        annotation_text=f"VaR 95%: ${var_95:,.0f}",
        annotation_position="top left",
    )
    return _apply_layout(fig, "Daily P&L Distribution", "Count")
