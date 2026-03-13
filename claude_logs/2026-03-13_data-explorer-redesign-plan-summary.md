# Data Explorer Redesign -- Summary Plan

**Date:** 2026-03-13
**Goal:** Restructure the Data Explorer with Features-first tab + new Data Catalog tab. Add seasonality profiles, distribution histograms, and summary stats.

---

## New Tab Structure

```
Data Explorer
  Tab 1: Features       (current Feature Explorer, enhanced)
  Tab 2: Data Catalog   (new -- raw data sources + quality + exploration)
```

## Key Changes

### Features Tab (enhanced)
- **Summary stats card**: mean, std, skew, kurtosis, null%, date range, freshness, source table
- **Seasonality profile chart**: avg feature value by month across all years
- **Distribution histogram**: histogram of values with mean / +/-1 std lines
- All existing functionality (AI catalog, manual browse, time series chart) preserved

### Data Catalog Tab (new)
- **Source cards** for each data source (Yahoo Finance futures, Open-Meteo weather)
- Per entity: date range, row count, last update, null% per column, derived features list
- **Raw data exploration**: pick a source + column, see seasonality + histogram (same chart types as Features tab)
- Data quality info lives here (freshness, gaps, nulls), not on Features tab
- Features tagged with source + freshness so users know where data comes from

### Files Modified
| File | Change |
|------|--------|
| `app/charts.py` | Add `seasonality_chart()` and `distribution_chart()` |
| `app/pages/2_Data_Explorer.py` | Restructure tabs, add stats/seasonality/histogram to Features, build Data Catalog tab |
| `etl/db.py` | Add `source_summary()` helper for catalog stats |
| `app/Home.py` | Update Data Explorer card description |
