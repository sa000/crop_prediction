# AI Feature Catalog Agent + Metadata Table — Detailed Plan

**Date:** 2026-03-13
**Status:** Implemented

---

## Context

The Feature Explorer tab had manual dropdowns only. We added a natural language interface where users ask questions about features and get structured, clickable results. A metadata Parquet layer (`features/metadata.parquet`) serves as the tabular source of truth for both the AI agent and the query layer.

## Architecture

### Metadata Schema (features/metadata.parquet)
One row per feature per entity (60 rows total):
- name, category, entity, entity_type (ticker/region)
- source_table, description, params (JSON string)
- available_from, freshness
- row_count, stat_min, stat_max, stat_mean, stat_std, null_pct
- parquet_path

### AI Agent (app/catalog_agent.py)
- `build_catalog_context(metadata_df)` — formats metadata as structured text grouped by category/entity
- `SYSTEM_PROMPT` — constrains model to catalog questions only, enforces JSON output
- `ask(question, metadata_df, api_key)` — calls Claude Haiku, parses JSON response
- Model: `claude-haiku-4-5-20251001`, max_tokens: 1024

### Pipeline Integration (features/pipeline.py)
- Metadata built inside `update_registry()` after all features computed
- Iterates all categories, entities (including aggregations), features
- Computes summary stats per feature column
- Serializes params as JSON strings
- Writes via `store.write_metadata()`

### Query Layer (features/query.py)
- `list_features()` reads from metadata.parquet first
- Falls back to registry.yaml if parquet missing
- YAML-based `load_registry()` kept for backward compatibility

### Data Explorer UI (app/pages/2_Data_Explorer.py)
- Text input at top of Feature Explorer tab
- On submit: loads metadata, calls agent, stores result in session_state
- Results displayed as answer text + clickable st.dataframe
- On row click: loads feature data, renders chart
- Manual dropdowns remain below divider as fallback
- Graceful degradation: shows info message if no API key configured

## Design Decisions
1. Metadata in Parquet not SQLite — warehouse.db is for raw validated data only
2. YAML stays as human-readable export alongside Parquet
3. Full context injection (Pattern A) — 60 rows fits in prompt (~3K tokens)
4. Structured JSON output — not free-text chat
5. Scope enforcement via system prompt — model can't hallucinate features
6. API key in .streamlit/secrets.toml — gitignored, Streamlit Cloud compatible
