# LESSONS (general)

Confirmed findings about the loop, the harness, and the metric — things that transfer to
any dataset. Dataset-specific findings live in datasets/<dataset_id>/LESSONS.md. Same
rules: confirmed = from a kept run whose branch the adversary passed, or corroborated by
two or more runs; one line each, citing the runs; never delete a line, append an
overturning line instead.

- [adversary r010, r022] On the v0 FOODS_3 harness, single-seed gains of ~0.005 were inside the seed-to-seed spread (~0.003); no v0 kept result survived reseeding. Evidence: adversary reruns at seeds 7 and 123. This is why v1 uses three seeds and the keep rule.
- [r038, r043, r051] The v1 paired-gain threshold is twice the child's own seed spread, so a change that adds seed noise raises its own bar: 80 origins (spread 0.0019), raw lags 1–3 (0.0012) and num_leaves 31 (0.0010) each showed a real aggregate gain and each missed by under 0.0004. Evidence: three runs; the quiet variant of one of them (r044) passed.
- [r015, r026, r042] Features or blends that improve WAPE in every horizon bucket but not WRMSSE are common; the dollar-weighted squared-error metric does not reward them, so a WAPE-only gain is not a keep. Evidence: three runs across v0 and v1, all WAPE-better / WRMSSE-neutral or mixed.
- [r049, r050, r060] Because the paired-gain threshold is twice the larger of parent and child seed spread, a deterministic postprocess that moves one fold is judged by the noise of whatever features its parent carries: the same Thanksgiving override missed at ~0.0013 on r044 (spread 0.0006) and passed at 0.00028 on the champion r037 (spread 0.00013). Evidence: three runs, identical fold-1 effect; order low-noise postprocess changes before features that add seed spread.
