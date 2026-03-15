# Paper-to-Strategy Pipeline — Detailed Plan

**Date:** 2026-03-14
**Status:** Implemented

---

## Context

Quants read research papers describing alpha strategies, then manually translate them into code. This feature automates that workflow: upload a paper, extract the strategy, map it to our data, and generate a runnable strategy module — all with human-in-the-loop checkpoints so the quant stays in control.

**Core principle:** If we have the raw data, we can derive any feature the paper describes. The system should generate the derivation code and let the quant verify it. It should never force the user to accept an approximation when an exact derivation is possible.

---

## Feature Classification (Three Buckets)

Every feature the paper requires falls into one of three buckets:

```
┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│  1. IN STORE         Paper wants "30-day precip z-score"            │
│     Feature already   We have: precip_anomaly_30d                   │
│     exists in our     → Use it directly. No code needed.            │
│     feature store                                                   │
│                                                                     │
│  2. DERIVABLE        Paper wants "8-day rolling precipitation"      │
│     Raw data exists   We have: precip_in (daily) in warehouse       │
│     in warehouse,     → Generate: df["precip_in"].rolling(8).sum()  │
│     just needs        The quant reviews the derivation code.        │
│     computation                                                     │
│                                                                     │
│  3. NOT POSSIBLE     Paper wants "soil moisture index"              │
│     We don't have     We have: no soil data anywhere                │
│     the raw data      → Flag it. Quant decides to skip or source    │
│     at all              the data separately.                        │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

**Why this matters:** The old design would have said "8-day precip ≈ 7-day precip (approximate match)." That's wrong. We have daily `precip_in` in `weather_daily` — we can compute the exact 8-day rolling sum. The system should know that and generate the code.

---

## What Raw Data Do We Have?

The mapper needs to know what's in the warehouse to assess derivability:

```
┌─────────────────────────────────────────────────────────────────────┐
│  futures_daily (source: Yahoo Finance)                              │
│  ├── date, ticker                                                   │
│  ├── open, high, low, close, volume                                 │
│  └── tickers: ZC=F (corn), ZS=F (soybeans), ZW=F (wheat)           │
│                                                                     │
│  weather_daily (source: Open-Meteo)                                 │
│  ├── date, state                                                    │
│  ├── temp_max_f, temp_min_f, precip_in                              │
│  └── states: Iowa, Illinois, Nebraska                               │
│       (aggregation: corn_belt = mean of all three)                  │
└─────────────────────────────────────────────────────────────────────┘
```

**Price columns available in strategy DataFrame:** `Close` is always present (loaded by `load_prices()`). `Open`, `High`, `Low`, `Volume` are also there.

**Weather columns NOT in strategy DataFrame:** Raw weather (`precip_in`, `temp_max_f`, `temp_min_f`) is in `warehouse.db` but not in feature Parquet files (`include_columns: []`). Generated code loads via `etl.db.load_raw_data()`.

---

## Available Compute Functions (for derivation awareness)

The mapper/generator should know what transformations exist in `features/compute/`:

```
momentum:       sma, ema, macd, macd_signal, rsi
mean_reversion: bollinger_upper, bollinger_lower, zscore, pct_rank
weather:        rolling_sum, rolling_mean, rolling_mean_diff, rolling_zscore
```

These are reference — the generated code can use these OR plain pandas operations. The quant sees exactly what computation is being done.

---

## User Workflow (Visual)

### Page Layout — Vertical Stepper

```
┌─────────────────────────────────────────────────────────────────────┐
│  Paper Upload                                               Page 3  │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─ Step 1: Upload Paper ──────────────────────────────────────┐   │
│  │                                                              │   │
│  │  [  Upload PDF  ]    — or —    [Paste text directly]         │   │
│  │                                                              │   │
│  │  ┌──────────────────────────────────────────────────────┐    │   │
│  │  │  smith_et_al_2024_drought_alpha.pdf                  │    │   │
│  │  │  12 pages · uploaded                                 │    │   │
│  │  └──────────────────────────────────────────────────────┘    │   │
│  │                                                              │   │
│  │  [ Extract Strategy → ]                                      │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─ Step 2: Review Extracted Strategy (locked until Step 1) ───┐   │
│  │   ...appears after extraction...                             │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─ Step 3: Feature Feasibility (locked until Step 2) ─────────┐   │
│  │   ...                                                        │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─ Step 4: Review & Edit Code (locked until Step 3) ──────────┐   │
│  │   ...                                                        │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─ Step 5: Save & Backtest (locked until Step 4) ─────────────┐   │
│  │   ...                                                        │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Step 1 → Step 2: Extraction Complete

AI parses the paper. Note: the extractor does NOT classify features into our internal categories. It just describes what the paper says — what data is needed, how it's computed, and its role in the signal. The mapper handles the classification later.

```
┌─ Step 2: Review Extracted Strategy ────────────────────────────────┐
│                                                                     │
│  Strategy Name:  [ Drought Corn Alpha          ]  (editable)        │
│                                                                     │
│  Thesis:                                                            │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ Corn prices rise during drought and extreme flood events     │   │
│  │ because both threaten crop supply. The strategy goes long    │   │
│  │ when precipitation anomalies indicate stress and short       │   │
│  │ during normal weather.                                       │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  Required Features:                                                 │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  #  │ Feature            │ Raw Data Needed  │ Computation    │   │
│  │ ────┼────────────────────┼──────────────────┼────────────────│   │
│  │  1  │ 8d rolling precip  │ daily precip     │ 8-day sum      │   │
│  │  2  │ 30d precip z-score │ daily precip     │ 30-day z-score │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  Signal Rules:                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  Condition                │ Signal │ Rationale                │   │
│  │ ──────────────────────────┼────────┼──────────────────────────│   │
│  │  precip_z < -1.5         │  +1    │ Drought → supply threat  │   │
│  │  precip_z > 2.0          │  +1    │ Flood → supply threat    │   │
│  │  -0.3 < precip_z < 0.3   │  -1    │ Normal → no threat       │   │
│  │  else                     │   0    │ Ambiguous zone           │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  Parameters:                                                        │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  drought_threshold = [ -1.5 ]                                │   │
│  │  flood_threshold   = [  2.0 ]                                │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  Target Assets: [ Corn futures ]                                    │
│                                                                     │
│  [ ← Re-extract ]                      [ Approve & Map Features → ] │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

Everything is editable — name, thesis, features, rules, parameters. The quant verifies: "Did the AI correctly read the paper?"

### Step 2 → Step 3: Feature Feasibility

The mapper checks each feature against (1) the feature store, then (2) raw data in the warehouse. This step uses AI to assess derivability — a focused call with our data catalog as context, not open-ended generation.

```
┌─ Step 3: Feature Feasibility ──────────────────────────────────────┐
│                                                                     │
│  Coverage: 2 of 2 features resolved                                 │
│  Feasibility: FEASIBLE                                              │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                                                             │   │
│  │  Feature 1: "30d precip z-score"                            │   │
│  │  Status: IN STORE                                           │   │
│  │                                                             │   │
│  │  Matched to: corn_belt_precip_anomaly_30d                   │   │
│  │  Source: weather / corn_belt                                 │   │
│  │  Reason: 30-day rolling z-score of precipitation —          │   │
│  │          exact match on computation and window              │   │
│  │                                                             │   │
│  │  [✓ Use this feature]                                       │   │
│  │                                                             │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                                                             │   │
│  │  Feature 2: "8d rolling precip"                             │   │
│  │  Status: DERIVABLE                                          │   │
│  │                                                             │   │
│  │  Raw data: precip_in (daily, in weather_daily)              │   │
│  │  Computation: 8-day rolling sum of precip_in                │   │
│  │  Region: Corn Belt (mean of Iowa, Illinois, Nebraska)       │   │
│  │                                                             │   │
│  │  Derivation code preview:                                   │   │
│  │  ┌──────────────────────────────────────────────────────┐   │   │
│  │  │  # Load raw weather, aggregate to Corn Belt          │   │   │
│  │  │  weather = load_raw_data("weather_daily", ...)       │   │   │
│  │  │  corn_belt = weather.groupby("date")["precip_in"]    │   │   │
│  │  │                      .mean()                         │   │   │
│  │  │  # 8-day rolling sum                                 │   │   │
│  │  │  precip_8d = corn_belt.rolling(8).sum()              │   │   │
│  │  └──────────────────────────────────────────────────────┘   │   │
│  │                                                             │   │
│  │  [✓ Derive this feature]    [ ] Skip                        │   │
│  │                                                             │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  (If any features were NOT POSSIBLE, they would appear here         │
│   with a red badge and explanation of what raw data is missing.)    │
│                                                                     │
│  Resolved Summary:                                                  │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  Paper Feature       →  Resolution                   Status  │   │
│  │  ──────────────────────────────────────────────────────────  │   │
│  │  30d precip z-score  →  corn_belt_precip_anomaly_30d  STORE  │   │
│  │  8d rolling precip   →  derive from precip_in      DERIVED   │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  [ ← Back to Spec ]                       [ Generate Strategy → ]   │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

**Key difference from previous plan:** The quant sees the DERIVATION CODE PREVIEW for derivable features. They verify "yes, an 8-day rolling sum of precip_in is what the paper means" before any strategy code is generated.

### Step 3 → Step 4: Code Generation

AI generates a complete strategy module. For "in store" features, it references column names from the feature store. For "derivable" features, it includes the inline derivation code at the top of `generate_signal`:

```
┌─ Step 4: Review & Edit Code ───────────────────────────────────────┐
│                                                                     │
│  Generated strategy: drought_corn_alpha.py                          │
│  File will be saved to: strategies/drought_corn_alpha.py            │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  1  """Drought Corn Alpha — extracted from Smith et al.      │   │
│  │  2                                                           │   │
│  │  3  Corn prices rise during drought and extreme flood...     │   │
│  │  4  """                                                      │   │
│  │  5                                                           │   │
│  │  6  import pandas as pd                                      │   │
│  │  7  from etl.db import load_raw_data                         │   │
│  │  8                                                           │   │
│  │  9  DROUGHT_THRESHOLD = -1.5                                 │   │
│  │ 10  FLOOD_THRESHOLD = 2.0                                    │   │
│  │ 11  NORMAL_LOW = -0.3                                        │   │
│  │ 12  NORMAL_HIGH = 0.3                                        │   │
│  │ 13                                                           │   │
│  │ 14  FEATURES = {                                             │   │
│  │ 15      "ticker_categories": [],                             │   │
│  │ 16      "unlinked": [                                        │   │
│  │ 17          {"category": "weather", "entity": "corn_belt"}   │   │
│  │ 18      ],                                                   │   │
│  │ 19  }                                                        │   │
│  │ 20                                                           │   │
│  │ 21  SUMMARY = "Long on drought/flood precipitation..."       │   │
│  │ 22                                                           │   │
│  │ 23                                                           │   │
│  │ 24  def _load_corn_belt_precip():                            │   │
│  │ 25      """Load raw daily precip, aggregate to Corn Belt."""  │   │
│  │ 26      frames = []                                          │   │
│  │ 27      for state in ["Iowa", "Illinois", "Nebraska"]:       │   │
│  │ 28          raw = load_raw_data(                              │   │
│  │ 29              "weather_daily", "state", state              │   │
│  │ 30          )                                                │   │
│  │ 31          frames.append(raw[["date", "precip_in"]])        │   │
│  │ 32      combined = pd.concat(frames)                         │   │
│  │ 33      return combined.groupby("date")["precip_in"].mean()  │   │
│  │ 34                                                           │   │
│  │ 35                                                           │   │
│  │ 36  def generate_signal(df):                                 │   │
│  │ 37      df = df.copy()                                       │   │
│  │ 38                                                           │   │
│  │ 39      # --- Derived feature: 8-day rolling precip ---      │   │
│  │ 40      precip_daily = _load_corn_belt_precip()              │   │
│  │ 41      precip_8d = precip_daily.rolling(8).sum()            │   │
│  │ 42      df = df.join(precip_8d.rename("precip_8d"))          │   │
│  │ 43                                                           │   │
│  │ 44      # --- From feature store ---                         │   │
│  │ 45      anomaly = df["corn_belt_precip_anomaly_30d"]         │   │
│  │ 46                                                           │   │
│  │ 47      # --- Signal logic ---                               │   │
│  │ 48      df["signal"] = 0                                     │   │
│  │ 49      df.loc[anomaly < DROUGHT_THRESHOLD, "signal"] = 1    │   │
│  │ 50      df.loc[anomaly > FLOOD_THRESHOLD, "signal"] = 1      │   │
│  │ 51      mask = (anomaly > NORMAL_LOW) & (anomaly < ...)      │   │
│  │ 52      df.loc[mask, "signal"] = -1                          │   │
│  │ 53      df.loc[anomaly.isna(), "signal"] = 0                 │   │
│  │ 54      return df                                            │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  You can edit the code directly above before saving.                │
│                                                                     │
│  [ ← Back to Mapping ]                   [ Save Strategy → ]        │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

The quant sees exactly:
- Which features come from the store (line 45)
- Which features are derived inline and how (lines 24-42)
- The signal logic (lines 48-53)
- All parameters as editable module constants (lines 9-12)

### Step 5: Save & Backtest

```
┌─ Step 5: Save & Backtest ──────────────────────────────────────────┐
│                                                                     │
│  Strategy saved to strategies/drought_corn_alpha.py                 │
│                                                                     │
│  The strategy is now available in the Strategy Dashboard.           │
│  Select "Drought Corn Alpha" from the sidebar to backtest it.      │
│                                                                     │
│  [ Open Strategy Dashboard → ]                                      │
│                                                                     │
│  ── Generation Log ──────────────────────────────────────────────   │
│  │ Source: smith_et_al_2024_drought_alpha.pdf                   │   │
│  │ Features from store: corn_belt_precip_anomaly_30d            │   │
│  │ Features derived: precip_8d (8-day rolling sum of precip_in) │   │
│  │ Skipped features: none                                       │   │
│  │ Not possible: none                                           │   │
│  │ Generated: 2026-03-14 14:32 UTC                              │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Data Flow Diagram

```
                         ┌──────────────────┐
                         │   PDF / Text      │
                         │   (user upload)   │
                         └────────┬─────────┘
                                  │
                    ──────────────▼──────────────
                   │  STAGE 1: extractor.py      │
                   │  Claude Sonnet               │
                   │  PDF text → strategy spec    │
                   │  (features described as-is,  │
                   │   NOT classified into our    │
                   │   internal categories)       │
                    ──────────────┬──────────────
                                  │
                         ┌────────▼─────────┐
                         │  Strategy Spec    │◄──── Quant reviews & edits
                         │  (JSON in state)  │      name, features, rules, params
                         └────────┬─────────┘
                                  │
                    ──────────────▼──────────────
                   │  STAGE 2: mapper.py          │
                   │  AI-assisted feasibility      │
                   │                               │
                   │  For each feature:            │
                   │  1. Check feature store       │
                   │     → IN STORE                │
                   │  2. Check raw data warehouse  │
                   │     → DERIVABLE (+ code plan) │
                   │  3. Neither available          │
                   │     → NOT POSSIBLE            │
                    ──────────────┬──────────────
                                  │
                         ┌────────▼─────────┐
                         │  Feasibility      │◄──── Quant verifies each mapping
                         │  Report           │      and derivation plan
                         └────────┬─────────┘
                                  │
                    ──────────────▼──────────────
                   │  STAGE 3: generator.py       │
                   │  Claude Sonnet               │
                   │  spec + resolved map          │
                   │  → Python strategy module     │
                   │                               │
                   │  IN STORE features:           │
                   │    reference column names     │
                   │  DERIVABLE features:          │
                   │    inline compute code using  │
                   │    etl.db.load_raw_data()     │
                    ──────────────┬──────────────
                                  │
                         ┌────────▼─────────┐
                         │  Generated .py    │◄──── Quant reviews & edits
                         │  (code string)    │      full strategy code
                         └────────┬─────────┘
                                  │
                    ──────────────▼──────────────
                   │  STAGE 4: Save to disk       │
                   │  strategies/<name>.py         │
                   │  Auto-discovered by           │
                   │  app/discovery.py             │
                    ──────────────┬──────────────
                                  │
                         ┌────────▼─────────┐
                         │  Strategy Dashboard │
                         │  (backtest ready)   │
                         └─────────────────────┘
```

---

## Module Architecture

```
app/
  paper_agent/
    __init__.py           # Package init
    extractor.py          # Stage 1: PDF → strategy spec
    mapper.py             # Stage 2: spec → feasibility report
    generator.py          # Stage 3: spec + map → Python strategy code
  pages/
    3_Paper_Upload.py     # Streamlit UI — orchestrates all stages
```

### extractor.py — Paper Parsing & Strategy Extraction

**Responsibilities:**
- Parse PDF text (pdfplumber) or accept raw text
- Send to Claude with structured extraction prompt
- Return a validated strategy spec dict

**Interface:**
```python
def extract_text_from_pdf(uploaded_file) -> str:
    """Extract plain text from uploaded PDF bytes."""

def extract_strategy(paper_text: str, api_key: str) -> dict:
    """Send paper text to Claude, return structured strategy spec.

    Returns:
        {
            "title": str,
            "thesis": str,
            "required_features": [
                {
                    "name": str,              # descriptive name from paper
                    "description": str,        # what the feature represents
                    "raw_data_needed": str,    # e.g. "daily precipitation"
                    "computation": str,        # e.g. "8-day rolling sum"
                    "parameters": dict,        # e.g. {"window": 8}
                    "role": str               # "signal" | "filter" | "exit"
                }
            ],
            "signal_rules": [
                {
                    "condition": str,
                    "signal": int,            # +1, -1, or 0
                    "rationale": str
                }
            ],
            "parameters": dict,               # named thresholds/constants
            "target_assets": list[str],
            "confidence_notes": str
        }
    """
```

**Key design choice:** The extractor does NOT classify features into our internal categories (momentum/weather/mean_reversion). It describes features as the paper describes them — what raw data they need and how they're computed. The mapper handles the rest.

**Model:** Claude Sonnet — needs strong reading comprehension for research papers.

**System prompt design:**
- Constrain output to JSON schema above
- Instruct: describe features in terms of what raw data they need and what computation is applied
- Instruct: only extract what the paper explicitly describes, do not invent
- Instruct: note any ambiguities in `confidence_notes`

### mapper.py — Feature Mapping & Feasibility

**Responsibilities:**
- For each extracted feature, check:
  1. Does it exist in the feature store? (check `features/registry.yaml`)
  2. Can it be derived from raw data in the warehouse? (check warehouse schema)
  3. Neither? → not possible
- For derivable features, produce a derivation plan (raw column, computation, code sketch)
- Return a structured feasibility report

**Interface:**
```python
def build_data_catalog() -> dict:
    """Build a catalog of all available data for feasibility checks.

    Returns:
        {
            "feature_store": {
                "features": [...],               # from registry.yaml
                "categories": ["momentum", ...],
            },
            "warehouse": {
                "futures_daily": {
                    "columns": ["open", "high", "low", "close", "volume"],
                    "entities": {"ticker": ["ZC=F", "ZS=F", "ZW=F"]},
                },
                "weather_daily": {
                    "columns": ["temp_max_f", "temp_min_f", "precip_in"],
                    "entities": {"state": ["Iowa", "Illinois", "Nebraska"]},
                    "aggregations": {"corn_belt": ["Iowa", "Illinois", "Nebraska"]},
                },
            },
            "compute_functions": [
                "rolling_sum", "rolling_mean", "rolling_zscore",
                "sma", "ema", "rsi", "macd", "bollinger", "zscore", ...
            ],
        }
    """

def map_features(spec: dict, api_key: str) -> dict:
    """Classify each required feature and produce a feasibility report.

    Uses AI to match paper features against our data catalog.
    The AI is given a constrained context (our catalog) and returns
    structured classifications.

    Returns:
        {
            "features": [
                {
                    "paper_feature": str,
                    "status": "in_store" | "derivable" | "not_possible",

                    # For in_store:
                    "store_feature": str | None,
                    "store_category": str | None,
                    "store_entity": str | None,
                    "match_reason": str | None,

                    # For derivable:
                    "raw_table": str | None,
                    "raw_column": str | None,
                    "raw_entity": str | None,
                    "derivation": str | None,       # human-readable
                    "derivation_code": str | None,   # code preview

                    # For not_possible:
                    "reason": str | None,
                }
            ],
            "feasible": bool,            # True if all signal-role features resolved
            "store_count": int,
            "derivable_count": int,
            "not_possible_count": int,
        }
    """
```

**Why AI-assisted (not purely deterministic):** The paper might describe a feature as "8-day cumulative rainfall over the central Corn Belt." A deterministic string matcher would struggle to connect that to `precip_in` in `weather_daily` for Iowa/Illinois/Nebraska averaged as Corn Belt. A focused AI call with our data catalog as context handles this reliably. The AI's answer is still constrained — it can only reference data from our catalog.

### generator.py — Strategy Code Generation

**Responsibilities:**
- Take the strategy spec + feasibility report (with quant's approvals)
- Generate a complete Python strategy module
- For "in_store" features: reference the column name from the feature store
- For "derivable" features: generate inline computation using `etl.db.load_raw_data()`
- Include proper FEATURES dict, SUMMARY, parameters, generate_signal()

**Interface:**
```python
def generate_strategy_code(
    spec: dict,
    feasibility: dict,
    api_key: str,
) -> str:
    """Generate a strategy module from the spec and feasibility report.

    Args:
        spec: Strategy spec from extractor (with quant edits).
        feasibility: Feasibility report from mapper (with quant approvals).
        api_key: Anthropic API key.

    Returns:
        Complete Python source code as a string.
    """
```

**Model:** Claude Sonnet.

**Prompt includes:**
- An example strategy (weather_precipitation.py) as a template for the interface
- The exact interface contract: `generate_signal(df) → df` with signal column
- The resolved feature map (which features from store, which to derive)
- The derivation code previews from the feasibility report
- Available infrastructure: `etl.db.load_raw_data(table, entity_col, entity_val)`
- Signal rules and parameters from the spec

**Code structure the AI generates:**
```python
"""Strategy docstring with paper attribution."""

import pandas as pd
from etl.db import load_raw_data     # only if derivable features exist

# Parameters
THRESHOLD_A = ...
THRESHOLD_B = ...

# Feature store declaration (for features from store)
FEATURES = {
    "ticker_categories": [...],
    "unlinked": [...],
}

SUMMARY = "..."

# Helper for derived features (if any)
def _derive_features():
    """Load raw data and compute derived features."""
    ...

def generate_signal(df):
    """Generate signal from paper's logic."""
    df = df.copy()

    # Derived features (loaded from warehouse, computed inline)
    ...

    # Features from store (already in df)
    ...

    # Signal logic
    df["signal"] = 0
    ...
    return df
```

### 3_Paper_Upload.py — Streamlit Page

**Responsibilities:**
- Orchestrate the pipeline stages via session state
- Render each stage as a collapsible section
- Handle user edits between stages
- Save final code to disk

**Session state keys:**
```python
st.session_state["paper_step"]          # current step (1-5)
st.session_state["paper_text"]          # raw text from PDF or paste
st.session_state["paper_spec"]          # extracted strategy spec (dict)
st.session_state["paper_feasibility"]   # feasibility report (dict)
st.session_state["paper_approvals"]     # quant's per-feature decisions
st.session_state["paper_code"]          # generated Python code (str)
st.session_state["paper_saved_path"]    # path where strategy was saved
```

**Step invalidation:** Changing a step clears all downstream state. E.g., re-extracting clears feasibility, approvals, code, and saved path.

---

## Design Decisions

1. **Three-bucket classification, not two.** "Approximate match" is a false category. If we have the raw data, we derive the exact feature. If we don't, it's not possible. There's no middle ground to fudge.

2. **AI-assisted mapping.** The feature store is small (~18 features) and the warehouse schema is small (8 columns). But the paper's language can be varied — "8-day cumulative rainfall" needs semantic matching to `precip_in` + `rolling_sum`. A focused AI call with our catalog as context is more robust than keyword matching.

3. **Derivation via `etl.db.load_raw_data()`.** Generated strategies that need derived features call this function (already in `etl/db.py` at line 256) to load raw data from the warehouse. This follows the project rule: "All database interactions go through `etl/db.py`."

4. **Price features use `Close` from the DataFrame.** The strategy DataFrame already has `Close` (and OHLCV) from `load_prices()`. So price-based derived features (e.g., a 10-day SMA not in the store) compute directly from `df["Close"]` without any extra data loading.

5. **Weather features require explicit data loading.** Raw weather columns (`precip_in`, etc.) are NOT in the feature Parquet files (`include_columns: []`). So derived weather features load from the warehouse via `load_raw_data()`. This is visible in the generated code for the quant to verify.

6. **Extractor doesn't classify features.** The paper describes features in its own terms. The extractor captures that faithfully. The mapper does the classification — matching paper descriptions to our data catalog. This separation keeps the extractor simple and avoids premature categorization errors.

7. **Three AI calls total.** (a) Extraction, (b) feasibility/mapping, (c) code generation. Each is focused with constrained context and structured output.

8. **Output is a standard strategy file.** Zero changes to `backtest.py`, `discovery.py`, or the Strategy Dashboard. The generated `.py` file follows the exact same interface as hand-written strategies.

---

## Edge Cases

| Scenario | Handling |
|----------|----------|
| PDF is image-only (scanned) | pdfplumber returns empty text → error: "Could not extract text. Try pasting the text directly." |
| Paper describes multiple strategies | Extraction prompt asks for the single most clearly defined strategy. `confidence_notes` flags if multiple found. |
| No features resolvable at all | `feasible: false`. Message: "This strategy requires data we don't have." Block code generation. |
| All required features are derivable, none in store | Valid! `FEATURES` dict has empty categories. All computation is inline. |
| Feature needs data we have in a different form | AI mapper handles this. E.g., "average Corn Belt temperature" → derivable from `temp_max_f` and `temp_min_f` via `(max + min) / 2`. |
| Paper uses different units | `confidence_notes` flags it. E.g., "Paper uses Celsius, our data is Fahrenheit." Quant handles in code review. |
| Generated code has syntax errors | Wrap in `compile()` check before save. If it fails, show error and let quant fix in the editor. |
| Strategy name conflicts with existing file | Check before save. Prompt quant to rename. |
| Paper is very long (>50 pages) | Truncate or chunk. For POC, set a page limit (~30 pages). |

---

## Dependencies

| Package | Purpose | Status |
|---------|---------|--------|
| `pdfplumber` | PDF text extraction | New dependency |
| `anthropic` | Claude API calls | Already installed |
| `streamlit` | UI framework | Already installed |

---

## Incremental Implementation Plan

### Piece 1: Backend modules (extractor, mapper, generator)
- `app/paper_agent/__init__.py`
- `app/paper_agent/extractor.py` — PDF parsing + Claude extraction
- `app/paper_agent/mapper.py` — data catalog + AI-assisted feasibility
- `app/paper_agent/generator.py` — Claude code generation
- Unit-testable independently of Streamlit

### Piece 2: Streamlit page (Steps 1-2)
- `app/pages/3_Paper_Upload.py` — upload + extraction + spec review UI
- Wired to extractor.py

### Piece 3: Streamlit page (Steps 3-5)
- Feature mapping UI, code review UI, save & backtest link
- Wired to mapper.py and generator.py
- End-to-end flow working

### Piece 4: Tests + polish
- Tests for extractor (mock API), mapper (AI + deterministic), generator (mock API)
- Error handling, edge cases, UI polish

---

## Verification

- Upload a real ag-commodity paper → strategy spec extracted correctly
- Feature mapping correctly classifies: in_store, derivable, not_possible
- Derivable features generate correct inline code using `etl.db.load_raw_data()`
- Features already in store correctly reference existing column names
- Generated code follows `generate_signal` interface and compiles
- Saved file auto-discovered by Strategy Dashboard
- Backtest runs without errors on generated strategy
- Editing spec at Step 2 invalidates downstream steps
- PDF parse failure shows helpful error message
- `python -m pytest tests/ -v` passes after implementation
