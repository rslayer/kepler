# SPEC v5 — Certifiable gains (kepler)

Purpose: the M5 recipe already scores hier 0.698 vs 0.785 on m5_all, kept on all eight folds, but the m5_3 screen cannot certify it because the screen's seed spread (0.011-0.016) is larger than the real gain (~0.020). This spec removes that noise floor, then adds the accuracy levers the M5 winners used and Kepler has not. Order matters: Parts A and B unblock the gate; Part C spends the headroom; Parts D and E produce numbers currently missing.

Hand to Claude Code at the repo root: "Read SPEC_v5_certifiable.md and execute Parts A through E in order. Stop after each part and report against its acceptance criteria before continuing. Never read, list, or write under any holdout/ path. Do not edit files listed as frozen in HARNESS_CHANGELOG. Commit before every backtest so no run is logged with a -dirty hash."

Frozen this session (do not edit): src/scorer.py, src/scorer_hier.py, src/report.py, src/score_holdout.py, src/scoring.py, tiers.json. The keep rule and fold logic in src/backtest.py MAY be edited only where Part A explicitly directs, as the harness owner; re-tag afterward.

Preflight (report, do not fix yet): run `make verify-frozen`; list any run in the last 30 rows of runs/runs.csv whose git_commit ends in `-dirty`; confirm the working tree is clean. If the tree is dirty, stop and tell the human.

---

## Part A — Seed-averaged forecasts (the gate unblocker)

Today each backtest fits once per seed and the three forecasts are scored separately, so the reported metric carries the full seed-to-seed spread. Averaging the forecasts before scoring cancels most of that noise and is also what a production model would serve.

### Tasks
- In `src/backtest.py`, add a `bag_seeds` mode (config flag, default ON for new runs, OFF reproduces old runs): for each (fold, series, horizon) predict with every seed and average the predictions, then score the single averaged forecast. Per-seed scores are still logged for the spread columns, but the headline `wrmsse` / `wrmsse_hier` is now the score of the bagged forecast.
- The `<metric>_spread` column keeps its meaning (max minus min across seeds, pre-bagging) so the adversary's noise-floor check still has its input.
- Add a `bagged` boolean to runs.csv and to detail JSON. The keep rule reads the bagged metric.
- Determinism: bagged runs must reproduce to six decimals across two invocations.

### Acceptance
- Re-run the baseline and the full recipe on the m5_3 screen with `bag_seeds=on`. Report the new screen spread and the recipe-vs-baseline gain against it.
- State plainly whether the recipe now clears the keep rule on m5_3 (gain > 2x aggregate spread AND no fold regresses beyond its own spread AND bias guardrail). If it does not, report by how much and stop for human review before Part B.
- Two identical bagged runs match to six decimals.
- Re-tag `v5-parta`; `make verify-frozen` clean.

---

## Part B — Bias / scale correction (cheap points, and a second gate unblocker)

Recipe runs r089, r091, r092 carry -4% to -4.5% bias. A multiplicative recalibration at the item-store level typically returns several points of WRMSSE and tightens the bias guardrail.

### Tasks
- Add an optional post-process in `src/model.py` (role-gated, not hardcoded to M5): after prediction, estimate a per-series multiplicative correction from the training tail (ratio of actual to predicted over the last N in-sample days, clipped to [0.5, 2.0], smoothed toward 1.0 by a shrinkage factor). Config-controlled, default OFF so existing configs are unchanged.
- This is a researcher-owned feature, so it goes below the RULES/PRIORS marker discipline: implement it, do not promote it. One variable: correction ON vs OFF on the current best recipe.

### Acceptance
- Backtest the best recipe with correction ON vs OFF on m5_3 and m5_all. Report WRMSSE and bias for each.
- Keep-rule verdict for correction-ON as a child of correction-OFF, on both tiers.
- Findings file written; ledger row added; branch `exp/<run_id>` committed.

---

## Part C — Per-store models (ingredient 7, the accuracy lever)

The M5 winners' largest structural gain came from models specialised below the global level. Ingredient 7 is defined but unrun.

### Tasks
- Implement per-store training: one model per store_id, predictions concatenated, scored by the same frozen hierarchical scorer. Role-driven (store_id from the contract), not M5-specific.
- Budget: this multiplies fit count by the store count. Use `--jobs N` parallel fits and respect the dataset timeout. If m5_all exceeds budget, run Part C on the m5_3 screen only and note m5_all as pending.
- One variable: global model vs per-store, best recipe held constant, correction at whatever Part B concluded.

### Acceptance
- Backtest per-store vs global on m5_3, seed-bagged. Report WRMSSE, bias, and per-fold deltas.
- Keep-rule verdict. If kept, run the adversary checklist on the branch and report its verdict (especially item 6 concentration and item 5 fold-consistency).
- Findings, ledger, branch committed. Do not promote.

---

## Part D — Measure the parallel speedup (a number you owe Magesh)

`--jobs N` is coded but the speedup has never been measured on an idle machine.

### Tasks
- On the current machine, with nothing else running, time one m5_all baseline backtest at `--jobs 1`, `--jobs 4`, and `--jobs max`. Record wall-clock and the resulting runs-per-hour at m5_all scale.
- Write `tools/cloud/BENCHMARK.md`: machine spec, the three timings, the implied cost per run at the measured token rate from runs/sessions.csv, and the projected cost of a 200-run cycle.

### Acceptance
- Three timings logged; runs-per-hour and cost-per-run stated for m5_all. This is the figure for the funding page's compute line.

---

## Part E — Pay down the audit debt (what the adversary cannot protect)

### Tasks
- Enforce commit-before-backtest: `make backtest` refuses to run if the tree is dirty, with a message telling the human to commit. (Same discipline the loop already uses for headless cycles; make it universal.)
- Reconcile the r080-r102 renumbering: confirm runs/v4_run_id_map.json is complete and that every detail JSON matches its runs.csv row. List any run whose git_commit cannot be resolved to a real commit.
- Update RESULTS.md with the v5 state: the m5_all recipe number (0.698 vs 0.785), the Kaggle field context (winner 0.520, rank-50 0.576, ES 0.671), whether the gate now passes on m5_3, and the measured runs-per-hour.

### Acceptance
- `make backtest` refuses on a dirty tree.
- No unresolved commit hashes remain, or the remaining ones are listed with a note.
- RESULTS.md reflects v5. Re-tag `v5-certifiable`.

---

## Out of scope this session
- Ensembling beyond seed-bagging (recursive models, model stacking) — a later cycle.
- Any change to the frozen scorers or the holdout.
- Promotion to champion — that stays a human-run gate with a human-run holdout score, outside this session.
- PepsiCo data. Public M5 only.

## The one thing to get right
Part A is the point of this spec. If seed-bagging does not shrink the screen spread enough to certify the gain that already exists, stop and report — do not compensate by loosening the keep rule. A gate that passes noise is worse than a gate that blocks a real gain.
