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
1. Read LESSONS.md (general), then datasets/<DATASET>/LESSONS.md and
   datasets/<DATASET>/PRIORS.md, then hypotheses/<DATASET>/ledger.csv, then
   runs/runs.csv and the last five findings files.
2. Read the error report from the current best run (make report RUN=<id>),
   paying attention to which horizon bucket and which series carry the error.
3. Pick an `untried` row from hypotheses/<DATASET>/ledger.csv that targets the largest
   error component, or add a new row. Never re-run a `discarded` or `kept` row.
   Prefer, in order: feature construction, training target transformation,
   loss function, model hyperparameters, ensembling. Architecture changes
   come last.
4. Implement it in src/features.py or src/model.py.
5. Run make backtest MODEL=<name> DATASET=<DATASET> AUTHOR=researcher
   PARENT=<current best> SESSION=<your session id> HYPOTHESIS=<the ledger row id>.
6. Write the findings file. Log the run. Update the ledger row's status,
   last_run, sessions, and evidence.
7. If kept, commit on exp/<run_id>. If discarded, revert the change.
7a. If the harness printed verdict=kept on the screening dataset (m5_3), run the
   same model once more with DATASET=m5_all PARENT=<the champion's m5_all run> and
   the same SESSION and HYPOTHESIS. The result is kept only if BOTH verdicts are
   kept; log both runs and report both in the findings file. A m5_all backtest takes
   about 90 minutes on this laptop and counts against the three-hour cap.
8. Repeat until told to stop or three hours have elapsed.
9. Before stopping, append any confirmed finding to datasets/<DATASET>/LESSONS.md
   (or LESSONS.md if it is about the loop or the metric rather than the data), one
   line, citing the run.

Report to the human, in one paragraph, at the end of the session:
runs completed, best WRMSSE versus baseline, and the single most
promising unexplored hypothesis.

- If the human has told you that you are the ADVERSARY, adversary/CLAUDE.md is your
  instruction file and overrides this file. The researcher role does not apply.

<!-- RULES: human-owned. Agents never edit above this line. -->
<!-- PRIORS: curator-editable below this line. -->
Priors and domain notes are per dataset: read datasets/<DATASET>/PRIORS.md, where
DATASET is the dataset you were told to work on (default m5_3, the hierarchical screen). The curator rewrites
that file; this file's block below the marker holds only harness notes.

---
Harness notes (how the rules above map onto this repo):
- Log a run as researcher with:
      make backtest MODEL=<name> DATASET=<id> AUTHOR=researcher PARENT=<current best run_id> \
          SESSION=<role>-<YYYYMMDD>-<n> HYPOTHESIS=<H###>
  The harness refuses a researcher run without SESSION and HYPOTHESIS. Use DATASET=m5_3
  (the hierarchical screen; the metric there is wrmsse_hier); every run is logged with its
  dataset. m5_ca1 is the retired item-level screen, kept for its history.
- "Current best" is the champion's backtest_run in champion.json when no kept run is
  built on top of it, otherwise the newest kept run whose parent chain leads to the
  champion. Promotion of a kept-and-passed run to champion is a human action
  (tools/promote.py); you never run it and never edit champion.json.
  A backtest is 8 folds x 3 seeds (about 5 minutes for lgbm_baseline). The harness
  prints the keep rule (paired gain, no fold regresses, bias guardrail) and writes
  verdict=kept|discarded to runs/runs.csv and runs/detail/<run_id>.json.
- Register a new model by adding a class to src/model.py and an entry in MODELS.
  Registered on main: seasonal_naive, lgbm_baseline (r033, WRMSSE 0.810828), lgbm_xmas0
  (r037, champion v1), lgbm_xmas0_tgd (champion since 2026-09-14, champion/m5_ca1/v2, r060,
  WRMSSE 0.804787, holdout 0.788779). Build on the champion. exp/r061 (roll_mean_3 on
  r060, INCONCLUSIVE) and exp/r070 (80 origins + 120-day half-life on r061, FAIL on fold 8
  at independent seeds, marginal) are the strongest unpromoted ideas; both may be
  re-implemented on the champion as new runs.
- Per-fold numbers for any run: make report RUN=<run_id>
- Features are "as-of-origin": every sales-derived feature is evaluated once at the
  fold origin and held constant across the 28-day horizon. Read the LEAK-FREE CONTRACT
  docstring at the top of src/features.py before adding a feature. A feature may only
  read panel columns strictly before origin_pos.
- Check frozen files are untouched at any time: make verify-frozen
