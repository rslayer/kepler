# Recursive member smoke (H161) — not competitive out of the box

**Model:** lgbm_recursive (src/recursive.py), 1-step LGBM applied recursively over 28 days.
Smoke: m5_3 fold 8 (28 Mar), seed 42, scratch run (not logged canonically).

**Result:** hier 0.702 vs recipe6_calendar_l2 0.538 on the same fold. Worse at every horizon
bucket (WAPE h1-7 0.773 vs 0.748; h8-14 0.777 vs 0.744; h15-28 0.802 vs 0.773) and heavily
over-forecasting (bias +9.9% vs the recipe's +0.5%).

**Diagnosis:** two problems. (1) The recursive 1-step model is simply less accurate than the
recipe's direct multi-horizon design even at short horizons — it lacks the recipe's richer
features (price-relative-to-group, event lead/lag, days-since-sale, target-relative lags).
(2) Small 1-step over-predictions compound along the horizon into a +9.9% bias.

**Consequence:** averaging this member with the recipe would drag the ensemble down, exactly
as the Tweedie member did (H160). An ensemble needs members of SIMILAR quality; this one is
not there yet.

**To make it viable (next build):** bring the recursive feature set up to the recipe's, and
control the compounding bias (a count-appropriate objective such as Tweedie/Poisson on the
1-step model, or explicit debiasing). Multi-iteration work with uncertain payoff.
