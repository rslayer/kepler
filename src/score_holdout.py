"""HUMAN ONLY: one-shot scoring of a model against holdout/<dataset>/.

    python -m src.score_holdout --model <name> [--dataset <id>]

Fits on the entire agent-visible snapshot and forecasts the held-out days once.
Appends to runs/holdout.csv. Refuses to score the same (dataset, model) twice - the
holdout is a gate, not a tuning signal.
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from datetime import datetime, timezone

import pandas as pd

from .adapters import get_adapter
from .backtest import config_hash, git_commit
from .scoring import scorer_frames
from .data import DEFAULT_DATASET, ROOT, load_dataset
from .features import HORIZON, Panel
from .model import get_model
from .scorer import score_window

HOLDOUT_CSV = ROOT / "runs" / "holdout.csv"
HOLDOUT_COLUMNS = [
    "timestamp", "git_commit", "dataset", "model_name", "config_hash",
    "wrmsse", "wape", "bias", "wape_h1_7", "wape_h8_14", "wape_h15_28", "seconds",
]


def already_scored(dataset: str, model_name: str) -> bool:
    if not HOLDOUT_CSV.exists():
        return False
    with HOLDOUT_CSV.open() as fh:
        return any(r["model_name"] == model_name and r.get("dataset", DEFAULT_DATASET) == dataset
                   for r in csv.DictReader(fh))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--dataset", default=DEFAULT_DATASET)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--force", action="store_true", help="re-score an already-scored model")
    args = parser.parse_args(argv)

    adapter = get_adapter(args.dataset)
    if not (adapter.holdout_dir / "sales.parquet").exists():
        raise SystemExit(f"no holdout for {args.dataset}. Run `make holdout DATASET={args.dataset}` first.")
    if already_scored(args.dataset, args.model) and not args.force:
        raise SystemExit(
            f"'{args.model}' has already been scored on the {args.dataset} holdout. One shot per "
            "candidate - that is the point of the gate. Use --force only if you know why."
        )

    visible = load_dataset(args.dataset)                 # agent-visible, cut
    full = get_adapter(args.dataset).load(with_holdout=True)  # visible + held-out days
    origin = visible.last_date + pd.Timedelta(days=1)
    panel = Panel(full)
    held = full.panel[full.panel["date"] >= origin].rename(columns={"series_id": "id", "y": "sales"})
    sales, calendar, prices = scorer_frames(full, origin)

    started = time.time()
    model = get_model(args.model)
    pred = model.forecast(panel, origin, HORIZON, args.seed)
    metrics, _ = score_window(held[["id", "date", "sales"]], pred,
                              sales[sales["date"] < origin], prices, calendar)
    seconds = time.time() - started

    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_commit": git_commit(),
        "dataset": args.dataset,
        "model_name": args.model,
        "config_hash": config_hash({"model": model.config(), "seed": args.seed}),
        "seconds": f"{seconds:.1f}",
        **{k: f"{metrics[k]:.6f}" for k in ("wrmsse", "wape", "bias", "wape_h1_7", "wape_h8_14", "wape_h15_28")},
    }
    rows = []
    if HOLDOUT_CSV.exists() and HOLDOUT_CSV.stat().st_size > 0:
        with HOLDOUT_CSV.open() as fh:
            rows = [{**{"dataset": DEFAULT_DATASET}, **r} for r in csv.DictReader(fh)]
    rows.append(row)
    with HOLDOUT_CSV.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=HOLDOUT_COLUMNS)
        w.writeheader()
        w.writerows({k: r.get(k, "") for k in HOLDOUT_COLUMNS} for r in rows)
    print(f"holdout {args.dataset} {args.model}: WRMSSE={row['wrmsse']} WAPE={row['wape']} bias={row['bias']}")
    print("appended to runs/holdout.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
