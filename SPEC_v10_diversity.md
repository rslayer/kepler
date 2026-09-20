# SPEC v10 — Diversity over refinement (kepler)

Purpose: champion/m5_all/v2 sits at holdout 0.622; top-50 is ~0.591, a gap of 0.031. The ledger (95 hypotheses) shows the refinement levers are spent: feature 16 discarded, horizon 8 discarded, recursive 5 discarded and blocked, and all three v9 mandates closed negative this week. Worse, the last gain shrank 5:1 from backtest (+0.0225) to holdout (+0.0041), which means the current folds over-reward winter-specialists and the loop is now finding backtest-specific gains.

Every M5 solution below 0.59 did two things Kepler has not: combined genuinely different model families, and exploited the hierarchy by training at aggregate levels rather than reconciling after the fact. This spec does exactly those two, plus one harness fix so the keep rule stops promoting gains that will not transfer. Nothing else.

Hand to Claude Code at the repo root: "Read SPEC_v10_diversity.md and execute Parts A through C in order. Stop after each part and report against its acceptance criteria. Never read, list, or write under any holdout/ path. Do not edit any file listed as frozen in HARNESS_CHANGELOG except where Part A explicitly directs a keep-rule weighting change, which the human authors. Commit before every backtest. Do not run any feature, horizon, objective, or recursive hypothesis; the ledger blocks them and so do I."

Laptop only for this spec; the cloud box is deferred. Budget accordingly: m5_screen for all exploration, m5_all only to confirm a screen winner, and the human scores the holdout at most twice across the whole spec.

Frozen this session: src/scorer.py, src/scorer_hier.py, src/score_holdout.py, src/scoring.py, tiers.json. The keep rule in src/backtest.py is edited ONLY in Part A, as directed, and re-tagged.

Preflight (report, do not fix): `make verify-frozen`; `python tools/audit_runs.py`; `python tools/ledger_check.py --dry`; clean tree; confirm champion/m5_all/v2 resolves to r147 with holdout 0.622271.

---

## Part A — Season-aware keep rule (fix the 5:1 shrinkage first)

The eight folds end on the last agent-visible day and step back 14 days; the holdout is a spring window. The champion's backtest edge came from Christmas folds and mostly did not transfer. Until the keep rule weights folds that resemble the evaluation season, every candidate will shrink the same way and waste holdout shots.

### Tasks
- Add fold metadata to `runs/detail/<run_id>.json`: each fold's calendar window and a `season_tag` (winter_holiday | winter | spring | summer | autumn) derived from the fold's forecast dates.
- Add `--fold-weights` to the keep rule with a named scheme `season_match`: folds whose season_tag matches the holdout's season (spring) get weight 2.0, adjacent seasons 1.0, winter_holiday 0.5. The paired sign test and median guard are computed on weighted per-fold deltas. Default remains the current unweighted rule so every historical verdict is reproducible; `season_match` is opt-in per run and logged in the detail JSON.
- Backfill: re-evaluate the v9 candidates under `season_match` WITHOUT re-running them (per-fold numbers are already in detail JSON). Report which historical verdicts flip. In particular: does the capacity lever (r147) still clear, and does the debiased ensemble (r132, which won the backtest and lost the holdout) now correctly fail on the backtest alone?
- Write `HARNESS_CHANGELOG.md` v10 entry with the flips and the reasoning. Re-tag `v10-season`. FROZEN_REF moves to `v10-season`.

### Acceptance
- r132 (holdout loser) FAILS the season_match rule on backtest alone. This is the test that the fix works: the rule must catch the mirage the holdout caught.
- r147 (holdout winner) still PASSES.
- If r132 still passes, stop and report; do not proceed to Parts B and C on a rule that cannot distinguish a transferable gain from a winter-specialist.

---

## Part B — Model-family diversity: champion + one foundation model (Researcher C mandate)

Why: the H172 stack failed because it stacked two near-identical LightGBMs; there was nothing to average away. Zero-shot time-series foundation models are a different family, free to try, and exactly the diversity the M5 medal ensembles had. This also turns the "leaderboard is foundation models" claim into evidence on our own data.

### Tasks
- Pick ONE model that runs on the laptop CPU within the m5_screen budget. Order of preference: Chronos-Bolt (small/base, fastest), then TimesFM-2.5, then Moirai-2 small. Add it as a registered model `fm_<name>` behind an adapter that produces the same per-series, per-horizon point forecast the scorer expects. Zero-shot: no fine-tuning, no GIFT-Eval train split, no M5 data in its context beyond the series history at the origin.
- Log the foundation model alone on m5_screen (its standalone WRMSSE is a required data point; it will likely lose to the champion at item level).
- Ledger first: new row, lever=ensemble, mechanism="cross-family blend: LightGBM champion + zero-shot foundation model; diversity, not refinement".
- Blend 1 (one variable): equal-weight mean of champion and FM predictions. Screen under `season_match`.
- Blend 2 (one variable): per-hierarchy-level weights — fit a single weight per WRMSSE level on the training folds (the FM will likely deserve more weight at aggregate levels, the champion at item level). Screen under `season_match`. This is the one that could carry most of the gap.
- If Blend 2 clears the screen, confirm on m5_all under the strict keep rule + `season_match`. Adversary pass. Queue for the human holdout via gate_queue. Do NOT score the holdout.
- Report the per-level decomposition: at which of the 12 levels does the blend win, and by how much. That table is the finding regardless of verdict.

### Acceptance
- FM standalone and both blends logged on m5_screen with per-fold and per-level deltas vs the champion.
- Blend 2 either clears m5_all + adversary and sits in GATE_QUEUE.md, or its ledger row states the mechanism of failure (e.g., FM adds noise at item level that outweighs aggregate gains).
- No holdout access by any tool.

---

## Part C — Level-aware training: aggregate-level model as features (Researcher B mandate)

Why: reconciliation was tried twice as a post-process and washed out (H159, H171). The winners did the inverse: trained at aggregate levels where signal is smoother, then fed those forecasts downward. WRMSSE weights aggregate levels heavily, so a model strong at store-category can outscore one strong at item.

### Tasks
- Build a level-3 model: train the champion recipe on the store-category aggregate series (about 10 stores x 7 categories = ~70 series, cheap), producing a per-(store, category, horizon) forecast at each fold origin. Leak-free by construction: it uses only pre-origin data, same as the item model.
- Ledger first: lever=architecture, mechanism="aggregate-level (store-category) forecast injected as a feature into the item model; top-down signal without post-hoc reconciliation".
- Variant C1 (one variable): item model gains one feature, the level-3 forecast for its store-category at that horizon, scaled by the item's historical share of the category. Screen under `season_match`.
- Variant C2 (one variable): same, plus the level-3 forecast used as a blend member at the aggregate levels only (item level stays pure). Screen under `season_match`.
- Best of C1/C2, if it clears the screen: confirm on m5_all, adversary pass, gate queue. Do NOT score the holdout.
- Calm-month diagnostic on the best variant: does injecting aggregate signal fix the champion's calm-month weakness? This is the specific question the level-3 model is supposed to answer; report per-month deltas.

### Acceptance
- Level-3 model logged standalone at the aggregate levels (its own WRMSSE contribution at levels 1-5 is a required data point).
- C1 and C2 logged on m5_screen with per-level and per-month deltas.
- The best variant is either in GATE_QUEUE.md or has a ledger mechanism of failure.

---

## The gate (human only, after Parts B and C)

- At most TWO holdout scorings for this entire spec. Candidates come only from GATE_QUEUE.md having cleared m5_screen (season_match), the strict m5_all keep rule (season_match), and the adversary.
- Score rule: score the holdout only if the m5_all backtest gain vs r147 is at least 0.015. Smaller gains will shrink below the noise floor and waste the shot.
- If B and C both clear, score the stronger m5_all candidate first. If it beats 0.622 on the holdout, the second shot goes to the blend of B and C together (a new ledger row), not to the weaker single.

## The number
A human-scored holdout at or below **0.60** puts top-50 (~0.591) within one more cycle. Below 0.591 is top-50 and the achievement is done.

## What this spec refuses to do, and why
- No feature, horizon, objective, or recursive hypotheses: the ledger says 33 discarded across those levers; the marginal one is not worth a holdout shot.
- No capacity follow-up (leaves 1023): the 5:1 shrinkage says capacity is already overfitting the backtest.
- No hand-tuning of blend weights on the holdout: weights are fit on training folds only. A blend tuned on the holdout is a leaderboard entry, not a production model.
- No cloud, no PepsiCo data.
