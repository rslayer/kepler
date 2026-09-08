"""Aggregates runs/runs.csv. FROZEN — never edited by any agent.

    python -m src.report              table of all runs sorted by WRMSSE
    python -m src.report --run <id>   error breakdown for one run
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RUNS_CSV = ROOT / "runs" / "runs.csv"
DETAIL_DIR = ROOT / "runs" / "detail"


def load_runs() -> pd.DataFrame:
    if not RUNS_CSV.exists():
        raise SystemExit(f"no run log at {RUNS_CSV}")
    runs = pd.read_csv(RUNS_CSV)
    if runs.empty:
        raise SystemExit("run log is empty - nothing to report")
    return runs


def table() -> None:
    runs = load_runs()
    cols = [
        "run_id", "model_name", "author", "status", "fold_count",
        "wrmsse", "wape", "bias", "wape_h1_7", "wape_h8_14", "wape_h15_28",
        "seconds", "git_commit",
    ]
    view = runs[[c for c in cols if c in runs.columns]].copy()
    view = view.sort_values("wrmsse", na_position="last", kind="mergesort")
    with pd.option_context("display.width", 200, "display.max_columns", 50):
        print(view.to_string(index=False))
    ok = runs[runs["status"] == "ok"]
    if not ok.empty:
        best = ok.loc[ok["wrmsse"].idxmin()]
        print(f"\nbest: {best['run_id']} ({best['model_name']}) WRMSSE={best['wrmsse']}")


def breakdown(run_id: str) -> None:
    path = DETAIL_DIR / f"{run_id}.json"
    if not path.exists():
        raise SystemExit(f"no detail for {run_id} at {path}")
    detail = json.loads(path.read_text())

    print(f"run {run_id}  model={detail['model_name']}  status={detail['status']}  "
          f"seed={detail['seed']}  author={detail['author']}\n")

    folds = pd.DataFrame(detail["folds"])
    fold_cols = ["fold", "origin", "wrmsse", "wape", "bias",
                 "wape_h1_7", "wape_h8_14", "wape_h15_28", "n_scored"]
    print("per fold")
    print(folds[[c for c in fold_cols if c in folds.columns]].to_string(index=False, float_format="%.6f"))

    print("\nhorizon buckets (mean WAPE across folds)")
    for bucket in ("wape_h1_7", "wape_h8_14", "wape_h15_28"):
        print(f"  {bucket:<12} {folds[bucket].mean():.6f}")

    series = pd.DataFrame(detail["per_series"])
    if series.empty:
        return
    id_col = series.columns[0]
    series = series.sort_values("contrib", ascending=False)
    total = series["contrib"].sum()
    top5pct = max(1, int(round(0.05 * len(series))))
    by_volume = series.sort_values("actual", ascending=False)
    share = by_volume.head(top5pct)["contrib"].sum() / total if total > 0 else float("nan")

    print(f"\nWRMSSE concentration: top {top5pct} series by volume "
          f"({top5pct / len(series):.1%} of series) carry {share:.1%} of WRMSSE")
    print("\ntop 10 series by WRMSSE contribution")
    view = series.head(10)[[id_col, "contrib", "rmsse", "weight_norm", "actual", "abs_err"]]
    print(view.to_string(index=False, float_format="%.6f"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", help="run_id to break down")
    args = parser.parse_args(argv)
    if args.run:
        breakdown(args.run)
    else:
        table()
    return 0


if __name__ == "__main__":
    sys.exit(main())
