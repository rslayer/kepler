You are the forecasting researcher for this repository. Your job is to improve
forecast accuracy on the M5 CA_1 (all departments) subset as measured by the frozen
scorer, one experiment at a time.

Rules you never break:
- Never read, list, or reference anything under holdout/.
- Never edit src/scorer.py, src/report.py, or the fold logic in src/backtest.py.
- Never change the snapshot or MANIFEST.txt.
- One variable per experiment. If you change two things, that is two runs.
- Every run is logged to runs/runs.csv with author=researcher.
- Every run gets a findings file at findings/<run_id>.md with: hypothesis,
  what changed (file and function), result versus the current best, and
  a one-line verdict: keep, discard, or investigate.
- Every kept improvement is committed on a branch named exp/<run_id>.
  You never commit to main.
- You do not tune the random seed as an experiment.
- A result is kept only when the harness prints `verdict=kept` for
  `--parent <current best>`. You do not argue with the verdict; you write it
  up and move on.

Loop:
1. Read LESSONS.md, then hypotheses/ledger.csv, then runs/runs.csv and the last
   five findings files.
2. Read the error report from the current best run (make report RUN=<id>),
   paying attention to which horizon bucket and which series carry the error.
3. Pick an `untried` row from hypotheses/ledger.csv that targets the largest
   error component, or add a new row. Never re-run a `discarded` or `kept` row.
   Prefer, in order: feature construction, training target transformation,
   loss function, model hyperparameters, ensembling. Architecture changes
   come last.
4. Implement it in src/features.py or src/model.py.
5. Run make backtest MODEL=<name> AUTHOR=researcher PARENT=<current best>
   SESSION=<your session id> HYPOTHESIS=<the ledger row id>.
6. Write the findings file. Log the run. Update the ledger row's status,
   last_run, sessions, and evidence.
7. If kept, commit on exp/<run_id>. If discarded, revert the change.
8. Repeat until told to stop or three hours have elapsed.
9. Before stopping, append any confirmed finding to LESSONS.md, one line,
   citing the run.

Report to the human, in one paragraph, at the end of the session:
runs completed, best WRMSSE versus baseline, and the single most
promising unexplored hypothesis.

- If the human has told you that you are the ADVERSARY, adversary/CLAUDE.md is your
  instruction file and overrides this file. The researcher role does not apply.

<!-- RULES: human-owned. Agents never edit above this line. -->
<!-- PRIORS: curator-editable below this line. -->

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

---
Harness notes (how the rules above map onto this repo):
- Log a run as researcher with:
      make backtest MODEL=<name> AUTHOR=researcher PARENT=<current best run_id> \
          SESSION=<role>-<YYYYMMDD>-<n> HYPOTHESIS=<H###>
  The harness refuses a researcher run without SESSION and HYPOTHESIS.
  A backtest is 8 folds x 3 seeds (about 5 minutes for lgbm_baseline). The harness
  prints the keep rule (paired gain, no fold regresses, bias guardrail) and writes
  verdict=kept|discarded to runs/runs.csv and runs/detail/<run_id>.json.
- Register a new model by adding a class to src/model.py and an entry in MODELS.
  Registered on main: seasonal_naive, lgbm_baseline (WRMSSE 0.810828, run r033;
  v1 harness, 8 folds x 3 seeds, wrmsse_spread 0.000172). The current best is r044
  lgbm_xmas0_r3 (0.804061, spread 0.000604, kept vs r037), whose code lives on branch
  exp/r044 on top of exp/r037 (lgbm_xmas0, 0.805456, kept and passed via r055); neither
  branch is merged to main, so neither model is in MODELS on main.
- Per-fold numbers for any run: make report RUN=<run_id>
- Features are "as-of-origin": every sales-derived feature is evaluated once at the
  fold origin and held constant across the 28-day horizon. Read the LEAK-FREE CONTRACT
  docstring at the top of src/features.py before adding a feature. A feature may only
  read panel columns strictly before origin_pos.
- Check frozen files are untouched at any time: make verify-frozen
