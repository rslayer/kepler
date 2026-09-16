# Harness changelog

## v5 Part A — seed-averaged forecasts — 2026-09-14 (SPEC_v5_certifiable.md; tag `v5-parta`)

Until v4 a backtest fitted once per seed and scored the three forecasts separately, so the
headline metric carried the full seed-to-seed spread (0.011–0.016 for the recipe on the
hierarchical screen, larger than the real gain of ~0.020). Since this part the three
per-seed forecasts are averaged per series and day and that one forecast is scored
(`bag_seeds`, `--bag-seeds on|off`, Makefile `BAG=`, default on; off reproduces v1–v4
runs bit for bit and keeps their config hash). `<metric>_spread` keeps its meaning (max
minus min of the three single-seed scores, pre-bagging) so the adversary's noise-floor
check has its input. `bagged` is a new column in runs.csv (migration v5; every earlier row
is False) and a field in the detail JSON, which also carries `bagged_aggregate` and each
fold's `seed_mean`. The keep rule reads a bagged parent's bagged headline (and records
`parent_bagged` / `child_bagged`); a bagged child of an unbagged parent is allowed but is
a different statistic and is flagged. Fold logic untouched. Frozen this session and
unchanged: scorer.py, scorer_hier.py, report.py, score_holdout.py, scoring.py, tiers.json.
**Results (m5_3 screen, r114–r116).** Baseline bagged hier **0.670844** (per-seed mean
0.671176, spread 0.003027); recipe bagged hier **0.648900** (per-seed mean 0.651377, spread
0.011121); bagged gain 0.021944. Two bagged baseline invocations (r114, r116) are identical
to six decimals on every metric, spread and fold; config hash b4eec26e00ec. **The recipe
does not clear the keep rule on the screen:** condition 1 fails by 0.0003 (gain 0.021944 vs
threshold 0.022242 = 2 x the recipe's single-seed spread, which bagging leaves unchanged by
design), and condition 2 fails on folds 5–8 (+0.035, +0.032, +0.058, +0.022 against
tolerances 0.006–0.054): the recipe loses the calm late-winter folds at the aggregate
levels — a real, repeatable loss (r104, r107, r108, r115), not seed noise. Bagging moved the
headline by 0.002–0.003, i.e. the seed noise it removes was never the reason the screen
rejects the recipe. Stopped for human review before Part B, as the spec directs; the keep
rule was not loosened. Note for that review: the honest noise floor of a bagged forecast is
the spread across bagged replicates (recipe_bag3, r107: 0.0027 across three seed triples),
not the single-seed spread — but even with that threshold condition 2 still fails.

## v4 (Parts A–C, E partial) — 2026-09-14 (tag `v4-partc`, SPEC_v4_quality.md)

**Part A.** `m5_all` adapter (all 10 stores, 30,490 series; compact wide snapshot; the
competition's evaluation period d_1914–1941 from sales_train_evaluation.csv is the holdout,
visible data untouched). `src/scorer_hier.py` — the 12-level WRMSSE (frozen from this tag;
its item-store level equals src/scorer.py exactly). `wrmsse_hier` / `wrmsse_hier_spread` in
runs.csv; the keep rule uses `wrmsse_hier` on hierarchical datasets (detail JSON records
`metric`). Timeout is a dataset property (m5_ca1 60 min, m5_3 60, m5_all 180). The
organisers' "Scores and Ranks" file is in datasets/m5_all/: winner 0.5204, rank 10 0.5475,
rank 50 0.576; benchmarks sNaive 0.847, ES_bu 0.671; top-50 item-store level 0.875–0.912.
Baselines on m5_all: seasonal_naive hier 1.004; lgbm_baseline hier **0.785** (item level
0.862), 42 min alone, deterministic (r083 = r085).
**Part B.** Two-tier harness: tiers.json, CLAUDE.md step 7a, promote condition 1b (same
model kept on the screen in the same session), scorecard tier columns. **The screen is
`m5_3`** (CA_1, TX_1, WI_1; 9,147 series; all 12 levels; naive 0.896, baseline 0.671,
~10–18 min per run). m5_ca1 is retired to history: its one-store item-level metric rejected
every recipe ingredient that then won on the real metric.
**Part C.** The M5 recipe, one ingredient per run on m5_ca1 (findings r086–r097, ledger
H111–H124): capacity 0.8081, +Tweedie 0.8177 (bias −4.5%), +direct multi-horizon 0.8105,
+rolling 0.8115, +price 0.8111, +calendar 0.8125; the L2 chain 0.8117 → 0.8113. None beat
the champion's 0.8055 at item level. On **m5_all the full L2 recipe scores hier 0.698 vs
0.785, better on all 8 folds, kept (r101)**; on the m5_3 screen 0.651 vs 0.671, a real gain
discarded by a bar set by its own seed spread (0.011; on m5_all 0.016 — ten times the
baseline's). Deviation from the spec: capacity is lr 0.05 / 1500 rounds, not 0.02 / 3000
(budget). Ingredient 7 (per-store models) not yet run. Part C's acceptance (recipe kept on
both tiers, yardstick < 0.65, promoted to champion/m5_all/v1) is NOT met yet: the screen
verdict is blocked by seed noise, and the yardstick is the human's one shot. Next levers, in
order: seed-averaged forecasts (shrinks the bar), bias/scale correction, per-store models,
event-effect features, recency-weighted long history.
**Part E (partial).** `--jobs N` parallel (fold, seed) fits, results identical to sequential
(verified on m5_ca1); parallel fits honour the budget; tools/cloud/README.md with measured
runtimes and the one-box setup. Speedup not yet measured on an idle machine.
**Field notes.** The worktree's harness-owner runs were renumbered r080–r102 at merge (the
loop's cycle-2 rows r060–r079 are canonical; mapping in runs/v4_run_id_map.json). A
keep-rule bug (parent mean read on `wrmsse` instead of the selected metric) crashed the first
m5_all recipe run after 95 minutes; fixed and rerun. The headless allowlist must include
env-var-prefixed commands (`Bash(KEPLER_RUNS_DIR=*)`); cycle.sh now warns when an adversary
session logs no reruns.

## v7 field notes — reconciliation, and the screen is an unreliable proxy — 2026-09-16

SPEC_v7 built middle-out multiplicative reconciliation (src/reconcile.py, recipe6_reconciled):
forecast a smooth aggregate level (store-category) with a light LGBM and scale the recipe's
item-store forecasts so their group sums match, gating the Christmas window + aftermath and
clipping [0.7,1.5]. On the m5_3 screen it is KEPT (r124: hier 0.615 vs 0.649; every aggregate
level L1-L9 better by 0.034-0.059; item levels untouched; the mechanism is textbook). On
m5_all it is DISCARDED (r125: hier 0.723 vs 0.695; EVERY level worse; folds 5-7 blow up). The
reason: on 3 stores the bottom-up aggregates are noisy so the aggregate model adds value; on
30,490 series the recipe's bottom-up aggregates are already excellent, so the light aggregate
model is worse than bottom-up and reconciling toward it hurts. Reconciliation this way does
not close the leaderboard gap.

**The important finding is about the harness, not the model.** The m5_3 screen disagrees with
m5_all in BOTH directions: the recipe screens as discarded but wins m5_all (screen too
strict, v5/v6); reconciliation screens as kept but loses m5_all (screen too lenient, here).
The 3-store screen changes the metric's noise structure vs the full data, so a kept-on-screen
verdict is not evidence of an m5_all win, and vice versa. The two-tier screen->confirm design
(tiers.json, CLAUDE.md step 7a) cannot be trusted as a cheap proxy for model changes that
interact with aggregation. A screen that matches m5_all's noise structure (more stores, or a
stratified sample) is needed before the screen can gate anything. Until then, m5_all is the
only reliable gate. recipe6_reconciled stays registered as a documented discarded experiment;
v7 is a negative result — not tagged, FROZEN_REF unchanged.

## v6.1 — condition 1 is a sign test, not mean-vs-SE — 2026-09-15 (tag `v6-keeprule-1`)

v6.0's condition 1 (mean paired gain > 2 x its standard error) had a false negative: a run
better on EVERY fold is rejected when one fold's gain is large enough to inflate the SE. The
recipe on m5_all is better on all 8 folds (sign_p 0.004) yet v6.0 discarded it, because the
Christmas fold's +0.41 blew up the SE bar to 0.13 against a mean gain of 0.087. The
zero-variance positive control had not exposed it. Condition 1 is now a one-sided sign test:
keep iff the model improves on significantly more than half the folds (binomial
p < KEEP_ALPHA = 0.05) and the mean gain is positive — magnitude-independent. Condition 4
(median gain > 0.002 floor) still carries the worth-a-champion magnitude; conditions 2 and 3
unchanged. Re-validated (tools/validate_keeprule.py): recipe on m5_all KEPT (8/8, p 0.004);
recipe on the m5_3 screen discarded (4/8, p 0.64); per-store on m5_3 now KEPT on the screen
(7/8, p 0.035) as a promising result that the m5_all confirmation (r120, 3/8) correctly
rejects; every bias/ratio/calibration run discarded; the uniform positive control kept. This
unblocked the m5_all recipe promotion (champion/m5_all/v1).

## v6 — a keep rule that measures the gain, not the parent's noise — 2026-09-15 (tag `v6-keeprule`, SPEC_v6_keeprule.md)

Two defects in the keep rule, both found by re-scoring the v5 corpus. **(1)** Condition 1's
bar was `2 x max(parent, child single-seed spread)` — it compared a v5 *bagged* headline
against *single-seed* spreads, and used the noise of the noisier operand rather than the
noise of the difference, so a low-noise child was judged against its noisy parent (per-store
r119, spread 0.0011, was denied by a 0.0222 bar that was all parent noise). **(2)** The real
one: a single mean over eight seasonal folds hid regime trades — the recipe's +0.022 mean vs
baseline is a +0.29 Christmas fold outvoting seven calm-month losses.

**Fix.** Condition 1 now tests the mean paired per-fold gain against its own standard error
(`gain > 2 x SE`, SE over `n_eff = ceil(folds x spacing / horizon) = 4` for the overlapping
8/14/28 screen) plus a 0.002 worth-a-champion floor. New condition 4: the MEDIAN per-fold
gain must be positive and above the floor — a win riding on one fold fails. Conditions 2
(no fold regresses) and 3 (bias guardrail) unchanged; all four required for `kept`. The
single-seed `<metric>_spread` columns are untouched (the adversary's item-7 input). The
detail JSON records `gain`, `se`, `n_eff`, `z`, `floor`, `gain_f`, and `median_gain`. The
event-density regime split first drafted for Part B was dropped: tested against the data,
event density does not separate the recipe's win-folds from its loss-folds (the split is
seasonal-level, not event-driven), so a robust median guard replaced it (human decision).

**Validation (tools/validate_keeprule.py, read-only re-evaluation of the v5 corpus).**

| child vs parent | recorded | v6 | decided by |
|---|---|---|---|
| r115 recipe vs baseline r114 | discarded | discarded | 1 (SE), 2, 4 (median −0.010) |
| r119 per-store vs recipe r115 | discarded | discarded | 1 (SE; fold-2 regression) |
| r117 correction-ON vs r115 | discarded | discarded | 1, 2, 3, 4 |
| r109 ratio-target vs r107 | discarded | discarded | 1, 2, 3, 4 |
| r113 calibration vs r107 | discarded | discarded | 1, 2, 4 |
| r120 per-store on m5_all vs r118 | discarded | discarded | 1, 2, 4 |
| synthetic uniform +0.010 vs r114 | — | **kept** | all four pass |

Every known-bad stays discarded; a constructed uniform improvement is kept — the gate can
still say yes. **Takeaway:** the screen was telling the truth. No recipe variant is better
on the typical fold; they trade holidays for calm months. A champion needs a model that
wins in both regimes, which is a research problem, not a gate problem. Part A acceptance:
r121 (baseline vs itself) discards, gain 0.000 below the floor.

## v5 Parts D & E — parallel benchmark + audit — 2026-09-15 (tag `v5-certifiable`)

**Part D.** m5_all baseline timed at JOBS 1/3/4/7 on this laptop (Apple M4 Max, 14 cores):
44.7 / 28.3 / 28.4 / 53.3 min. Best speedup 1.58x at JOBS=3; more workers oversubscribe
(4-thread fits x 3 already fills 14 cores, and the 12-level scorer is single-threaded between
folds). Rule: `JOBS = floor(cores/4)`. Results identical across worker counts to six decimals.
tools/cloud/BENCHMARK.md has the table, the cost model ($0.70/run agent tokens; 200-run
m5_all cycle ~$140 laptop / ~$216 cloud) and the not-an-idle-machine caveat. Also this
session: the laptop idle-sleeps after 1 minute even on AC and killed the first benchmark
overnight; `make backtest` and cycle.sh now wrap the run in `caffeinate -i` on macOS.

**Part E.** `make backtest` refuses a dirty tree when logging to the canonical runs/ (adversary
KEPLER_RUNS_DIR reruns exempt), so no run is logged with a -dirty hash. tools/audit_runs.py
reconciles every row against its detail JSON and resolves its commit hash: 120 rows, 0
unresolvable hashes, 0 mismatches; r032's row (shifted six columns when the v1 migration
missed a Part-B-layout row) realigned; r100-r102's detail JSONs, lost in the v4 renumbering,
report as a documented NOTE (findings say so; identical reruns are r103/r104/r106).
v4_run_id_map.json verified complete (23 entries). RESULTS.md rewritten for v5.

## v5 Part C — per-store models (recipe ingredient 7) — 2026-09-15 (tag `v5-partc`)

`roles["partition"]` (store_id on M5; src/adapters/m5.py, both layouts) is bound as
`features.PARTITION_COLUMN`; `recipe6_per_store` fits one recipe chain per partition and
concatenates the predictions (role-driven; refuses a dataset without the role). Frames now
carry every series attribute as plain columns (not features). **Results, bagged, correction
OFF:** m5_3 r119 hier **0.637942** vs global r115 0.648900 — better on 7/8 folds, no fold
regresses, bias guardrail passes, aggregate seed spread **0.0011 vs 0.0111** — discarded on
condition 1 alone (gain 0.011 < 2 x the *parent's* spread 0.022). m5_all r120 hier
**0.702771** vs global r118 0.695249 — worse (fold 2 +0.047, bias −2.0% vs −0.9%),
discarded. The screen gain does not transfer to ten stores: cross-store pooling wins.
Wall clock equal to the global model (288 / 960 smaller fits). Keep rule unchanged. Observation
for the human: a child ten times less noisy than its parent cannot clear a bar set by the
parent's noise (r119); SPEC_v5 forbids loosening the rule in this session, so it is recorded
here, not acted on. Frozen set: adapters/m5.py changed (partition role) → re-tag `v5-partc`,
FROZEN_REF moved; the five session-frozen files remain byte-identical to v4-partc.

## v5 Part B — per-series bias correction — 2026-09-14/15 (SPEC_v5 Part B)

`series_correction()` in src/model.py: after prediction, a per-series multiplicative factor
1 + shrink x (actual / predicted over the 28-day validation window − 1), clipped to
[0.5, 2.0], shrink 0.5; the window is the newest simulated origin's rows, which the fold's
models never train on, so the correction is leak-free and role-free (keyed on the contract's
series id). Config-controlled (`CORRECTION` on the model class, in the config hash), default
OFF; `recipe6_calendar_l2_corr` is the one-variable ON model. **Results:** m5_3, both bagged:
OFF r115 hier 0.648900 / bias −0.45%; ON r117 hier **0.661308** / bias **+3.07%** —
discarded on all three conditions (gain −0.012; folds 2 and 8 regress by 0.029 and 0.058;
guardrail 0.031 > 0.025). The correction helps the two calm folds where the recipe
under-forecasts most and hurts the other six; it is the same failure as the store x
department calibration (r113): the model's errors on the last 28 in-sample days do not
persist into the forecast window. m5_all: the bagged correction-OFF reference is r118, hier
**0.695249** (per-seed mean 0.698220 = r106), bias −0.86%; the correction-ON run on m5_all
was skipped by the human after r117 (95 minutes saved for Part C). Branch exp/r117 labels
the correction commit; correction stays OFF for Part C.

## v3 field notes — cycle 2 (2026-09-13), first headless cycle

Run by `tools/cycle.sh m5_ca1 3` after the human renewed the CLI login (the first attempt
aborted on `OAuth session expired`; the script now aborts a cycle when a session fails before
doing work). Researcher-20260913-2: 14 runs in 2h20m, 3 kept (r060 Thanksgiving-dip
multiplier; r061 roll_mean_3 re-implemented on the champion, matching its pre-contract twin
to six decimals; r070 = 80 training origins with a 120-day half-life, the v0 "most
promising unexplored" hypothesis H023, 7 of 8 folds better, best WRMSSE 0.798186), 0
repeats, **cost $9.78 per session, $0.70 per run** — the number v0 could not report.
Adversary: r060 FAIL (item 5: fold 1 supplies 100% of the gain — the same structural
event-in-one-window case as r037's Christmas fix, no override on record); r061
INCONCLUSIVE (item 6, 65% concentration, as its twin r044); r070 INCONCLUSIVE only because
the headless session's rerun command was blocked by a permission prompt (`Bash(make:*)`
does not match `KEPLER_RUNS_DIR=... make ...`; fixed in cycle.sh, plus a warning when an
adversary session logs no reruns). r070 was re-reviewed with reruns afterwards (see
adversary/reviews/exp/r070-rereview.md). Curator branch FAILed item 9 on substance: its
priors built on the FAILed r060, cited discarded single runs as evidence, and aimed the
first experiment at one fold; merge gate refused. The curator's instructions now spell out
those three rules and make it read earlier curator reviews. Cycle wall clock 2h41m, total
agent cost about $19.

## v3 — 2026-09-13 (tag `v3-engine`, SPEC_v3_engine.md)

**Amendment (2026-09-13, human decision):** promotion condition 4 is "holdout not worse
than the champion" (ties promote), not "strictly better". First case: exp/r037's
Christmas-zero fix scored exactly the champion's 0.788779 on a holdout window that contains
no 25 December. Promoted as champion/m5_ca1/v1. Lesson for v4: a single fixed 28-day
holdout cannot adjudicate seasonal fixes; the live scoreboard is the better promotion
instrument once it spans a year of as-of dates.

v2 made the loop learn; v3 makes it an engine. Data contract (`src/contract.py`): panel
(series_id, date, y), series attributes, exog_date, exog_series, and roles; adapters
(`src/adapters/m5.py`) own every dataset-specific name and the download/snapshot/holdout
steps; datasets live under `data/<id>/` and `holdout/<id>/`; `make ... DATASET=<id>`
everywhere; `runs.csv` gained `dataset`. `src/features.py` and `src/model.py` read only
contract tables and roles (`features.bind()` resolves roles into FEATURE_COLUMNS once per
process, so configs and hashes are stable: r057 reproduced r033 to six decimals with the
same config hash 900159c6f3dd). The frozen scorer is fed through `src/scoring.py`, the one
harness file that still spells its legacy column names. Champion registry
(`champion.json`, human-owned) seeded with r033; `tools/promote.py` promotes an exp/*
branch only when kept, adversary-PASS or human-overridden, frozen-clean, holdout-better
(from a human-run `make score-holdout` row it will never produce itself), and cleanly
mergeable on allowed paths; on success it tags `champion/<dataset>/vN` and logs
`runs/promotions.csv`. Serving: `make forecast ASOF=<date>` writes
`forecasts/<dataset>/<asof>/forecast.parquet` + provenance from the champion (a true-future
forecast as of last day + 1 is allowed; the price matrix now spans the exog range);
`make evaluate` scores past forecasts once actuals exist into `runs/live.csv`;
`tools/live_report.py` puts live WRMSSE beside backtest WRMSSE per champion. Memory is per
dataset: `datasets/<id>/{LESSONS,PRIORS}.md`, `hypotheses/<id>/ledger.csv`, with a 3-line
general `LESSONS.md`; CLAUDE.md's block below the PRIORS marker is now harness notes only,
and the curator may touch only memory files and its report (merge_gate condition 1).
`tools/cycle.sh` runs a whole cycle headless (`claude -p`, per-session token cost to
`runs/sessions.csv`, integrity check after every session, lock and dirty-tree refusals);
promotion is deliberately outside it. The researcher's hooks from exp/r037 (FEATURES,
extra_config, postprocess) are on main; the Christmas-zero model itself lives on the ported
exp/r037 branch as the first challenger. exp/r010, exp/r022, exp/planted-leak and the
pre-port exp/r037 (tag exp/r037-v2) and exp/r044 are pre-contract branches: historical.

## v2 field notes — cycle 1 (2026-09-12/13)

First full cycle of the v2 loop, all four agent sessions launched as background subagents
from the harness-owner session with the human's explicit go-ahead (the spec says
human-launched; the cold-start property held because each subagent starts with only its
prompt and its CLAUDE.md). Researcher-20260912-1: 16 runs in 2h08m (376 s/run), 2 kept
(r037 Christmas-zero, r044 roll_mean_3), 0 repeats, stopped itself 52 min early. Adversary:
r037 FAIL on item 5 (gain confined to the two folds containing 25 Dec, zero elsewhere) —
overruled to PASS by the human as structural, recorded as row r055 beside the FAIL row
r053; r044 INCONCLUSIVE on item 6 (66% of gain in top-5% series). Curator branch passed
item 9 with three flagged lines, which the human amended before the gate. Merge gate:
all four conditions met; merged as commit 9626220. Scorecard: keep_rate 0.08 -> 0.125,
repeat_rate 0 -> 0. Fixes made during the cycle: scorecard repeats now use the ledger as
committed at session start (re-testing an inconclusive row is allowed and was being
counted); merge_gate falls back to a merge commit because main always moves after a
curator branch is cut. Operational lessons: subagents background each five-minute
backtest and pause, then resume on completion — that works, and the pause notifications
are heartbeats; stopping one subagent with TaskStop killed another's running backtest
(shared process group), which cost one rerun. For the next adversary spec: item 5 needs an
event-driven clause (a gain confined to the folds whose windows contain a known calendar
event, with zero delta elsewhere, is structural, not concentrated).

## v2 — 2026-09-12 (tag `v2-loop`, SPEC_v2_selfimprove.md)

v1 fixed the keep rule but left the researcher amnesiac: each session started from the same
CLAUDE.md, and the only cross-session memory was findings files nobody re-reads. v2 makes the
loop learn without a human rewriting instructions. Memory: `LESSONS.md` (one line per
confirmed finding, 13 seeded from the v0 session) and `hypotheses/ledger.csv` (30 rows:
every v0 hypothesis with its status, plus untried next steps); the researcher reads both
first, may only pick `untried` or `inconclusive` rows, and appends confirmed findings last.
`runs.csv` gained `session` and `hypothesis_id` (backfilled empty; `tools/migrate_runs.py`
now handles v0/v1/v2 layouts) and the harness refuses a researcher run without both.
`CLAUDE.md` is split by two marker lines into a human-owned Rules block and a
curator-editable Priors block (5 seeded prior lines); `tools/check_claude_diff.py` enforces
the boundary and is part of `make verify-frozen`. A curator role (`curator/CLAUDE.md`)
turns a session's findings and reviews into lesson lines, ledger updates, and a Priors
rewrite on a `curator/<session>` branch. The adversary's harness notes were rewritten for
v1 (`SEEDS=`, logged spreads, `PARENT`, the keep_rule block as evidence, a merge-base rule
that treats pre-v1 `exp/*` branches as historical) and it gained checklist item 9,
instruction leakage, for curator branches. `tools/merge_gate.py` fast-forwards a curator
branch into main only when the diff scope, an adversary PASS, evidence citations, and the
scorecard trend all hold, replacing the human approval. `tools/scorecard.py` writes
`LOOP_SCORECARD.md` (keep rate, runs per kept, repeat rate per session); v0 scores 25 runs,
2 kept, 0 repeats. One frozen-file defect worked around: `report.py` reads
`detail["seed"]`, which v1 detail files lacked; `backtest.py` now writes it as the joined
seed list and the v1 detail files were backfilled. Human gates that remain: holdout,
edits above the RULES marker, and a weekly read of the scorecard and merged curator diffs.

## v1 — 2026-09-12 (tag `v1-harness`, SPEC_v1_harness.md)

v0 could not tell a real gain from seed noise: on the FOODS_3 subset the best honest
improvements (~0.005 WRMSSE) were the same size as the seed-to-seed spread (~0.003), and the
researcher's keep rule ("beats on all four folds at one seed") admitted two wins that
reversed under reseeding. v1 raises the signal-to-noise on three axes and moves the keep
decision into the harness. The subset widens from one department (823 series) to the whole
store CA_1 (3,049 series, all seven departments). Folds go from four at 28-day spacing to
eight at 14-day spacing, windows overlapping by 14 days, the last still ending on the last
visible day. Every backtest now fits once per seed (42, 7, 123) per fold and logs the mean
under the existing metric names plus a `<metric>_spread` column (max minus min across
seeds). `make backtest ... PARENT=<run_id>` evaluates a three-condition keep rule on WRMSSE
and writes `verdict` to runs.csv: (1) paired gain > 2 x max(parent, child) aggregate
spread; (2) no fold regresses by more than that fold's own seed spread; (3) |bias| does not
grow by more than 0.02. Condition 2 uses fold-level spreads deliberately: the aggregate
spread is 10-20x smaller than any single fold's, because averaging eight folds cancels seed
noise, and using it there would discard on ordinary noise. The cost is throughput: a
`lgbm_baseline` backtest went from 18 s to about 317 s. Also in v1: `make data` builds an
uncut snapshot and no longer inspects holdout/; every backtest refuses to run until the
human has cut the holdout; `tools/migrate_runs_v1.py` moved runs.csv to the v1 layout
(`fold_spacing`, six spread columns, `verdict`), backfilling v0 rows with 28 / empty / empty.
Frozen files `src/scorer.py`, `src/report.py`, `src/score_holdout.py` are byte-identical to
v0; fold logic in `src/backtest.py` was edited by the harness owner and is frozen again from
this tag. `src/features.py` and `src/model.py` were not touched.

## Baselines, v0 vs v1

**v0 and v1 WRMSSE are not comparable.** The subset changed (FOODS_3 -> all departments),
the fold set changed (4 x 28-day spacing -> 8 x 14-day spacing, three folds now in
Nov-Dec), and v1 numbers are three-seed means. Compare within a harness version only.

| harness | model | run | WRMSSE | spread | WAPE | bias | folds | seeds | seconds |
|---|---|---|---|---|---|---|---|---|---|
| v0 | seasonal_naive | r001 | 1.016667 | — | 0.7740 | -0.0482 | 4 x 28d | 1 | 1.3 |
| v0 | lgbm_baseline | r002 | 0.782956 | — | 0.6594 | -0.0123 | 4 x 28d | 1 | 18.4 |
| v1 | seasonal_naive | r036 | 1.086397 | 0.000000 | 0.9156 | -0.0099 | 8 x 14d | 3 | 20.7 |
| v1 | lgbm_baseline | r033 | 0.810828 | 0.000172 | 0.7812 | +0.0087 | 8 x 14d | 3 | 314.4 |

v1 keep-rule bar for a child of r033: paired gain > 0.000345 (2 x 0.000172) AND no fold
worse than r033's fold mean by more than that fold's spread (0.0018-0.0039) AND |bias| <=
0.0287. r034 and r035 are byte-identical repeats of r033 (determinism and keep-rule
self-test); r032 is a single-seed 8-fold naive from Part B, superseded by r036.

## Known stale references (out of scope for v1, fix in the adversary step)

- `adversary/CLAUDE.md` harness notes still say `SEED=<n>`; v1 uses `SEEDS=a,b,c` and logs
  spread itself, so checklist items 7 and 8 need rewording against v1 columns.
- Old `runs/detail/r0NN.json` files (v0) have no `seeds` block and cannot be a `--parent`.
