# LOOP SCORECARD

Per researcher session, computed by `tools/scorecard.py` from runs/runs.csv and
hypotheses/ledger.csv. Definitions in the script docstring. Newest session last.

| session | runs | kept | confirm_runs | confirmed | keep_rate | runs_per_kept | repeats | repeat_rate | best_wrmsse | wall_minutes |
|---|---|---|---|---|---|---|---|---|---|---|
| researcher-20260911-1 | 25 | 2 | 0 | 0 | 0.08 | 12.5 | 0 | 0.00 | 0.766310 | 26.1 |
| researcher-20260912-1 | 16 | 2 | 0 | 0 | 0.12 | 8.0 | 0 | 0.00 | 0.801983 | 119.3 |
| researcher-20260913-2 | 14 | 3 | 0 | 0 | 0.21 | 4.7 | 0 | 0.00 | 0.798186 | 130.5 |

Trend (researcher-20260912-1 -> researcher-20260913-2): keep_rate 0.12 -> 0.21 (improved); repeat_rate 0.00 -> 0.00 (unchanged).
