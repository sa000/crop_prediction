# Paper Upload UX Overhaul — Summary

## Date: 2026-03-15

## Goal

Restructure Paper Upload into a guided single-button flow, remove feasibility hints from demo names, and surface duration estimates in AI Usage.

## Key Changes

1. **Remove feasibility hints from demo paper names** — "Demo 1: Precipitation Stress Signals" instead of "(derivable)"
2. **Single-button guided pipeline** — One "Run Pipeline" button runs all 3 AI agents (extract → map → generate) sequentially with inline progress. No intermediate buttons. Pipeline auto-stops if not feasible, auto-generates code if feasible. Only "Save" remains as a separate action.
3. **Time estimates** — Show total pipeline estimate before running. Add avg duration column to AI Usage "By Function" tab.

## Files Affected

- `app/paper_agent/extractor.py` — neutral demo names
- `app/pages/4_Paper_Upload.py` — full UI rewrite
- `app/pages/5_AI_Usage.py` — avg duration in function table
- `app/ai_usage.py` — add avg_duration_s to function breakdown query
