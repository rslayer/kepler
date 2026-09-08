"""Rolling-origin backtest driver.

Fold logic is HUMAN-OWNED (see CODEOWNERS). Agents add entries to the model registry
and nothing else. Four folds, 28-day horizon, origins spaced 28 days apart, ending at
the last day of the agent-visible snapshot. Verifies data/snapshot/MANIFEST.txt before
running and aborts on mismatch.

Filled in during Phase 1.
"""
