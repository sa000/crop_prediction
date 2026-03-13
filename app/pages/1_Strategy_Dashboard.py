"""Strategy Dashboard -- run backtests and view performance metrics.

Loads futures from SQLite, weather features from Parquet, runs the selected
strategy's signal generator and backtest engine, then displays summary stats,
charts, and the full trade log. Supports multi-ticker comparison via tabs."""

import sys
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import charts, discovery
from app.style import inject_css, sidebar_logo, BG_CARD, BG_DARK
from etl.db import load_prices
from features import store
from features.query import list_tickers, read_strategy_features
from strategies import analytics
from strategies.backtest import run_backtest

CAPITAL = 100_000_000
RISK_PCT = 0.01
COST_PER_TRADE = 0.0

TICKER_MAP = {
    "Corn": "ZC=F",
    "Soybeans": "ZS=F",
    "Wheat": "ZW=F",
}

SYMBOL_TO_NAME = {t["symbol"]: t["name"] for t in list_tickers()}

inject_css()
sidebar_logo()


def show_chart(fig, height=450):
    """Render a Plotly figure via HTML to bypass st.plotly_chart issues."""
    html = fig.to_html(include_plotlyjs="cdn", full_html=False)
    wrapper = f"""
    <div style="background: {BG_CARD}; border-radius: 8px;
                border: 1px solid rgba(59,130,246,0.12); padding: 4px;">
        {html}
    </div>
    """
    components.html(wrapper, height=height, scrolling=False)


def render_results(result_df, trade_log, stats, rs, rw, mr, dd):
    """Render backtest metrics, charts, and trade log for a single ticker."""
    # --- Header ---
    st.markdown(
        f'<p style="color: #64748b; font-size: 0.85rem; margin-bottom: 1.5rem;">'
        f'{result_df.index[0].date()} to {result_df.index[-1].date()} &nbsp;&bull;&nbsp; '
        f'{len(result_df)} trading days</p>',
        unsafe_allow_html=True,
    )

    # --- Summary Stats ---
    row1 = st.columns(5)
    row1[0].metric("Total P&L", f"${stats['total_pnl']:,.0f}", delta=f"{stats['total_return_pct']:.3f}%", delta_color="normal")
    row1[1].metric("Sharpe", f"{stats['sharpe_ratio']:.2f}")
    row1[2].metric("Sortino", f"{stats['sortino_ratio']:.2f}")
    row1[3].metric("Calmar", f"{stats['calmar_ratio']:.2f}")
    row1[4].metric("Profit Factor", f"{stats['profit_factor']:.2f}")

    row2 = st.columns(5)
    row2[0].metric("Trades", stats["num_trades"])
    row2[1].metric("Win Rate", f"{stats['win_rate']:.1%}")
    row2[2].metric("Max Drawdown", f"{stats['max_drawdown_pct']:.3f}%")
    row2[3].metric("VaR 95%", f"${stats['var_95']:,.0f}")
    row2[4].metric("CVaR 95%", f"${stats['cvar_95']:,.0f}")

    # --- Charts ---
    st.markdown("")

    show_chart(charts.equity_curve(result_df, CAPITAL), height=460)
    show_chart(charts.price_with_signals(result_df, trade_log), height=490)
    show_chart(charts.drawdown_chart(result_df), height=460)

    # Drawdown periods table
    if not dd.empty:
        with st.expander("Drawdown Periods"):
            fmt_dd = dd.copy()
            fmt_dd["start"] = pd.to_datetime(fmt_dd["start"]).dt.strftime("%Y-%m-%d")
            fmt_dd["trough_date"] = pd.to_datetime(fmt_dd["trough_date"]).dt.strftime("%Y-%m-%d")
            fmt_dd["recovery_date"] = fmt_dd["recovery_date"].apply(
                lambda x: pd.to_datetime(x).strftime("%Y-%m-%d") if pd.notna(x) else "Open"
            )
            fmt_dd["max_dd_dollars"] = fmt_dd["max_dd_dollars"].map("${:,.0f}".format)
            fmt_dd["max_dd_pct"] = fmt_dd["max_dd_pct"].map("{:.3f}%".format)
            st.dataframe(fmt_dd, use_container_width=True, hide_index=True)

    # Alpha decay
    st.markdown("### Alpha Decay")
    col_sharpe, col_win = st.columns(2)
    with col_sharpe:
        show_chart(charts.rolling_sharpe_chart(rs), height=460)
    with col_win:
        show_chart(charts.rolling_win_rate_chart(rw), height=460)

    # Monthly returns
    show_chart(charts.monthly_return_heatmap(mr), height=max(260, 120 * len(mr)))

    # Return distribution
    show_chart(charts.return_distribution(result_df, stats["var_95"]), height=460)

    # Trade log
    st.markdown("### Trade Log")
    if not trade_log.empty:
        display_log = trade_log.copy()
        display_log["entry_date"] = pd.to_datetime(display_log["entry_date"]).dt.date
        display_log["exit_date"] = pd.to_datetime(display_log["exit_date"]).dt.date
        st.dataframe(
            display_log.style.format({
                "entry_price": "${:.2f}",
                "exit_price": "${:.2f}",
                "units": "{:,.1f}",
                "pnl": "${:,.2f}",
                "pnl_per_unit": "${:.2f}",
            }).map(
                lambda v: "color: #22c55e" if isinstance(v, (int, float)) and v > 0
                else ("color: #ef4444" if isinstance(v, (int, float)) and v < 0 else ""),
                subset=["pnl"],
            ),
            use_container_width=True,
            hide_index=True,
            height=400,
        )
    else:
        st.info("No trades generated.")


st.markdown(
    '<h1 style="font-weight: 600; font-size: 1.8rem; color: #e2e8f0;">'
    'Strategy Dashboard</h1>',
    unsafe_allow_html=True,
)

# --- Sidebar ---
strategies = discovery.discover_strategies()

if not strategies:
    st.error("No strategies found in strategies/ directory.")
    st.stop()

st.sidebar.markdown("---")
selected_name = st.sidebar.selectbox("Strategy", list(strategies.keys()))
strategy_module = strategies[selected_name]
metadata = discovery.get_strategy_metadata(strategy_module)

if metadata["summary"]:
    st.sidebar.markdown(
        f'<p style="color: #94a3b8; font-size: 0.8rem; margin-top: 0.5rem;">'
        f'{metadata["summary"]}</p>',
        unsafe_allow_html=True,
    )

selected_tickers = st.sidebar.pills(
    "Tickers", list(TICKER_MAP.keys()), default=["Corn"],
    selection_mode="multi",
)

st.sidebar.markdown(
    f'<p style="color: #64748b; font-size: 0.75rem; margin-top: 1rem;">'
    f'Capital: $100M &nbsp;|&nbsp; Risk: 1% &nbsp;|&nbsp; Cost: $0</p>',
    unsafe_allow_html=True,
)

run = st.sidebar.button("Run Backtest", type="primary", use_container_width=True)


def load_and_run(ticker: str):
    """Load data, generate signals, run backtest, compute analytics."""
    futures = load_prices(ticker)
    features_config = getattr(strategy_module, "FEATURES", None)

    if features_config and features_config.get("ticker_specific"):
        ticker_name = SYMBOL_TO_NAME[ticker]
        feat_df = read_strategy_features(
            ticker_name, categories=features_config.get("categories"),
        )
        feat_df = feat_df.set_index(pd.to_datetime(feat_df["date"]))
        feat_df = feat_df.drop(columns=["date"], errors="ignore")
        df = futures.join(feat_df, how="inner")
        df = df.loc["2025-01-01":]
    else:
        weather = store.read_features("weather", "corn_belt")
        weather = weather.set_index(pd.to_datetime(weather["date"]))
        df = futures.join(weather[["precip_anomaly_30d"]], how="inner")
        df = df.loc["2025-01-01":]

    df = strategy_module.generate_signal(df)
    result_df, trade_log, stats = run_backtest(
        df, capital=CAPITAL, risk_pct=RISK_PCT, cost_per_trade=COST_PER_TRADE,
    )

    rs = analytics.rolling_sharpe(result_df)
    rw = analytics.rolling_win_rate(trade_log, result_df)
    mr = analytics.monthly_returns(result_df, CAPITAL)
    dd = analytics.drawdown_periods(result_df)

    return result_df, trade_log, stats, rs, rw, mr, dd


if run:
    if not selected_tickers:
        st.warning("Select at least one ticker.")
        st.stop()

    all_results = {}
    with st.spinner("Running backtest..."):
        for name in selected_tickers:
            ticker_symbol = TICKER_MAP[name]
            all_results[name] = load_and_run(ticker_symbol)

    st.session_state["results"] = all_results
    st.session_state["strategy_name"] = selected_name
    st.session_state["ticker_names"] = selected_tickers

if "results" not in st.session_state:
    st.markdown(
        '<p style="color: #64748b; margin-top: 3rem; text-align: center;">'
        'Select a strategy and click <b>Run Backtest</b> to begin.</p>',
        unsafe_allow_html=True,
    )
    st.stop()

all_results = st.session_state["results"]
ticker_names = st.session_state["ticker_names"]

st.markdown(
    f'<p style="color: #64748b; font-size: 0.85rem; margin-bottom: 1.5rem;">'
    f'{st.session_state["strategy_name"]}</p>',
    unsafe_allow_html=True,
)

tabs = st.tabs(ticker_names)
for tab, name in zip(tabs, ticker_names):
    with tab:
        render_results(*all_results[name])
