# SPEC v4 — Model quality on the leaderboard scale (kepler, Step 5)

Purpose: make "world-class" measurable and then move toward it. v0–v3 proved the loop and
built the engine on one store, scored at the item level. v4 (1) puts the engine on the full
M5 dataset with the competition's official 12-level WRMSSE, scored on the competition's own
evaluation window so the number is directly comparable to the public leaderboard
(winner 0.520; top-50 roughly 0.57; the organisers' statistical benchmarks 0.75–0.85 —
the last two are approximate and should be re-read from the leaderboard before they are
quoted); (2) keeps the fast one-store harness as a screening tier so the loop's throughput
survives; (3) replaces the 300-tree baseline with the published M5 recipe as the new
champion, built by hand, so the loop refines a strong model instead of rediscovering 2020;
(4) makes promotion seasonal-aware through the live scoreboard. Nothing in v4 changes the
keep rule, the adversary's checklist, or the fold design.

Hand this file to Claude Code at the repo root and say: "Read SPEC_v4_quality.md and
execute Parts A through E in order. Stop after each part and report against the
acceptance criteria. Do not run any researcher, adversary, or curator session." Part C is
modelling work the harness owner does directly (it is the baseline, not an experiment);
everything the researcher later does is measured against it.

Frozen for this session: `src/scorer.py` (the level-12 scorer stays as is and keeps
scoring `wrmsse`), `src/report.py`, fold logic and keep rule in `src/backtest.py`. The new
hierarchical scorer is a new frozen file once tagged.

Definitions:
- **Screening tier**: dataset `m5_ca1` (3,049 series, ~5 min per backtest). Where the
  researcher iterates.
- **Confirmation tier**: dataset `m5_all` (30,490 series, all 10 stores). Where a screened
  candidate must also win before it can be promoted.
- **Yardstick**: the hierarchical WRMSSE of a model fit on d_1–d_1913 and scored on
  d_1914–d_1941, the competition's evaluation period. For `m5_all` this IS the holdout; it
  is scored once per model by the human, exactly like `make score-holdout` today.
- **Recipe**: the feature and model design shared by the top M5 solutions (below).

---

## Part A — Full dataset and the hierarchical scorer

### Tasks
- Adapter `m5_all` (`src/adapters/m5.py`, same class, `store_id=None`): all stores. Snapshot
  = `sales_train_validation.csv` (d_1–d_1913, all 30,490 series). Holdout = the 28 extra
  days in `sales_train_evaluation.csv` (d_1914–d_1941), written to `holdout/m5_all/` by
  `make holdout DATASET=m5_all` WITHOUT cutting the visible snapshot — the agents already
  see exactly what competitors saw. `is_cut()` for this adapter checks the holdout file
  exists rather than comparing end dates. Series attributes: item_id, dept_id, cat_id,
  store_id, state_id. Roles add `hierarchy`: the 12 M5 aggregation levels as lists of
  series columns (`[]` total; `[state_id]`; `[store_id]`; `[cat_id]`; `[dept_id]`;
  `[state_id, cat_id]`; `[state_id, dept_id]`; `[store_id, cat_id]`; `[store_id, dept_id]`;
  `[item_id]`; `[item_id, state_id]`; `[item_id, store_id]`).
- `src/scorer_hier.py` (new; frozen after Part E): `score_window_hier(truth, pred,
  train_long, prices, calendar, series, hierarchy)` aggregates forecasts and actuals to
  every level, computes RMSSE per aggregate with the same scale/weight definitions as
  `src/scorer.py`, weights levels equally (the competition rule), and returns
  `wrmsse_hier` plus a per-level table. It must reproduce the competition's published
  weights for the evaluation period to four decimals on `m5_all` (the organisers' weight
  file is public; download it into `data/m5_all/raw/` as part of `make data`).
- `runs/runs.csv` gains `wrmsse_hier` (mean over seeds) and `wrmsse_hier_spread`, appended
  last; `tools/migrate_runs.py` backfills empty. `make backtest` logs them whenever the
  dataset's roles include `hierarchy`; otherwise empty. The per-level table goes into the
  detail JSON under `hier`.
- Keep rule: unchanged in form. On datasets with `hierarchy`, `--parent` evaluates all three
  conditions on `wrmsse_hier` instead of `wrmsse`; the detail JSON records which metric the
  verdict used (`keep_rule.metric`).
- Runtime: a `m5_all` backtest with `lgbm_baseline` must finish under 60 minutes on this
  laptop with `SEEDS` run sequentially. If it does not, Part E's parallelism moves earlier.

### Acceptance
- `make data DATASET=m5_all` and `make holdout DATASET=m5_all`: 30,490 series x 1,913 days
  visible; holdout has 30,490 x 28; manifests written; the screening tier `m5_ca1` is
  untouched (hashes unchanged).
- `make backtest MODEL=seasonal_naive DATASET=m5_all` logs `wrmsse` and `wrmsse_hier`;
  `wrmsse_hier` for the seasonal naive is in the range the organisers published for naive
  methods (roughly 1.0–1.1); the per-level table has 12 rows.
- `make backtest MODEL=lgbm_baseline DATASET=m5_all` completes under 60 minutes and twice
  gives identical means and spreads.
- `make backtest MODEL=lgbm_baseline DATASET=m5_ca1` still reproduces r033 to six decimals.

---

## Part B — Two-tier harness

### Tasks
- `CLAUDE.md` Loop: step 5 runs on `DATASET=m5_ca1`; a new step 7a: "If the harness
  printed verdict=kept on m5_ca1, run the same model with `DATASET=m5_all
  PARENT=<the champion's m5_all run>`. The result is kept only if BOTH verdicts are kept.
  Log both runs; the findings file reports both." The 3-hour cap counts both tiers.
- `champion.json` entries are per dataset already; add `m5_all` (seeded in Part C).
  `tools/promote.py` for `m5_all` additionally requires the same model to have a kept run
  on `m5_ca1` in the same session (condition 1b) — a candidate must win the screen and the
  confirmation.
- `tools/scorecard.py`: per session, count screening runs, confirmation runs, and
  "confirmed kept" separately.
- Adversary harness notes: reruns for `m5_all` branches use `SEEDS=11` (one extra seed) to
  keep review time under an hour; item 7 compares against the logged three-seed spread.

### Acceptance
- A synthetic session (harness owner, `AUTHOR=human`) that logs one m5_ca1 kept run and one
  m5_all run of the same model shows both on the scorecard with the confirmation counted.
- `tools/promote.py exp/<x>` for `m5_all` refuses with condition 1b when the m5_ca1 kept run
  is absent (demonstrate on a scratch branch).

---

## Part C — The recipe baseline (harness owner, modelling work)

### Tasks
Implement `lgbm_recipe` in `src/model.py` (and its features in `src/features.py`), one
change at a time on a branch `recipe/*`, each step backtested on `m5_ca1` with
`PARENT=<previous step>` so the ledger records what each ingredient was worth. Ingredients,
in order:
1. Capacity: `n_estimators` 3000 with early stopping on the newest training origin held
   out as validation; `learning_rate` 0.02; `num_leaves` 127; `min_child_samples` 100;
   `feature_fraction` 0.7; `bagging_fraction` 0.7 with `bagging_freq` 1 (seeded).
2. Objective: Tweedie, variance power 1.1, with a per-series level correction: the ratio of
   mean sales over the 28 days before the origin to the mean over the training window,
   applied as a feature (not a multiplier) — this is the level-growth fix the v0 lessons
   asked for (ledger H027).
3. Direct multi-horizon: four models, one per horizon week (h1–7, 8–14, 15–21, 22–28), each
   with lags chosen so every lag is strictly before the origin (week k uses lags >= 7k).
4. Rolling statistics at the origin: mean, std, max over 7/14/28/56/180 days; zero-run
   length; days since first sale; days since last sale.
5. Price: price relative to the item's max, price momentum (this week / last week), price
   relative to the department mean that week, count of items in the department on
   promotion.
6. Calendar: event lead/lag flags (±3 days around every event), SNAP for the series' own
   state, day-of-month, week-of-year.
7. Per-store models on `m5_all` (10 fits per horizon week) versus one global model: keep
   whichever the harness keeps.
Then: `make backtest MODEL=lgbm_recipe DATASET=m5_all`; `make score-holdout MODEL=lgbm_recipe
DATASET=m5_all` (the yardstick; human-run, one shot); `tools/promote.py` for `m5_all`
against a seeded `m5_all` champion entry for `lgbm_baseline` (which needs its own yardstick
row first, also one shot).

### Acceptance
- Every ingredient has a run with `PARENT=` and a findings file; the ledger has one row per
  ingredient with its measured contribution on `m5_ca1`.
- `lgbm_recipe` is kept against `lgbm_baseline` on both tiers.
- Yardstick (`runs/holdout.csv`, dataset `m5_all`): `lgbm_recipe`'s `wrmsse_hier` is below
  0.65 — beating the organisers' benchmarks by a clear margin — and recorded once. The
  world-class goal (0.55 or better) is NOT a v4 acceptance criterion; it is what the loop
  works toward from here.
- `lgbm_recipe` is promoted to `champion/m5_all/v1` through `tools/promote.py`.
- Backtest runtime for `lgbm_recipe` on `m5_all` is recorded; if over 90 minutes, Part E's
  parallelism is mandatory before Part D.

---

## Part D — Live scoreboard as the promotion gate

### Tasks
- `make forecast` gains `--every 28` mode via `tools/backfill.sh <dataset> <n>`: forecasts
  at the last n as-of dates 28 days apart that end inside the visible snapshot, then
  `make evaluate`. For `m5_all` this yields a year of true out-of-sample scores per
  champion in about n x (fit time).
- `tools/promote.py` condition 4 for a dataset with at least 12 live rows for the champion:
  the challenger is backfilled on the same as-of dates (a harness step inside promote,
  allowed because those dates are all before the holdout) and must not be worse than the
  champion on the mean of the paired live scores AND on the yardstick. Ties promote
  (existing rule). A seasonal fix is now judged on the windows that contain the season.
- `runs/live.csv` gains `wrmsse_hier` when available; `tools/live_report.py` shows both.

### Acceptance
- `tools/backfill.sh m5_ca1 12` produces 12 live rows for the current champion; the live
  report shows their mean and spread beside the backtest number.
- A promotion attempt on `m5_ca1` prints the paired live comparison as condition 4 and
  refuses or passes accordingly (demonstrate with the existing `exp/r044` idea
  re-implemented on the champion as a new run, or with a scratch branch).

---

## Part E — Compute

### Tasks
- `--jobs N` on `make backtest`: seeds (and, if N > 3, folds) run in parallel processes;
  results are identical to sequential (determinism check). Default 1; `tools/cycle.sh`
  passes `JOBS=` through.
- A `tools/cloud/README.md` describing the one-box setup that has been tested: instance
  size, `make env`, data download, expected `m5_all` backtest time with `--jobs 8`, and
  cost per backtest. No cloud provisioning is done by an agent.
- Runtime table in `HARNESS_CHANGELOG.md`: per (dataset, model, jobs), seconds per
  backtest, on the laptop and on the box.
- Tag `v4-quality`. `src/scorer_hier.py` joins the frozen set; `make verify-frozen`
  includes it.

### Acceptance
- `make backtest MODEL=lgbm_baseline DATASET=m5_ca1 JOBS=3` matches `JOBS=1` to six
  decimals and is at least 2x faster.
- The changelog runtime table has real numbers for both datasets and both models.
- Tag exists; `make verify-frozen` clean.

---

## Human gates, permanently
- Everything from v0–v3 (holdout/yardstick scoring, promotion, Rules block, frozen files,
  weekly scorecard read).
- The yardstick is scored once per model, ever. It is the leaderboard; treating it as a
  tuning signal would make the headline number meaningless.

## Out of scope for v4
- Deep or foundation models (N-BEATS/N-HiTS, TFT, Chronos, TimesFM, Moirai) — a v5 A/B as
  ensemble members once the recipe champion exists.
- Hierarchical reconciliation methods beyond bottom-up (MinT etc.) — v5.
- Any dataset other than M5; any private data.
- Hermes Agent or any other runtime.
