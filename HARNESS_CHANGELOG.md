# Harness changelog

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
