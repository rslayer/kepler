"""Rolling-origin backtest driver.

FOLD LOGIC IS HUMAN-OWNED (see CODEOWNERS). Agents add entries to MODELS in
src/model.py and nothing else in the fold path.

Four folds, 28-day horizon, origins spaced 28 days apart, the last fold ending on the
last day of the agent-visible snapshot. Training data for a fold is strictly prior to
that fold's origin.

A DELIBERATE DESIGN CHOICE: the model is handed the whole visible panel, not a panel
truncated at the origin. Truncating would make look-ahead structurally impossible - and
would also make the Phase 3 planted-leak test impossible to construct. The no-look-ahead
rule is therefore a contract enforced by src/features.py assertions and by the adversary,
not by the harness withholding data. That is the property under test.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from . import scorer, scorer_hier
from .data import DEFAULT_DATASET, ROOT, load_dataset
from .scoring import scorer_frames
from .features import HORIZON, Panel
from .model import get_model

# KEPLER_RUNS_DIR redirects the run log + detail output (used by the adversary to rerun a
# branch's model without appending to the canonical, append-only runs/runs.csv).
_RUNS_DIR = Path(os.environ["KEPLER_RUNS_DIR"]) if os.environ.get("KEPLER_RUNS_DIR") else ROOT / "runs"
RUNS_CSV = _RUNS_DIR / "runs.csv"
DETAIL_DIR = _RUNS_DIR / "detail"
FINDINGS_DIR = ROOT / "findings"

N_FOLDS = 8
SEEDS = (42, 7, 123)  # every backtest fits once per seed per fold; metrics are logged as mean and spread
FOLD_SPACING = 14  # days between consecutive fold origins; windows overlap by 14 days
TIMEOUT_SECONDS = 20 * 60  # default; a Dataset may set timeout_minutes (m5_all: 90)

RUN_COLUMNS = [
    "run_id", "timestamp", "git_commit", "model_name", "config_hash", "fold_count", "fold_spacing",
    "wrmsse", "wape", "bias", "wape_h1_7", "wape_h8_14", "wape_h15_28",
    "wrmsse_spread", "wape_spread", "bias_spread",
    "wape_h1_7_spread", "wape_h8_14_spread", "wape_h15_28_spread",
    "seconds", "status", "findings_file", "author", "verdict", "session", "hypothesis_id", "dataset",
    "wrmsse_hier", "wrmsse_hier_spread",
    "bagged",  # v5: True when the headline metrics score the seed-averaged forecast
]
BAG_SEEDS_DEFAULT = True  # v5 Part A: new runs bag seeds unless --bag-seeds off (reproduces v1-v4 runs)
METRIC_KEYS = ["wrmsse", "wape", "bias", "wape_h1_7", "wape_h8_14", "wape_h15_28"]
HIER_KEY = "wrmsse_hier"  # logged when the dataset's roles define a hierarchy; the keep rule then uses it


def bag_forecasts(preds: list[pd.DataFrame]) -> pd.DataFrame:
    """Seed-averaged forecast: the mean of the per-seed forecasts for every (id, date).
    All frames must cover the same (id, date) set; rows are aligned on the first frame's
    order so the result is deterministic. This is the forecast a production model would
    serve, and scoring it (rather than each seed separately) removes most seed-to-seed
    noise from the headline metric."""
    if len(preds) == 1:
        return preds[0]
    base = preds[0][["id", "date"]].reset_index(drop=True)
    stack = []
    for f in preds:
        g = f.set_index(["id", "date"])["forecast"]
        stack.append(g.reindex(pd.MultiIndex.from_frame(base)).to_numpy(dtype=float))
        if np.isnan(stack[-1]).any():
            raise SystemExit("seed forecasts do not cover the same (id, date) set; cannot bag")
    return base.assign(forecast=np.mean(np.vstack(stack), axis=0))


# --------------------------------------------------------------------------- fold logic
def make_folds(
    panel: Panel, n_folds: int = N_FOLDS, horizon: int = HORIZON, spacing: int = FOLD_SPACING
) -> list[pd.Timestamp]:
    """Origins of each fold, oldest first, `spacing` days apart. The last fold's window
    ends on the snapshot's last day. With spacing < horizon, consecutive windows overlap."""
    n_days = len(panel.dates)
    needed = (n_folds - 1) * spacing + horizon
    if n_days < needed + horizon:
        raise SystemExit(f"snapshot has {n_days} days; need at least {needed + horizon}")
    origins = []
    for f in range(n_folds):
        end_pos = n_days - 1 - (n_folds - 1 - f) * spacing
        origins.append(pd.Timestamp(panel.dates[end_pos - horizon + 1]))
    return origins


# ------------------------------------------------------------------------------ logging
def git_commit() -> str:
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True
        ).stdout.strip()
        return f"{sha}-dirty" if dirty else sha
    except Exception:
        return "unknown"


def config_hash(config: dict) -> str:
    blob = json.dumps(config, sort_keys=True, default=str).encode()
    return hashlib.sha256(blob).hexdigest()[:12]


def next_run_id() -> str:
    if not RUNS_CSV.exists():
        return "r001"
    with RUNS_CSV.open() as fh:
        n = sum(1 for _ in csv.DictReader(fh))
    return f"r{n + 1:03d}"


def append_run(row: dict) -> None:
    RUNS_CSV.parent.mkdir(parents=True, exist_ok=True)
    exists = RUNS_CSV.exists() and RUNS_CSV.stat().st_size > 0
    with RUNS_CSV.open("a", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=RUN_COLUMNS)
        if not exists:
            writer.writeheader()
        writer.writerow({k: row.get(k, "") for k in RUN_COLUMNS})


# ---------------------------------------------------------------------------- keep rule
BIAS_GUARDRAIL = 0.02
# v6: condition 1 tests the paired per-fold gain against its OWN uncertainty, not 2x the
# noisier run's single-seed spread. Z sigmas above zero, with a minimum worth-a-champion floor.
KEEP_Z = 2.0
KEEP_FLOOR = 0.002  # minimum mean paired gain on wrmsse / wrmsse_hier to matter at all


def load_parent(run_id: str) -> dict:
    path = DETAIL_DIR / f"{run_id}.json"
    if not path.exists():
        path = ROOT / "runs" / "detail" / f"{run_id}.json"  # canonical log, when redirected
    if not path.exists():
        raise SystemExit(f"parent {run_id}: no detail file at runs/detail/{run_id}.json")
    parent = json.loads(path.read_text())
    if "seeds" not in parent or not parent.get("seed_list"):
        raise SystemExit(f"parent {run_id} has no seeds block: parent must be a v1 run")
    if parent.get("status") != "ok":
        raise SystemExit(f"parent {run_id} has status={parent.get('status')}; parent must be an ok run")
    return parent


def keep_rule(child_row: dict, child_folds: list[dict], parent: dict, metric: str = "wrmsse") -> dict:
    """The v1 keep rule, evaluated on WRMSSE. All three conditions required for `kept`.

    1. paired gain: parent mean - child mean > 2 * max(parent spread, child spread),
       spreads at the aggregate (run) level.
    2. no fold regresses: for every fold, child fold-mean <= parent fold-mean +
       max(parent fold spread, child fold spread), spreads at the fold level. Fold-level
       spreads are used here because the aggregate spread is 10-20x smaller than any single
       fold's (averaging folds cancels seed noise) and would discard on ordinary noise.
    3. bias guardrail: |child bias| <= |parent bias| + 0.02.
    """
    if parent.get("bagged") and parent.get("bagged_aggregate"):
        # v5: a bagged parent's headline is the score of its seed-averaged forecast
        p_agg = {k: float(parent["bagged_aggregate"][k]) for k in (metric, "bias")}
    else:
        p_agg = {k: float(np.mean([parent["seeds"][s]["aggregate"][k] for s in parent["seeds"]]))
                 for k in (metric, "bias")}
    c_bias = float(child_row["bias"])

    p_folds = parent["folds"]
    if [f["origin"] for f in p_folds] != [f["origin"] for f in child_folds]:
        raise SystemExit("parent and child fold origins differ; runs are not comparable")

    # Condition 1 (v6): the paired per-fold gain (parent - child, positive = child better) tested
    # against its own standard error, not 2x the noisier run's single-seed spread. n_eff discounts
    # the fold-window overlap (14-day spacing, 28-day horizon -> each window ~half-independent).
    gain_f = [float(pf[metric]) - float(cf[metric]) for pf, cf in zip(p_folds, child_folds)]
    gain = float(np.mean(gain_f))
    n_eff = max(1, math.ceil(len(gain_f) * FOLD_SPACING / HORIZON))
    sd = float(np.std(gain_f, ddof=1)) if len(gain_f) > 1 else 0.0
    se = sd / math.sqrt(n_eff)
    cond1 = {"pass": bool(gain > 0 and gain > KEEP_Z * se and gain > KEEP_FLOOR),
             "gain": gain, "se": se, "n_eff": n_eff, "z": KEEP_Z, "floor": KEEP_FLOOR,
             "threshold": max(KEEP_Z * se, KEEP_FLOOR), "gain_f": gain_f,
             "parent_mean": float(p_agg[metric]), "child_mean": float(child_row[metric])}
    per_fold = []
    for pf, cf in zip(p_folds, child_folds):
        ftol = max(pf[f"{metric}_spread"], cf[f"{metric}_spread"])
        regress = cf[metric] - pf[metric]
        per_fold.append({"fold": cf["fold"], "origin": cf["origin"], "parent": pf[metric],
                         "child": cf[metric], "delta": regress, "tolerance": ftol,
                         "pass": bool(regress <= ftol)})
    cond2 = {"pass": all(f["pass"] for f in per_fold), "folds": per_fold}

    cond3 = {"pass": bool(abs(c_bias) <= abs(p_agg["bias"]) + BIAS_GUARDRAIL),
             "parent_abs_bias": abs(p_agg["bias"]), "child_abs_bias": abs(c_bias),
             "guardrail": BIAS_GUARDRAIL}

    verdict = "kept" if (cond1["pass"] and cond2["pass"] and cond3["pass"]) else "discarded"
    return {"parent": parent["run_id"], "verdict": verdict, "metric": metric,
            "parent_bagged": bool(parent.get("bagged", False)), "child_bagged": bool(child_row.get("bagged") in (True, "True")),
            "paired_gain": cond1, "no_fold_regresses": cond2, "bias_guardrail": cond3}


def print_keep_rule(kr: dict) -> None:
    c1, c2, c3 = kr["paired_gain"], kr["no_fold_regresses"], kr["bias_guardrail"]
    print(f"\nkeep rule vs parent {kr['parent']} on {kr.get('metric', 'wrmsse')}:")
    print(f"  1 paired gain      {'PASS' if c1['pass'] else 'FAIL'}  gain={c1['gain']:+.6f} "
          f"threshold={c1['threshold']:.6f} ({c1['z']} x SE {c1['se']:.6f} over n_eff={c1['n_eff']}, floor {c1['floor']})")
    worst = max(c2["folds"], key=lambda f: f["delta"] - f["tolerance"])
    print(f"  2 no fold regress  {'PASS' if c2['pass'] else 'FAIL'}  "
          f"{sum(f['pass'] for f in c2['folds'])}/{len(c2['folds'])} folds within tolerance; "
          f"worst fold {worst['fold']} delta={worst['delta']:+.6f} tol={worst['tolerance']:.6f}")
    print(f"  3 bias guardrail   {'PASS' if c3['pass'] else 'FAIL'}  "
          f"|bias| child={c3['child_abs_bias']:.4f} parent={c3['parent_abs_bias']:.4f} +{c3['guardrail']}")
    print(f"  verdict={kr['verdict']}")


# ---------------------------------------------------------------------- parallel fits
# --jobs N: the (fold, seed) fits run in N worker processes, each loading the dataset once.
# Scoring, logging, the timeout check and the fold loop stay in the main process, in the
# same order as sequential, so results are identical (each fit is independent and seeded).
_W: dict = {}


def _worker_init(dataset_id: str, model_name: str) -> None:
    import os as _os
    _os.environ.setdefault("OMP_NUM_THREADS", "4")
    _W["ds"] = load_dataset(dataset_id)
    _W["panel"] = Panel(_W["ds"])
    _W["model"] = get_model(model_name)


def _worker_fit(task: tuple) -> tuple:
    origin, horizon, seed = task
    pred = _W["model"].forecast(_W["panel"], pd.Timestamp(origin), horizon, seed)
    return (str(origin), seed, pred)


def parallel_forecasts(dataset_id: str, model_name: str, origins: list, seeds: tuple, horizon: int,
                       jobs: int, budget_seconds: float | None = None) -> dict:
    """{(origin_str, seed): forecast frame}, computed with `jobs` processes. Stops
    submitting new fits once `budget_seconds` has elapsed; the caller then sees missing
    (origin, seed) pairs and marks the run timeout, as the sequential path would."""
    import concurrent.futures as cf
    import multiprocessing as mp
    tasks = [(str(o), horizon, sd) for o in origins for sd in seeds]
    out = {}
    t0 = time.time()
    ctx = mp.get_context("spawn")
    with cf.ProcessPoolExecutor(max_workers=jobs, mp_context=ctx,
                                initializer=_worker_init, initargs=(dataset_id, model_name)) as ex:
        pending = {}
        it = iter(tasks)
        for _ in range(jobs):
            t = next(it, None)
            if t: pending[ex.submit(_worker_fit, t)] = t
        while pending:
            done, _ = cf.wait(list(pending), return_when=cf.FIRST_COMPLETED)
            for fut in done:
                pending.pop(fut)
                o, sd, pred = fut.result()
                out[(o, sd)] = pred
                if budget_seconds is None or time.time() - t0 < budget_seconds:
                    t = next(it, None)
                    if t: pending[ex.submit(_worker_fit, t)] = t
    return out


# ------------------------------------------------------------------------------- driver
def run_backtest(
    model_name: str,
    seeds: tuple[int, ...] = SEEDS,
    author: str = "human",
    n_folds: int = N_FOLDS,
    parent_id: str | None = None,
    session: str = "",
    hypothesis_id: str = "",
    dataset_id: str = DEFAULT_DATASET,
    jobs: int = 1,
    bag_seeds: bool = BAG_SEEDS_DEFAULT,
) -> dict:
    parent = load_parent(parent_id) if parent_id else None  # fail fast, before any fit
    ds = load_dataset(dataset_id)
    panel = Panel(ds)
    model = get_model(model_name)
    origins = make_folds(panel, n_folds)
    seeds = tuple(seeds)
    sales, calendar, prices = scorer_frames(ds, origins[0])
    hierarchy = ds.roles.get("hierarchy") or []
    metric = HIER_KEY if hierarchy else "wrmsse"
    timeout = int(getattr(ds, "timeout_minutes", TIMEOUT_SECONDS // 60)) * 60

    print(f"dataset={dataset_id} model={model_name} seeds={list(seeds)} author={author} jobs={jobs} "
          f"bag_seeds={'on' if bag_seeds else 'off'}")
    print(f"snapshot: {len(panel.ids)} series, {len(panel.dates)} days, last {panel.last_date.date()}")
    print(f"fold origins ({len(origins)} folds, {FOLD_SPACING}-day spacing, {HORIZON}-day horizon): "
          + ", ".join(str(pd.Timestamp(o).date()) for o in origins))

    started = time.time()
    precomputed = (parallel_forecasts(dataset_id, model_name, origins, seeds, HORIZON, jobs, timeout)
                   if jobs > 1 else None)
    fold_metrics: list[dict] = []          # per fold: mean across seeds
    seed_folds: dict[int, list[dict]] = {sd: [] for sd in seeds}  # per seed: per-fold metrics
    per_series: list[pd.DataFrame] = []    # per fold: per-series detail (bagged forecast, or mean across seeds)
    bag_folds: list[dict] = []             # per fold: metrics of the seed-averaged forecast (bag_seeds on)
    status = "ok"

    def score(pred: pd.DataFrame, truth: pd.DataFrame, train_long: pd.DataFrame) -> tuple[dict, pd.DataFrame]:
        metrics, detail = scorer.score_window(truth[["id", "date", "sales"]], pred, train_long, prices, calendar)
        if hierarchy:
            hm, _ = scorer_hier.score_window_hier(
                truth[["id", "date", "sales"]], pred, train_long, prices, calendar, ds.series, hierarchy
            )
            metrics[HIER_KEY] = hm["wrmsse_hier"]
            metrics["hier_levels"] = hm["levels"]
        return metrics, detail

    for i, origin in enumerate(origins, start=1):
        window_end = origin + pd.Timedelta(days=HORIZON - 1)
        truth = sales[(sales["date"] >= origin) & (sales["date"] <= window_end)]
        train_long = sales[sales["date"] < origin]

        seed_details = []
        seed_preds = []
        for sd in seeds:  # fits are sequential here unless --jobs precomputed them
            if precomputed is not None and (str(origin), sd) not in precomputed:
                break  # budget ran out during the parallel fits
            pred = precomputed[(str(origin), sd)] if precomputed else model.forecast(panel, origin, HORIZON, sd)
            if (pred["date"] < origin).any() or (pred["date"] > window_end).any():
                raise SystemExit(f"model returned dates outside fold {i}'s window")
            seed_preds.append(pred)
            metrics, detail = score(pred, truth, train_long)
            metrics["fold"] = i
            metrics["origin"] = str(pd.Timestamp(origin).date())
            metrics["seed"] = sd
            seed_folds[sd].append(metrics)
            seed_details.append(detail)
            if time.time() - started > timeout:
                break

        done = [seed_folds[sd][-1] for sd in seeds if len(seed_folds[sd]) == i]
        keys = METRIC_KEYS + ([HIER_KEY] if hierarchy else [])
        seed_mean = {k: float(np.mean([m[k] for m in done])) for k in keys}
        bagged_fold = bag_seeds and len(done) == len(seeds)
        if bagged_fold:
            # v5: the headline fold metrics score the seed-averaged forecast; per-seed
            # means and spreads are kept alongside (spread = the noise-floor input).
            bag_metrics, bag_detail = score(bag_forecasts(seed_preds), truth, train_long)
            bag_metrics.update(fold=i, origin=str(pd.Timestamp(origin).date()))
            bag_folds.append(bag_metrics)
            fold_mean = {k: float(bag_metrics[k]) for k in keys}
            fold_mean["seed_mean"] = seed_mean
            if hierarchy:
                fold_mean["hier_levels"] = bag_metrics["hier_levels"]
        else:
            fold_mean = dict(seed_mean)
            if hierarchy:
                fold_mean["hier_levels"] = {lv: float(np.mean([m["hier_levels"][lv] for m in done])) for lv in done[0]["hier_levels"]}
        if hierarchy:
            fold_mean["wrmsse_hier_spread"] = float(max(m[HIER_KEY] for m in done) - min(m[HIER_KEY] for m in done))
        fold_mean["bagged"] = bool(bagged_fold)
        fold_mean.update(
            fold=i,
            origin=str(pd.Timestamp(origin).date()),
            n_series=done[0]["n_series"],
            n_scored=done[0]["n_scored"],
            seeds_done=len(done),
            wrmsse_spread=float(max(m["wrmsse"] for m in done) - min(m["wrmsse"] for m in done)),
        )
        fold_metrics.append(fold_mean)
        per_series.append(
            bag_detail.assign(fold=i) if bagged_fold
            else pd.concat(seed_details).groupby(level=0).mean(numeric_only=True).assign(fold=i)
        )

        elapsed = time.time() - started
        hier_txt = f" hier={fold_mean[HIER_KEY]:.6f}" if hierarchy else ""
        print(
            f"  fold {i} origin={pd.Timestamp(origin).date()} "
            f"wrmsse={fold_mean['wrmsse']:.6f} (spread {fold_mean['wrmsse_spread']:.6f}){hier_txt} "
            f"wape={fold_mean['wape']:.6f} bias={fold_mean['bias']:+.6f}  "
            f"[{len(done)}/{len(seeds)} seeds, {elapsed:.1f}s]"
        )
        if elapsed > timeout or len(done) < len(seeds):
            status = "timeout"
            print(f"  exceeded {timeout}s budget - marking run as timeout")
            break

    seconds = time.time() - started
    run_id = next_run_id()
    row = {
        "run_id": run_id,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_commit": git_commit(),
        "model_name": model_name,
        "config_hash": config_hash(
            {"model": model.config(), "seeds": list(seeds), "folds": n_folds, "fold_spacing": FOLD_SPACING,
             **({"bag_seeds": True} if bag_seeds else {})}  # off = the v1-v4 hash, unchanged
        ),
        "fold_count": len(fold_metrics),
        "fold_spacing": FOLD_SPACING,
        "seconds": f"{seconds:.1f}",
        "status": status,
        "findings_file": f"findings/{run_id}.md",
        "author": author,
        "session": session,
        "hypothesis_id": hypothesis_id,
        "dataset": dataset_id,
        "bagged": bool(bag_seeds),
    }
    seed_aggregates = {}
    bag_aggregate = None
    if status == "ok":
        # Aggregate each seed over folds with the frozen scorer, then mean / spread across seeds.
        seed_aggregates = {sd: scorer.aggregate_folds(seed_folds[sd]) for sd in seeds}
        if hierarchy:
            for sd in seeds:
                seed_aggregates[sd][HIER_KEY] = float(np.mean([m[HIER_KEY] for m in seed_folds[sd]]))
        if bag_seeds:
            # v5: headline = the seed-averaged forecast's own aggregate (same frozen aggregation)
            bag_aggregate = scorer.aggregate_folds(bag_folds)
            if hierarchy:
                bag_aggregate[HIER_KEY] = float(np.mean([m[HIER_KEY] for m in bag_folds]))
        for k in METRIC_KEYS + ([HIER_KEY] if hierarchy else []):
            vals = [seed_aggregates[sd][k] for sd in seeds]
            row[k] = f"{(bag_aggregate[k] if bag_seeds else float(np.mean(vals))):.6f}"
            row[f"{k}_spread"] = f"{float(max(vals) - min(vals)):.6f}"  # pre-bagging, by design

    kr = None
    if parent is None:
        row["verdict"] = "no_parent"
    elif status != "ok":
        row["verdict"] = "discarded"
        kr = {"parent": parent["run_id"], "verdict": "discarded", "reason": f"run status {status}"}
    else:
        use = metric if (metric in row and "seeds" in parent and all(HIER_KEY in parent["seeds"][s]["aggregate"] for s in parent["seeds"])) else "wrmsse"
        kr = keep_rule(row, fold_metrics, parent, use)
        row["verdict"] = kr["verdict"]

    DETAIL_DIR.mkdir(parents=True, exist_ok=True)
    series_detail = (
        pd.concat(per_series)
        .groupby(level=0)[["weight_norm", "rmsse", "contrib", "actual", "abs_err"]]
        .mean()
        .sort_values("contrib", ascending=False)
    )
    (DETAIL_DIR / f"{run_id}.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "model_name": model_name,
                "dataset": dataset_id,
                "metric": metric,
                "seed": ",".join(map(str, seeds)),  # frozen report.py prints detail["seed"]
                "seed_list": list(seeds),
                "fold_spacing": FOLD_SPACING,
                "author": author,
                "status": status,
                "config": model.config(),
                "bagged": bool(bag_seeds),
                "bagged_aggregate": bag_aggregate,
                "folds": fold_metrics,
                "keep_rule": kr,
                "seeds": {
                    str(sd): {"folds": seed_folds[sd], "aggregate": seed_aggregates.get(sd)}
                    for sd in seeds
                },
                "per_series": series_detail.reset_index().rename(columns={"index": "id"}).to_dict("records"),
            },
            indent=2,
            default=str,
        )
    )
    append_run(row)
    print(f"\nlogged {run_id}  status={status}  seconds={seconds:.1f}")
    if status == "ok":
        print(
            f"  WRMSSE={row['wrmsse']} (spread {row['wrmsse_spread']})"
            + (f"  WRMSSE_hier={row['wrmsse_hier']} (spread {row['wrmsse_hier_spread']})" if hierarchy else "")
            + f"  WAPE={row['wape']}  bias={row['bias']}\n"
            f"  WAPE h1-7={row['wape_h1_7']} h8-14={row['wape_h8_14']} h15-28={row['wape_h15_28']}"
        )
        if bag_seeds:
            sm = {k: float(np.mean([seed_aggregates[sd][k] for sd in seeds])) for k in ("wrmsse", *([HIER_KEY] if hierarchy else []))}
            print("  headline scores the seed-averaged forecast (bagged=True); per-seed means: "
                  + "  ".join(f"{k}={v:.6f}" for k, v in sm.items()))
    print(f"  detail: runs/detail/{run_id}.json   findings: {row['findings_file']}")
    if kr and "paired_gain" in kr:
        print_keep_rule(kr)
    elif kr:
        print(f"\nkeep rule vs parent {kr['parent']}: verdict=discarded ({kr['reason']})")
    else:
        print("  verdict=no_parent (pass --parent <run_id> to evaluate the keep rule)")
    return row


def reparent(run_id: str, parent_id: str, author: str, session: str) -> dict:
    """Log a new row that re-evaluates an existing run's keep rule against a different
    parent, from its recorded per-seed, per-fold metrics. No fit is made; the fits are
    deterministic and the forecasts' scores are exactly the detail file's. Use when a run
    was logged against an intermediate parent and the comparison that matters is against
    the champion (or vice versa)."""
    src = ROOT / "runs" / "detail" / f"{run_id}.json"
    if not src.exists():
        raise SystemExit(f"no detail for {run_id}")
    d = json.loads(src.read_text())
    if d.get("status") != "ok" or "seeds" not in d:
        raise SystemExit(f"{run_id} must be an ok v1+ run")
    parent = load_parent(parent_id)
    seeds = [int(s) for s in d["seeds"]]
    metric = d.get("metric", "wrmsse")
    row = {k: "" for k in RUN_COLUMNS}
    new_id = next_run_id()
    keys = METRIC_KEYS + ([HIER_KEY] if metric == HIER_KEY else [])
    bagged = bool(d.get("bagged")) and bool(d.get("bagged_aggregate"))
    for k in keys:
        vals = [d["seeds"][str(sd)]["aggregate"][k] for sd in seeds]
        row[k] = f"{(d['bagged_aggregate'][k] if bagged else float(np.mean(vals))):.6f}"
        row[f"{k}_spread"] = f"{float(max(vals) - min(vals)):.6f}"
    row["bagged"] = bagged
    row.update(run_id=new_id, timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"), git_commit=git_commit(),
               model_name=d["model_name"], config_hash=config_hash({"model": d["config"], "seeds": seeds, "folds": len(d["folds"]),
                                                                    "fold_spacing": d.get("fold_spacing", FOLD_SPACING)}),
               fold_count=len(d["folds"]), fold_spacing=d.get("fold_spacing", FOLD_SPACING), seconds="0.0", status="ok",
               findings_file=f"findings/{new_id}.md", author=author, session=session, hypothesis_id=d.get("hypothesis_id", ""),
               dataset=d.get("dataset", ""))
    kr = keep_rule(row, d["folds"], parent, metric)
    row["verdict"] = kr["verdict"]
    out = dict(d); out.update(run_id=new_id, keep_rule=kr, reparent_of=run_id, author=author, session=session)
    (ROOT / "runs" / "detail" / f"{new_id}.json").write_text(json.dumps(out, indent=2, default=str))
    append_run(row)
    print(f"logged {new_id}: {d['model_name']} on {d.get('dataset')} re-evaluated against {parent_id} (from {run_id}'s forecasts)")
    print_keep_rule(kr)
    return row


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Rolling-origin backtest")
    parser.add_argument("--reparent", default=None, help="existing run_id: re-evaluate its keep rule against --parent, no fit")
    parser.add_argument("--model", required=False, default=None)
    parser.add_argument(
        "--seeds", default=",".join(map(str, SEEDS)),
        help=f"comma-separated seeds, default {','.join(map(str, SEEDS))}",
    )
    parser.add_argument("--author", default="human", choices=["human", "researcher", "adversary"])
    parser.add_argument("--folds", type=int, default=N_FOLDS)
    parser.add_argument("--parent", default=None, help="run_id to evaluate the keep rule against")
    parser.add_argument("--session", default="", help="<role>-<YYYYMMDD>-<n>; required for researcher runs")
    parser.add_argument("--hypothesis", default="", help="H### from hypotheses/ledger.csv; required for researcher runs")
    parser.add_argument("--dataset", default=DEFAULT_DATASET)
    parser.add_argument("--jobs", type=int, default=1, help="worker processes for the (fold, seed) fits")
    parser.add_argument("--bag-seeds", choices=["on", "off"], default="on" if BAG_SEEDS_DEFAULT else "off",
                        help="on (default): headline metrics score the seed-averaged forecast; off reproduces v1-v4 runs")
    args = parser.parse_args(argv)
    if args.reparent:
        if not args.parent:
            raise SystemExit("--reparent needs --parent")
        reparent(args.reparent, args.parent, args.author, args.session)
        return 0
    if not os.environ.get("KEPLER_RUNS_DIR"):
        # v5 Part E: a run logged to the canonical runs/ must carry a clean commit hash.
        # (Reruns redirected with KEPLER_RUNS_DIR - adversary scratch - are exempt; their
        # hash still records -dirty.) tools/cycle.sh enforces the same before a headless cycle.
        dirty = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
        if dirty:
            raise SystemExit("working tree is dirty; commit (or stash) before a backtest so the run's git_commit is "
                             "reproducible:\n  " + "\n  ".join(dirty.splitlines()[:8]) + ("\n  ..." if len(dirty.splitlines()) > 8 else ""))
    if args.author == "researcher" and not (args.session and args.hypothesis):
        raise SystemExit(
            "researcher runs must name SESSION=<role>-<YYYYMMDD>-<n> and HYPOTHESIS=<H### from "
            "hypotheses/ledger.csv>; both are logged to runs/runs.csv"
        )
    try:
        seeds = tuple(int(x) for x in args.seeds.split(",") if x.strip())
        if not seeds:
            raise SystemExit("--seeds must name at least one seed")
        run_backtest(args.model, seeds, args.author, args.folds, args.parent or None,
                     args.session, args.hypothesis, args.dataset, max(1, args.jobs), args.bag_seeds == "on")
    except SystemExit:
        raise
    except Exception as exc:  # log the failure rather than losing it
        run_id = next_run_id()
        append_run(
            {
                "run_id": run_id,
                "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "git_commit": git_commit(),
                "model_name": args.model,
                "config_hash": "",
                "fold_count": 0,
                "fold_spacing": FOLD_SPACING,
                "seconds": "0.0",
                "status": "error",
                "findings_file": f"findings/{run_id}.md",
                "author": args.author,
                "verdict": "discarded" if args.parent else "no_parent",
                "session": args.session,
                "hypothesis_id": args.hypothesis,
                "dataset": args.dataset,
                "bagged": args.bag_seeds == "on",
            }
        )
        print(f"run failed, logged {run_id} with status=error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
