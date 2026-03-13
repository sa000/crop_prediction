"""Crop Yield Trading Platform -- Streamlit entry point.

Configures page layout and sidebar branding. Strategy Dashboard and Data
Explorer pages are auto-discovered from the app/pages/ directory."""

import streamlit as st

st.set_page_config(
    page_title="Crop Yield Trading Platform",
    layout="wide",
)

st.sidebar.title("Crop Yield Trading Platform")
st.sidebar.caption("Agricultural commodity futures strategy analysis")

st.title("Crop Yield Trading Platform")

st.markdown(
    """
    Navigate using the sidebar to access:

    - **Strategy Dashboard** -- Run backtests on crop futures strategies,
      view performance metrics, equity curves, and trade logs.
    - **Data Explorer** -- Browse price data, weather data, and engineered
      features from the feature store.
    """
)
