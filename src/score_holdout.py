"""HUMAN ONLY: one-shot scoring of a model against holdout/. FROZEN.

    python -m src.score_holdout --model <name>

Fits on the entire agent-visible snapshot and forecasts the 28 held-out days once.
Appends to runs/holdout.csv. Refuses to score the same model twice - the holdout is a
gate, not a tuning signal.
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime, timezone

import pandas as pd

from .backtest import RUNS_CSV, config_hash, git_commit  # noqa: F401
from .data import HOLDOUT, ROOT, load_snapshot, verify_manifest
from .features import HORIZON, Panel
from .model import get_model
from .scorer import score_window

HOLDOUT_CSV = ROOT / "runs" / "holdout.csv"
HOLDOUT_COLUMNS = [
    "timestamp", "git_commit", "model_name", "config_hash",
    "wrmsse", "wape", "bias", "wape_h1_7", "wape_h8_14", "wape_h15_28", "seconds",
]


def already_scored(model_name: str) -> bool:
    if not HOLDOUT_CSV.exists():
        return False
    with HOLDOUT_CSV.open() as fh:
        return any(row["model_name"] == model_name for row in csv.DictReader(fh))


def main(argv: list[str] | None = None) -> int:
    import time

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--force", action="store_true", help="re-score an already-scored model")
    args = parser.parse_args(argv)

    if not (HOLDOUT / "sales.parquet").exists():
        raise SystemExit("no holdout/. Run `make holdout` first.")
    if already_scored(args.model) and not args.force:
        raise SystemExit(
            f"'{args.model}' has already been scored on the holdout. One shot per candidate - "
            "that is the point of the gate. Use --force only if you know why."
        )
    verify_manifest(HOLDOUT, ("sales.parquet",))

    sales, calendar, prices = load_snapshot()
    held = pd.read_parquet(HOLDOUT / "sales.parquet")
    panel = Panel(pd.concat([sales, held], ignore_index=True), calendar, prices)
    origin = pd.Timestamp(sorted(held["date"].unique())[0])

    started = time.time()
    model = get_model(args.model)
    pred = model.forecast(panel, origin, HORIZON, args.seed)
    metrics, _ = score_window(held[["id", "date", "sales"]], pred, sales, prices, calendar)
    seconds = time.time() - started

    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_commit": git_commit(),
        "model_name": args.model,
        "config_hash": config_hash({"model": model.config(), "seed": args.seed}),
        "seconds": f"{seconds:.1f}",
        **{k: f"{metrics[k]:.6f}" for k in
           ("wrmsse", "wape", "bias", "wape_h1_7", "wape_h8_14", "wape_h15_28")},
    }
    exists = HOLDOUT_CSV.exists() and HOLDOUT_CSV.stat().st_size > 0
    with HOLDOUT_CSV.open("a", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=HOLDOUT_COLUMNS)
        if not exists:
            writer.writeheader()
        writer.writerow({k: row.get(k, "") for k in HOLDOUT_COLUMNS})

    print(f"holdout {args.model}: WRMSSE={row['wrmsse']} WAPE={row['wape']} bias={row['bias']}")
    print(f"appended to runs/holdout.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
