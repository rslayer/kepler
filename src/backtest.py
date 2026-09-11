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
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from . import scorer
from .data import ROOT, load_snapshot
from .features import HORIZON, Panel
from .model import get_model

# KEPLER_RUNS_DIR redirects the run log + detail output (used by the adversary to rerun a
# branch's model without appending to the canonical, append-only runs/runs.csv).
_RUNS_DIR = Path(os.environ["KEPLER_RUNS_DIR"]) if os.environ.get("KEPLER_RUNS_DIR") else ROOT / "runs"
RUNS_CSV = _RUNS_DIR / "runs.csv"
DETAIL_DIR = _RUNS_DIR / "detail"
FINDINGS_DIR = ROOT / "findings"

N_FOLDS = 4
TIMEOUT_SECONDS = 20 * 60

RUN_COLUMNS = [
    "run_id", "timestamp", "git_commit", "model_name", "config_hash", "fold_count",
    "wrmsse", "wape", "bias", "wape_h1_7", "wape_h8_14", "wape_h15_28",
    "seconds", "status", "findings_file", "author",
]


# --------------------------------------------------------------------------- fold logic
def make_folds(panel: Panel, n_folds: int = N_FOLDS, horizon: int = HORIZON) -> list[pd.Timestamp]:
    """Origins of each fold, oldest first. The last fold ends on the snapshot's last day."""
    n_days = len(panel.dates)
    needed = n_folds * horizon
    if n_days < needed + horizon:
        raise SystemExit(f"snapshot has {n_days} days; need at least {needed + horizon}")
    origins = []
    for f in range(n_folds):
        end_pos = n_days - 1 - (n_folds - 1 - f) * horizon
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


# ------------------------------------------------------------------------------- driver
def run_backtest(
    model_name: str, seed: int = 42, author: str = "human", n_folds: int = N_FOLDS
) -> dict:
    sales, calendar, prices = load_snapshot()
    panel = Panel(sales, calendar, prices)
    model = get_model(model_name)
    origins = make_folds(panel, n_folds)

    print(f"model={model_name} seed={seed} author={author}")
    print(f"snapshot: {len(panel.ids)} series, {len(panel.dates)} days, last {panel.last_date.date()}")
    print("fold origins: " + ", ".join(str(pd.Timestamp(o).date()) for o in origins))

    started = time.time()
    fold_metrics: list[dict] = []
    per_series: list[pd.DataFrame] = []
    status = "ok"

    for i, origin in enumerate(origins, start=1):
        window_end = origin + pd.Timedelta(days=HORIZON - 1)
        truth = sales[(sales["date"] >= origin) & (sales["date"] <= window_end)]
        train_long = sales[sales["date"] < origin]

        pred = model.forecast(panel, origin, HORIZON, seed)
        if (pred["date"] < origin).any() or (pred["date"] > window_end).any():
            raise SystemExit(f"model returned dates outside fold {i}'s window")

        metrics, detail = scorer.score_window(
            truth[["id", "date", "sales"]], pred, train_long, prices, calendar
        )
        metrics["fold"] = i
        metrics["origin"] = str(pd.Timestamp(origin).date())
        fold_metrics.append(metrics)
        per_series.append(detail.assign(fold=i))

        elapsed = time.time() - started
        print(
            f"  fold {i} origin={pd.Timestamp(origin).date()} "
            f"wrmsse={metrics['wrmsse']:.6f} wape={metrics['wape']:.6f} "
            f"bias={metrics['bias']:+.6f}  [{elapsed:.1f}s]"
        )
        if elapsed > TIMEOUT_SECONDS:
            status = "timeout"
            print(f"  exceeded {TIMEOUT_SECONDS}s budget - marking run as timeout")
            break

    seconds = time.time() - started
    run_id = next_run_id()
    row = {
        "run_id": run_id,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_commit": git_commit(),
        "model_name": model_name,
        "config_hash": config_hash({"model": model.config(), "seed": seed, "folds": n_folds}),
        "fold_count": len(fold_metrics),
        "seconds": f"{seconds:.1f}",
        "status": status,
        "findings_file": f"findings/{run_id}.md",
        "author": author,
    }
    if status == "ok":
        row.update({k: f"{v:.6f}" for k, v in scorer.aggregate_folds(fold_metrics).items()})

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
                "seed": seed,
                "author": author,
                "status": status,
                "config": model.config(),
                "folds": fold_metrics,
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
            f"  WRMSSE={row['wrmsse']}  WAPE={row['wape']}  bias={row['bias']}\n"
            f"  WAPE h1-7={row['wape_h1_7']} h8-14={row['wape_h8_14']} h15-28={row['wape_h15_28']}"
        )
    print(f"  detail: runs/detail/{run_id}.json   findings: {row['findings_file']}")
    return row


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Rolling-origin backtest")
    parser.add_argument("--model", required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--author", default="human", choices=["human", "researcher", "adversary"])
    parser.add_argument("--folds", type=int, default=N_FOLDS)
    args = parser.parse_args(argv)
    try:
        run_backtest(args.model, args.seed, args.author, args.folds)
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
                "seconds": "0.0",
                "status": "error",
                "findings_file": f"findings/{run_id}.md",
                "author": args.author,
            }
        )
        print(f"run failed, logged {run_id} with status=error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
