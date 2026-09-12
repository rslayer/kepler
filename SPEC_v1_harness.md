# SPEC v1 — Harness upgrade (kepler, Step 2)

Purpose: raise the signal-to-noise of the backtest so the keep rule can separate real gains from seed spread. Nothing in this spec changes how models are built. Nothing touches `holdout/`.

Hand this file to Claude Code at the repo root and say: "Read SPEC_v1_harness.md and execute Parts A through E in order. Stop after each part and report against the acceptance criteria."

Frozen-file rule for this session: `src/scorer.py` is not edited. `src/report.py` is not edited. The fold logic in `src/backtest.py` IS edited in this session because the human is the author of this spec; every other session keeps it frozen. Tag the result `v1-harness`; `make verify-frozen` compares against that tag from now on.

---

## Part A — Widen the subset

### Tasks
- In `src/data.py`, change the snapshot definition from store `CA_1`, department `FOODS_3` to store `CA_1`, all departments. Expected size: about 3,049 series, 1,913 days.
- Keep the SNAP column as `snap_CA`. Keep the price and calendar joins unchanged.
- Regenerate the snapshot with `make data` and rewrite `data/snapshot/MANIFEST.txt`.
- Do NOT run `make holdout`. Print the instruction "Human must run `make holdout` before any backtest" and stop at the end of Part A.

### Acceptance
- `make data` completes; MANIFEST.txt has new hashes; the snapshot has roughly 3,049 ids.
- `holdout/` is untouched by the agent (verify: `git status` and directory mtime).
- The agent has stopped and asked the human to run `make holdout`.

The human runs `make holdout`, confirms the last 28 days are cut, then tells the agent to continue.

---

## Part B — Eight folds, 14-day spacing

### Tasks
- In `src/backtest.py`, set `N_FOLDS = 8` and add `FOLD_SPACING = 14`. `make_folds` returns eight origins spaced 14 days apart, oldest first, with the last fold ending on the last day of the agent-visible snapshot. Horizon stays 28 days, so consecutive fold windows overlap by 14 days; that is intended.
- `--folds` on the command line still overrides `N_FOLDS` for quick runs, but the logged `fold_count` must reflect the actual number scored.
- `runs/runs.csv` gains one column, `fold_spacing`, appended after `fold_count`. Existing rows are backfilled with `28` by a one-time script `tools/migrate_runs_v1.py` that also adds the columns from Part C.

### Acceptance
- `make backtest MODEL=seasonal_naive` prints eight origins 14 days apart, the last window ending on the snapshot's final day.
- `runs.csv` has the new column and every historical row carries `28`.

---

## Part C — Three seeds per run, mean and spread logged

### Tasks
- A backtest now fits the model once per seed for each fold. Default seeds: `(42, 7, 123)`. `SEEDS` is a module constant in `src/backtest.py`; `--seeds` on the command line overrides it as a comma-separated list.
- For each metric already logged (`wrmsse`, `wape`, `bias`, the three horizon WAPEs), log the mean across seeds under the existing column name, and add a `<metric>_spread` column holding max minus min across seeds. Six new columns.
- Per-fold detail in `runs/detail/<run_id>.json` gains a `seeds` block: for each seed, the per-fold metrics. Per-series detail is the mean across seeds.
- `seconds` is the wall-clock for all seeds. `TIMEOUT_SECONDS` stays 20 minutes for the whole run.
- Seeds run sequentially; do not add parallelism in this session.

### Acceptance
- `make backtest MODEL=lgbm_baseline` run twice logs identical means and spreads to six decimals.
- `wrmsse_spread` for `lgbm_baseline` is reported; note it in the Part C report.
- `tools/migrate_runs_v1.py` has backfilled the six spread columns as empty for historical rows.

---

## Part D — Keep rule inside the harness

### Tasks
- Add `--parent <run_id>` to `make backtest` (Makefile variable `PARENT`). When given, the harness compares the new run to the parent and writes a `verdict` column to `runs.csv`: `kept`, `discarded`, or `no_parent`.
- The rule, evaluated on WRMSSE, all conditions required for `kept`:
  1. Paired gain: parent mean minus child mean is greater than 2 × max(parent spread, child spread).
  2. No fold regresses: for every fold, child fold-mean is not worse than parent fold-mean by more than max(parent spread, child spread).
  3. Bias guardrail: absolute child bias is not more than 0.02 greater than absolute parent bias.
- The verdict and the three condition results are printed at the end of the run and written into `runs/detail/<run_id>.json` under `keep_rule`.
- The parent's per-fold numbers are read from its detail JSON; if the parent predates Part C and has no seeds block, the harness refuses with a clear message ("parent must be a v1 run").
- Remove the "beats on all four folds" sentence from `CLAUDE.md` and replace it with: "A result is kept only when the harness prints `verdict=kept` for `--parent <current best>`. You do not argue with the verdict; you write it up and move on."

### Acceptance
- `make backtest MODEL=lgbm_baseline PARENT=<v1 baseline run_id>` returns `discarded` (a model cannot beat itself).
- The keep-rule block appears in the detail JSON with all three conditions.
- CLAUDE.md updated as specified; `make verify-frozen` shows no diff on `scorer.py` or `report.py`.

---

## Part E — Re-baseline and tag

### Tasks
- Log `seasonal_naive` and `lgbm_baseline` under v1 with `AUTHOR=human`. Update the "current best" line in CLAUDE.md with the new baseline run_id and WRMSSE.
- Commit on `main` as `feat: harness v1 (CA_1 all depts, 8 folds, 3 seeds, keep rule)`. Tag `v1-harness`.
- Update `Makefile` `verify-frozen` to diff against `v1-harness`.
- Write `HARNESS_CHANGELOG.md` with one paragraph on what changed and why, and the v0 and v1 baseline numbers side by side. State that v0 and v1 WRMSSE are not comparable because the subset changed.

### Acceptance
- Tag exists; `make verify-frozen` is clean.
- CLAUDE.md names the v1 baseline.
- Two v1 baseline rows in `runs.csv` with spreads populated.

---

## Out of scope for this session

- Any change to `src/features.py` or `src/model.py` (Step 4).
- Rerunning r011 (Step 3, a separate session after this one is tagged).
- Parallelism, cron, `loop.sh`, or the adversary (Steps 7 and 8).
- Any edit to `src/scorer.py` or `src/report.py`.
