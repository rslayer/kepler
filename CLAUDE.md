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

Priors (what to try first, and what not to bother with; every line cites LESSONS.md):
- First lever: long training history. 80 origins beat 40 by 0.03-0.04 on the December
  fold in four v0 runs and lost 0.002-0.009 on fold 3 every time [r008, r011, r013, r024].
  The v1 keep rule tolerates a fold-3 loss inside that fold's seed spread, so retry it
  with a recency half-life or wider origin spacing (ledger H022, H023) before anything else.
- Second lever: a Tweedie member in an ensemble with a regularised L2 member. Tweedie alone
  under-forecasts 4-5% from level growth, not calibration [r007, r017, r027, r028]; blended
  it captured the fold-3 gain [r022]. Fix the level growth (H027), do not add rounds or
  change the variance power; if the blend loses folds 2/4, weight the L2 member higher
  before changing members [r021, r023].
- Regularisation (min_child_samples 200, num_leaves 31) gives ~0.005 that failed only on
  fold 3 by noise-sized amounts [r018, r020]; cheap to retest under three seeds.
- Do not bother with: long rolling windows [r006], removing month [r019], dropping
  pre-launch rows [r012], untempered metric weights [r016], WAPE-only features such as
  price ratios and intermittency state [r015, r026].
- On this data a single-seed gain of ~0.005 is noise; only the harness verdict counts
  [adversary r010, r022].

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
  Existing: seasonal_naive, lgbm_baseline (current best, WRMSSE 0.810828, run r033;
  v1 harness, 8 folds x 3 seeds, wrmsse_spread 0.000172).
- Per-fold numbers for any run: make report RUN=<run_id>
- Features are "as-of-origin": every sales-derived feature is evaluated once at the
  fold origin and held constant across the 28-day horizon. Read the LEAK-FREE CONTRACT
  docstring at the top of src/features.py before adding a feature. A feature may only
  read panel columns strictly before origin_pos.
- Check frozen files are untouched at any time: make verify-frozen
