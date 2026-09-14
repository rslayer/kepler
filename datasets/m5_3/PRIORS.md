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
  rejected every ingredient. [r063 vs the recipe run on m5_all]

Priors (what to try first; every line cites a run id or a LESSONS line):
- Bias and scale first: the recipe's bias is -2% to -5% on most windows; at the total that
  is most of the error. Per-series scaled targets or a per-store x department calibration
  from the last 28 days [recipe m5_all folds; SPEC_v4 lever 1].
- Seed-averaged forecasts (harness lever), per-store models (ingredient 7), event-effect
  features from prior years generalising r037/r060, then long history with recency
  (r070) — in that order [SPEC_v4 Part C notes; LESSONS m5_ca1 r070].
