# Paper-to-Strategy Pipeline — Summary

**Date:** 2026-03-14
**Status:** Implemented

## Goal

Add a "Paper Upload" page where a quant uploads a research paper, the system extracts the strategy, maps features to our data (or derives them from raw data), and generates a runnable strategy module — with human checkpoints at every stage.

## Core Principle

**If we have the raw data, we can derive any feature.** The system never forces approximations (e.g., using 7-day precip for 8-day). Instead, it recognizes that daily `precip_in` exists in the warehouse and generates the exact 8-day rolling sum code inline.

## Three-Bucket Feature Classification

```
IN STORE     →  Feature exists in feature store. Use directly.
DERIVABLE    →  Raw data exists in warehouse. Generate compute code. Quant verifies.
NOT POSSIBLE →  Raw data doesn't exist. Flag it. Quant decides to skip or source.
```

## User Flow

```
Upload PDF ──→ Review Spec ──→ Feature Feasibility ──→ Review Code ──→ Save & Backtest
    │            │ (editable)     │                       │                │
    ▼            ▼                ▼                       ▼                ▼
  AI parses    Quant verifies   For each feature:       Quant reviews    File saved to
  paper text   features, rules  IN STORE: show match    full code incl.  strategies/
               params, thesis   DERIVABLE: show code    derivation and   auto-discovered
                                NOT POSSIBLE: flag      signal logic
```

## Key Decisions

- **Three AI calls** — extraction (paper → spec), mapping (features → our data catalog), code generation (spec + map → Python). Each focused and constrained.
- **Claude Sonnet** for all AI stages.
- **AI-assisted mapping** — paper language varies ("8-day cumulative rainfall over central Corn Belt"), needs semantic matching against our catalog, not just string comparison.
- **Derivable features use `etl.db.load_raw_data()`** — the function already exists. Generated code loads raw weather data from the warehouse and computes inline. Follows the "all DB access through etl/db.py" rule.
- **Price features derive from `Close`** — already in the strategy DataFrame. No extra loading needed.
- **Standard output** — generates a `.py` file with `generate_signal()`, `FEATURES`, `SUMMARY`. Zero changes to backtest engine, discovery, or dashboard.
- **Extractor doesn't classify features** — it describes them as the paper does. The mapper handles matching to our system.

## Files Changed

| File | Action | Purpose |
|------|--------|---------|
| `app/paper_agent/__init__.py` | Created | Package init |
| `app/paper_agent/extractor.py` | Created | PDF parsing + Claude strategy extraction |
| `app/paper_agent/mapper.py` | Created | Data catalog + AI-assisted feasibility check |
| `app/paper_agent/generator.py` | Created | Claude code generation for strategy module |
| `app/pages/3_Paper_Upload.py` | Created | Streamlit page — 5-step workflow with checkpoints |
| `requirements.txt` | Modified | Add `pdfplumber` |
| `CLAUDE.md` | Modified | Update project structure |

## Implementation Order (Incremental)

1. **Backend modules** — extractor, mapper, generator (testable without Streamlit)
2. **UI Steps 1-2** — upload + extraction + spec review
3. **UI Steps 3-5** — feasibility mapping + code review + save
4. **Tests + polish** — edge cases, error handling

## Verification

- Extracted spec correctly captures paper's strategy
- Mapper classifies features as in_store / derivable / not_possible
- Derivable features generate correct `load_raw_data()` + computation code
- Generated code compiles and follows `generate_signal` interface
- Saved strategy appears in dashboard and backtests successfully
- All existing tests pass
