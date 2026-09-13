# PRIORS — m5_all (all 10 Walmart stores, 30,490 series; the competition's own setup)

Curator-editable. This dataset is the confirmation tier and the yardstick: the visible
snapshot is d_1–d_1913 (sales_train_validation), the holdout is the competition's evaluation
period d_1914–d_1941, and the headline metric is `wrmsse_hier` (12 levels, equally
weighted). The keep rule uses `wrmsse_hier` here.

Domain notes:
- Same store data as m5_ca1 for CA_1; nine more stores across CA, TX, WI. SNAP days differ
  by state: the `snap_CA` role is a placeholder until the series-own-state SNAP feature
  (SPEC_v4 Part C item 6) exists.
- Leaderboard calibration (datasets/m5_all/M5_Scores_and_Ranks.xlsx, from the organisers):
  winner 0.5204, rank 10 0.5475, rank 50 0.5760; organiser benchmarks sNaive 0.847,
  ES_bu 0.671, best statistical combination 0.682. Top-50 item-store level (L12) is
  0.875–0.912: most of the score is in the aggregate levels, so a change that helps totals,
  stores and departments can matter more than one that helps items.

Priors (what to try first; every line cites a run id or a LESSONS line):
- Nothing is confirmed on this dataset yet. Screen on m5_ca1 first (5 min per backtest);
  confirm here (see SPEC_v4 Part B). The m5_ca1 priors are a starting point, not evidence.
