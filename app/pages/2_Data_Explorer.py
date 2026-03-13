"""Data Explorer -- browse price, weather, and feature data.

Placeholder page. Full implementation in Phase 5c."""

import sys
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.style import inject_css, sidebar_logo

inject_css()
sidebar_logo()

st.markdown(
    '<h1 style="font-weight: 600; font-size: 1.8rem; color: #e2e8f0;">'
    'Data Explorer</h1>',
    unsafe_allow_html=True,
)

tab_price, tab_features, tab_weather = st.tabs(["Price Data", "Feature Explorer", "Weather Data"])

with tab_price:
    ticker = st.selectbox("Ticker", ["corn", "soybeans", "wheat"], key="price_ticker")
    st.info(f"Price chart for {ticker} will be added in Phase 5c.")

with tab_features:
    category = st.selectbox("Category", ["momentum", "mean_reversion", "weather"], key="feat_category")
    st.info(f"Feature explorer for {category} will be added in Phase 5c.")

with tab_weather:
    region = st.selectbox("Region", ["corn_belt"], key="weather_region")
    st.info(f"Weather summary for {region} will be added in Phase 5c.")
