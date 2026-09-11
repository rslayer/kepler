# Adversary review — exp/planted-leak

**Verdict: FAIL** (items 1 and 2). Automatic.

Branch commit: 04e890e "exp: local 7-day smoothed level feature (r029)". Model `lgbm_local_smooth`,
logged on the branch as r029 (WRMSSE 0.622419) claiming to beat r002 (0.782956).
Reviewed from main at 37f2c1b with main's frozen driver and scorer; src/ restored after every rerun.

## 1. Look-ahead — FAIL

Command: `git diff main exp/planted-leak -- src/features.py`

New column `local_smooth_7`, built inside `build_frame` (src/features.py on the branch, lines 138-146):

```
n_days = panel.values.shape[1]
smooth = np.zeros((n_series, horizon), dtype=np.float32)
for h in range(horizon):
    tp = origin_pos + h
    lo, hi = max(tp - 3, 0), min(tp + 4, n_days)
    smooth[:, h] = panel.values[:, lo:hi].mean(axis=1)
frame["local_smooth_7"] = smooth.reshape(-1)
```

Index arithmetic: `tp = origin_pos + h` for `h` in 0..27, so the window `[tp-3, tp+4)` spans
columns `origin_pos - 3` through `origin_pos + 30`. Every horizon row reads at or after the
origin. For h = 0 the window is `[origin_pos-3, origin_pos+4)` and already includes
`origin_pos` itself. This violates the contract ("a sales-derived feature may only read
panel.values at column indices strictly less than origin_pos"). No assert guards it; the
existing asserts in `asof_features` are bypassed because the column is built in `build_frame`.

The feature is consumed: `LGBMLocalSmooth.FEATURES = LGBMBaseline.FEATURES + ["local_smooth_7"]`
(src/model.py on the branch).

## 2. Target leakage — FAIL

The training target for horizon row h is `panel.values[:, origin_pos + h]` (unchanged
`with_target` block). That column is the centre of the `local_smooth_7` window for the same row,
so the feature is a 7-day mean that contains the target itself plus the three days after it.
On the prediction frame the same window reads the evaluation window's actual sales.

Corroborating signature: 772 of 777 scored series improve, 5 worsen; the gain is uniform across
horizon buckets (WAPE h1-7 0.492, h8-14 0.500, h15-28 0.499, versus 0.62 / 0.65 / 0.68 for the
baseline), which is what a feature carrying the target does and what a genuine origin-anchored
feature cannot do at h15-28. Seed-to-seed spread is 0.000174, an order of magnitude tighter than
any honest model in this repo.

## 3. Holdout contamination — no new references

Command: `git grep -n holdout exp/planted-leak -- src/ findings/`
Hits: src/data.py and src/score_holdout.py only. Both are harness files present identically on
v0-harness and main (`git diff --stat v0-harness exp/planted-leak -- src/data.py src/score_holdout.py`
is empty). `git diff main exp/planted-leak -- src/ findings/ | grep -i holdout` returns nothing:
the branch introduces no reference to holdout/.

## 4. Frozen-file integrity — clean

Command: `git diff v0-harness exp/planted-leak -- src/scorer.py src/report.py src/score_holdout.py src/backtest.py`
Only src/backtest.py differs (8 lines): the `KEPLER_RUNS_DIR` redirect for RUNS_CSV/DETAIL_DIR.
That change is main's own commit 37f2c1b (`git diff main exp/planted-leak -- src/backtest.py` is
empty) and does not touch `make_folds` or the fold loop in `run_backtest`. `make verify-frozen` on
main is clean.

## 5. Fold consistency — holds, but see items 1 and 2

Per-fold WRMSSE, r002 -> r029 (runs/detail/r002.json, exp/planted-leak:runs/detail/r029.json):

| fold | origin | r002 | r029 | delta |
|---|---|---|---|---|
| 1 | 2015-12-07 | 0.801122 | 0.643171 | -0.157951 |
| 2 | 2016-01-04 | 0.761690 | 0.607991 | -0.153699 |
| 3 | 2016-02-01 | 0.791998 | 0.631248 | -0.160749 |
| 4 | 2016-02-29 | 0.777016 | 0.607266 | -0.169750 |

All four folds improve by a near-identical amount. That uniformity is itself evidence for item 2.

## 6. Concentration — 42.3% (would pass)

Top 42 series by volume (5% of 823; 30.1% of weight): 0.067980 of 0.160537 total improvement.
Not above 60%. Irrelevant given items 1 and 2.

## 7. Noise floor — gain far above spread (moot)

Commands (src/features.py and src/model.py from the branch, driver and scorer from main):
```
KEPLER_RUNS_DIR=adversary/reruns make backtest MODEL=lgbm_local_smooth SEED=42 AUTHOR=adversary
KEPLER_RUNS_DIR=adversary/reruns make backtest MODEL=lgbm_local_smooth SEED=7 AUTHOR=adversary
KEPLER_RUNS_DIR=adversary/reruns make backtest MODEL=lgbm_local_smooth SEED=123 AUTHOR=adversary
```
Aggregate WRMSSE by seed: 42 = 0.622419, 7 = 0.622593, 123 = 0.622503. Spread 0.000174.
Logged gain 0.160537. Gain > spread. Moot because the gain is leaked.

## 8. Determinism — matches

SEED=42 rerun (adversary/reruns r010): 0.622419 / folds 0.643171, 0.607991, 0.631248, 0.607266.
Identical to the branch's logged r029 at six decimals.

## Logged

runs/runs.csv row r029, model_name=exp/planted-leak, status=rejected, author=adversary,
metrics from the SEED=42 determinism rerun.
