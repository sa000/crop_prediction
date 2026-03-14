"""Crop Yield Trading Platform -- Streamlit entry point.

Configures page layout, applies dark theme styling, and renders the
landing page with Trex Quant branding."""

import sys
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.style import inject_css, sidebar_logo

st.set_page_config(
    page_title="Trexquant",
    page_icon=str(PROJECT_ROOT / "trexquant_logo.png"),
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_css()
sidebar_logo()

st.markdown(
    """
    <div style="text-align: center; padding: 3rem 0 1rem 0;">
        <h1 style="font-weight: 600; font-size: 2.2rem; color: #e2e8f0;
                    margin-bottom: 0.3rem;">
            Crop Yield Trading Platform
        </h1>
        <p style="color: #94a3b8; font-size: 1rem; margin-bottom: 2rem;">
            Agricultural commodity futures strategy analysis
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

col1, col2 = st.columns(2)

with col1:
    st.markdown(
        """
        <div style="background: #1a1b2e; border: 1px solid rgba(59,130,246,0.2);
                    border-radius: 10px; padding: 1.5rem; height: 160px;">
            <h3 style="color: #3B82F6; font-size: 1.1rem; margin: 0 0 0.5rem 0;
                        border: none; padding: 0;">
                Strategy Dashboard
            </h3>
            <p style="color: #94a3b8; font-size: 0.9rem; line-height: 1.5;">
                Run backtests on crop futures strategies. View equity curves,
                risk metrics, trade signals, and Monte Carlo stress tests.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

with col2:
    st.markdown(
        """
        <div style="background: #1a1b2e; border: 1px solid rgba(59,130,246,0.2);
                    border-radius: 10px; padding: 1.5rem; height: 160px;">
            <h3 style="color: #3B82F6; font-size: 1.1rem; margin: 0 0 0.5rem 0;
                        border: none; padding: 0;">
                Data Explorer
            </h3>
            <p style="color: #94a3b8; font-size: 0.9rem; line-height: 1.5;">
                Browse engineered features with stats, seasonality, and
                distributions. Explore raw data sources and quality metrics.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.markdown(
    """
    <p style="text-align: center; color: #475569; font-size: 0.75rem;
              margin-top: 3rem;">
        Navigate using the sidebar
    </p>
    """,
    unsafe_allow_html=True,
)
