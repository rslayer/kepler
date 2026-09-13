# SPEC v3 — Forecasting engine (kepler, Step 4)

Purpose: turn the research loop into a forecasting engine. Today the loop improves
branches; nothing it learns reaches a model anyone can run, and every module hardcodes M5
column names. v3 adds the three missing planes: a data contract so the engine is not
M5-specific, a champion/challenger promotion path so kept-and-passed work lands on main
and becomes the model that forecasts, and a forecast output with a live scoreboard so the
champion is judged on data that did not exist when it was promoted. Nothing in v3 changes
the scorer, the fold design, the keep rule, or the adversary's checklist.

Hand this file to Claude Code at the repo root and say: "Read SPEC_v3_engine.md and
execute Parts A through E in order. Stop after each part and report against the
acceptance criteria. Do not run any researcher, adversary, or curator session." The
harness-owner session may edit src/data.py, src/features.py's data-access layer,
src/model.py's registry plumbing, src/backtest.py outside the fold logic and keep rule,
tools/, Makefile, and the instruction files' harness notes. It may not edit
src/scorer.py, src/report.py, make_folds, the fold loop, keep_rule, or any model's
features or parameters.

Definitions:
- **Champion**: the model registered in `champion.json` on main. It is what
  `make forecast` runs. There is exactly one per dataset.
- **Challenger**: an exp/* branch with verdict=kept whose adversary review says PASS.
- **Promotion**: merging a challenger into main and updating `champion.json`. A harness
  action with its own log; agents never do it.
- **As-of date**: the first day being forecast. A forecast made as of D uses only data
  strictly before D.

---

## Part A — Data contract and the M5 adapter

### Tasks
- Define the contract in `src/contract.py` as three tables and a check function:
  - `panel`: columns `series_id, date, y` (one row per series per day; no gaps; y >= 0).
  - `series`: `series_id` plus any static attributes (for M5: item_id, dept_id, cat_id,
    store_id, state_id). Attribute names are dataset-specific; models receive them by
    role, not by name (see `roles`).
  - `exog`: `date` (and optionally `series_id`) plus known-in-advance regressors: calendar
    flags, events, prices. Everything here is knowable at the as-of date by construction;
    the adapter is responsible for that claim and must document it.
  - `roles`: a small mapping the adapter provides: which `series` column is the
    categorical grouping for a global model (`group`), which `exog` columns are
    `calendar_flags`, `event_flags`, `price`, and which is the `weight_price` used by
    the scorer's dollar weights.
  - `validate(dataset)` raises on any violation; every backtest calls it after the
    manifest check.
- Move the M5-specific logic into `src/adapters/m5.py`: download, subset, snapshot, holdout
  cut, and the mapping to the contract. `src/data.py` becomes contract-only: load a
  dataset by id, verify manifest, verify cut, validate.
- Datasets live under `data/<dataset_id>/{raw,snapshot,MANIFEST.txt}` and
  `holdout/<dataset_id>/`. The current `data/` and `holdout/` become `data/m5_ca1/` and
  `holdout/m5_ca1/`. `make data DATASET=m5_ca1`, `make holdout DATASET=m5_ca1`, and every
  backtest takes `DATASET=` (default `m5_ca1`). Snapshot hashes must be unchanged by the
  move.
- `src/features.py` and `src/model.py` read only contract columns and roles. The feature
  set and model parameters of `lgbm_baseline` and `seasonal_naive` are unchanged.
- `runs/runs.csv` gains a `dataset` column (appended last; `tools/migrate_runs.py`
  backfills `m5_ca1`).

### Acceptance
- `make backtest MODEL=lgbm_baseline DATASET=m5_ca1` reproduces r033 to six decimals
  (same means, spreads, and config hash after accounting for the new dataset field).
- `grep -rn "snap_CA\|wm_yr_wk\|dept_id\|store_id" src/features.py src/model.py
  src/backtest.py src/scorer.py` returns nothing; those names appear only in
  `src/adapters/m5.py`.
- `validate()` rejects a panel with a missing day, a negative y, or an exog table that
  contains the target.
- `data/m5_ca1/snapshot/MANIFEST.txt` hashes equal the current `data/snapshot/MANIFEST.txt`.

---

## Part B — Champion registry and promotion

### Tasks
- `champion.json` at the repo root, one entry per dataset:
  `{dataset, model_name, git_tag, config_hash, backtest_run, backtest_wrmsse,
  holdout_wrmsse, promoted_at, promoted_by, previous}`. Seed it with `lgbm_baseline`
  for `m5_ca1` from r033 and its holdout score (runs/holdout.csv). Committed; human-owned
  in CODEOWNERS.
- `tools/promote.py exp/<run_id>`: the promotion gate. Exit 0 and promote if and only if
  all of:
  1. the run's `verdict` is `kept` and its parent chain leads to the current champion's
     `backtest_run` (a challenger must be built on the champion, not on an older base);
  2. an adversary review for the branch exists with verdict PASS, or a human override row
     (`author=human, status=ok, model_name=<branch>`) exists in runs.csv;
  3. `make verify-frozen` is clean on the branch;
  4. `make score-holdout MODEL=<model> DATASET=<dataset>` — run by the human, one shot —
     scored strictly better than the champion's `holdout_wrmsse` (the tool refuses to run
     the holdout itself; it reads runs/holdout.csv and requires the row to exist);
  5. the branch merges into main without conflicts in src/ (tools/ and instruction files
     may not be touched by an exp/* branch at all; FAIL if they are).
  On success: merge (ff or merge commit), tag `champion/<dataset>/v<N>`, update
  `champion.json` with `previous` pointing at the old entry, append a row to
  `runs/promotions.csv` (`timestamp, dataset, from_run, to_run, from_wrmsse, to_wrmsse,
  holdout_from, holdout_to, tag`). On failure print which condition failed; change nothing.
- The researcher's harness notes: "the current best" is defined as the champion's
  `backtest_run` when no kept run exists on top of it, otherwise the newest kept run whose
  chain leads to the champion. `PARENT=` defaults to that when omitted.
- exp/r037 is the first challenger: it is kept, PASS by override, and built on r033. The
  human runs its holdout score; if it wins, Part B's acceptance promotes it.

### Acceptance
- `tools/promote.py exp/r037` refuses before the holdout row exists, naming condition 4.
- After the human runs `make score-holdout MODEL=lgbm_xmas0 DATASET=m5_ca1`:
  `tools/promote.py exp/r037` promotes (or refuses on 4 if the holdout lost; both are
  acceptable outcomes and the report must say which), `champion.json` reflects it, the tag
  exists, `runs/promotions.csv` has one row.
- `tools/promote.py exp/r044` refuses on condition 2 (INCONCLUSIVE, no override).

---

## Part C — Forecast output and the live scoreboard

### Tasks
- `make forecast DATASET=<id> ASOF=<date> [HORIZON=28]`: loads the dataset, fits the
  champion on data strictly before ASOF, writes
  `forecasts/<dataset>/<asof>/forecast.parquet` (`series_id, date, horizon, yhat`) and
  `forecast.json` (champion tag, config hash, git commit, seconds, feature manifest).
  Refuses if ASOF is later than the snapshot's last day + 1 (it cannot forecast a future it
  has no features for) or if the working tree is dirty.
- `make evaluate DATASET=<id>`: for every forecast directory whose 28 days are now fully
  covered by actuals in the snapshot, scores it with the frozen scorer (same WRMSSE, WAPE,
  bias, horizon buckets) and appends to `runs/live.csv`
  (`dataset, asof, champion_tag, wrmsse, wape, bias, wape_h1_7, wape_h8_14, wape_h15_28,
  scored_at`). Idempotent: an (asof, champion_tag) pair is scored once.
- Live scoreboard: `tools/live_report.py` prints `runs/live.csv` by champion, with the
  mean and spread of live WRMSSE per champion version, and the backtest WRMSSE from
  `champion.json` beside it. This is the number that tells you whether the backtest
  predicts reality.
- Backfill: with the m5_ca1 snapshot, run `make forecast` for four as-of dates 28 days
  apart ending at the last visible day minus 28, then `make evaluate`. These are true
  out-of-sample forecasts for the champion (the champion was never fit past ASOF), but
  they are not new information about the holdout; keep the holdout rule as is.

### Acceptance
- `make forecast DATASET=m5_ca1 ASOF=2016-02-29` writes 3,049 x 28 rows and a manifest;
  the same command twice produces byte-identical parquet.
- `make evaluate` scores the four backfilled forecasts; `tools/live_report.py` prints
  their mean live WRMSSE for the champion beside its backtest WRMSSE, and the two are
  within the fold-to-fold range seen in the backtest.
- A forecast with ASOF past the snapshot end is refused with a clear message.

---

## Part D — Per-dataset memory

### Tasks
- Split `LESSONS.md` into `LESSONS.md` (general: about the loop, noise, the keep rule)
  and `datasets/<dataset_id>/LESSONS.md` (about that data: Christmas-zero, Thanksgiving
  dip, SNAP). Same for the ledger: `hypotheses/<dataset_id>/ledger.csv`. The researcher
  reads general first, then the dataset's. The curator writes to the dataset's files by
  default and to the general file only for a finding that cites runs on two datasets or is
  about the harness itself.
- `CLAUDE.md`'s Priors block becomes per-dataset: `datasets/<dataset_id>/PRIORS.md`,
  included by reference from CLAUDE.md ("read datasets/<DATASET>/PRIORS.md"). The
  check_claude_diff scope rule extends to: curator branches may edit only
  `datasets/*/PRIORS.md`, `datasets/*/LESSONS.md`, `hypotheses/*/ledger.csv`, the
  general LESSONS.md, and their report.
- Migrate the current 22 lessons and 40 ledger rows into the split by hand in this part;
  the general file should end up with 3–5 lines.

### Acceptance
- `tools/check_claude_diff.py` still passes on main; a scratch curator branch that edits
  `datasets/m5_ca1/PRIORS.md` passes and one that edits CLAUDE.md below the marker fails.
- `make scorecard` output is unchanged for existing sessions.
- The researcher's CLAUDE.md loop step 1 names both lessons files and the dataset ledger.

---

## Part E — Scheduled cycle and cost

### Tasks
- `tools/cycle.sh <dataset>`: runs one full cycle unattended using headless sessions
  (`claude -p` with a permission policy that allows exactly the researcher's, adversary's,
  and curator's write paths): researcher (time cap from CLAUDE.md) -> adversary on the
  session's exp/* branches -> curator -> adversary on the curator branch -> merge gate ->
  scorecard. Promotion is NOT in the cycle: it needs the human's holdout run. The cycle
  ends by printing the challengers that are ready for a holdout decision.
- Each session's start, end, and API token usage are written to `runs/sessions.csv`
  (`session, role, dataset, started, ended, input_tokens, output_tokens, cost_usd`). This
  is the cost-per-run number the v0 RESULTS.md could not report.
- A launchd/cron entry template (not installed by the agent) that runs `tools/cycle.sh`
  nightly and posts the scorecard line and the ready-for-holdout list to a file the human
  reads in the morning.
- The cycle refuses to start if the working tree is dirty, main is behind origin, or a
  previous cycle's lock file exists.

### Acceptance
- One cycle run by the human via `tools/cycle.sh m5_ca1` completes end to end and
  `runs/sessions.csv` has four rows with non-empty token counts and cost.
- The cost per researcher run (session cost / runs logged) is printed and recorded in
  `RESULTS.md` under the v0 item it fills in.
- The lock and dirty-tree refusals are demonstrated.

---

## Human gates, permanently
- `make holdout` and `make score-holdout`; `runs/holdout.csv`; every promotion
  (`tools/promote.py` runs only with a holdout row the human produced).
- Edits to `champion.json` outside `tools/promote.py`.
- Everything the v2 spec lists (Rules block, frozen files, weekly scorecard read).

## Out of scope for v3
- Making the champion good: all-stores data, the 12-level WRMSSE, the M5-recipe baseline
  (direct multi-horizon, richer features, Tweedie with early stopping, ensembling). That is
  SPEC v4, and it depends on v3's data contract and promotion path existing first.
- Any dataset other than m5_ca1 (a second adapter is the first v4 task, to prove the
  contract).
- Any private data. The contract is what would make that possible later; this repo stays
  public-data only.
- Serving beyond a parquet file and a CLI (no API, no UI).
- Hermes Agent or any other runtime for the sessions.
