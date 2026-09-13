# Human override — exp/r037

**Verdict: PASS** (human override of the adversary's item-5 FAIL, 2026-09-13)

The adversary graded exp/r037 FAIL on item 5 because the whole gain sits in folds 2 and 3
(+0.0223, +0.0207 vs r033) and the other six folds show exactly +0.0000. It flagged the
case as boundary/structural and invited an override. The human accepts every other finding
in adversary/reviews/exp/r037.md (leak-free, frozen files clean, concentration 51%, gain
0.0053 against a rerun spread 0.0003, determinism exact) and overrules item 5 on this
reasoning:

- The feature forecasts zero on 25 December, a day the store is closed. That date lies in
  exactly two of the eight fold windows. The gain appears in both, at near-equal size, and
  is zero (not negative) in every window that does not contain the date. There is no fold
  where the gain could have appeared and did not.
- Item 5 guards against a gain that is luck on one window. Its wording is "if the aggregate
  gain comes from one fold, FAIL"; here it comes from two, 52/48, for a mechanism that is
  known and not seasonal luck.
- The harness keep rule (no fold regresses, all eight folds within tolerance) already
  treats a zero delta as non-regression, and passed the run.

Recorded as runs.csv row r055 (model_name=exp/r037, author=human, status=ok). The
adversary's row r053 (status=rejected) stands in the log; this file sits beside it.

Follow-up for the next adversary spec: item 5 needs an event-driven clause — a gain
confined to the folds whose windows contain the event, with zero delta elsewhere, is
structural, not concentrated.
