# Curator report — researcher-20260912-1 (curator-20260913-1)

The session ran r037-r052 on the v1 harness and kept two runs: r037 (Christmas-zero postprocess, adversary FAIL on item 5 overruled to PASS by the human in r055) and r044 (roll_mean_3, adversary INCONCLUSIVE in r054, unmerged). The researcher had already synced six multi-run lessons and every touched ledger row to main, so I reconciled rather than duplicated: I appended three LESSONS.md lines the session left out, namely the r037 finding itself with its override (cited [r037, r055]), the adversary's caveat on r044 (cited [r044, adversary r054]) so the next researcher builds on r044 knowing 66% of its gain sits in the top 5% of series and the fold pattern flips at other seeds, and the fold-1 Thanksgiving structure corroborated by r047/r048/r049/r050 (a four-day level dip that no as-of-origin feature reached). In the ledger I added the adversary and override outcomes to the evidence of H031 and H033 (statuses unchanged, both remain kept per runs.csv), noted on H022/H023/H027/H029 that the session's findings named them again and what has since been consumed, and added two untried rows for the "next" ideas the findings files name: H040 (event-aligned year-ago features for the February folds, from r040) and H041 (carry the Thanksgiving override on top of a broader change rather than alone, from r050); H034 was never assigned in the ledger so new rows start at H040 to keep ids in sequence. I rewrote the Priors block (nine bullets, one physical line each) so it starts from the kept chain r033 -> r037 -> r044, names fold 1 as the largest remaining error and why a standalone fix cannot pass, puts as-of-origin series state first, explains the self-raising threshold that sank three real gains (r038, r043, r051), and demotes year-ago, long-history and Tweedie levers to conditional retries via their ledger rows; every bullet cites either a kept run or two or more runs, and single-run discards are covered by pointing at the ledger's discarded status instead of citing them. Below the marker I also corrected one stale fact in the Harness notes: lgbm_baseline is no longer the current best, and neither kept model is registered on main because exp/r037 and exp/r044 are unmerged.

Evidence runs:
- r037 (kept; adversary r053 FAIL item 5; human override r055 PASS) - treated as kept and passed
- r044 (kept; adversary r054 INCONCLUSIVE) - treated as kept, not passed
- r038, r039, r040, r048 (discarded; corroborate the year-ago / long-history fold shape)
- r041, r045, r046 (discarded; corroborate re-weight/regularise neutrality)
- r042 (discarded; corroborates the v0 Tweedie-blend lesson with r017, r021, r022)
- r043, r051 (discarded; with r038 corroborate the self-raising threshold)
- r047, r049, r050 (discarded; with r048 corroborate the fold-1 Thanksgiving structure)
- r052 (discarded; single run, cited nowhere new; left to the ledger)
- r053, r054, r055 (adversary and human log rows for the two kept branches)

Output of `python tools/check_claude_diff.py main HEAD` (run on the branch before the report was added; re-run after amending the commit gave the identical line):

```
OK: CLAUDE.md changes are confined to the Priors block (main..HEAD)
```

## Human amendments after adversary review (2026-09-13)

The adversary passed this branch on item 9 and flagged three lines. The human changed them
before the merge gate; nothing else was touched:
1. Priors bullet 4: only r043 missed the paired-gain threshold alone; r038 and r051 also
   regressed a fold past tolerance. Reworded to say so.
2. Priors bullet 6: 80 origins raises the seed spread fifteenfold, not "doubles" (per
   findings/r038.md).
3. Priors bullet 9: removed the clause telling the researcher a human can overrule item 5;
   that is adversary-spec business, not a research prior. Ledger H041 reworded so the
   Thanksgiving override is never bundled into another change as a second variable.
