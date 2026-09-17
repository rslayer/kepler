# Recursive member (H161) — not competitive; a hard calibration problem

The recursive 1-step forecaster (src/recursive.py) as an ensemble member for the direct
recipe. Smoke tests on m5_3 fold 8 (28 Mar), seed 42 (scratch runs; degenerate hierarchy is
irrelevant for judging the member's own accuracy/bias). Recipe on this fold: hier **0.538**.

| variant | objective / target | hier | bias | note |
|---|---|---|---|---|
| lgbm_recursive | regression | 0.702 | +9.9% | over-forecasts, compounds |
| lgbm_recursive_tw | Tweedie 1.1 | 0.701 | +9.6% | objective does not fix the drift |
| lgbm_recursive_log | log1p target | 1.126 | −21.2% | over-corrects; aggregate WRMSSE blows up |

**Diagnosis.** A point 1-step model of intermittent demand never predicts exact zeros; the
small positive predictions feed forward into the lags and compound into a ~+10% over-forecast
(regression and Tweedie alike). Moving to a log1p target swings it to −21% (predicting the
mean in log space then exponentiating under-predicts the arithmetic mean, and the aggregate
levels blow up). The true calibration is somewhere between raw and log — a hard problem, not
a one-line objective swap.

**Consequence.** For an ensemble to help, the member must be within ~0.02-0.03 of the recipe
(0.538) with decorrelated errors. The best recursive variant (0.701) is 0.16 away — averaging
it in makes things worse, like the Tweedie ensemble (H160). The recursive member needs real
calibration work (a middle transform, an explicit recursive-bias correction, or multi-step
training) before it can ensemble. Three principled attempts did not get there.

**Verdict:** recursive+direct ensemble not achievable without solving recursive calibration —
genuine research, not an overnight tune. Recorded; recursive variants stay registered as
documented experiments.
