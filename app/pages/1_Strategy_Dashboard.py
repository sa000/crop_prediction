"""Strategy Dashboard -- run backtests and view performance metrics.

Loads futures from SQLite, weather features from Parquet, runs the selected
strategy's signal generator and backtest engine, then displays summary stats,
charts, and the full trade log. Supports multi-ticker comparison via tabs."""

import json
import sys
import uuid
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import charts, discovery, trade_analyst
from app.style import inject_css, sidebar_logo, BG_CARD, BG_DARK
from etl.db import (
    get_connection, init_tables, load_prices,
    save_shared_analysis, load_shared_analysis,
)
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
NAME_TO_SYMBOL = {v: k for k, v in SYMBOL_TO_NAME.items()}


def _serialize_result(result_df, trade_log, stats):
    """Serialize backtest outputs to JSON strings for DB storage."""
    result_json = result_df.reset_index().to_json(orient="records", date_format="iso")
    trade_log_json = trade_log.to_json(orient="records", date_format="iso")
    safe_stats = {
        k: (1e18 if v == float("inf") else v)
        for k, v in stats.items()
    }
    stats_json = json.dumps(safe_stats)
    return result_json, trade_log_json, stats_json


def _deserialize_result(row):
    """Deserialize a shared_analyses DB row back to DataFrames and stats dict."""
    result_df = pd.read_json(row["result_data"], orient="records")
    result_df["date"] = pd.to_datetime(result_df["date"])
    result_df = result_df.set_index("date")

    trade_log = pd.read_json(row["trade_log_data"], orient="records")
    if not trade_log.empty:
        for col in ["entry_date", "exit_date"]:
            if col in trade_log.columns:
                trade_log[col] = pd.to_datetime(trade_log[col])

    stats = json.loads(row["stats_data"])
    return result_df, trade_log, stats


def _auto_copy_share_link(share_id: str):
    """Auto-copy share URL to clipboard via st.html (runs in main page, no iframe)."""
    st.html(f"""
    <script>
    (function() {{
        var base = window.location.origin + window.location.pathname;
        var url = base + '?share={share_id}';
        navigator.clipboard.writeText(url).catch(function() {{
            var el = document.createElement('textarea');
            el.value = url;
            el.style.position = 'fixed';
            el.style.left = '-9999px';
            document.body.appendChild(el);
            el.select();
            document.execCommand('copy');
            document.body.removeChild(el);
        }});
    }})();
    </script>
    """, unsafe_allow_javascript=True)


inject_css()
sidebar_logo()

# Reserve a slot at the very top of the page for clipboard JS.
# Writing to this placeholder later injects the script early in the DOM,
# so it executes before the heavy chart iframes below and while the
# user-activation from the Share button click is still valid (~5 s).
_clipboard_slot = st.empty()


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


# --- Shared view detection ---
share_id = st.query_params.get("share")
if share_id:
    conn = get_connection()
    init_tables(conn)
    row = load_shared_analysis(conn, share_id)
    conn.close()

    if not row:
        st.error("Shared analysis not found.")
        st.stop()

    result_df, trade_log, stats = _deserialize_result(row)

    rs = analytics.rolling_sharpe(result_df)
    rw = analytics.rolling_win_rate(trade_log, result_df)
    mr = analytics.monthly_returns(result_df, row["capital"])
    dd = analytics.drawdown_periods(result_df)

    created = row["created_at"][:10]
    st.markdown(
        f'<div style="background: linear-gradient(135deg, rgba(59,130,246,0.15), rgba(139,92,246,0.10)); '
        f'border: 1px solid rgba(59,130,246,0.3); border-radius: 8px; padding: 1rem 1.25rem; '
        f'margin-bottom: 1.5rem;">'
        f'<span style="color: #93c5fd; font-weight: 600;">Shared Analysis</span>'
        f'<span style="color: #94a3b8;"> &mdash; {row["strategy_name"]} on {row["ticker_name"]}'
        f' &mdash; Saved {created}</span></div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<a href="?" style="color: #60a5fa; text-decoration: none; font-size: 0.85rem;">'
        '&larr; Back to Dashboard</a>',
        unsafe_allow_html=True,
    )

    render_results(result_df, trade_log, stats, rs, rw, mr, dd)
    st.stop()

st.markdown(
    '<h1 style="font-weight: 600; font-size: 1.8rem; color: #e2e8f0;">'
    'Strategy Dashboard</h1>',
    unsafe_allow_html=True,
)

# --- Sidebar ---
conn = get_connection()
init_tables(conn)
strategies = discovery.sync_strategies_to_db(conn)
conn.close()

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


def _render_postmortem_sidebar():
    """Render AI Post-Mortem section in sidebar when backtest results exist."""
    if "results" not in st.session_state:
        return

    pm_results = st.session_state["results"]
    pm_tickers = st.session_state.get("ticker_names", [])
    has_trades = any(
        not pm_results[name][1].empty for name in pm_tickers if name in pm_results
    )

    if not has_trades:
        return

    st.sidebar.markdown("---")
    has_pm_key = False
    try:
        pm_api_key = st.secrets["ANTHROPIC_API_KEY"]
        if pm_api_key and not pm_api_key.startswith("sk-ant-your-key"):
            has_pm_key = True
    except (KeyError, FileNotFoundError):
        pass

    if not has_pm_key:
        st.sidebar.info(
            "Add your Anthropic API key to .streamlit/secrets.toml "
            "to enable AI post-mortem analysis."
        )
        return

    if st.sidebar.button("AI Post-Mortem Analysis", use_container_width=True):
        for name in pm_tickers:
            if name not in pm_results:
                continue
            tl = pm_results[name][1]
            if tl.empty:
                continue
            ticker_symbol = TICKER_MAP.get(name, NAME_TO_SYMBOL.get(name, name))
            with st.spinner(f"Analyzing {name} trades..."):
                pm_result = trade_analyst.analyze_trades(
                    tl, ticker_symbol, name, pm_api_key,
                )
            st.session_state[f"postmortem_{name}"] = pm_result

    # Render post-mortem results in sidebar
    for name in pm_tickers:
        pm_key = f"postmortem_{name}"
        if pm_key not in st.session_state:
            continue
        pm = st.session_state[pm_key]

        st.sidebar.markdown(
            f'<p style="color: #93c5fd; font-weight: 600; '
            f'margin-top: 1rem;">{name} Post-Mortem</p>',
            unsafe_allow_html=True,
        )

        if pm.get("error"):
            st.sidebar.warning(pm["error"])
            continue

        # Notable trade cards with collapsible analysis
        sections = pm.get("sections", {})
        if not pm["trades"].empty:
            for _, t in pm["trades"].iterrows():
                pnl_color = "#22c55e" if t["pnl"] > 0 else "#ef4444"
                entry_d = pd.to_datetime(t["entry_date"]).strftime("%b %d, %Y")
                exit_d = pd.to_datetime(t["exit_date"]).strftime("%b %d, %Y")
                direction = t.get("direction", "long")
                if direction == "long":
                    action_entry, action_exit = "Bought", "Sold"
                else:
                    action_entry, action_exit = "Shorted", "Covered"
                st.sidebar.markdown(
                    f'<div style="background: rgba(30,41,59,0.7); '
                    f'border-radius: 6px; padding: 0.6rem 0.75rem; '
                    f'margin-bottom: 0; border-radius: 6px 6px 0 0; '
                    f'border-left: 3px solid {pnl_color};">'
                    # Label
                    f'<div style="color: #e2e8f0; font-weight: 600; '
                    f'font-size: 0.85rem; margin-bottom: 0.4rem;">{t["label"]}</div>'
                    # Entry row
                    f'<div style="display: flex; justify-content: space-between; '
                    f'margin-bottom: 0.2rem;">'
                    f'<span style="color: #94a3b8; font-size: 0.78rem;">'
                    f'{action_entry} on {entry_d}</span>'
                    f'<span style="color: #e2e8f0; font-weight: 600; '
                    f'font-size: 0.78rem;">${t["entry_price"]:.2f}</span>'
                    f'</div>'
                    # Exit row
                    f'<div style="display: flex; justify-content: space-between; '
                    f'margin-bottom: 0.35rem;">'
                    f'<span style="color: #94a3b8; font-size: 0.78rem;">'
                    f'{action_exit} on {exit_d}</span>'
                    f'<span style="color: {pnl_color}; font-weight: 600; '
                    f'font-size: 0.78rem;">${t["exit_price"]:.2f}</span>'
                    f'</div>'
                    # P&L row
                    f'<div style="border-top: 1px solid rgba(148,163,184,0.15); '
                    f'padding-top: 0.3rem;">'
                    f'<span style="color: {pnl_color}; font-weight: 600; '
                    f'font-size: 0.85rem;">'
                    f'${t["pnl"]:,.0f}</span>'
                    f'<span style="color: {pnl_color}; font-size: 0.78rem; '
                    f'margin-left: 0.4rem;">({t["pct_change"]:+.2f}%)</span>'
                    f'</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

                # Collapsible AI analysis under each card
                label = t["label"]
                section_text = sections.get(label, "")
                if section_text:
                    with st.sidebar.expander("AI Analysis", expanded=False):
                        st.markdown(section_text)

        # Patterns section at the end
        patterns_text = sections.get("Patterns", "")
        if patterns_text:
            with st.sidebar.expander("Patterns Across Trades", expanded=False):
                st.markdown(patterns_text)


def load_and_run(ticker: str):
    """Load data, generate signals, run backtest, compute analytics."""
    futures = load_prices(ticker)
    features_config = getattr(strategy_module, "FEATURES", None)

    if not features_config:
        df = futures.loc["2025-01-01":]
    else:
        ticker_name = SYMBOL_TO_NAME.get(ticker)
        ticker_categories = features_config.get("ticker_categories", [])
        unlinked = features_config.get("unlinked", [])

        feat_df = read_strategy_features(
            ticker_name,
            categories=ticker_categories or None,
            unlinked=unlinked or None,
        )
        feat_df = feat_df.set_index(pd.to_datetime(feat_df["date"]))
        feat_df = feat_df.drop(columns=["date"], errors="ignore")
        df = futures.join(feat_df, how="inner")
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

_render_postmortem_sidebar()

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
        _, share_col = st.columns([10, 2])
        with share_col:
            if st.button("Share", key=f"share_{name}", use_container_width=True):
                sid = uuid.uuid4().hex[:12]
                result_df, trade_log, stats = all_results[name][:3]
                r_json, tl_json, s_json = _serialize_result(result_df, trade_log, stats)
                ticker_symbol = TICKER_MAP.get(name, NAME_TO_SYMBOL.get(name, name))
                conn = get_connection()
                init_tables(conn)
                save_shared_analysis(
                    conn, sid,
                    strategy_name=st.session_state["strategy_name"],
                    ticker_symbol=ticker_symbol,
                    ticker_name=name,
                    capital=CAPITAL,
                    risk_pct=RISK_PCT,
                    cost_per_trade=COST_PER_TRADE,
                    result_data=r_json,
                    trade_log_data=tl_json,
                    stats_data=s_json,
                )
                conn.close()
                st.session_state[f"shared_id_{name}"] = sid

        if f"shared_id_{name}" in st.session_state:
            with _clipboard_slot:
                _auto_copy_share_link(st.session_state[f"shared_id_{name}"])
            st.toast("Link copied to clipboard!")
            del st.session_state[f"shared_id_{name}"]

        render_results(*all_results[name])
