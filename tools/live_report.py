"""Live scoreboard: does the backtest predict reality?

    python tools/live_report.py [--dataset m5_ca1]

Prints runs/live.csv grouped by champion version (mean, spread, n of live WRMSSE) with the
champion's backtest WRMSSE from champion.json beside it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", default="m5_ca1")
    a = ap.parse_args(argv[1:])
    live = ROOT / "runs" / "live.csv"
    if not live.exists():
        print("no runs/live.csv yet - run `make forecast` then `make evaluate`"); return 0
    df = pd.read_csv(live)
    df = df[df["dataset"] == a.dataset]
    if df.empty:
        print(f"no live rows for {a.dataset}"); return 0
    champions = json.loads((ROOT / "champion.json").read_text())
    backtest = {}
    c = champions.get(a.dataset)
    while c:
        backtest[c["git_tag"]] = c["backtest_wrmsse"]; c = c.get("previous")
    print(f"live scoreboard - {a.dataset}\n")
    print(df[["asof", "champion_tag", "model_name", "wrmsse", "wape", "bias"]].to_string(index=False))
    print()
    g = df.groupby(["champion_tag", "model_name"])["wrmsse"].agg(["count", "mean", "min", "max"]).reset_index()
    g["spread"] = g["max"] - g["min"]
    g["backtest_wrmsse"] = g["champion_tag"].map(backtest)
    g["live_minus_backtest"] = g["mean"] - g["backtest_wrmsse"]
    print(g[["champion_tag", "model_name", "count", "mean", "spread", "backtest_wrmsse", "live_minus_backtest"]]
          .rename(columns={"count": "n", "mean": "live_mean"}).to_string(index=False, float_format=lambda x: f"{x:.6f}"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
