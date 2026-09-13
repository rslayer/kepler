"""Score past forecasts against actuals that have since arrived: the live scoreboard.

    python -m src.evaluate --dataset <id>

For every forecasts/<dataset>/<asof>/ whose horizon is fully covered by the agent-visible
snapshot, scores it with the FROZEN scorer and appends to runs/live.csv. Idempotent: an
(asof, champion_tag) pair is scored once. Uses only the visible snapshot; never holdout/.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone

import pandas as pd

from .data import DEFAULT_DATASET, ROOT, load_dataset
from .scorer import score_window
from .scoring import scorer_frames

FORECASTS = ROOT / "forecasts"
LIVE = ROOT / "runs" / "live.csv"
LIVE_COLUMNS = ["dataset", "asof", "champion_tag", "model_name", "wrmsse", "wape", "bias",
                "wape_h1_7", "wape_h8_14", "wape_h15_28", "n_series", "scored_at"]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", default=DEFAULT_DATASET)
    a = ap.parse_args(argv)

    done = set()
    if LIVE.exists():
        done = {(r["dataset"], r["asof"], r["champion_tag"]) for r in csv.DictReader(LIVE.open())}
    root = FORECASTS / a.dataset
    if not root.exists():
        print(f"no forecasts under {root.relative_to(ROOT)}"); return 0

    ds = None
    new_rows = []
    for d in sorted(root.iterdir()):
        mf = d / "forecast.json"
        if not mf.exists():
            continue
        m = json.loads(mf.read_text())
        key = (a.dataset, m["asof"], m["champion_tag"])
        if key in done:
            continue
        if ds is None:
            ds = load_dataset(a.dataset)
        asof = pd.Timestamp(m["asof"]); end = asof + pd.Timedelta(days=m["horizon"] - 1)
        if end > ds.last_date:
            print(f"  {m['asof']}: actuals not complete yet (needs through {end.date()}), skipping")
            continue
        fc = pd.read_parquet(d / "forecast.parquet").rename(columns={"series_id": "id", "yhat": "forecast"})
        sales, calendar, prices = scorer_frames(ds, asof)
        truth = sales[(sales["date"] >= asof) & (sales["date"] <= end)][["id", "date", "sales"]]
        metrics, _ = score_window(truth, fc[["id", "date", "forecast"]], sales[sales["date"] < asof], prices, calendar)
        row = {"dataset": a.dataset, "asof": m["asof"], "champion_tag": m["champion_tag"], "model_name": m["model_name"],
               **{k: f"{metrics[k]:.6f}" for k in ("wrmsse", "wape", "bias", "wape_h1_7", "wape_h8_14", "wape_h15_28")},
               "n_series": metrics["n_series"], "scored_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        new_rows.append(row)
        print(f"  {m['asof']} {m['model_name']} ({m['champion_tag']}): WRMSSE={row['wrmsse']} WAPE={row['wape']} bias={row['bias']}")

    if new_rows:
        exists = LIVE.exists() and LIVE.stat().st_size > 0
        with LIVE.open("a", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=LIVE_COLUMNS)
            if not exists:
                w.writeheader()
            w.writerows(new_rows)
    print(f"scored {len(new_rows)} new forecast(s); runs/live.csv now has {len(done) + len(new_rows)} row(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
