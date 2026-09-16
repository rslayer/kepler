# SPEC v7 — Hierarchical reconciliation (kepler)

Purpose: close the leaderboard gap. The recipe wins m5_all (0.698 backtest, 0.626 yardstick)
but sits between the statistical baselines and rank 50 (0.576). WRMSSE is won on the
aggregate levels, and the recipe forecasts only at the bottom (item-store) and sums up
(bottom-up). Independent forecasts of the smoother aggregate series carry level information
the noisy bottom forecasts lack. This spec adds reconciliation: correct the bottom forecasts
so a chosen aggregate level matches its own independent forecast.

Hand to Claude Code at the repo root: "Read SPEC_v7_reconciliation.md and execute Parts A
through D in order. Stop after each part and report against its acceptance criteria. Never
read/list/write under any holdout/ path. Commit before every backtest so no run is logged
with a -dirty hash."

Frozen (do not edit): `src/scorer.py`, `src/scorer_hier.py`, `src/report.py`,
`src/score_holdout.py`, `src/scoring.py`, `src/backtest.py`, `src/data.py`, `src/contract.py`,
`src/adapters/m5.py`, `tiers.json`. Reconciliation is a new model in `src/model.py` plus a new
`src/reconcile.py`; it never touches the scorer or the keep rule. Re-tag `v7-reconciliation`.

Preflight (report, do not fix): `make verify-frozen`; clean tree; `tools/audit_runs.py`.

## Method — middle-out multiplicative reconciliation

Full MinT (G = (S'W⁻¹S)⁻¹S'W⁻¹) needs a bottom×bottom inverse — 30,490² at m5_all, infeasible
here. Instead:

1. Base bottom forecast: the current champion recipe (recipe6_calendar_l2), item-store, as today.
2. Independent aggregate forecast at one reconciliation level R from the contract's hierarchy
   (default store-department, M5 level 9: few, smooth series). Sum the bottom history to each
   group in R, fit a light model (LGBM on lags 7/14/28/364 + rolling means + calendar dow/
   month/event flags; no price/SNAP, which do not aggregate) once per group, forecast 28 days.
3. Reconcile: for each group g in R and horizon day h, scale every bottom forecast in g by
   factor f(g,h) = Â(g,h) / Σ_bottom(g,h), where Â is the independent aggregate forecast and
   Σ_bottom is the bottom-up sum. Clip f to [0.5, 2.0]; where the independent forecast is
   missing or the bottom sum is ~0, f = 1. The reconciled bottom forecasts go to the frozen
   scorer, which re-aggregates them to all 12 levels.

This borrows the smoother aggregate's level (correcting the recipe's ~-2.5% aggregate bias)
without a large inverse. Role-driven: R is a hierarchy entry, not hardcoded to M5.

## Part A — Reconciliation machinery
- `src/reconcile.py`: `aggregate_history(panel, keys)` (sum bottom to groups), an aggregate
  forecaster (light LGBM per the method), and `reconcile(bottom_pred, agg_pred, groups)` →
  scaled bottom predictions. Leak-free: aggregate features read only history before the origin
  (reuse the as-of-origin contract; assert it).
- `LGBMRecipeReconciled` in `src/model.py`: base = recipe6_calendar_l2; `RECON_LEVEL` = the
  hierarchy keys to reconcile at (default `["store_id","dept_id"]`); `forecast()` returns the
  reconciled bottom frame. Config records the level and clip.
- Acceptance: unit test on a 2-group toy — reconciled group sums equal the (clipped) aggregate
  forecast; bottom proportions within a group are preserved when f is unclipped.
  `make verify-frozen` clean.

## Part B — Screen backtest
- Backtest `recipe6_reconciled` on m5_3 vs the bagged recipe r115, seed-bagged, as researcher
  (SESSION, HYPOTHESIS, ledger, findings). Report the per-level WRMSSE (L1–L12) vs the recipe:
  reconciliation should help the aggregate levels (L1–L9) most.
- Keep-rule verdict under v6.1. The screen under-certifies recipe changes, so report the
  per-level breakdown regardless of verdict; the m5_all confirmation is the real test.

## Part C — m5_all confirmation
- Backtest `recipe6_reconciled` on m5_all vs the recipe r118 (bagged), seed-bagged. Report
  WRMSSE_hier and the per-level table vs r118. Keep-rule verdict (v6.1 sign test).
- If it wins m5_all, it is the strongest champion candidate; promotion still needs a clean
  human yardstick (see runs/promotions/m5_all_v1_PENDING.md) and stays a human action.

## Part D — Document and tag
- Findings, ledger, `HARNESS_CHANGELOG.md` (method + per-level results), `RESULTS.md`
  (new best if it wins). Commit on main; tag `v7-reconciliation`; move `FROZEN_REF`.

## Out of scope
- Full MinT / trace minimization (needs sparse solvers) — a later cycle if middle-out helps.
- Promotion to champion (human gate + human yardstick).
- Any change to the frozen scorer or holdout. PepsiCo data — public M5 only.

## The one thing to get right
Reconciliation must be leak-free: the aggregate forecast may read only history strictly before
the origin, exactly like the bottom model. If middle-out does not beat bottom-up on the m5_all
per-level table, report that plainly — a coherent-but-not-better reconciliation is a negative
result, not a win to force.
