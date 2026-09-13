# PRIORS — m5_ca1

Curator-editable. Rewritten by the curator after each session so a fresh researcher
chooses its first experiments well. Every line cites a run id or a LESSONS line.

Domain notes for this dataset:
- Daily sales at one Walmart store, all seven departments (FOODS, HOBBIES,
  HOUSEHOLD), 3,049 series. Heavy intermittency: many series have zero-sales days.
- Prices change weekly and price drops drive spikes.
- SNAP benefit days matter in California.
- Events (holidays, sports) are in the calendar table.
- The M5 winning solutions used lag features, rolling statistics, price
  features, and LightGBM with Tweedie loss. That is prior art, not a
  constraint.

Priors (what to try first, and what not to bother with; every line cites a run id or a LESSONS.md line):
- Base: the kept chain is r033 lgbm_baseline 0.810828 -> r037 lgbm_xmas0 0.805456 (Christmas-zero postprocess; adversary FAIL on item 5 overruled to PASS by the human, r055) -> r044 lgbm_xmas0_r3 0.804061 (roll_mean_3; adversary INCONCLUSIVE, r054). Build on r044 and expect its gain to be seed-fragile: 66% of it sits in the top 5% of series [LESSONS r037/r055 and r044/r054].
- The largest remaining error is fold 1 (Thanksgiving week): the whole first week is over-forecast (bias +0.054) by a four-day dip that event-day and year-ago-shape features do not reach; a four-day override removes the bias but is worth ~0.0008 aggregate against a ~0.0013 threshold [r047, r048, r049, r050; r049, r050]. Do not spend a standalone run on it (ledger H041).
- First lever: as-of-origin series state. Raw lags 1-3 gained on all eight folds and their 3-day mean passed the keep rule; the quieter the feature, the lower its own bar [r043, r044]. Untried siblings, one per run: other short windows, or the same state at department or store level.
- The keep threshold is twice the child's own seed spread, so a change that adds seed noise raises its own bar: raw lags 1-3 showed a real aggregate gain and missed the paired-gain threshold by under 0.0004 [r043]; 80 origins and num_leaves 31 also gained but each regressed a fold past its tolerance as well [r038, r051]. num_leaves 31 is the strongest hyperparameter signal on v1 (December folds -0.004/-0.008) while min_child_samples 200 is neutral [r041, r045, r046]; retest leaves only in a lower-noise form, and read the spread before the gain.
- Year-ago information: series-level features and 80 origins gain 0.005-0.017 on the Nov-Jan folds and lose the February folds in three runs; the store-level year-ago shape has no February loss but only 60% of the threshold [r038, r039, r040, r048]. Retry only with an event-aligned mechanism for February (ledger H040).
- Long history: 80 origins beat 40 on the December folds in four v0 runs and one v1 run, and on v1 it raises the seed spread fifteenfold and loses folds 6-8 [r008, r011, r013, r024; r038]. Retry only with wider spacing or a recency half-life (ledger H022, H023), never bare.
- Tweedie: alone it under-forecasts 4-5% from level growth, not calibration [r007, r017, r027, r028]; blended equal-weight with L2 it improves WAPE in every bucket but not WRMSSE, inherits -0.011 bias and loses the Christmas fold by 0.008 [r042, r017, r021, r022]. Fix the level growth first (ledger H027); do not add rounds or change the variance power.
- Do not bother with: re-weighting or regularising the same inputs (min_child_samples 200, tempered metric weights, day_of_month: neutral to four decimals) [r041, r045, r046]; WAPE-only features such as price ratios and intermittency state [r015, r026]; any row with status discarded in hypotheses/ledger.csv, which the loop forbids re-running anyway.
- Single-seed and single-fold gains are noise on this data and only the harness verdict counts [adversary r010, r022; r038, r043, r051].
