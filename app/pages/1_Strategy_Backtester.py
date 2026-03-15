"""Strategy Backtester -- run backtests and view performance metrics.

Loads futures from SQLite, weather features from Parquet, runs the selected
strategy's signal generator and backtest engine, then displays summary stats,
charts, and the full trade log. Supports multi-ticker comparison via tabs."""

import json
import sys
import uuid
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

st.set_page_config(
    page_title="Backtester | Cortex",
    page_icon=str(PROJECT_ROOT / "brain.png"),
    layout="wide",
)

from app import charts, discovery, trade_analyst
from app.style import (
    inject_css, sidebar_logo,
    ACCENT, ACCENT_DIM, BG_CARD, BG_CARD_SOLID, BG_DARK, BORDER, BORDER_SUBTLE,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_DIM, TEXT_FAINT,
    GREEN, RED, AMBER, LINK, BADGE,
)
from etl.db import (
    get_connection, init_tables, load_prices,
    get_app_connection, init_app_tables,
    save_shared_analysis, load_shared_analysis,
    save_backtest_run, load_backtest_run,
)
from features.query import list_tickers, read_strategy_features
from strategies import analytics
from strategies.backtest import run_backtest
from strategies.robustness import run_monte_carlo, run_bootstrap, compute_regime_stats

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


def _auto_log_run(strategy_name, module_name, ticker_symbol, ticker_name,
                   result_df, trade_log, stats, capital, risk_pct, cost_per_trade,
                   run_type="manual"):
    """Auto-log a backtest run to the leaderboard (fire-and-forget)."""
    try:
        run_id = uuid.uuid4().hex
        r_json, tl_json, s_json = _serialize_result(result_df, trade_log, stats)
        date_start = str(result_df.index[0].date()) if len(result_df) > 0 else None
        date_end = str(result_df.index[-1].date()) if len(result_df) > 0 else None
        conn = get_app_connection()
        init_app_tables(conn)
        save_backtest_run(
            conn, run_id,
            strategy_name=strategy_name,
            strategy_module=module_name,
            run_type=run_type,
            ticker=ticker_symbol,
            ticker_name=ticker_name,
            date_range_start=date_start,
            date_range_end=date_end,
            capital=capital,
            risk_pct=risk_pct,
            cost_per_trade=cost_per_trade,
            total_pnl=stats.get("total_pnl"),
            sharpe_ratio=stats.get("sharpe_ratio"),
            max_drawdown_pct=stats.get("max_drawdown_pct"),
            win_rate=stats.get("win_rate"),
            num_trades=stats.get("num_trades"),
            sortino_ratio=stats.get("sortino_ratio"),
            calmar_ratio=stats.get("calmar_ratio"),
            profit_factor=stats.get("profit_factor"),
            result_data=r_json,
            trade_log_data=tl_json,
            stats_data=s_json,
        )
        conn.close()
    except Exception:
        pass


inject_css()
sidebar_logo(PROJECT_ROOT)

# Reserve a slot at the very top of the page for clipboard JS.
# Writing to this placeholder later injects the script early in the DOM,
# so it executes before the heavy chart iframes below and while the
# user-activation from the Share button click is still valid (~5 s).
_clipboard_slot = st.empty()


def show_chart(fig, height=450):
    """Render a Plotly figure via HTML to bypass st.plotly_chart issues."""
    html = fig.to_html(include_plotlyjs="cdn", full_html=False)
    wrapper = f"""
    <div style="background: {BG_CARD_SOLID}; border-radius: 10px;
                border: 1px solid {BORDER}; padding: 4px;">
        {html}
    </div>
    """
    components.html(wrapper, height=height, scrolling=False)


def render_results(result_df, trade_log, stats, rs, rw, mr, dd, feature_df=None,
                    generate_signal_fn=None, ticker_key=""):
    """Render backtest metrics, charts, trade log, and stress test for a ticker."""
    # --- Header (always visible above sub-tabs) ---
    st.markdown(
        f'<p style="color: {TEXT_DIM}; font-size: 0.85rem; margin-bottom: 1.5rem;">'
        f'{result_df.index[0].date()} to {result_df.index[-1].date()} &nbsp;&bull;&nbsp; '
        f'{len(result_df)} trading days</p>',
        unsafe_allow_html=True,
    )

    # --- Sub-tabs ---
    has_stress = feature_df is not None and generate_signal_fn is not None
    tab_labels = ["Overview", "Analysis", "Trade Log"]
    if has_stress:
        tab_labels.append("Stress Test")
    sub_tabs = st.tabs(tab_labels)

    # --- Overview ---
    with sub_tabs[0]:
        def _fmt_dollar(v):
            """Format a dollar value compactly for metric cards."""
            if abs(v) >= 1e6:
                return f"${v / 1e6:.2f}M"
            if abs(v) >= 1e3:
                return f"${v / 1e3:.0f}K"
            return f"${v:,.0f}"

        row1 = st.columns(5)
        row1[0].metric("Total P&L", _fmt_dollar(stats['total_pnl']),
                        delta=f"{stats['total_return_pct']:.3f}%", delta_color="normal")
        row1[1].metric("Sharpe", f"{stats['sharpe_ratio']:.2f}")
        row1[2].metric("Sortino", f"{stats['sortino_ratio']:.2f}")
        row1[3].metric("Calmar", f"{stats['calmar_ratio']:.2f}")
        row1[4].metric("Profit Factor", f"{stats['profit_factor']:.2f}")

        row2 = st.columns(5)
        row2[0].metric("Trades", stats["num_trades"])
        row2[1].metric("Win Rate", f"{stats['win_rate']:.1%}")
        row2[2].metric("Max DD", f"{stats['max_drawdown_pct']:.3f}%",
                        delta=_fmt_dollar(stats['max_drawdown']),
                        delta_color="off", delta_arrow="off")
        row2[3].metric("VaR 95%", _fmt_dollar(stats['var_95']))
        row2[4].metric("CVaR 95%", _fmt_dollar(stats['cvar_95']))

        st.markdown("")

        show_chart(charts.equity_curve(result_df, CAPITAL), height=460)
        show_chart(charts.price_with_signals(result_df, trade_log), height=490)
        show_chart(charts.drawdown_chart(result_df), height=460)

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
                st.dataframe(fmt_dd, width="stretch", hide_index=True)

    # --- Analysis ---
    with sub_tabs[1]:
        col_sharpe, col_win = st.columns(2)
        with col_sharpe:
            show_chart(charts.rolling_sharpe_chart(rs), height=460)
        with col_win:
            show_chart(charts.rolling_win_rate_chart(rw), height=460)

        show_chart(charts.monthly_return_heatmap(mr), height=max(260, 120 * len(mr)))
        show_chart(charts.return_distribution(result_df, stats["var_95"]), height=460)

    # --- Trade Log ---
    with sub_tabs[2]:
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
                    lambda v: f"color: {GREEN}" if isinstance(v, (int, float)) and v > 0
                    else (f"color: {RED}" if isinstance(v, (int, float)) and v < 0 else ""),
                    subset=["pnl"],
                ),
                width="stretch",
                hide_index=True,
                height=400,
            )
        else:
            st.info("No trades generated.")

    # --- Stress Test ---
    if has_stress:
        with sub_tabs[3]:
            stress_tabs = st.tabs(["Monte Carlo", "Trade Reordering", "Volatility Regime"])

            # --- Monte Carlo Noise Injection ---
            with stress_tabs[0]:
                st.caption("Inject noise into returns and re-run the strategy across synthetic paths.")

                mc_key = f"mc_result_{ticker_key}"
                if mc_key not in st.session_state:
                    with st.spinner("Running 200 Monte Carlo paths..."):
                        mc_result = run_monte_carlo(
                            feature_df,
                            generate_signal_fn=generate_signal_fn,
                            n_paths=200,
                            noise_scale=0.5,
                            capital=CAPITAL,
                            risk_pct=RISK_PCT,
                            cost_per_trade=COST_PER_TRADE,
                        )
                    st.session_state[mc_key] = mc_result

                mc = st.session_state[mc_key]
                sharpe_ratios = mc["sharpe_ratios"]
                total_returns = mc["total_returns"]
                median_sharpe = float(np.median(sharpe_ratios)) if sharpe_ratios else 0.0
                p5 = float(np.percentile(sharpe_ratios, 5)) if sharpe_ratios else 0.0
                p95 = float(np.percentile(sharpe_ratios, 95)) if sharpe_ratios else 0.0

                mc_row = st.columns(5)
                mc_row[0].metric("Med. Sharpe", f"{median_sharpe:.2f}")
                mc_row[1].metric("5th Pctile", f"{p5:.2f}")
                mc_row[2].metric("95th Pctile", f"{p95:.2f}")
                mc_row[3].metric("% Profitable", f"{mc['pct_profitable']:.0%}")
                mc_row[4].metric("Orig. Pctile", f"{mc['original_sharpe_percentile']:.0f}th")

                pnl_values = [CAPITAL * r / 100 for r in total_returns] if total_returns else [0.0]
                fmt = lambda v: f"${v / 1e6:+.1f}M" if abs(v) >= 1e6 else f"${v / 1e3:+,.0f}K"
                pnl_row = st.columns(5)
                pnl_row[0].metric("Med. P&L", fmt(float(np.median(pnl_values))))
                pnl_row[1].metric("5th Pctile", fmt(float(np.percentile(pnl_values, 5))))
                pnl_row[2].metric("95th Pctile", fmt(float(np.percentile(pnl_values, 95))))
                pnl_row[3].metric("Max P&L", fmt(float(np.max(pnl_values))))
                pnl_row[4].metric("Min P&L", fmt(float(np.min(pnl_values))))

                st.markdown("")
                col_sharpe, col_fan = st.columns(2)
                with col_sharpe:
                    show_chart(
                        charts.sharpe_distribution_chart(sharpe_ratios, mc["original_sharpe"]),
                        height=460,
                    )
                with col_fan:
                    show_chart(
                        charts.equity_fan_chart(mc["equity_curves"], mc["original_equity"], CAPITAL),
                        height=460,
                    )

                with st.expander("Re-run with different parameters"):
                    col_ns, col_np, col_run = st.columns([2, 2, 1])
                    with col_ns:
                        noise_scale = st.slider(
                            "Noise Scale", min_value=0.1, max_value=1.0, value=0.5,
                            step=0.1, key=f"noise_{ticker_key}",
                            help="Fraction of daily return std used as noise amplitude.",
                        )
                    with col_np:
                        n_paths = st.slider(
                            "Number of Paths", min_value=100, max_value=1000, value=200,
                            step=100, key=f"paths_{ticker_key}",
                        )
                    with col_run:
                        st.markdown("<div style='height: 1.6rem'></div>", unsafe_allow_html=True)
                        if st.button(
                            "Re-run", key=f"run_mc_{ticker_key}",
                            type="primary", width="stretch",
                        ):
                            with st.spinner(f"Running {n_paths} Monte Carlo paths..."):
                                mc_result = run_monte_carlo(
                                    feature_df,
                                    generate_signal_fn=generate_signal_fn,
                                    n_paths=n_paths,
                                    noise_scale=noise_scale,
                                    capital=CAPITAL,
                                    risk_pct=RISK_PCT,
                                    cost_per_trade=COST_PER_TRADE,
                                )
                            st.session_state[mc_key] = mc_result
                            st.rerun()

            # --- Trade Reordering (Bootstrap) ---
            with stress_tabs[1]:
                st.caption("Reshuffle trade P&Ls to test if drawdown depends on trade ordering.")

                bs_key = f"bootstrap_result_{ticker_key}"
                if bs_key not in st.session_state:
                    with st.spinner("Running 500 bootstrap reshuffles..."):
                        bs_result = run_bootstrap(
                            trade_log, capital=CAPITAL, n_paths=500,
                        )
                    st.session_state[bs_key] = bs_result

                bs = st.session_state[bs_key]
                fmt_dd = lambda v: f"${v / 1e6:.2f}M" if abs(v) >= 1e6 else f"${v / 1e3:,.0f}K"
                bs_row = st.columns(4)
                bs_row[0].metric("Median Max DD", fmt_dd(bs["median_drawdown"]))
                bs_row[1].metric("Actual Max DD", fmt_dd(bs["original_max_drawdown"]))
                bs_row[2].metric("Paths Worse", f"{bs['pct_worse_drawdown']:.0%}")
                bs_row[3].metric("Paths", f"{bs['n_paths']:,}")

                if bs["max_drawdowns"]:
                    show_chart(
                        charts.bootstrap_drawdown_chart(
                            bs["max_drawdowns"], bs["original_max_drawdown"],
                        ),
                        height=460,
                    )

                with st.expander("Re-run bootstrap with different parameters"):
                    col_bp, col_br = st.columns([3, 1])
                    with col_bp:
                        bs_n_paths = st.slider(
                            "Number of Paths", min_value=100, max_value=2000, value=500,
                            step=100, key=f"bs_paths_{ticker_key}",
                        )
                    with col_br:
                        st.markdown("<div style='height: 1.6rem'></div>", unsafe_allow_html=True)
                        if st.button(
                            "Re-run", key=f"run_bs_{ticker_key}",
                            type="primary", width="stretch",
                        ):
                            with st.spinner(f"Running {bs_n_paths} bootstrap reshuffles..."):
                                bs_result = run_bootstrap(
                                    trade_log, capital=CAPITAL, n_paths=bs_n_paths,
                                )
                            st.session_state[bs_key] = bs_result
                            st.rerun()

            # --- Volatility Regime Analysis ---
            with stress_tabs[2]:
                st.caption("Compare performance in high-volatility vs. low-volatility regimes.")

                regime = compute_regime_stats(result_df, trade_log, capital=CAPITAL)

                def _regime_card(label: str, color: str, data: dict) -> str:
                    """Build an HTML card for one volatility regime."""
                    return (
                        f'<div style="background: {BG_CARD}; backdrop-filter: blur(12px); '
                        f'-webkit-backdrop-filter: blur(12px); border-radius: 10px; '
                        f'border: 1px solid {color}33; padding: 1rem 1.25rem; '
                        f'margin-bottom: 0.75rem;">'
                        f'<div style="color: {color}; font-weight: 600; font-size: 1rem; '
                        f'margin-bottom: 0.75rem;">{label}'
                        f'<span style="color: {TEXT_DIM}; font-weight: 400; font-size: 0.82rem; '
                        f'margin-left: 0.5rem;">{data["num_days"]} days</span></div>'
                        f'<div style="display: flex; gap: 1.5rem; flex-wrap: wrap;">'
                        f'<div><div style="color: {TEXT_DIM}; font-size: 0.75rem;">Sharpe</div>'
                        f'<div style="color: {TEXT_PRIMARY}; font-size: 1.1rem; font-weight: 600;">'
                        f'{data["sharpe_ratio"]:.2f}</div></div>'
                        f'<div><div style="color: {TEXT_DIM}; font-size: 0.75rem;">Return</div>'
                        f'<div style="color: {TEXT_PRIMARY}; font-size: 1.1rem; font-weight: 600;">'
                        f'{data["total_return_pct"]:.3f}%</div></div>'
                        f'<div><div style="color: {TEXT_DIM}; font-size: 0.75rem;">Max DD</div>'
                        f'<div style="color: {TEXT_PRIMARY}; font-size: 1.1rem; font-weight: 600;">'
                        f'{data["max_drawdown_pct"]:.3f}%</div></div>'
                        f'<div><div style="color: {TEXT_DIM}; font-size: 0.75rem;">Trades</div>'
                        f'<div style="color: {TEXT_PRIMARY}; font-size: 1.1rem; font-weight: 600;">'
                        f'{data["num_trades"]}</div></div>'
                        f'<div><div style="color: {TEXT_DIM}; font-size: 0.75rem;">Win Rate</div>'
                        f'<div style="color: {TEXT_PRIMARY}; font-size: 1.1rem; font-weight: 600;">'
                        f'{data["win_rate"]:.1%}</div></div>'
                        f'</div></div>'
                    )

                col_hi, col_lo = st.columns(2)
                with col_hi:
                    st.markdown(
                        _regime_card("High Volatility", AMBER, regime["high_vol"]),
                        unsafe_allow_html=True,
                    )
                with col_lo:
                    st.markdown(
                        _regime_card("Low Volatility", ACCENT, regime["low_vol"]),
                        unsafe_allow_html=True,
                    )

                show_chart(charts.regime_comparison_chart(regime), height=460)


# --- Leaderboard drill-down detection ---
leaderboard_run_id = st.session_state.pop("leaderboard_run_id", None)
if leaderboard_run_id:
    app_conn = get_app_connection()
    init_app_tables(app_conn)
    row = load_backtest_run(app_conn, leaderboard_run_id)
    app_conn.close()

    if not row:
        st.error("Leaderboard run not found.")
        st.stop()

    result_df, trade_log, stats = _deserialize_result(row)

    rs = analytics.rolling_sharpe(result_df)
    rw = analytics.rolling_win_rate(trade_log, result_df)
    mr = analytics.monthly_returns(result_df, row["capital"])
    dd = analytics.drawdown_periods(result_df)

    created = row["created_at"][:10]
    st.markdown(
        f'<div style="background: linear-gradient(135deg, {ACCENT_DIM}, rgba(74,155,217,0.10)); '
        f'border: 1px solid {ACCENT}33; border-radius: 10px; padding: 1rem 1.25rem; '
        f'margin-bottom: 1.5rem;">'
        f'<span style="color: {BADGE}; font-weight: 600;">Leaderboard Run</span>'
        f'<span style="color: {TEXT_SECONDARY};"> &mdash; {row["strategy_name"]} on {row["ticker_name"]}'
        f' &mdash; {created} &mdash; by {row["run_by"]}</span></div>',
        unsafe_allow_html=True,
    )
    st.page_link("pages/2_Strategy_Leaderboard.py", label="Back to Strategy Leaderboard")

    _lb_tabs = st.tabs([row["ticker_name"]])
    with _lb_tabs[0]:
        render_results(result_df, trade_log, stats, rs, rw, mr, dd)
    st.stop()

# --- Shared view detection ---
share_id = st.query_params.get("share")
if share_id:
    app_conn = get_app_connection()
    init_app_tables(app_conn)
    row = load_shared_analysis(app_conn, share_id)
    app_conn.close()

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
        f'<div style="background: linear-gradient(135deg, {ACCENT_DIM}, rgba(74,155,217,0.10)); '
        f'border: 1px solid {ACCENT}33; border-radius: 10px; padding: 1rem 1.25rem; '
        f'margin-bottom: 1.5rem;">'
        f'<span style="color: {BADGE}; font-weight: 600;">Shared Analysis</span>'
        f'<span style="color: {TEXT_SECONDARY};"> &mdash; {row["strategy_name"]} on {row["ticker_name"]}'
        f' &mdash; Saved {created}</span></div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<a href="?" style="color: {LINK}; text-decoration: none; font-size: 0.85rem;">'
        f'&larr; Back to Dashboard</a>',
        unsafe_allow_html=True,
    )

    _sv_tabs = st.tabs([row["ticker_name"]])
    with _sv_tabs[0]:
        render_results(result_df, trade_log, stats, rs, rw, mr, dd)
    st.stop()

st.markdown(
    f'<h1 style="font-weight: 600; font-size: 1.8rem; color: {TEXT_PRIMARY};">'
    f'Strategy Backtester</h1>',
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
        f'<p style="color: {TEXT_SECONDARY}; font-size: 0.8rem; margin-top: 0.5rem;">'
        f'{metadata["summary"]}</p>',
        unsafe_allow_html=True,
    )

selected_tickers = st.sidebar.pills(
    "Tickers", list(TICKER_MAP.keys()), default=["Corn"],
    selection_mode="multi",
)

st.sidebar.markdown(
    f'<p style="color: {TEXT_DIM}; font-size: 0.75rem; margin-top: 1rem;">'
    f'Capital: $100M &nbsp;|&nbsp; Risk: 1% &nbsp;|&nbsp; Cost: $0</p>',
    unsafe_allow_html=True,
)

run = st.sidebar.button("Run Backtest", type="primary", width="stretch")


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
            "to enable AI post-mortem analysis (uses web search)."
        )
        return

    if st.sidebar.button("AI Post-Mortem Analysis", width="stretch"):
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
            f'<p style="color: {BADGE}; font-weight: 600; '
            f'margin-top: 1rem;">{name} Post-Mortem</p>',
            unsafe_allow_html=True,
        )

        if pm.get("error"):
            st.sidebar.warning(pm["error"])
            continue

        # Notable trade cards with collapsible analysis
        sections = pm.get("sections", {})
        sec_citations = pm.get("section_citations", {})
        if not pm["trades"].empty:
            for _, t in pm["trades"].iterrows():
                pnl_color = GREEN if t["pnl"] > 0 else RED
                entry_d = pd.to_datetime(t["entry_date"]).strftime("%b %d, %Y")
                exit_d = pd.to_datetime(t["exit_date"]).strftime("%b %d, %Y")
                direction = t.get("direction", "long")
                if direction == "long":
                    action_entry, action_exit = "Bought", "Sold"
                else:
                    action_entry, action_exit = "Shorted", "Covered"
                st.sidebar.markdown(
                    f'<div style="background: {BG_CARD}; '
                    f'backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px); '
                    f'border-radius: 8px; padding: 0.6rem 0.75rem; '
                    f'margin-bottom: 0; border-radius: 8px 8px 0 0; '
                    f'border-left: 3px solid {pnl_color};">'
                    # Label
                    f'<div style="color: {TEXT_PRIMARY}; font-weight: 600; '
                    f'font-size: 0.85rem; margin-bottom: 0.4rem;">{t["label"]}</div>'
                    # Entry row
                    f'<div style="display: flex; justify-content: space-between; '
                    f'margin-bottom: 0.2rem;">'
                    f'<span style="color: {TEXT_SECONDARY}; font-size: 0.78rem;">'
                    f'{action_entry} on {entry_d}</span>'
                    f'<span style="color: {TEXT_PRIMARY}; font-weight: 600; '
                    f'font-size: 0.78rem;">${t["entry_price"]:.2f}</span>'
                    f'</div>'
                    # Exit row
                    f'<div style="display: flex; justify-content: space-between; '
                    f'margin-bottom: 0.35rem;">'
                    f'<span style="color: {TEXT_SECONDARY}; font-size: 0.78rem;">'
                    f'{action_exit} on {exit_d}</span>'
                    f'<span style="color: {pnl_color}; font-weight: 600; '
                    f'font-size: 0.78rem;">${t["exit_price"]:.2f}</span>'
                    f'</div>'
                    # P&L row
                    f'<div style="border-top: 1px solid {BORDER_SUBTLE}; '
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
                # Fuzzy match: the model may add extra text to headings
                label = t["label"]
                section_text = ""
                matched_key = ""
                for sec_key, sec_val in sections.items():
                    if label in sec_key:
                        section_text = sec_val
                        matched_key = sec_key
                        break
                if section_text:
                    with st.sidebar.expander("AI Analysis", expanded=False):
                        st.markdown(section_text)
                        # Sources for this specific trade
                        trade_cites = sec_citations.get(matched_key, [])
                        if trade_cites:
                            links_html = "".join(
                                f'<div style="margin-bottom: 0.25rem;">'
                                f'<a href="{c["url"]}" target="_blank" '
                                f'style="color: {LINK}; font-size: 0.72rem; '
                                f'text-decoration: none;">{c["title"]}</a></div>'
                                for c in trade_cites
                            )
                            st.markdown(
                                f'<div style="border-top: 1px solid '
                                f'{BORDER_SUBTLE}; padding-top: 0.4rem; '
                                f'margin-top: 0.5rem;">'
                                f'<div style="color: {TEXT_SECONDARY}; font-size: 0.72rem; '
                                f'font-weight: 600; margin-bottom: 0.3rem;">'
                                f'Sources</div>{links_html}</div>',
                                unsafe_allow_html=True,
                            )

        # Patterns section at the end
        patterns_text = ""
        for sec_key, sec_val in sections.items():
            if "pattern" in sec_key.lower():
                patterns_text = sec_val
                break
        if patterns_text:
            with st.sidebar.expander("Patterns Across Trades", expanded=False):
                st.markdown(patterns_text)


def load_and_run(ticker: str):
    """Load data, generate signals, run backtest, compute analytics."""
    futures = load_prices(ticker)
    features_config = getattr(strategy_module, "FEATURES", None)

    if not features_config:
        df = futures.loc["2025-01-01":"2025-12-31"]
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
        df = df.loc["2025-01-01":"2025-12-31"]

    feature_df = df.copy()
    df = strategy_module.generate_signal(df)
    result_df, trade_log, stats = run_backtest(
        df, capital=CAPITAL, risk_pct=RISK_PCT, cost_per_trade=COST_PER_TRADE,
    )

    rs = analytics.rolling_sharpe(result_df)
    rw = analytics.rolling_win_rate(trade_log, result_df)
    mr = analytics.monthly_returns(result_df, CAPITAL)
    dd = analytics.drawdown_periods(result_df)

    return result_df, trade_log, stats, rs, rw, mr, dd, feature_df


# --- Paper Upload auto-run detection ---
paper_auto = st.session_state.pop("paper_auto_run", None)
if paper_auto:
    _pa_strategy_name = paper_auto["strategy_name"]
    _pa_ticker_name = paper_auto.get("ticker_name", "Corn")
    _pa_ticker_symbol = TICKER_MAP.get(_pa_ticker_name, "ZC=F")

    if _pa_strategy_name in strategies:
        strategy_module = strategies[_pa_strategy_name]
        selected_name = _pa_strategy_name

        st.markdown(
            f'<div style="background: linear-gradient(135deg, {ACCENT_DIM}, rgba(74,155,217,0.10)); '
            f'border: 1px solid {ACCENT}33; border-radius: 10px; padding: 1rem 1.25rem; '
            f'margin-bottom: 1.5rem;">'
            f'<span style="color: {BADGE}; font-weight: 600;">Paper Strategy</span>'
            f'<span style="color: {TEXT_SECONDARY};"> &mdash; {_pa_strategy_name} on '
            f'{_pa_ticker_name}</span></div>',
            unsafe_allow_html=True,
        )

        with st.spinner("Running backtest..."):
            _pa_res = load_and_run(_pa_ticker_symbol)

        _pa_result_df, _pa_trade_log, _pa_stats = _pa_res[:3]
        _auto_log_run(_pa_strategy_name, strategy_module.__name__,
                      _pa_ticker_symbol, _pa_ticker_name,
                      _pa_result_df, _pa_trade_log, _pa_stats,
                      CAPITAL, RISK_PCT, COST_PER_TRADE, run_type="paper")

        _pa_tabs = st.tabs([_pa_ticker_name])
        with _pa_tabs[0]:
            render_results(
                *_pa_res[:7],
                feature_df=_pa_res[7],
                generate_signal_fn=strategy_module.generate_signal,
                ticker_key=_pa_ticker_name,
            )
        st.stop()
    else:
        st.error(f"Strategy '{_pa_strategy_name}' not found.")

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

    for name in selected_tickers:
        ticker_symbol = TICKER_MAP[name]
        result_df, trade_log, stats = all_results[name][:3]
        _auto_log_run(selected_name, strategy_module.__name__,
                      ticker_symbol, name, result_df, trade_log, stats,
                      CAPITAL, RISK_PCT, COST_PER_TRADE)

_render_postmortem_sidebar()

if "results" not in st.session_state:
    st.markdown(
        f'<p style="color: {TEXT_DIM}; margin-top: 3rem; text-align: center;">'
        f'Select a strategy and click <b>Run Backtest</b> to begin.</p>',
        unsafe_allow_html=True,
    )
    st.stop()

all_results = st.session_state["results"]
ticker_names = st.session_state["ticker_names"]

st.markdown(
    f'<p style="color: {TEXT_DIM}; font-size: 0.85rem; margin-bottom: 1.5rem;">'
    f'{st.session_state["strategy_name"]}</p>',
    unsafe_allow_html=True,
)

tabs = st.tabs(ticker_names)
for tab, name in zip(tabs, ticker_names):
    with tab:
        _, share_col = st.columns([10, 2])
        with share_col:
            if st.button("Share", key=f"share_{name}", width="stretch"):
                sid = uuid.uuid4().hex[:12]
                result_df, trade_log, stats = all_results[name][:3]
                r_json, tl_json, s_json = _serialize_result(result_df, trade_log, stats)
                ticker_symbol = TICKER_MAP.get(name, NAME_TO_SYMBOL.get(name, name))
                app_conn = get_app_connection()
                init_app_tables(app_conn)
                save_shared_analysis(
                    app_conn, sid,
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
                app_conn.close()
                st.session_state[f"shared_id_{name}"] = sid

        if f"shared_id_{name}" in st.session_state:
            with _clipboard_slot:
                _auto_copy_share_link(st.session_state[f"shared_id_{name}"])
            st.toast("Link copied to clipboard!")
            del st.session_state[f"shared_id_{name}"]

        res = all_results[name]
        render_results(
            *res[:7],
            feature_df=res[7],
            generate_signal_fn=strategy_module.generate_signal,
            ticker_key=name,
        )
