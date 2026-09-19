# Gate queue (SPEC v9) — human holdout decision

Candidates that cleared the m5_all strict keep rule, ordered by gain vs the champion
(recipe v9 baseline hier 0.6666). The holdout is scored ONLY by the human,
at most 2/week (LEDGER_RULES.md). No tool in this repo scores the holdout.

## r147  (H169)  —  blocked: awaiting-adversary
- m5_all wrmsse_hier: **0.6523**  (gain vs champion **+0.0143**)
- gates: screen ✓ (directional) · m5_all keep ✓ · adversary: awaiting-adversary
- lever: ensemble · mechanism: batch 2: capacity still climbing at 511 — all KEEP + gate PASS. leaves511 best spring +0.0321; easter+leaves511 best agg +0.0210 (spring +0.0306). Anchor ~neutr

## r146  (H169)  —  blocked: awaiting-adversary
- m5_all wrmsse_hier: **0.6589**  (gain vs champion **+0.0077**)
- gates: screen ✓ (directional) · m5_all keep ✓ · adversary: awaiting-adversary
- lever: ensemble · mechanism: batch 2: capacity still climbing at 511 — all KEEP + gate PASS. leaves511 best spring +0.0321; easter+leaves511 best agg +0.0210 (spring +0.0306). Anchor ~neutr

## r131  (H163)  —  blocked: awaiting-adversary
- m5_all wrmsse_hier: **0.6745**  (gain vs champion **-0.0079**)
- gates: screen ✓ (directional) · m5_all keep ✓ · adversary: awaiting-adversary
- lever: recursive · mechanism: validation-window debias removed the recursive COMPOUNDING BIAS and the recursive+direct ensemble won BOTH backtest tiers, but the gain was winter-fold-specific

## r106  (H124)  —  blocked: awaiting-adversary
- m5_all wrmsse_hier: **0.6982**  (gain vs champion **-0.0316**)
- gates: screen ✓ (directional) · m5_all keep ✓ · adversary: awaiting-adversary
- lever: feature · mechanism: WRMSSE 0.811325 vs champion 0.805456; end of L2 chain

## r101  (H124)  —  blocked: awaiting-adversary
- m5_all wrmsse_hier: **0.6982**  (gain vs champion **-0.0316**)
- gates: screen ✓ (directional) · m5_all keep ✓ · adversary: awaiting-adversary
- lever: feature · mechanism: WRMSSE 0.811325 vs champion 0.805456; end of L2 chain

---
READY for a human holdout shot: none (all awaiting adversary)
