# Compute for the confirmation tier (SPEC_v4 Part E)

## Why

Measured on this laptop (Apple Silicon, 14 cores, 36 GB; `num_threads=4` per fit,
`JOBS=3`, LightGBM 4.5):

| dataset | series | model | fits | wall clock | notes |
|---|---|---|---|---|---|
| m5_ca1 | 3,049 | lgbm_baseline | 24 | 5.5 min sequential; ~5 min JOBS=2 (machine shared) | v1 baseline |
| m5_ca1 | 3,049 | recipe (early-stopped, lr 0.05/1500) | 24 | 12–15 min, JOBS=3 | 25+ min when the machine is shared |
| m5_3 | 9,147 | lgbm_baseline | 24 | (being measured) | hierarchical screen |
| m5_all | 30,490 | seasonal_naive | 24 | 4.5 min | all of it is scoring |
| m5_all | 30,490 | lgbm_baseline | 24 | 42 min alone; 60 min shared | hier 0.785 |
| m5_all | 30,490 | recipe6_calendar_l2 | 96 (4 per fold x seed) | 95 min, JOBS=3 | hier 0.698 |

One confirmation run per evening is the binding constraint on the loop, not ideas.

## The one-box setup (to be tested by the human; no agent provisions cloud resources)

Any Linux VM with 32 vCPU / 64 GB is enough; the fits are CPU-bound and the full
dataset needs ~6 GB per worker process. Suggested: a spot/preemptible instance of that
class (order of $1–2 per hour on the major clouds at the time of writing).

```bash
# on the box
sudo apt-get install -y build-essential git   # Debian/Ubuntu
curl -LsSf https://astral.sh/uv/install.sh | sh
gh auth login && git clone https://github.com/rslayer/kepler && cd kepler
make env                                       # no libomp step needed on Linux
# data: either copy data/<dataset>/raw from the laptop (rsync) or place ~/.kaggle/access_token
# on the box (mode 600) and run `make data DATASET=m5_all`; then `make holdout DATASET=m5_all`
# (wide layout: writes the evaluation-period holdout, snapshot untouched)
make backtest MODEL=lgbm_baseline DATASET=m5_all JOBS=8
```

Expected with `JOBS=8` and `num_threads=4`: `m5_all` `lgbm_baseline` in roughly 15 minutes,
the recipe in roughly 30, i.e. 3–4 confirmation runs per researcher session instead of one.
Results are identical to the laptop's for the same seeds (determinism verified for JOBS
1 vs 2 on m5_ca1; LightGBM's `deterministic=True, force_row_wise=True` with a fixed thread
count) — re-verify once on the box with `make backtest MODEL=lgbm_baseline DATASET=m5_ca1`
against r033 (0.810828, config 900159c6f3dd) before trusting cross-machine comparisons.

Headless cycles on the box need `claude login` once (the CLI's own OAuth), then
`tools/cycle.sh m5_3 3` (screen) with confirmations on `m5_all` following automatically
(CLAUDE.md step 7a). Fill in the measured column of the table above after the first run.

## What is deliberately not automated
Provisioning, credentials (Kaggle token, GitHub, Claude login), and the yardstick
(`make score-holdout MODEL=<m> DATASET=m5_all`, one shot per model, ever) stay human.
