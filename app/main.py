"""The Cortex -- Streamlit entry point.

Configures page layout, applies dark theme styling, and renders the
landing page with TREXQUANT branding plus clickable quick-nav cards."""

import sys
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import base64

from app.style import (
    inject_css, sidebar_logo,
    ACCENT, BG_CARD, BG_CARD_HOVER, BG_CARD_SOLID, BORDER, BORDER_SUBTLE,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_DIM, TEXT_FAINT,
)

st.set_page_config(
    page_title="The Cortex | TREXQUANT",
    page_icon=str(PROJECT_ROOT / "logo.png"),
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_css()
sidebar_logo()

# ---------------------------------------------------------------------------
# Hero
# ---------------------------------------------------------------------------
_logo_path = PROJECT_ROOT / "logo.png"
_logo_b64 = ""
if _logo_path.exists():
    _logo_b64 = base64.b64encode(_logo_path.read_bytes()).decode()

_logo_html = (
    f'<img src="data:image/png;base64,{_logo_b64}" width="56" '
    f'style="border-radius: 8px; vertical-align: middle; margin-right: 14px;" />'
    if _logo_b64 else ""
)

st.markdown(
    f"""
    <div style="text-align: center; padding: 3rem 0 1rem 0;">
        <div style="display: inline-flex; align-items: center; justify-content: center;
                    margin-bottom: 0.3rem;">
            {_logo_html}
            <h1 class="hero-gradient" style="font-weight: 700; font-size: 2.2rem;
                        margin: 0;">
                The Cortex
            </h1>
        </div>
        <p style="color: {TEXT_SECONDARY}; font-size: 1rem; margin-bottom: 2rem;">
            Analyze strategies, run backtests, and extract alpha from research papers
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Quick-nav cards (clickable)
# ---------------------------------------------------------------------------
NAV_CARDS = [
    ("Strategy Dashboard",
     "Run backtests on crop futures strategies. View equity curves, "
     "risk metrics, trade signals, and Monte Carlo stress tests.",
     "pages/1_Strategy_Dashboard.py"),
    ("Data Explorer",
     "Browse engineered features with stats, seasonality, and "
     "distributions. Explore raw data sources and quality metrics.",
     "pages/2_Data_Explorer.py"),
    ("Paper Upload",
     "Extract trading strategies from research papers. Map features "
     "to available data and generate runnable strategy modules.",
     "pages/3_Paper_Upload.py"),
    ("Strategy Leaderboard",
     "Browse, filter, and compare all backtest runs across strategies "
     "and tickers. Star top performers and drill into saved results.",
     "pages/4_Strategy_Leaderboard.py"),
    ("AI Usage",
     "Track API costs, token consumption, and call history across "
     "Claude and DeepSeek, broken down by day, model, and function.",
     "pages/5_AI_Usage.py"),
]

_CARD_CSS = (
    f"background: {BG_CARD}; backdrop-filter: blur(12px); "
    f"-webkit-backdrop-filter: blur(12px); border: 1px solid {BORDER}; "
    f"border-radius: 12px; padding: 1.5rem; height: 140px; "
    f"transition: background 0.2s ease, border-color 0.2s ease; cursor: pointer;"
)
_HOVER_ON = f"this.style.background='{BG_CARD_HOVER}'; this.style.borderColor='rgba(148,163,184,0.14)'"
_HOVER_OFF = f"this.style.background='{BG_CARD}'; this.style.borderColor='{BORDER}'"

row1 = st.columns(3)
row2 = st.columns(3)
all_cols = row1 + row2

for col, (title, desc, page) in zip(all_cols, NAV_CARDS):
    with col:
        st.markdown(
            f'<div style="{_CARD_CSS}" '
            f'onmouseover="{_HOVER_ON}" onmouseout="{_HOVER_OFF}">'
            f'<h3 style="color: {ACCENT}; font-size: 1.1rem; margin: 0 0 0.5rem 0; '
            f'border: none; padding: 0;">{title}</h3>'
            f'<p style="color: {TEXT_SECONDARY}; font-size: 0.88rem; line-height: 1.5; '
            f'margin: 0;">{desc}</p></div>',
            unsafe_allow_html=True,
        )
        st.page_link(page, label=f"Open {title}", width="stretch")

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------
st.markdown(
    f"""
    <p style="text-align: center; color: {TEXT_FAINT}; font-size: 0.75rem;
              margin-top: 3rem;">
        Navigate using the sidebar or the cards above
    </p>
    """,
    unsafe_allow_html=True,
)
