# Promotion — champion/m5_all/v2 — recipe6_calendar_l2_cap511 (2026-09-20)

**What:** the recipe at higher capacity (num_leaves 127 -> 511). Self-contained named model,
byte-identical to recipe_search with {num_leaves:511} (r147).

**Result:** frozen holdout wrmsse_hier **0.622271** vs the recipe champion **0.626358** (+0.0041,
generalised — the first candidate to beat the holdout since the recipe). m5_all backtest hier
0.652342 vs 0.666 (+0.0143, 7/8). Still ~0.031 above rank-50 (~0.591 our window): a real gain, not top-50.

**Gates cleared (SPEC v9 serial gate):**
1. m5_screen directional filter — kept (batch 2, r142/H169).
2. strict m5_all keep rule — kept (r147, 7/8, sign_p 0.035, all 4 conditions).
3. adversary — PASS, all 8 items (adversary/reviews/exp/r147.md); item-7 noise floor +0.0129 on
   unseen seed 11 (3x the 0.0044 spread), not seed-fragile.
4. frozen holdout — human shot, 0.622271, better than champion. 1 of 2 weekly shots used.

**Lineage:** previous champion recipe6_calendar_l2 (champion/m5_all/v1, holdout 0.626358) becomes
`previous` in champion.json. Promoted by decision (harness-owner run), conditions manually verified.
