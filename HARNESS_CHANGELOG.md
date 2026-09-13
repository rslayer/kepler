# Harness changelog

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
