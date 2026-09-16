# Promotion PENDING — m5_all recipe → champion/m5_all/v1 (NOT executed)

**Status:** prepared, blocked on a holdout audit-trail gap. champion.json is unchanged.
Decided by Claude (Opus 4.8) on 2026-09-15 under "pursue option 2"; held for human review.

## Candidate
recipe6_calendar_l2 on m5_all, backtest run **r106** (config 1c83fbc41e45, wrmsse_hier
**0.698220**, bagged=False), the M5 recipe (capacity + Tweedie→L2 + direct multi-horizon +
rolling + price + calendar). Current m5_all champion: lgbm_baseline (r083, 0.785019).

## Promotion conditions (tools/promote.py), checked by hand
- **1 kept + chains to champion backtest_run:** PASS. r106 verdict=kept; keep_rule.parent =
  r083 = champion.backtest_run.
- **1b screen keep (tiers.json: m5_all←m5_3):** FAIL as written, but WAIVABLE. The recipe is
  discarded on the 3-store screen (r115, 4/8 folds) — but v6 established that is a
  small-sample artifact: on the full 10-store data the recipe is better on **all 8 folds**
  (r106; v6.1 sign test p=0.0039). The screen's job is to save compute before an m5_all run;
  here the m5_all run exists and is decisive, so 1b is moot. A human waiver is appropriate.
- **2 adversary PASS / human override:** N/A — r106 is a harness-owner run, not a researcher
  experiment with an exp/ branch and adversary review. The recipe is deterministic and
  leak-free by construction (built on the v4 as-of-origin contract). Human override applies.
- **3 frozen files clean:** PASS on HEAD (verify-frozen clean vs v6-keeprule-1).
- **4 holdout NOT WORSE:** the recipe's holdout wrmsse_hier is **0.626358** vs the champion's
  0.723437 — far better. **BUT the audit trail is broken (see blocker).**
- **5 allowed paths:** N/A (no branch; direct promotion).

## BLOCKER — the yardstick's provenance cannot be reproduced
The human one-shot yardstick (runs/holdout.csv) recorded recipe6_calendar_l2 m5_all
wrmsse_hier 0.626358, but:
- it was scored on a **dirty tree**: git_commit `2bbc887-dirty` (2bbc887 = 2026-09-13 23:55,
  "model: recipe_scaled …"), i.e. uncommitted changes on top of that commit;
- its config_hash `1ae10e30d56f` matches **no committed run** in runs.csv;
- the runs of that era (r100–r102) **lost their detail JSONs** in the v4 renumbering.

So 0.626358 cannot be tied to a reproducible run. Git shows the recipe's *forecast-
generating* code (LGBMRecipe1..6 params/features/_fit_predict) is unchanged since — only
dormant subclasses (…Corr, …PerStore) and the off-by-default _row_weights/CALIBRATE hooks
were added, which do not alter recipe6_calendar_l2's output (backtest hier identical:
r101 = r106 = 0.698220). That is strong evidence the 0.626 still applies, but it is a
code-inspection argument, not a reproducible audit link.

## What the human decides
1. **Accept** the code-inspection argument (forecast code unchanged; score-identity across
   the config drift) and promote — I can execute the champion.json update + tag + promotions
   row in one step on your say-so.
2. **Re-yardstick** the current committed recipe cleanly (`make score-holdout MODEL=
   recipe6_calendar_l2 DATASET=m5_all` on a clean HEAD). The "one shot per model" rule is
   arguably not spent, because the first score was on an unreproducible dirty tree. This
   re-establishes the audit link and is the cleanest path.
3. **Hold** — leave lgbm_baseline as the m5_all champion for now.

My recommendation: **option 2 (clean re-yardstick), then promote.** It restores the audit
trail on the project's headline number, which is the whole point of the harness.
