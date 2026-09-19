# kepler on a cloud box (SPEC v9 Part A)

Goal: one m5_all backtest in <=4 min (vs ~28 min serial on the laptop) by running the 24
fold×seed fits in parallel and parallelizing the 12-level scorer. Parallel search, serial gate:
**the holdout is never provisioned here and is never scored by any researcher or tool.**

## 1. Launch (your credentials — the script only prints the template)
```
tools/cloud/provision.sh launch     # prints an AWS spot run-instances template; edit + run yourself
```
Pick the cheapest >=64 vCPU / >=128 GB spot box you have credentials for. Defaults: `c7i.16xlarge`
(64 vCPU / 128 GB), Ubuntu 22.04. `r7i.16xlarge` if a fit turns out memory-bound.

## 2. Set up the box
```
scp ~/.kaggle/kaggle.json ubuntu@BOX:~/.kaggle/kaggle.json   # chmod 600 on the box
ssh ubuntu@BOX
./tools/cloud/provision.sh setup <commit>     # installs uv env, clones repo at <commit>
./tools/cloud/provision.sh pull-data          # rebuilds m5_all + m5_screen snapshots from Kaggle
```
`pull-data` writes only under `data/<id>/snapshot/`. It never creates or copies `holdout/`.

## 3. Run a parallel backtest
```
make backtest MODEL=recipe6_calendar_l2 DATASET=m5_all FIT_JOBS=$(( $(nproc) / 4 ))
```
`--fit-jobs N` (Makefile `FIT_JOBS=`) runs N fits concurrently, each with 4 threads; default is
`floor(vCPU/4)`. A per-fold feature cache builds the feature matrix once and shares it across the
3 seeds. The 12-level scorer runs its level aggregations concurrently (arithmetic unchanged;
verified identical to six decimals).

## 4. Determinism
`--fit-jobs` changes only scheduling: each (fold, seed) fit is independent and seeded, so results
match the serial run to six decimals. Verify with `tools/cloud/verify_identical.py <serial_run> <parallel_run>`.

## 5. Benchmark
See `BENCHMARK.md`. Fill its v9 section with measured numbers from THIS box (serial vs
`--fit-jobs max`, wall-clock, spot $/run, projected 200-run cycle cost).

## What is deliberately absent
- No `holdout/` on the box. The gate is human-run on the laptop only.
- No scorer-arithmetic changes. Only the *invocation* is parallelized.
