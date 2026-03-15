# Paper Upload UX Overhaul — Detailed Plan

## Date: 2026-03-15

## Context

User feedback on the Paper Upload page:

1. **Demo paper names leak feasibility** — Names like "Demo 1: Precipitation Stress Signals (derivable)" tell you the outcome before running analysis. Remove hints.
2. **Sequential guided flow** — Current layout requires clicking separate buttons for extraction, then code generation. User wants ONE button that runs all 3 AI agents sequentially, showing progress inline. Minimize clicks.
3. **Duration estimates** — Already tracked in `ai_usage` table. Show total pipeline estimate (all 3 agents summed) before running. Add avg duration column to AI Usage "By Function" tab.

## AI Pipeline Architecture (confirmed correct)

- **Agent 1 (Extractor)**: Extract features and thesis from paper text
- **Agent 2 (Mapper)**: Map features against data catalog + feature store to assess feasibility
- **Agent 3 (Generator)**: Generate runnable strategy code from spec + mapping (only if feasible)

## Changes

### 1. `app/paper_agent/extractor.py` — Remove feasibility hints from demo names

```python
# Before
DEMO_PAPERS = {
    "Demo 1: Precipitation Stress Signals (derivable)": "demo_1_derivable.txt",
    "Demo 2: Soil Moisture & NDVI (not possible)": "demo_2_not_possible.txt",
}

# After
DEMO_PAPERS = {
    "Demo 1: Precipitation Stress Signals": "demo_1_derivable.txt",
    "Demo 2: Soil Moisture & NDVI": "demo_2_not_possible.txt",
}
```

### 2. `app/pages/4_Paper_Upload.py` — Rewrite to guided single-button flow

**New flow:**

1. **Select Paper** — dropdown with neutral names, paper preview expander
2. **"Run Pipeline" button** — single button, shows total time estimate
3. **On click:** runs all 3 agents sequentially inside `st.status()`:
   - Agent 1: Extract → shows title as it completes
   - Agent 2: Map features → shows feasibility result
   - If NOT feasible: pipeline stops, shows explanation
   - If feasible: Agent 3: Generate code → stores result
4. **After pipeline completes** — page reruns and shows inline:
   - Strategy spec (title, thesis)
   - Feasibility banner (FEASIBLE/NOT FEASIBLE) — right after strategy spec
   - Feature list with status badges
   - Signal rules, parameters, confidence notes
   - If not feasible: stop message, no code section
   - If feasible: generated code editor + save button
5. **Save** — only remaining button click needed

**Key session state changes:**
- Remove `_clear_downstream()` step-based clearing
- Store all results from pipeline in one go: `paper_spec`, `paper_feasibility`, `paper_code`
- Clear all on new pipeline run
- Track `paper_demo` to detect paper change → auto-clear results

**Time estimate display:**
- Sum avg durations for `paper_extractor` + `paper_mapper` + `paper_generator`
- Show before the Run Pipeline button as "Estimated time: ~Xs"

### 3. `app/pages/5_AI_Usage.py` — Add avg duration to "By Function" tab

- Use `get_avg_durations()` to get per-feature averages
- Add an "Avg Duration (s)" column to the function breakdown table
- Merge the dict into the dataframe by feature key

### 4. `app/ai_usage.py` — Add avg duration to function breakdown query

- Modify `get_function_breakdown()` to include `AVG(duration_s)` in the SQL query
- Return it as `avg_duration_s` in each row dict

## Files Modified

| File | Change |
|------|--------|
| `app/paper_agent/extractor.py` | Remove feasibility hints from demo names |
| `app/pages/4_Paper_Upload.py` | Full rewrite: single-button guided flow |
| `app/pages/5_AI_Usage.py` | Add avg duration column to function breakdown |
| `app/ai_usage.py` | Add avg_duration_s to function breakdown query |

## Verification

1. `python -m pytest tests/ -v` — all pass
2. Demo dropdown shows neutral names (no "derivable"/"not possible")
3. One "Run Pipeline" button runs all agents sequentially with progress
4. Not-feasible paper stops after feasibility with explanation
5. Feasible paper auto-generates code, shows editor + save
6. AI Usage "By Function" tab shows avg duration column
7. Time estimate shown before Run Pipeline button
