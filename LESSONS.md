# LESSONS

Confirmed findings only: from a run with verdict=kept whose branch the adversary passed, or
corroborated by two or more runs. One line each, citing the runs. The researcher reads this
first and appends to it last; the curator reconciles it. Never delete a line; if a lesson is
overturned, append the overturning line and cite both.

- [r008, r011, r013, r024] Training on 80 simulated origins (~560 days) instead of 40 cut the December fold's WRMSSE by 0.030–0.044 in four separate runs, and cost 0.002–0.009 on fold 3 (origin 2016-02-01) every time. Evidence: same shape in all four; the fold-3 loss is diffuse across series, not one bad group.
- [r010, adversary r010] Lags 1–3 at the origin (series state) improved all four v0 folds by 0.0007–0.0075, but the adversary found 72% of the gain in one series (FOODS_3_120) and fold gains reversed at other seeds. Evidence: kept under v0 rule, INCONCLUSIVE under review; treat as unproven.
- [r007, r017, r027, r028] Tweedie alone under-forecasts 4–5% out of sample but only ~1% in sample; the bias is level growth between training and forecast windows, not calibration or capacity. Evidence: 600 rounds made it worse (r027), variance power 1.1 left it unchanged (r028).
- [r017, r021, r022] Tweedie is the only single change that clearly helps fold 3; averaging it with an L2 member captured that (r022 beat r010 on all four folds) at the cost of inheriting −4% bias. Evidence: r021/r022/r023 all show the fold-3 gain; adversary rated r022 INCONCLUSIVE on seed-paired margins.
- [r019] `month` carries real signal even when the horizon's month is unseen in training; removing it cost 0.014 on the December fold. Evidence: worse on 3 of 4 folds.
- [r006] Long as-of-origin windows (roll_mean_56/91/182) hurt on every fold under L2 and pull long horizons toward stale levels (fold 1 h15-28 WAPE 0.797→0.850). Evidence: single run, all folds worse.
- [r005, r014] A same-weekday mean over the 4 weeks before origin (dow_mean_4w) helps fold 2 only and is mixed elsewhere, on two different bases. Evidence: two runs, same pattern.
- [r012] Pre-launch all-zero training rows are not what harms folds 3–4 under long history; dropping them made every fold worse. Evidence: worse than r011 on all folds.
- [r016] Metric-aligned sample weights (dollar weight / scale, untempered) are too heavy-tailed: 13% of rows get zero weight, weights reach 14×, and folds 3–4 get worse. Evidence: single run; a tempered variant is untried.
- [r018, r020] Regularising the L2 model (min_child_samples 200, or num_leaves 31) gives ~0.005 aggregate gains that fail only on fold 3 by amounts inside fold noise. Evidence: two runs, same shape.
- [r015, r026] Price-ratio features and intermittency-state features improve WAPE but not WRMSSE; the dollar-weighted squared-error metric does not reward them. Evidence: two runs, both WAPE-better / WRMSSE-mixed.
- [adversary r010, r022] On the v0 FOODS_3 harness, single-seed gains of ~0.005 were inside the seed-to-seed spread (~0.003); no v0 kept result survived reseeding. Evidence: adversary reruns at seeds 7 and 123. This is why v1 uses three seeds and the keep rule.
- [r021, r023] Tweedie's under-forecast pulls an equal-weight L2/Tweedie blend below the L2 member on folds 2 and 4; a 0.7/0.3 L2-heavy blend recovered them while keeping most of the fold-1/3 gain. Evidence: r023 beat r010 on all four v0 folds where r021 did not; both dominated by r022's stronger L2 member.
