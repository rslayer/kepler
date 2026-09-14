# Human override — exp/r060

**Verdict: PASS** (human override of the adversary's item-5 FAIL, 2026-09-13)

The adversary (adversary-20260913-3, row r074) graded exp/r060 FAIL on item 5: fold 1
supplies 100% of the summed gain and folds 2-8 are exactly +0.0000 at every seed. The
human accepts every other finding in adversary/reviews/exp/r060.md (leak-free arithmetic,
no holdout references, frozen files untouched) and overrules item 5 on the same reasoning
as exp/r037 (adversary/reviews/exp/r037-override.md):

- The feature multiplies forecasts for Thanksgiving Day and the three days after it by each
  department's dip in earlier years. Those four days lie in exactly one of the eight fold
  windows (fold 1, origin 2015-11-23). The gain appears there and is zero, not negative, in
  every window that does not contain the event. There is no fold where the gain could have
  appeared and did not.
- Item 5 guards against a gain that is luck on one window; a known calendar event whose
  effect is confined by construction to the windows containing it is structural, not luck.
- The harness keep rule (no fold regresses) passed the run.

Recorded as runs.csv row r079 (model_name=exp/r060, author=human, status=ok). The
adversary's row r074 (status=rejected) stands beside it.

Standing note, now applied twice: the adversary's item 5 needs an event-driven clause. A
gain confined to the folds whose windows contain a known calendar event, with zero delta
elsewhere, is structural, not concentrated. To be written into the next adversary spec.
