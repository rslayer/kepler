# RESULTS — Forecasting Research Loop Prototype (kepler)

Mechanics test on public M5 data (Walmart store CA_1, department FOODS_3: 823 series,
1,913 days). Not an accuracy claim. Nothing here is a claim about PepsiCo.

Phases 0–3 executed 2026-09-08 to 2026-09-11. Phase 4 scored the baseline only; see item 4.

## v5 state — 2026-09-15 (SPEC_v5_certifiable.md; tag `v5-certifiable`)

The prototype is now a forecasting engine on the full M5 panel (all 10 stores, 30,490
series) scored on the competition's 12-level WRMSSE, with the research loop, champion
promotion and a live scoreboard around it. Public M5 only; nothing here is a claim about
PepsiCo.

**Accuracy (m5_all, 8-fold backtest, wrmsse_hier).** lgbm_baseline **0.785** (r083);
the M5 recipe (capacity + Tweedie→L2 + direct multi-horizon + rolling stats + price +
calendar) **0.698** unbagged (r106, kept on all 8 folds) and **0.695** with seed-averaged
forecasts (r118). Human yardstick on the competition's evaluation period: baseline 0.723,
recipe **0.626**. Kaggle field context (organisers' scores on that period): winner 0.520,
rank 10 0.548, rank 50 0.576; benchmarks sNaive 0.847, ES_bu 0.671. The recipe therefore
beats every published benchmark and sits between rank 50 and the statistical baselines;
the remaining gap to the top is bias on calm months at the aggregate levels, not item-level
error.

**Does the gate pass on m5_3?** No. With seed-averaged forecasts (Part A) the recipe's
gain over the baseline on the screen is 0.0219 against a bar of 0.0222 (2 x the recipe's
single-seed spread, unchanged by bagging), and it regresses on the four calm late-winter
folds by 0.02–0.06 — a real, repeatable loss (r104, r107, r108, r115), not noise. Bagging
moved the headline by 0.003. Four bias levers (ratio target, momentum features, weighted
ratio target, store x department calibration: r109–r113) and the Part B per-series
correction (r117) all made it worse; per-store models (Part C) won on the 3-store screen
(0.638 vs 0.649, r119, discarded on the parent's noise bar) and lost on all 10 stores
(0.703 vs 0.695, r120). The keep rule was not loosened. The m5_all recipe remains a kept
run that the screen cannot certify; promotion to champion/m5_all is a human decision.

**Throughput (Part D, m5_all baseline, Apple M4 Max 14-core / 36 GB, machine otherwise
lightly loaded).** RUNS_PER_HOUR_PENDING

**Audit (Part E).** `make backtest` refuses a dirty tree when logging to runs/ (adversary
scratch reruns exempt); `tools/audit_runs.py` reconciles rows, detail JSONs and commit
hashes: 120 rows, 0 unresolvable hashes; r032's shifted row realigned; r100–r102's detail
JSONs were lost in the v4 renumbering and are recorded as such (findings/r100–r102.md; the
identical reruns are r103, r106, r104). Runs r114–r120 all carry clean hashes.

## The five numbers

### 1. Researcher runs per hour: **49**

25 scored runs (r004–r028) in one session, all `status=ok`, all with findings files.
Session wall clock 04:20:05 → 04:50:31 UTC on 2026-09-11 = **30.4 minutes**, from the
session's own creation and last-activity timestamps. The session stopped at the 25-run cap
in CLAUDE.md, not at the two-hour limit. Run log spans 04:23:07–04:49:15 (26.1 min);
on that basis the rate is 57/h. 49/h is the conservative figure.

### 2. Seconds per run and cost per run

- Backtest compute: **33.7 s mean** per run (min 17, max 75; ensembles fit two models).
  Total 14.0 min of compute inside 30.4 min of wall clock — the agent spent roughly half
  its time thinking and half waiting on LightGBM.
- Wall clock per run, all-in: **73 s**.
- Cost per run: **not measured in v0.** Sessions ran on a Claude desktop subscription, not
  API billing. v3's `tools/cycle.sh` records per-session token usage and cost to
  `runs/sessions.csv`; `python tools/cost_report.py` prints cost per researcher run once a
  headless cycle has been run (SPEC_v3 Part E acceptance). First measured value: pending.

### 3. Adversary: planted leak caught **yes**; real branches rejected **2 of 2**

| branch | verdict | deciding item | evidence |
|---|---|---|---|
| exp/planted-leak | FAIL | 1 (look-ahead), 2 (target leakage) | Named `local_smooth_7`; showed window `[tp-3, tp+4)` spans `origin_pos-3 … origin_pos+30`, centred on the training target column. Signature: 772/777 series improve, gain flat across horizons, seed spread 0.00017. |
| exp/r010 | INCONCLUSIVE | 6 (concentration) | 81.5% of the gain from top 5% of series by volume; one series (FOODS_3_120) carries 72%. Worse than parent on folds 1 and 3 at seeds 7 and 123. |
| exp/r022 | INCONCLUSIVE | 5/7 under reseeding | Every threshold met at seed 42 (concentration 59.2% < 60%; gain 0.0049 > spread 0.0031). Paired against parent at seed 7 the gain is 0.0005; fold 4 flips sign at both alternate seeds. Aggregate direction positive at all three seeds. |

Adversary session: 12.4 min wall clock for three branches, 12 reruns. Both rejections are
logged `status=rejected` (r030, r031). By the checklist's letter r022 passes; the adversary
graded it INCONCLUSIVE on a seed-paired test the checklist did not ask for. The human
accepted that verdict.

### 4. Holdout WRMSSE: baseline **0.7620**; best PASS candidate **none**

`lgbm_baseline` scored once on the 28 held-out days (2016-03-28 … 2016-04-24):
WRMSSE 0.762011, WAPE 0.608, bias −1.0%. Backtest estimate was 0.783; holdout came in
slightly better, inside the fold-to-fold range (0.762–0.801).

No researcher branch received PASS, so no candidate was scored. The gate was not iterated.

### 5. Most promising unexplored hypothesis

Researcher's words: a fold-robust long-history variant. Training on 80 simulated origins
instead of 40 produced the largest gains of the session in four separate runs (aggregate
0.006–0.013 lower; the December fold 0.03–0.04 lower; best aggregate 0.7663 in r011) but was
blocked each time by a 0.002–0.009 loss on fold 3, which a per-series diagnostic showed to be
diffuse rather than structural. Next runs: wider origin spacing or a tuned recency decay on
the 80-origin set, tested inside the r022 ensemble.

## Backtest ladder

| run | model | WRMSSE | vs baseline | status |
|---|---|---|---|---|
| r001 | seasonal_naive | 1.0167 | +29.9% | floor |
| r002 | lgbm_baseline | 0.7830 | — | baseline, deterministic to 6 dp |
| r010 | + lags 1–3 at origin | 0.7790 | −0.5% | kept by researcher; adversary INCONCLUSIVE |
| r022 | ensemble L2(mcs200) + Tweedie | 0.7740 | −1.1% | kept by researcher; adversary INCONCLUSIVE |
| r011 | 80 origins (not kept) | 0.7663 | −2.1% | fails all-folds rule on fold 3 |

## What the mechanics test showed

Worked:
- Unattended scored experimentation at ~1 run/minute with a complete audit trail
  (runs.csv, findings/, runs/detail/, one branch per kept run).
- Frozen files untouched; holdout never referenced; main never committed to.
- Determinism to six decimals, which made the adversary's seed and rerun checks meaningful.
- The adversary found the planted leak from the code, not from the branch name, and was
  strict enough to reject the researcher's own wins.

Did not work:
- The loop produced no candidate that survives adversarial review. Honest gains (~0.005)
  are the same size as the seed spread (~0.003). Single-seed runs cannot separate signal
  from noise on this subset.
- The researcher's keep rule ("beats on all four folds") is too weak for that noise level;
  it admitted two seed-fragile wins.

## Changes for v1

1. Keep rule: require a seed-paired gain (≥3 seeds) larger than the seed spread, and a
   concentration check, before a result is "kept". Move both into the harness.
2. Make time the binding constraint: drop or raise the 25-run cap.
3. Fix run_id collisions across branches (planted run and adversary review are both r029).
4. Don't name the planted branch `exp/planted-leak`.
5. `make report` should rank by the keep rule, not by aggregate alone (frozen in v0).
6. Bias guardrail: r022 improved WRMSSE while doubling under-forecast bias to −4%.
7. Measure cost: run Phase 2 on API billing once.

## Deviations from SPEC

- Repo renamed `forecast-research-loop` → `kepler` on 2026-09-10.
- Kaggle token is `~/.kaggle/access_token` (Kaggle no longer issues `kaggle.json`);
  CLI 2.2.4 run through `truststore` to pass corporate TLS interception.
- No git-lfs: snapshot parquet regenerated by `make data`; MANIFEST.txt committed.
- Python 3.12; `brew install libomp` required for LightGBM on macOS.
- `make holdout` run by the human. `make score-holdout MODEL=lgbm_baseline` run by the
  harness session (not the researcher) with the human's go-ahead, since there was no
  candidate to iterate on.
- Researcher session ended at the 25-run cap after 30 minutes, not at two hours.
- Planted-leak branch was written by the harness session, not the human; the adversary
  was a separate fresh session and was not told which branch was planted.
