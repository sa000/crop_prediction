# AI Feature Catalog Agent + Metadata Table — Summary

**Date:** 2026-03-13
**Status:** Implemented

## Goal
Add a natural language interface to the Feature Explorer tab where users ask questions like "What weather features do we have?" and get back a structured, clickable table. Clicking a row plots the feature over time.

## Key Decisions
- **Metadata in Parquet** (`features/metadata.parquet`), not SQLite — warehouse.db is for raw data only
- **Claude Haiku** (`claude-haiku-4-5-20251001`) for the agent — fast, cheap, catalog is small (~60 rows, ~3K tokens)
- **Full context injection** — metadata fits in prompt; no tool-use needed yet
- **Structured JSON output** — model returns `{"answer": str, "features": list}` rendered as clickable table
- **API key** in `.streamlit/secrets.toml` (gitignored)

## Files Changed
| File | Action | Purpose |
|------|--------|---------|
| `features/store.py` | Modified | Added `write_metadata()` / `read_metadata()` |
| `features/pipeline.py` | Modified | Generates `metadata.parquet` with summary stats in `update_registry()` |
| `features/query.py` | Modified | `list_features()` reads from Parquet first, YAML fallback |
| `.streamlit/secrets.toml` | Created | API key (gitignored) |
| `.gitignore` | Modified | Added `.streamlit/secrets.toml` |
| `requirements.txt` | Modified | Added `anthropic>=0.40`, bumped `streamlit>=1.35` |
| `app/catalog_agent.py` | Created | Agent module — prompt building, API call, structured output |
| `app/pages/2_Data_Explorer.py` | Modified | Agent text box, clickable results table, chart on select |
| `CLAUDE.md` | Modified | Updated project structure docs |

## Verification
- `python -m features.pipeline --rebuild` generates 60-row metadata.parquet
- `registry.yaml` still generated unchanged
- Catalog context: ~11K chars (~3K tokens)
