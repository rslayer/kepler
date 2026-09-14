# LESSONS — m5_3

Dataset-specific confirmed findings. Same rules as the general LESSONS.md. Nothing yet.
- A level-invariant (ratio) target on the bagged recipe trades folds instead of fixing bias:
  it improves the four calm late-winter folds by 0.03–0.04 hier and worsens the folds whose
  origin follows the holidays by 0.05–0.07, because the origin's 28-day mean carries
  December's level; weighting the loss by level halves the bias (+2.7% → +1.6%) but keeps
  the trade [r109, r112 vs r107].
- Momentum ratios (7/28, 28/56, 28/180 days) add nothing on top of the lags and rolling
  means: gain 0.003 inside the bar, bias unchanged [r110 vs r107].
- A multiplicative per store x department correction estimated on the 28 days before the
  origin (actual / predicted, shrunk and clipped) lowers the overall bias but worsens the
  hierarchical score on 7/8 folds: the model's recent errors do not persist into the
  forecast window, and after the holidays the window still carries December [r113 vs r107].
