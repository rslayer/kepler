"""Produce a forecast with the champion model (the serving plane).

    python -m src.forecast --dataset <id> --asof <YYYY-MM-DD> [--horizon 28] [--seed 42]

Fits the champion on data strictly before ASOF and writes
  forecasts/<dataset>/<asof>/forecast.parquet   series_id, date, horizon, yhat
  forecasts/<dataset>/<asof>/forecast.json      provenance
ASOF may be any snapshot day with enough history, or the day after the snapshot's last
day (a true-future forecast). Refuses a later ASOF and refuses a dirty working tree.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .backtest import config_hash, git_commit
from .data import DEFAULT_DATASET, ROOT, load_dataset
from .features import FEATURE_COLUMNS, HORIZON, Panel
from .model import get_model

CHAMPION = ROOT / "champion.json"
FORECASTS = ROOT / "forecasts"


def champion_for(dataset: str) -> dict:
    champions = json.loads(CHAMPION.read_text())
    if dataset not in champions:
        raise SystemExit(f"no champion for {dataset} in champion.json")
    return champions[dataset]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", default=DEFAULT_DATASET)
    ap.add_argument("--asof", required=True)
    ap.add_argument("--horizon", type=int, default=HORIZON)
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args(argv)

    dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    if dirty:
        raise SystemExit("working tree is dirty; commit or stash before forecasting (provenance must be exact)")

    champ = champion_for(a.dataset)
    ds = load_dataset(a.dataset)
    panel = Panel(ds)
    asof = pd.Timestamp(a.asof)
    latest_allowed = panel.last_date + pd.Timedelta(days=1)
    if asof > latest_allowed:
        raise SystemExit(f"ASOF {asof.date()} is after the latest allowed {latest_allowed.date()} "
                         f"(the day after the snapshot's last day); the engine has no features for that future")
    if asof < panel.dates[0] + pd.Timedelta(days=60):
        raise SystemExit("ASOF too early: not enough history for the champion's training origins")

    started = time.time()
    model = get_model(champ["model_name"])
    pred = model.forecast(panel, asof, a.horizon, a.seed)
    seconds = time.time() - started

    out_dir = FORECASTS / a.dataset / asof.strftime("%Y-%m-%d")
    out_dir.mkdir(parents=True, exist_ok=True)
    fc = pred.rename(columns={"id": "series_id", "forecast": "yhat"}).copy()
    fc["horizon"] = ((fc["date"] - asof).dt.days + 1).astype("int16")
    fc = fc[["series_id", "date", "horizon", "yhat"]].sort_values(["series_id", "date"]).reset_index(drop=True)
    fc.to_parquet(out_dir / "forecast.parquet", index=False)
    manifest = {
        "dataset": a.dataset, "asof": asof.strftime("%Y-%m-%d"), "horizon": a.horizon, "seed": a.seed,
        "champion_tag": champ["git_tag"], "model_name": champ["model_name"],
        "champion_backtest_run": champ["backtest_run"], "config_hash": config_hash({"model": model.config(), "seed": a.seed}),
        "git_commit": git_commit(), "features": list(FEATURE_COLUMNS),
        "snapshot_manifest": (ROOT / "data" / a.dataset / "snapshot" / "MANIFEST.txt").read_text().split(),
        "n_series": int(fc["series_id"].nunique()), "rows": int(len(fc)),
        "seconds": round(seconds, 1), "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    (out_dir / "forecast.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"forecast {a.dataset} asof={asof.date()} champion={champ['model_name']} ({champ['git_tag']}): "
          f"{manifest['n_series']} series x {a.horizon} days -> {out_dir.relative_to(ROOT)}/  [{seconds:.1f}s]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
