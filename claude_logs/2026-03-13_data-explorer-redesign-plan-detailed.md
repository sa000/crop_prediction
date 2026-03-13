# Data Explorer Redesign -- Detailed Plan

**Date:** 2026-03-13
**Goal:** Restructure the Data Explorer with a Features-first tab and a new Data Catalog tab. Add seasonality profiles, distribution histograms, and summary stats to both tabs.

---

## Current State

The Data Explorer (`app/pages/2_Data_Explorer.py`) has two tabs:
- **Price Data**: Candlestick/line chart for futures tickers
- **Feature Explorer**: AI catalog agent + manual dropdown browse with time series chart

Metadata already stores: `stat_min`, `stat_max`, `stat_mean`, `stat_std`, `null_pct`, `freshness`, `available_from`, `source_table`.

---

## New Tab Structure

```
Data Explorer
  Tab 1: Features        (promoted to first, enhanced)
  Tab 2: Data Catalog    (new -- raw data sources, quality, exploration)
```

---

## Tab 1: Features (Enhanced)

### What stays
- AI catalog agent (text input + results table + click-to-chart)
- Manual dropdown browsing (category / entity / feature selectors)
- Time series line chart for selected feature

### What's added

**A. Summary Stats Card**
When a feature is selected, display a row of metrics above/below the chart:
- Mean, Std Dev, Skew, Kurtosis, Null %, Date Range
- Source data freshness (latest date) -- pulled from metadata.parquet `freshness` column
- Source table tag (e.g., "from futures_daily") -- already in metadata

Skew and kurtosis are NOT currently in metadata. Two options:
1. Compute on the fly from the Parquet data when a feature is selected (simpler, no pipeline change)
2. Add to metadata.parquet in the pipeline

**Decision: Compute on the fly.** The data is already loaded for the chart. Adding `df[feature].skew()` and `df[feature].kurtosis()` is trivial. No pipeline changes needed.

For metadata stats (mean, std, null_pct, freshness), pull from `metadata.parquet` so we don't recompute. For skew/kurtosis, compute from the loaded data.

**B. Seasonality Profile Chart**
New chart: average feature value by month (1-12), aggregated across all years.
- X-axis: Jan through Dec
- Y-axis: average feature value
- Optionally show individual year lines faintly behind the average, or just the average with min/max band
- Implementation: group loaded feature data by month, compute mean

**C. Distribution Histogram**
New chart: histogram of feature values.
- Simple histogram with ~50 bins
- Show vertical lines for mean and +/- 1 std dev
- Complements the summary stats visually

**Layout for B and C:**
After the time series chart, show seasonality and histogram side-by-side in two columns.

---

## Tab 2: Data Catalog

### Purpose
Answer: "What raw data do we ingest, where does it come from, and is it healthy?"

### Data Sources to Display
Read from `etl/scrapers/config.yaml` + query `warehouse.db` for live stats.

**Futures (Yahoo Finance)**:
- For each ticker (corn, soybeans, wheat):
  - Symbol, name, source ("Yahoo Finance")
  - Date range (min/max date from `futures_daily`)
  - Row count
  - Last update date
  - Null % per column
  - Derived features: list from registry's `ticker_feature_map`

**Weather (Open-Meteo)**:
- For each state (Iowa, Illinois, Nebraska):
  - State, coordinates (from config), source ("Open-Meteo")
  - Date range (min/max from `weather_daily`)
  - Row count
  - Last update date
  - Null % per column
  - Derived features: list from registry's `unlinked_features`

### Layout
- Two sections: "Futures" and "Weather", each with an expander or card per entity
- Summary row at top: total data points, overall date range, overall freshness
- Each entity card shows the stats above

### Raw Data Exploration
Within the Data Catalog tab, allow selecting a data source + column to view:
- **Seasonality profile** (same chart type as Features tab)
- **Distribution histogram** (same chart type as Features tab)

This reuses the same chart functions from Features. User picks: source (futures/weather) -> entity (corn/Iowa) -> column (close/precip_in) -> sees seasonality + histogram.

---

## File Changes

### `app/charts.py` -- Add 2 new chart functions

1. **`seasonality_chart(df, date_col, value_col, title)`**
   - Groups by month, computes mean
   - Bar chart or line chart with month labels on x-axis
   - Returns Plotly Figure

2. **`distribution_chart(df, value_col, title, mean_val, std_val)`**
   - Histogram with ~50 bins
   - Vertical lines at mean and +/- 1 std
   - Returns Plotly Figure

### `app/pages/2_Data_Explorer.py` -- Restructure

1. Change tabs from `["Price Data", "Feature Explorer"]` to `["Features", "Data Catalog"]`
2. Move all Feature Explorer content into the first tab
3. Add stats card, seasonality, and histogram to Features tab
4. Build Data Catalog tab:
   - Query warehouse.db for source stats
   - Read scraper config for source metadata
   - Read registry for feature-to-source mappings
   - Render source cards with stats
   - Add raw data exploration with seasonality + histogram

### `etl/db.py` -- Add helper query function

Add `source_summary()` function that returns date range, row count, null counts per column for a given table + entity. Used by the Data Catalog tab.

### `app/Home.py` -- Update card description

Update the Data Explorer card description to mention both features and data catalog.

---

## New Dependencies
None. Uses existing Plotly, pandas, sqlite3.

---

## Edge Cases
- Empty feature data: show "No data" message, skip stats/charts
- Weather aggregation entity (corn_belt): handle as a virtual entity in the catalog -- it's derived, not a raw source
- Null handling in seasonality: drop NaN before grouping by month
- Skew/kurtosis on constant series: handle gracefully (returns 0/NaN)

---

## Verification
1. Run `python -m pytest tests/ -v` -- all existing tests pass
2. Run the Streamlit app locally and verify:
   - Features tab loads with all existing functionality intact
   - Selecting a feature shows stats card, seasonality chart, histogram
   - Data Catalog tab shows all sources with correct stats
   - Raw data exploration works in Data Catalog
3. No hardcoded paths or configuration in app code
