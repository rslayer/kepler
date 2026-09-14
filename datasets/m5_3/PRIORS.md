# PRIORS — m5_3 (stores CA_1, TX_1, WI_1: one per state; 9,147 series)

Curator-editable. This is the SCREENING tier for m5_all: the same competition setup
(visible d_1–d_1913, holdout = evaluation period d_1914–d_1941), scored on all 12 levels
(`wrmsse_hier`), at about a third of m5_all's cost. The keep rule uses `wrmsse_hier`.
A kept result here is confirmed on m5_all before it counts (CLAUDE.md step 7a).

Domain notes:
- Three states, so state-level SNAP matters here (feature snap_own) where it did not on
  m5_ca1. Seven departments, three categories.
- The leaderboard is won on the aggregate levels (top-50 item-store scores are 0.875–0.912;
  their totals are 0.2–0.35). A change that helps totals, stores and departments matters
  more than one that helps items. Bias of a few percent is nearly invisible at item level
  and dominates the total.
- On m5_all the M5 recipe (capacity + direct multi-horizon + rolling stats + price + calendar,
  L2 objective) scored hier 0.698 vs the baseline's 0.785, better on all 8 folds, while
  moving the item level only 0.862 -> 0.851. The one-store item-level screen (m5_ca1) had
  rejected every ingredient. [r083 vs the recipe run on m5_all]

Priors (what to try first; every line cites a run id or a LESSONS line):
- The recipe's gain on this screen is the holiday window: fold 1 (Thanksgiving/Christmas)
  1.13 -> 0.83, while on the four calm late-winter folds it is WORSE than the baseline at
  every aggregate level (fold 7 total 0.51 vs 0.40) and equal at item level, with bias
  -1% to -2% where the baseline's is ~0 [r103 vs r107]. Calm-month aggregate error is
  bias; fix bias before adding features.
- Bagging three fits (recipe_bag3) cuts the seed spread from 0.011 to 0.003 and moves the
  mean by +0.003 [r104 vs r107]; use the bagged base so later changes are judged against a
  ~0.005 bar, not 0.022.
- Bias and scale first: the recipe's bias is -2% to -5% on most windows; at the total that
  is most of the error. Per-series ratio targets are NOT the fix (they trade calm folds for
  post-holiday folds, LESSONS r109/r112); momentum features are neutral (r110). Still open:
  per-store x department calibration from the 28 days before the origin (recipe_calib,
  H145), an event-robust scale for the ratio target (H146), per-store models (H147).
- Seed-averaged forecasts (harness lever), per-store models (ingredient 7), event-effect
  features from prior years generalising r037/r060, then long history with recency
  (r070) — in that order [SPEC_v4 Part C notes; LESSONS m5_ca1 r070].
