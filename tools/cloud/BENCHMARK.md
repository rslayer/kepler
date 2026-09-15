# Parallel speedup benchmark (SPEC_v5 Part D)

Model `lgbm_baseline`, dataset `m5_all` (30,490 series, 8 folds x 3 seeds = 24 fits),
seed-averaged (bag_seeds on, v5 default). One backtest timed end to end at four worker
counts. Logged to a scratch runs dir (reproductions of the champion's m5_all baseline r083,
not new results); results identical across worker counts to six decimals (determinism below).

## Machine

Apple M4 Max, 14 cores (10 performance + 4 efficiency), 36 GB. macOS. LightGBM 4.5,
`num_threads=4` per fit, `deterministic=True, force_row_wise=True`.

**Caveat: not a clean idle machine.** This is a corporate-managed laptop; Zscaler, Tanium,
Lakeside, Teams and Outlook run continuously and the numbers below carry their contention.
The 1-minute load average at the start of each phase is recorded; the jobs=1 phase in
particular began while the 5-minute load was ~20 (post-wake background sync), so its
wall clock is an upper bound. A dedicated Linux box (see README.md) will be faster and
steadier; re-run there before quoting a single headline number.

## Timings

| workers (`--jobs`) | threads requested | wall clock | runs/hour (m5_all baseline) | notes |
|---|---|---|---|---|
| 1 | 4  | 44.7 min (2684 s) | 1.34 | serial; early background contention |
| 3 | 12 | 28.3 min (1698 s) | 2.12 | **best**: fits within 14 cores |
| 4 | 16 | 28.4 min (1702 s) | 2.11 | no gain over 3 (already core-bound) |
| 7 | 28 | 53.3 min (3197 s) | 1.12 | oversubscribed: slower than serial |

Peak resident memory ~12 GB (dominated by the main process during the single-threaded
12-level hierarchical scoring), well within 36 GB, at every worker count.

**Speedup.** Best is 1.58x (jobs=1 -> jobs=3), far short of linear. Two reasons: each fit
already uses 4 threads, so 3 workers = 12 threads already fill a 14-core machine; and the
hierarchical scorer runs single-threaded in the main process between folds, an Amdahl floor
that no worker count removes. Requesting more workers than `cores / num_threads` (here 3-4)
oversubscribes and thrashes — jobs=7 is worse than serial. **Rule of thumb: set
`JOBS = floor(cores / 4)`.** On this laptop that is 3.

## Determinism

jobs=1 and jobs=4 produce identical per-fold and aggregate scores to six decimals
(WRMSSE 0.861064, WRMSSE_hier 0.784656). Parallelism changes wall clock only.

## Cost per run

Two independent costs:

- **Agent tokens** (the research loop driving the run): measured **$0.70/run** from
  `runs/sessions.csv` (session researcher-20260913-2: $9.78 for 14 runs, 129 turns). The
  agent spends tokens only on its turns (reading state, deciding, writing findings), not
  while a backtest runs, so this holds regardless of dataset or wall clock.
- **Compute**: on this laptop, sunk (owned hardware). On a cloud spot box (~32 vCPU / 64 GB,
  order $1.50/hr): at the laptop's best 28.3 min that is ~$0.71/run; the README projects
  `JOBS=8` on such a box finishes an m5_all baseline in ~15 min, i.e. **~$0.38/run** compute.

## Projected cost of a 200-run cycle

At m5_all-baseline scale (an upper bound; most loop runs are m5_3 screen runs at ~10-18 min):

| | wall clock | agent tokens | compute | total |
|---|---|---|---|---|
| laptop, JOBS=3 | 200 x 28.3 min = ~94 h (~3.9 days continuous) | $140 | $0 (owned) | **~$140** |
| cloud spot, JOBS=8 | 200 x ~15 min = ~50 h | $140 | 200 x $0.38 = ~$76 | **~$216** |

The binding constraint is wall clock, not dollars: one machine does ~2 m5_all runs/hour, so
a 200-run cycle is days of continuous compute. Parallelising across several boxes (or using
the cheaper m5_3 screen for most runs and reserving m5_all for confirmations) is the lever,
not more workers per box.
