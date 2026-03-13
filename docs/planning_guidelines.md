# Planning Guidelines

All implementation plans in this project must follow these standards.

## Plan Files

Every plan produces two Markdown files in `claude_logs/` before implementation begins:

- **Detailed plan**: `claude_logs/YYYY-MM-DD_<topic>-plan-detailed.md`
  Full specification including context, file-by-file changes, design decisions, edge cases, and verification steps.

- **Summary plan**: `claude_logs/YYYY-MM-DD_<topic>-plan-summary.md`
  High-level overview: goal, key changes, and files affected. This is what gets reviewed before approval.

## Workflow

1. Draft both the detailed and summary plan files in `claude_logs/`.
2. Present the summary to the user for review.
3. Get explicit approval before starting implementation.
4. Implement the plan.
5. Keep both files permanently in `claude_logs/` as a historical record.

## Naming

- Date prefix: `YYYY-MM-DD` (the date the plan is created).
- Topic slug: lowercase, hyphen-separated, descriptive (e.g., `feature-store-rebuild`, `backtest-enhancements`).

## Retention

Plan files are never deleted. They serve as a permanent audit trail of what was planned, what was decided, and why.
