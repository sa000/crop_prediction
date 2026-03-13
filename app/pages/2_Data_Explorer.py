"""Data Explorer -- browse price, weather, and feature data.

Placeholder page. Full implementation in Phase 5c."""

import streamlit as st

st.title("Data Explorer")

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
