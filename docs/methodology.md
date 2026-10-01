# Methodology

How kepler measures a forecast, decides whether a change is real, and protects the holdout.
Everything here is enforced in code; file references point to where.

## 1. Data

All work uses the public M5 Forecasting dataset (Walmart unit sales, 2011-01-29 to 2016-04-24
for agent-visible data; 1,913 days). A data contract (`src/contract.py`) separates the harness
from the dataset; `src/adapters/m5.py` translates M5 into it. Datasets are registered in
`src/adapters/__init__.py`:

| Dataset | Series | Role |
|---|---:|---|
| `m5_all` | 30,490 | Full panel, all 10 stores. The strict confirmation tier. |
| `m5_screen` | 10,160 | All 10 stores, a fixed one-third sample of items. The fast screening tier. |
| `m5_ca1` | 3,049 | One store (CA_1). Early phases; retired. |
| `m5_3` | — | One store per state. Retired: its degenerate hierarchy (state = store) flipped verdicts relative to `m5_all`. |

`make data` downloads with the user's own Kaggle credentials, builds a parquet snapshot, and
writes a SHA-256 manifest (`data/<id>/snapshot/MANIFEST.txt`, committed). Every backtest
verifies the manifest first and aborts on mismatch.

**The holdout** is the competition's evaluation period, d_1914 to d_1941 (2016-04-25 to
2016-05-22). `make holdout` (a human command) moves it out of the agent-visible data into a
gitignored `holdout/` directory. Agents never read, list or write under it.

## 2. Metric

The headline metric is the M5 competition's **12-level hierarchical WRMSSE**
(`src/scorer_hier.py`, frozen). Forecasts and actuals are summed to each of the 12 levels
(total, state, store, category, department, the pairwise combinations, item, item-state,
item-store), and every aggregate series is scored as:

```
scale_a = mean over training of (y_t − y_{t−1})², from the series' first non-zero day
rmsse_a = sqrt( mean over the horizon of (y − ŷ)² / scale_a )
w_a     = the series' dollar sales over the final 28 training days, normalised within its level
level score  = Σ_a w_a · rmsse_a
WRMSSE_hier  = mean of the 12 level scores (equal weights, the competition rule)
```

Level 12 alone is `wrmsse` (`src/scorer.py`). The harness also reports WAPE, bias
(Σ(ŷ − y) / Σy) and WAPE by horizon bucket (days 1–7, 8–14, 15–28). Dollar weighting means
aggregate levels and high-revenue items dominate: a change that helps WAPE everywhere but not
the top levels often does not move WRMSSE.

## 3. Backtest

`src/backtest.py` runs a rolling-origin backtest. Each fold has a forecast origin and a
28-day horizon. For each fold the model is trained only on data before the origin and
forecasts all 28 days.

- **Seeds and bagging.** Every fold is fit with three seeds (42, 7, 123). The three forecasts
  are averaged and the average is scored (the headline). The spread of the three single-seed
  scores is logged separately and is the noise-floor input for the adversary.
- **Training set.** Each model trains on 40 simulated origins spaced 7 days apart before the
  fold origin, each with its own 28-day target window that closes before the fold origin.

### Fold layouts

The fold layout turned out to be the single most important design choice. Three have been
used:

| Layout | Folds | Window | Why it changed |
|---|---|---|---|
| v1–v8 | 8, 14 days apart, ending at the snapshot | Dec to Apr | All winter. Rewarded winter specialists. |
| `quarterly` (v9) | 8, 91 days apart | 2 springs, 2 summers, 2 autumns, 2 winters | Year-round coverage, but no fold reaches May. |
| `holdout_mirror` (v10) | 4, one per prior year | late April to late May, 2012–2015 | Mirrors the holdout's calendar window. |

The holdout is a May window. Under the earlier layouts no fold forecast May, so a model that
was uniformly better on the backtest but worse in May was invisible until the holdout. Backtest
gains overstated holdout gains by about 5:1. The `holdout_mirror` layout
(`--folds-scheme holdout_mirror`) forecasts the same calendar window in each prior year; on it
the champion's backtest gain (+0.0061) is close to its holdout gain (+0.0041). Screening now
uses `holdout_mirror` with `--fold-weights season_match`.

### Leak-free features

Every sales-derived feature is computed **as of the fold origin** and read only from columns
strictly before it (`src/features.py`, the LEAK-FREE CONTRACT docstring, enforced with asserts).
Target-relative lags (`tlag_k`, the value k days before the target day) are defined only where
the lagged day is before the origin (k ≥ h for horizon day h); elsewhere they are missing.
Calendar, price and SNAP features are treated as known in advance.

## 4. The keep rule

A candidate is compared with a parent run on the same folds. It is **kept** only if all four
conditions hold (`keep_rule` in `src/backtest.py`):

1. **Sign test.** Per-fold gains (parent minus child) are tested with a one-sided binomial sign
   test; the child must improve on significantly more than half the folds (p < 0.05), and the
   mean gain must be positive. Magnitude-independent, so one huge fold cannot carry a loss
   everywhere else.
2. **No fold regresses** beyond the larger of the parent's and child's seed spread on that fold.
3. **Bias guardrail.** |child bias| ≤ |parent bias| + 0.02.
4. **Median gain.** The median per-fold gain is positive and above a 0.002 floor.

With `--fold-weights season_match`, folds whose season matches the holdout (spring) count double
and holiday folds count half in conditions 1 and 4. The default is unweighted so every historical
verdict reproduces exactly.

The rule went through several versions. The first used "gain > 2 × the noisier run's spread,"
which punished changes for their own noise; a later mean-versus-standard-error version wrongly
rejected a model that won all 8 folds because one huge holiday fold inflated the standard
error. `tools/validate_keeprule.py` re-evaluates the run history under any rule change.

## 5. Two-tier screening

- **Screen** (`m5_screen`): a directional filter. A positive mean gain makes a candidate
  *promising*, even if the strict sign test fails, because sampling one-third of items can tip
  a near-tie fold.
- **Confirm** (`m5_all`): the strict gate. Only a `verdict=kept` here advances.

## 6. The adversary

A separate agent (`adversary/CLAUDE.md`), started fresh with no knowledge of the researcher's
reasoning, reviews every candidate against an eight-item checklist and writes a verdict to
`adversary/reviews/`:

1. **Look-ahead:** every feature traced to its source column and date.
2. **Target leakage:** including through aggregations, price tables and calendar joins.
3. **Holdout contamination:** any reference to `holdout/` is an automatic fail.
4. **Frozen-file integrity:** any change to the scorer or fold logic is an automatic fail.
5. **Fold consistency:** fail if one fold supplies more than half the gain.
6. **Concentration:** inconclusive if more than 60% of the gain comes from the top 5% of series.
7. **Noise floor:** rerun on seeds the harness never used; fail if the gain is smaller than the
   seed-to-seed spread.
8. **Determinism:** rerun once; metrics must match to six decimals.

Item 7 has been decisive more than once: gains that cleared every other gate shrank to noise on
an unseen seed.

## 7. Holdout and promotion

The holdout is scored by a human with `make score-holdout`, once per candidate, and only for a
candidate that cleared the screen, the strict keep rule and the adversary. Holdout shots are
treated as scarce (at most two per week). `tools/promote.py` promotes a candidate to champion
only if it was kept on `m5_all`, was promising on the screen in the same session, passed the
adversary,
left frozen files untouched, and is no worse than the current champion on the holdout.
`champion.json` records each champion with its full lineage.

## 8. Reproducibility

- `make backtest` refuses to run on a dirty git tree, so every row in `runs/runs.csv` carries a
  clean commit hash. Each run also has a config hash and a detail JSON (`runs/detail/`).
- Frozen files (`src/scorer.py`, `src/scorer_hier.py`, `src/score_holdout.py`, `src/report.py`,
  `src/backtest.py`, and others) are checked by `make verify-frozen` against a tagged baseline.
- `tools/audit_runs.py` reconciles every run row against its detail file and commit.
- Fits run in parallel across folds (`--fit-jobs`, default floor(vCPU / 4)) with a per-fold
  feature cache; results are bit-identical to the serial run.

## 9. The champion model

`recipe6_calendar_l2_cap511` (`src/model.py`) is a LightGBM implementation of the published M5
"recipe," built one ingredient at a time, each ingredient a separate logged experiment:

- **Capacity:** up to 1,500 rounds at learning rate 0.05 with early stopping (the newest
  simulated origin is the validation set), feature and row subsampling of 0.7,
  **num_leaves 511** (the v2 change from 127), min_child_samples 100.
- **Objective:** L2 regression (Tweedie was tried and under-forecast).
- **Direct multi-horizon:** one model per horizon week (days 1–7, 8–14, 15–21, 22–28), each with
  target-relative lags of 7 to 35 days.
- **Rolling statistics:** means, standard deviations and maxima over 7 to 180 days; zero-run
  length; days since first and last sale.
- **Price:** price relative to its historical maximum, week-over-week momentum, a promotion flag,
  price relative to its group, and the group's promotion share.
- **Calendar:** event lead and lag flags (±3 days), SNAP for the series' own state, day of month,
  week of year; forecasts are set to zero on Christmas Day, when stores are closed.
- **Bagging:** three seeds averaged.
