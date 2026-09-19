# SPEC v9 — Parallel search, serial gate (kepler)

Purpose: the champion (recipe6_calendar_l2, holdout 0.626) beats every published M5 benchmark and sits ~0.05 above rank-50 (0.576). The search that has to close that gap is stuck: every candidate since the champion has been rejected one at a time, serially, and the hypothesis ledger that should stop the loop re-trying dead ends is empty. Compute is the other ceiling: one m5_all backtest is 28 min on the laptop, capped at 1.58x speedup by core count and a serial scorer.

This spec does four things, in order: (A) make one backtest 8-10x faster on a cloud box; (B) turn the ledger into the loop's real memory; (C) run three mandate-scoped researchers in parallel with the adversary and the human holdout gate kept strictly serial; (D) give Researcher A its first mandate, multi-horizon direct models, which is the largest structural lever left.

Hand to Claude Code at the repo root: "Read SPEC_v9_parallel.md and execute Parts A through D in order. Stop after each part and report against its acceptance criteria. Never read, list, or write under any holdout/ path. Do not edit any file listed as frozen in HARNESS_CHANGELOG. Commit before every backtest. Part D is a research mandate: run it as Researcher A only, do not start Researchers B or C in this session."

Frozen this session: src/scorer.py, src/scorer_hier.py, src/score_holdout.py, src/scoring.py, tiers.json, the keep rule in src/backtest.py. Part A MAY change how the scorer is *invoked in parallel* (a wrapper), never its arithmetic; scores must remain identical to six decimals.

Non-negotiable throughout: the holdout is scored only by the human, only for a candidate that has cleared (1) the m5_screen directional filter, (2) the strict m5_all keep rule, and (3) the adversary. Researchers never score the holdout. Parallel search, serial gate.

Preflight (report, do not fix): `make verify-frozen`; `python tools/audit_runs.py`; confirm a clean tree; confirm the champion row (r106-equivalent, clean hash) resolves.

---

## Part A — One backtest in 3 minutes (cloud + parallelism)

Where the 28 min goes: 24 fits (8 folds x 3 seeds) at 4 threads each, then single-threaded 12-level scoring. Fits are embarrassingly parallel across (fold, seed); the laptop could not exploit that. The scorer is the serial tail.

### Tasks
- `tools/cloud/`: a provisioning script and README for a spot instance with >= 64 vCPU and >= 128 GB RAM (choose the cheapest provider the person already has credentials for; default to a documented AWS spot type and a Ubuntu image). The script installs the env from pyproject, clones the repo at a given commit, and pulls the m5_all and m5_screen snapshots by manifest. It must NOT copy or reference any holdout/ path.
- Fit-level parallelism: `make backtest` gains `--fit-jobs N`. Launch fits across (fold, seed) pairs concurrently with a process pool; each fit keeps its 4 threads. Default N = floor(vCPU / 4). Determinism: results must match the serial run to six decimals (fixed seeds, no shared RNG state across processes).
- Feature cache: build the feature matrix once per fold and share it across the 3 seeds (the seeds only affect model fitting, not features). Cache in memory or on local disk per fold; invalidated by config hash.
- Scorer parallelism: wrap the 12-level hierarchical scorer so the 12 level aggregations run concurrently; the arithmetic inside src/scorer_hier.py is untouched. Verify identical output to six decimals on the champion row.
- Benchmark and write `tools/cloud/BENCHMARK.md` (append a v9 section): serial vs --fit-jobs max on the cloud box, wall-clock per m5_all backtest, cost per run at spot pricing, projected cost of a 200-run cycle. Also record m5_screen timing.

### Acceptance
- One m5_all backtest of the champion config on the cloud box in <= 4 minutes wall-clock, output identical to the committed champion row to six decimals.
- One m5_screen backtest in <= 90 seconds.
- BENCHMARK.md v9 section filled with measured numbers, not projections.
- `make verify-frozen` clean. Tag `v9-cloud`.

---

## Part B — The ledger becomes the loop's memory

hypotheses/m5_all/ledger.csv has 3 placeholder rows. The real history lives in commit messages and findings/, where no researcher reads it. This is why dead ends get re-tried and why recombination (e.g. r011 + r022) was never testable.

### Tasks
- Backfill the ledger from findings/ and git history: one row per hypothesis (H001..H163 where identifiable), with columns exactly: `hypothesis_id, status (kept|discarded|inconclusive|held|skipped|pending), lever (feature|target|objective|architecture|horizon|hierarchy|ensemble|data|recursive|other), summary, mechanism (one line on WHY it did or did not work), first_run, last_run, best_wrmsse_hier, holdout_wrmsse (if scored), rejected_by (keep_rule|adversary|holdout|human|n/a), evidence (findings path or commit)`.
- Add a `LEDGER_RULES.md` next to it: a hypothesis may not be re-run with the same lever+mechanism unless the ledger row is marked `reopen` by a human with a reason. Recombinations are new rows that cite their parents.
- Session start rule, added to CLAUDE.md (below the RULES marker): every researcher session opens by reading the ledger, the champion row, and the calm-month diagnostic (`make report RUN=<champion> --by month`), and writes its chosen hypothesis as a `pending` ledger row BEFORE running anything. Session end writes the verdict and mechanism.
- `tools/ledger_check.py`: fails a run if its ledger row is missing or if lever+mechanism duplicates a non-reopened row.

### Acceptance
- Ledger has one row per historically identifiable hypothesis, every rejected row has a `mechanism` and `rejected_by`.
- The four recursive variants (H161 family) are present, all `discarded`, all `rejected_by=keep_rule` or `holdout`, mechanism naming compounding bias — this is the dead end the ledger must now block.
- `tools/ledger_check.py` blocks a re-run of a recursive-with-same-mechanism hypothesis and allows a `reopen`ed one.
- Commit; tag `v9-ledger`.

---

## Part C — Three researchers, one referee, one gate

### Design
Three researcher sessions with DISJOINT mandates, sharing one ledger, one frozen scorer, one adversary, one human gate:
- **Researcher A — horizon.** Multi-horizon direct models with per-horizon feature sets. (Part D is its first mandate.)
- **Researcher B — hierarchy.** Level-aware modeling and reconciliation across the 12 WRMSSE levels; tuning the one discarded attempt (r129) rather than restarting.
- **Researcher C — ensemble.** Fold-robust ensembling: stacking weights fit across all 8 folds, diversity across A and B outputs, every candidate holdout-gated by the human.

A mandate may not run a hypothesis whose `lever` belongs to another mandate; `tools/ledger_check.py` enforces it. Researchers do not talk to each other; the ledger is the only shared state.

### Tasks
- `tools/orchestrate.sh`: launches N named researcher sessions (`claude -p` headless, one per mandate) with a per-session hour budget and a per-session `CLAUDE.md` overlay that pins the mandate and its allowed levers. Each session writes to branches namespaced `exp/<mandate>/<run_id>` and its own findings subfolder. Runs may execute concurrently on the cloud box; `--fit-jobs` is divided across live sessions so the box is not oversubscribed.
- The adversary runs as ONE serial pass after the researchers finish (`tools/adversary_pass.sh`): reviews every new `exp/*` branch in order of backtest gain, writes verdicts back to runs.csv and the ledger. Never more than one adversary process.
- The gate stays human. `tools/gate_queue.py` lists candidates that have cleared screen + m5_all keep rule + adversary, in order, with their ledger rows, for the human to choose which (if any) to score on the holdout. No tool scores the holdout.
- Holdout budget rule, written into LEDGER_RULES.md: at most 2 holdout scorings per week across all mandates. Every holdout score is logged with the candidate's ledger id. If a candidate fails the holdout, its lever+mechanism is marked `held` and cannot be re-scored without a `reopen`.
- Nightly cron on the cloud box: orchestrate (3 sessions, 4h budget each) -> adversary pass -> gate queue emailed/written to `runs/GATE_QUEUE.md`. The human reviews in the morning.

### Acceptance
- One full nightly cycle completes unattended on the cloud box: three researcher sessions, one adversary pass, a written gate queue. Report sessions run, runs per mandate, adversary verdicts, and cost from runs/sessions.csv.
- `tools/ledger_check.py` blocks a session running a hypothesis outside its mandate.
- Zero holdout scorings by any tool (verify: no process referenced holdout/; audit log clean).
- Tag `v9-parallel`.

---

## Part D — Researcher A, first mandate: multi-horizon direct models

Why this lever: the champion is one model predicting 28 days with features frozen at the origin, and it wins Christmas while losing calm months. The M5 medal solutions used direct models per horizon bucket (or per day), each with lags valid for that horizon. Unlike recursion (four variants, all rejected for compounding bias), direct multi-horizon has no compounding, so it does not repeat the failed lever.

### Tasks (run as Researcher A, on the cloud box, using Part A's parallelism)
- Implement `lgbm_direct_mh` in src/model.py: separate models per horizon bucket, initially 4 buckets (d1-7, d8-14, d15-21, d22-28). Each bucket's feature set uses only lags >= its minimum horizon (so a d15-21 model uses lag >= 15), plus the champion's calendar/price/SNAP features. Role-driven, not M5-specific.
- Ledger first: write the `pending` row (lever=horizon, mechanism="per-horizon direct models with horizon-valid lags; no compounding").
- Screen on m5_screen (directional filter), then confirm on m5_all under the strict keep rule vs the champion as parent. One variable: bucket count. Try 4, then 7 (weekly), then 28 (per-day) if compute allows.
- Run the calm-month diagnostic on the best bucket variant vs the champion: does it stop trading holidays for calm months? Report per-month gain.
- Adversary pass on the best branch. Do NOT score the holdout; queue it for the human via gate_queue.

### Acceptance
- At least one `lgbm_direct_mh` variant with positive mean gain on m5_screen and a strict m5_all keep vs the champion, OR a clear ledger row explaining why the lever failed and what mechanism killed it.
- Calm-month diagnostic written to findings/ showing per-month deltas for the best variant.
- Adversary verdict recorded; candidate present in GATE_QUEUE.md if it cleared.
- Ledger row closed with verdict and mechanism.

---

## The number this spec is aiming at
A human-scored holdout below **0.60** on a candidate that cleared screen, keep rule, and adversary. That is inside striking distance of rank-50 (0.576). If Part D alone gets below 0.61 on the holdout, Researcher B's reconciliation cycle is the next spec; if it does not, the ledger row will say why and Researcher B starts on the calm-month problem instead.

## Out of scope
- Any recursive forecasting hypothesis (blocked by the ledger unless a human reopens with a new mechanism).
- Any change to scorer arithmetic, holdout, or tiers.json.
- PepsiCo data. Public M5 only.
- Promotion to champion — human-run, outside this session.
