# Adversary re-review — exp/r070

**Verdict: FAIL** (item 5, fold consistency, on the independent-seed rerun: fold 8 (origin
2016-02-29) regresses by +0.002293 against a tolerance of 0.001255 at seeds 11,99, and the harness
keep rule on those seeds returns `discarded`. Across all five seeds now available, fold 8 is worse
than the parent at four of five.) Items 1-4, 6, 7 and 8 pass. The aggregate gain itself is real and
reproducible; what fails is the requirement that the improvement hold on every fold.

This completes adversary/reviews/exp/r070.md (adversary-20260913-3, runs.csv row r076), which was
INCONCLUSIVE only because items 7 and 8 could not run in that session. Items 1-4 are not repeated
here; their findings stand and are summarized in one line each. Reviewed from main at d300acd,
session adversary-20260913-5. Both reruns used the notes' recipe (checkout exp/r070 --
src/features.py src/model.py; KEPLER_RUNS_DIR=adversary/reruns make backtest ...; checkout main --
src/features.py src/model.py). `src/` was restored after each; `git status` is clean apart from
this file and the runs.csv row.

Branch: exp/r070 = r060 + r061 + 5219469 (`lgbm_xmas0_tgd_r3_o80hl120`: 80 training origins,
120-day recency half-life on r061). Logged r070: WRMSSE 0.798186, spread 0.001385, verdict kept
against parent r061 (0.803303). Champion lgbm_xmas0 is r037 (0.805456).

## 1-4. Look-ahead, target leakage, holdout, frozen files — clean (from r070.md)

1. No feature change; sample weights depend only on origin index; every training origin satisfies
   `candidate + 27 < fold_origin`. 2. No new column; longer window is pre-origin sales. 3. `git grep
   -n holdout exp/r070 -- src/ findings/`: same 38 hits as main, none in findings/. 4. `git diff
   v1-harness exp/r070 -- src/scorer.py src/report.py src/score_holdout.py src/backtest.py` matches
   main; `git diff main exp/r070 -- src/backtest.py src/scorer.py src/report.py src/score_holdout.py
   Makefile tools/ CLAUDE.md` is empty.

## 7. Noise floor — PASS

Command:
```
git checkout exp/r070 -- src/features.py src/model.py
KEPLER_RUNS_DIR=adversary/reruns make backtest MODEL=lgbm_xmas0_tgd_r3_o80hl120 DATASET=m5_ca1 SEEDS=11,99 AUTHOR=adversary SESSION=adversary-20260913-5 PARENT=r061
git checkout main -- src/features.py src/model.py
```
Result: adversary/reruns row **r017** (detail adversary/reruns/detail/r017.json), 501.3 s.
WRMSSE 0.798218 (spread 0.000958), WAPE 0.760660, bias -0.008949, h1-7 0.735090, h8-14 0.758159,
h15-28 0.774817. Per-seed aggregate: seed 11 = 0.797739, seed 99 = 0.798697.

Paired gain over r061 (0.803303): **+0.005085**. max(logged spread 0.001385, rerun spread
0.000958) = 0.001385. Gain is 3.7x the larger spread; harness threshold on these seeds
0.001916, paired_gain PASS. Pooling all five seeds (42, 7, 123, 11, 99): child mean 0.798199,
five-seed spread 0.001385 (min 0.797663 at seed 7, max 0.799048 at seed 123), gain +0.005104.
The gain is not noise.

## 8. Determinism — PASS

Same recipe with the default seeds (SEEDS omitted -> 42,7,123). Result: adversary/reruns row
**r018** (detail adversary/reruns/detail/r018.json), 986.1 s (the machine was running another
backtest). config_hash 5f39caedbfa9 on both rows. All twelve columns match the logged r070 row
exactly: wrmsse 0.798186, wape 0.761406, bias -0.008983, wape_h1_7 0.736043, wape_h8_14 0.758737,
wape_h15_28 0.775545, wrmsse_spread 0.001385, wape_spread 0.002201, bias_spread 0.004266,
wape_h1_7_spread 0.001471, wape_h8_14_spread 0.001353, wape_h15_28_spread 0.003070. The eight
per-fold means and per-fold wrmsse_spreads in the two detail files are identical to nine decimals.
Keep rule on the rerun: paired gain +0.005117 PASS, no_fold_regresses 8/8 PASS, bias PASS,
verdict kept, as logged.

## 5. Fold consistency — FAIL on the independent seeds; fold 8 regresses

Logged run (runs/detail/r070.json, unchanged from r070.md): no_fold_regresses 8/8 pass; fold 8
delta +0.001348 against tolerance 0.002896; largest single-fold share of the summed gain 38.0%.

Rerun r017 (seeds 11,99) keep_rule.no_fold_regresses vs r061:

| fold | origin | r061 | r017 | delta | tolerance | pass | share of summed gain |
|---|---|---|---|---|---|---|---|
| 1 | 2015-11-23 | 0.823604 | 0.821767 | -0.001837 | 0.003409 | yes | 4.5% |
| 2 | 2015-12-07 | 0.814159 | 0.804191 | -0.009968 | 0.001690 | yes | 24.5% |
| 3 | 2015-12-21 | 0.835075 | 0.819185 | -0.015890 | 0.004992 | yes | **39.1%** |
| 4 | 2016-01-04 | 0.785411 | 0.777623 | -0.007788 | 0.001621 | yes | 19.1% |
| 5 | 2016-01-18 | 0.794178 | 0.790133 | -0.004045 | 0.001688 | yes | 9.9% |
| 6 | 2016-02-01 | 0.801558 | 0.800062 | -0.001496 | 0.003489 | yes | 3.7% |
| 7 | 2016-02-15 | 0.790515 | 0.788569 | -0.001946 | 0.001849 | yes | 4.8% |
| 8 | 2016-02-29 | 0.781924 | 0.784217 | **+0.002293** | 0.001255 | **no** | -5.6% |

Harness verdict on r017: **discarded** ("7/8 folds within tolerance; worst fold 8
delta=+0.002293 tol=0.001255"). No fold supplies more than half the gain (max 39.1%; folds 2-4
together 82.7%, the same holiday-weighted shape as the logged run).

Fold-8 WRMSSE by seed, child vs parent:

| seed | child fold 8 | parent fold 8 | child - parent mean (0.781924) |
|---|---|---|---|
| 42 | 0.783096 | 0.782393 | +0.001172 |
| 7 | 0.781911 | 0.782027 | -0.000013 |
| 123 | 0.784808 | 0.781353 | +0.002884 |
| 11 | 0.783589 | (not run) | +0.001665 |
| 99 | 0.784844 | (not run) | +0.002920 |

Five-seed child fold-8 mean 0.783650, parent 0.781924, delta **+0.001726**; worse at four of five
seeds, and the four losses (0.0012 to 0.0029) all exceed the parent's own fold-8 seed spread
(0.001040). Five-seed child-minus-parent fold means: -0.001622, -0.010198, -0.015701, -0.008370,
-0.003751, -0.001681, -0.001235, +0.001726. Every fold but 8 improves; fold 8 gets worse.

Why the logged run passed and the rerun did not: the tolerance is max(parent fold spread, child
fold spread). At seeds 42,7,123 the child's fold-8 spread was 0.002896 (seed 123 is the high
outlier), which made a +0.001348 regression pass. At seeds 11,99 the child's spread was 0.001255
and the same-shaped regression (+0.002293) failed. A pooled five-seed tolerance would be
max(0.001040, 0.002933) = 0.002933, which +0.001726 would pass, so a human may reasonably read
this as marginal. The checklist wording is that the improvement must hold on all folds, and the
adversary's independent evidence is that it does not hold on fold 8: the sign is consistent,
the harness's own rule discards the run on the independent seeds, and the gain is 85% holiday
folds trading against a late-February loss. That is the pattern item 5 exists to catch, so FAIL.

## 6. Concentration — 56.1%, under the 60% bar (re-checked with r017)

Improvement per series = weight_norm x rmsse (r061 per_series) - weight_norm x rmsse (r017
per_series), joined on id (3,049 series). Volume = parent `actual`. Top 152 by volume (5%,
35.1% of volume): 0.003166 of net 0.005641 = **56.1%** (logged run in r070.md: 52.7%). On the
`contrib` column: 0.002828 of 0.005085 = 55.6%. 1,480 series improve, 1,483 worsen, 86
unchanged; gross +0.008718 against -0.003077. Slightly more concentrated than the logged run,
still under the threshold, so no INCONCLUSIVE from this item.

## The r060 link in the chain

r070 <- r061 <- r060 <- r037. r060 was graded FAIL on item 5 by adversary-20260913-3 (100% of its
gain on fold 1, a Thanksgiving multiplier; folds 2-8 unchanged to six decimals). It does not
change this verdict, for two reasons. First, this review's FAIL is on fold 8 of r070's own
increment over r061 and would stand on any base; r060's effect is confined to fold 1, where r070's
delta is small and within tolerance at every seed set. Second, even had r070's increment passed
every item, exp/r070 carries r060's src/ change: promoting or merging the branch brings in a link
that FAILed, so the branch could not be promoted without a human overruling the r060 review. The
r060 FAIL therefore blocks the branch independently but is not what decides r070's grade.

## Other observations (not gates, carried from r070.md)

80 origins and the 120-day half-life were changed together (H023); which knob carries the gain is
not isolated. Bias grows from -0.004547 to -0.008983 (|bias| well under the +0.02 guardrail);
fold-6 bias is -0.024834 in both the logged run and the rerun.

## Logged

runs/runs.csv row r078, model_name=exp/r070, status=rejected, author=adversary,
session=adversary-20260913-5, metrics and spreads = item-8 rerun r018 (identical to logged r070).
Row r076 (adversary-20260913-3) is left as it was. Rerun rows r017 and r018 are in
adversary/reruns/runs.csv (gitignored).
