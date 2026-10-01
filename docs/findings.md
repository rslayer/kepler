# Findings

What the loop found, what it ruled out, and what we learned about running forecasting research
with autonomous agents. Run IDs (`r###`) refer to rows in `runs/runs.csv`; each has a write-up
in `findings/`. Hypothesis IDs (`H###`) refer to `hypotheses/m5_all/ledger.csv`.

## Summary

| Claim | Result |
|---|---|
| Throughput | 49 scored, committed runs per hour from one researcher session; about $0.70 of agent cost per run |
| Integrity | The adversary caught a planted leak and rejected every real candidate whose gain did not survive reseeding |
| Transfer | Two promotions, each better on the frozen holdout: 0.723 → 0.626 → 0.622 |
| Self-correction | Backtest gains overstated holdout gains about 5:1; the loop found why and fixed it (about 1.5:1) |

The champion (holdout 0.622) beats every published M5 benchmark and is about 0.03 short of the
leaderboard's top 50 after adjusting for our harder evaluation window.

## How the project unfolded

| Version | Focus | Outcome |
|---|---|---|
| v0 | One store, one department (823 series) | 49 runs/hour; planted leak caught. Honest gains (~0.005) were the same size as seed noise (~0.003), so none survived. |
| v1–v3 | One store, all departments; seeds, keep rule, promotion | First champion promotions (Christmas-zero, then Thanksgiving postprocess). |
| v4 | Full M5 panel, 12-level WRMSSE | The M5 recipe built one ingredient at a time. |
| v5 | Certifiable runs | Seed bagging, parallel fits, run audit. |
| v6 | Keep rule | Replaced threshold tests with a sign test and a median guard. |
| v7 | Hierarchical reconciliation | Washed out at full scale. |
| v8 | Screening tier | Retired a degenerate screen; the holdout rejected an ensemble that won the backtest; the recipe promoted (0.626). |
| v9 | Parallel search, year-round folds, ledger | Capacity found by an automated search loop and promoted (0.622). |
| v10 | Calibrated folds, model diversity | `holdout_mirror` folds; foundation-model and level-aware levers ruled out. |

`RESULTS.md` and `HARNESS_CHANGELOG.md` record each version in full.

## What worked

**The M5 recipe (champion v1, holdout 0.626).** A LightGBM pipeline with direct multi-horizon
models, rolling statistics, price and calendar features, built ingredient by ingredient. It beat
the baseline on every backtest fold and on the holdout (0.723 → 0.626).

**Capacity (champion v2, holdout 0.622).** An automated search loop over configuration space
found that raising `num_leaves` from 127 to 511 helped consistently, including on spring folds.
It was kept on the full panel (7 of 8 folds), passed all eight adversary checks including an
unseen-seed rerun, and improved the holdout by 0.0041 (r147).

**A calibrated backtest.** Moving to folds that mirror the holdout's calendar window made
backtest gains predictive of holdout gains. This is the most durable result of the project:
every later candidate was judged on a backtest that no longer overstated transfer.

## What did not work

Every rejected idea has a ledger row with its mechanism, and `tools/ledger_check.py` stops the
loop from trying it again.

| Lever | What was tried | Result | Mechanism |
|---|---|---|---|
| Recursive forecasting | One-step model applied recursively; four target transforms; a debiased version blended with the direct model | Rejected, then blocked | Errors compound along the horizon (bias +9.9% to −30% across variants). The debiased blend won both backtest tiers but lost the holdout (0.644 vs 0.626). |
| Longer training history | Three years of origins instead of ~9 months | Rejected | +0.006 overall but −0.057 on spring folds. Seasonal peaks drift year to year; recent history beats more history. |
| Finer horizon models | 7 and 28 models instead of 4 weekly ones | Rejected | Fewer rows per model; holiday folds lost 0.03–0.07 because holidays are rare per horizon day. |
| Hierarchical reconciliation | Middle-out reconciliation, full and partial | Rejected | Helped the screen but every level got worse at full scale: a light aggregate model cannot beat 30,490-series bottom-up. |
| Objective ensembles | Regression + Tweedie mean; validation-weighted stacking | Rejected | Members too similar, and Tweedie is weaker. Nothing to average away. |
| Per-store models | One model per store | Rejected | 0.703 vs 0.695. |
| Lower regularization | min_child_samples 50 | Rejected | Worse overall and on spring folds. |
| Zero-shot foundation model | Chronos-Bolt-small, alone and blended | Rejected | 2.6× worse than the champion (1.68 vs 0.65), bias −35%. It under-forecasts intermittent demand and the error compounds at aggregate levels, where WRMSSE is decided. |
| Level-aware feature | Store-category aggregate level as a feature; gated off in holidays; stacked with capacity | Rejected by the adversary | Real effect: helps calm months and spring, hurts holidays. The stack was kept on both tiers (+0.0063 screen, +0.0038 full panel), but the gain fell to +0.0011 on an unseen seed, inside the noise. |

## The mirages that were caught

These are the cases where something looked like progress and the gates stopped it. Each would
have cost a holdout shot, or been promoted, without the corresponding check.

| Candidate | Looked like | Caught by | Evidence |
|---|---|---|---|
| Planted look-ahead feature | 772 of 777 series improved | Adversary, look-ahead check | The window reached past the forecast origin |
| Two early researcher branches | Gains above threshold at one seed | Adversary, concentration and reseeding | 72% of one gain came from a single series; the other fell to 0.0005 at another seed |
| Debiased recursive + direct ensemble | Won both backtest tiers, every level | The frozen holdout | 0.644 vs the champion's 0.626 |
| Three years of history | +0.006 aggregate, 6 of 8 folds | Year-round folds | −0.057 on the spring folds that mirror the holdout |
| Level-aware feature + capacity | Kept on both tiers | Adversary, unseen-seed rerun | +0.0038 bagged became +0.0011 on seed 11 |

## Lessons for practitioners

1. **Seed noise is as large as honest gains.** On M5, single-seed improvements of about 0.005
   sat inside a seed spread of about 0.003. Average several seeds and compare runs fold by fold
   on paired gains, not on a single headline number.
2. **Your folds must reach the evaluation window.** A backtest that never forecasts the
   holdout's season will reward models that fail exactly there. Mirror the evaluation window
   in prior years.
3. **WAPE gains are not WRMSSE gains.** Dollar-weighted, hierarchy-averaged error is decided at
   the aggregate levels. Many changes improved WAPE in every horizon bucket and did nothing for
   WRMSSE.
4. **A holiday can carry a mean.** One Christmas fold once outvoted seven calm-month losses. Use
   a sign test and a median guard, not a mean gain.
5. **Ensembles need different and comparably good members.** Two near-identical models, or a
   much weaker one, add nothing.
6. **Zero-shot foundation models are not ready for intermittent retail demand.** Untuned, they
   regress toward low values; an evaluation on your own data should come before any adoption.
7. **Keep a ledger of mechanisms.** Recording why an idea failed is what stops an autonomous
   loop from rediscovering the same dead end.
8. **Make the holdout physically unreachable.** The agents never had a path to it, so the final
   check could not be quietly optimized against.

## Open questions

- **A diverse model family of comparable quality.** The zero-shot foundation model failed; a
  fine-tuned one is the untried candidate for a genuinely different ensemble member.
- **A wider search.** The configuration search covered capacity and a few regularization
  settings. A larger search on more compute might find more, now that the backtest is calibrated.
- **Level-aware modeling.** The aggregate signal is real but small. Modeling aggregate levels
  directly, rather than as a feature, has not been tried.
- **The last 0.03.** Closing the gap to the top 50 likely needs one of the above rather than
  further tuning of the levers already explored.
