# SPEC v6 — A keep rule that measures the gain, not the parent's noise (kepler)

Purpose: the v5 work proved seed-bagging is not enough to certify the M5 recipe on the
`m5_3` screen, and it exposed a defect in the keep rule itself. This spec fixes the keep
rule. It does NOT try to force any current model through: on the evidence below, no recipe
variant deserves to be kept on the screen yet. The goal is a gate that rejects for the
right reason and can still say yes to a genuinely uniform improvement.

Hand to Claude Code at the repo root: "Read SPEC_v6_keeprule.md and execute Parts A through
D in order. Stop after each part and report against its acceptance criteria before
continuing. Never read, list, or write under any holdout/ path. Commit before every backtest
so no run is logged with a -dirty hash. Run the preflight first and report it before Part A."

Frozen this session (do not edit): `src/scorer.py`, `src/scorer_hier.py`, `src/report.py`,
`src/score_holdout.py`, `src/scoring.py`, `src/adapters/m5.py`, `tiers.json`. The keep rule
AND the fold logic in `src/backtest.py` MAY be edited this session — the human is the author
of this spec and owns the keep rule — but nothing else in the fold path changes. Re-tag
`v6-keeprule` afterward and move `FROZEN_REF`.

Preflight (report, do not fix): `make verify-frozen`; confirm the working tree is clean;
`uv run -- python tools/audit_runs.py` (expect 0 unresolvable hashes). If the tree is dirty,
stop and tell the human.

---

## The diagnosis (read before touching code)

Two defects, one small and one real. Both were found by re-scoring the v5 corpus with
`--reparent` (no new fits).

**Defect 1 — condition 1 compares the wrong quantities.** The paired-gain test is

```
gain = parent_mean - child_mean ;  keep if gain > 2 * max(parent_spread, child_spread)
```

where the spreads are the aggregate single-seed spread (max−min across the three seeds).
Since v5 the headline `parent_mean` / `child_mean` are the scores of the *seed-averaged*
forecast, but the bar is still built from *single-seed* spreads — a category error (a
bagged mean has ~1/√n the dispersion of one seed). Worse, `max(parent, child)` uses the
noise of the *noisier operand*, not the noise of the *difference*. So a low-noise child is
judged against its noisy parent's spread. Example: per-store `r119` (aggregate spread
0.0011) vs the recipe `r115` (0.0111) was denied by a bar of 0.0222 that is entirely the
parent's noise.

**Defect 2 — the real one — a single mean over eight seasonal folds hides regime trades.**
The per-fold gains are not noise around a common mean; they are structurally split by
season. Recipe vs baseline on `m5_3`, per-fold gain (positive = recipe better):

```
fold 1 (21 Dec, holiday)  +0.295
fold 2 (04 Jan)           +0.010
fold 3 (18 Jan)           +0.001
fold 4 (01 Feb)           +0.016
fold 5 (15 Feb)           -0.035
fold 6 (29 Feb)           -0.032
fold 7 (14 Mar)           -0.058
fold 8 (28 Mar)           -0.022
```

The recipe wins the holiday fold enormously and loses every calm late-winter fold. The
aggregate mean (+0.022) is a holiday win averaged against calm-month losses. A gate built on
that mean is asking the wrong question. The honest question is: *is this model better in
every regime, or is it trading one regime for another?* The recipe is trading — it should
not be kept, and the current condition 2 (no fold regresses) already catches it, for the
right reason. But condition 1's mean-based framing is what made "just shrink the spread"
(seed-bagging) look like the fix in v4/v5, when it never could be.

Consequence for this spec: **the fix is to make condition 1 measure the uncertainty of the
gain and to make the keep decision regime-aware, so a holiday win paid for by calm-month
losses is named as a trade, not a win.** Neither change makes the gate more permissive on
the current corpus; both make it correct.

---

## Part A — Condition 1 measures the gain's own uncertainty

### Tasks
- In `src/backtest.py` `keep_rule`, replace the condition-1 bar. The gain is the paired
  per-fold difference on the metric actually scored (the bagged fold metric for a bagged
  run, the seed-mean fold metric for a v1–v4 run — `folds[i][metric]` already holds the
  right one). Compute:
  - `gain_f = parent_fold[i][metric] - child_fold[i][metric]` for each fold i,
  - `gain = mean(gain_f)`,
  - `se = stdev(gain_f, ddof=1) / sqrt(n_eff)`, where `n_eff = ceil(n_folds * FOLD_SPACING / HORIZON)` (windows overlap; on the 8-fold/14-day/28-day screen `n_eff = 4`),
  - keep condition 1 iff `gain > 0` AND `gain > Z * se` AND `gain > FLOOR`.
  - `Z = 2.0`; `FLOOR` = a minimum worth-a-champion improvement on the metric, default
    `0.002` for `wrmsse`/`wrmsse_hier` (tune only if a validation gate in Part C fails, and
    document why). The FLOOR stops a microscopic-but-consistent gain from passing on
    significance alone.
- Keep the single-seed `<metric>_spread` columns exactly as they are: the adversary's
  item-7 noise-floor check consumes them and is out of scope here.
- Record in `keep_rule` (detail JSON) the new fields: `gain`, `se`, `n_eff`, `z`, `floor`,
  and the per-fold `gain_f`. Print the new condition-1 line.

### Acceptance
- `make backtest MODEL=lgbm_baseline PARENT=<a v5 baseline>` still returns `discarded`
  (a model cannot beat itself; gain ≈ 0).
- Re-scoring the corpus in Part C runs without error and the detail JSON carries the new
  fields.
- `make verify-frozen` clean; the five scorer/report files untouched.

---

## Part B — A robust median-gain guard

### Finding that redirected this part
The regime split first drafted here (group folds by forward-window event density) was tested
against the data and does not hold: event density does not separate the recipe's win-folds
from its loss-folds. The recipe's advantage is essentially one fold (Christmas, +0.29); the
Feb-Mar losses are a seasonal-level effect with no clean calendar covariate. So Part B is a
robust central-tendency guard instead of a regime split (human decision, 2026-09-15).

### Tasks
- Add condition 4 to `keep_rule`: the MEDIAN per-fold gain must be positive and above the
  FLOOR (`median(gain_f) > 0 and > KEEP_FLOOR`). The mean (condition 1) is dominated by one
  extreme fold; the median asks "is this model better on the TYPICAL fold?" and rejects a
  win that rides on a single fold. Robust, role-free, no calendar covariate.
- `verdict = kept` iff conditions 1, 2, 3, 4 all pass. Record `median_gain` in the detail
  JSON and print a condition-4 line.

### Acceptance
- Recipe vs baseline on `m5_3`: condition 4 FAILS (median per-fold gain negative), naming the
  "one-fold win" directly. Report the median.
- A uniform improvement (the Part C positive control) passes condition 4.

## Part C — Validate on the frozen corpus and a positive control

A keep rule is only trustworthy if it both rejects the known-bad and accepts a known-good.
No new model fits are needed for the corpus (use `--reparent`); the positive control needs
one construction.

### Tasks
- Re-evaluate, with `--reparent` against the correct parent, and tabulate old vs new
  verdict with the deciding condition:
  - `r115` recipe vs baseline `r114` — must stay `discarded` (condition 4: calm regime).
  - `r119` per-store vs recipe `r115` — report the verdict honestly. On the recorded folds
    its calm-regime gain is positive but fold 2 swings negative; state which condition
    decides and whether it changes from the old rule.
  - `r117` correction-on vs `r115`, `r109` ratio-target, `r113` calibration — must stay
    `discarded` (bias / regressions).
  - `r120` per-store on `m5_all` vs `r118` — must stay `discarded`.
- Positive control: construct one run the rule MUST keep, to prove it can say yes. Build a
  synthetic child from an existing run's recorded per-fold, per-seed forecasts by scaling
  every fold's error toward the truth by a fixed fraction (a uniform, regime-neutral
  improvement), score it through the frozen scorer, and `--reparent` it against its source.
  The rule must return `kept` (positive gain in every regime, above FLOOR and Z·SE). Put
  the constructor in `tools/make_positive_control.py`; it never touches `holdout/` and is
  clearly labelled synthetic (like `tools/make_fixture.py`).
- If any corpus verdict flips to `kept`, stop and report before writing anything: a flip is
  either a real discovery or a bug in the new rule, and the human decides which.

### Acceptance
- The table above; every known-bad stays `discarded`; the positive control is `kept`.
- The deciding condition is named for each row.
- No promotion, no champion change (that stays a human gate with a human holdout score).

---

## Part D — Document, re-tag, and hand back

### Tasks
- Update `CLAUDE.md` (harness notes, below the RULES/PRIORS marker only) and
  `adversary/CLAUDE.md`: the keep rule now tests the paired gain against its own SE with a
  FLOOR, and adds a per-regime consistency condition; the single-seed spread is unchanged
  and is still the adversary's item-7 input. Do not touch the human-owned Rules block.
- `HARNESS_CHANGELOG.md`: one section — the two defects, the fix, the corpus table, the
  positive control, and the plain-language takeaway (the screen was telling the truth; the
  recipes trade holidays for calm months; a champion needs a model that wins in both
  regimes).
- `RESULTS.md`: update the "does the gate pass on m5_3" paragraph to reflect the corrected
  rule and the regime finding.
- Commit on `main`; tag `v6-keeprule`; move `FROZEN_REF` to it; `make verify-frozen` clean.

### Acceptance
- Tag exists; `verify-frozen` clean; docs updated; `tools/audit_runs.py` still 0 unresolved.

---

## Out of scope this session
- Any change to the frozen scorers, the holdout, or `tiers.json`.
- New model ideas to beat the calm-month regime (that is the next research cycle: a model
  that does not trade holidays for calm months — e.g. a regime-conditioned or two-model
  blend). This spec only fixes the measurement.
- Promotion to champion; that stays a human gate with a human-run holdout score.
- PepsiCo data. Public M5 only.

## The one thing to get right
The fix must make the gate more honest, not more permissive. Two guardrails prove it: every
known-bad run in the v5 corpus must stay `discarded`, and a constructed uniformly-better run
must be `kept`. If the new rule keeps something the old rule rejected, that is a finding to
report to the human, never a silent pass. A gate that rubber-stamps is worse than the one we
have.
