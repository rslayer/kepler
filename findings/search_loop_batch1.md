# H168 — self-improvement loop, batch 1 (v9 proxy, spring-gated)

Orchestrator `tools/search_loop.py`; baseline r134 (recipe, v9); parent r134. Holdout untouched.

## Leaderboard (spring-gated: aggregate gain AND no spring regression)
| run | config | hier | agg gain | spring gain | keep(v6.1) | gate |
|-----|--------|------|----------|-------------|------------|------|
| r140 | easter+leaves255 | 0.6741 | +0.0153 | **+0.0252** | discarded(6/8) | PASS |
| r138 | leaves255 | 0.6802 | +0.0092 | +0.0174 | **kept(7/8)** | PASS |
| r137 | easter_anchor | 0.6834 | +0.0059 | +0.0041 | kept | PASS |
| r139 | min_child_50 | 0.6966 | -0.0072 | -0.0101 | discarded | FAIL |
| baseline r134 | recipe | 0.6893 | — | — | — | — |

## Read
- **Model capacity (num_leaves 127->255) is a genuine, SPRING-POSITIVE lever** — the first change
  that improves the holdout-relevant folds since the search began. leaves255 keeps cleanly (7/8);
  stacking the validated Easter anchor (r140) gives the best aggregate AND best spring (+0.025) but
  is strict-discarded at 6/8 (two tiny -0.005/-0.001 folds; six large +0.011..+0.023 wins) — the
  known screen under-certification (recipe: 6/8 screen -> 8/8 m5_all).
- min_child_50 correctly rejected by the spring gate (aggregate AND spring negative).
- The engine works: honest proxy + spring gate surfaced a real lever and rejected a false one,
  with no holdout shot spent. Champion unchanged (recipe6_calendar_l2, holdout 0.626) — screen
  keeps do not promote; promotion needs m5_all confirmation + a human yardstick shot.

## Next
Confirm the capacity lever on m5_all under v9 (strict gate), then a human holdout-shot decision.
If the stack's screen spring gain (+0.025) transfers, holdout ~0.626 -> ~0.60, vs rank-50 ~0.591.
