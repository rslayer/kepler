"""Cost per researcher run, from runs/sessions.csv (written by tools/cycle.sh) and runs/runs.csv.

    python tools/cost_report.py [session_id]
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str]) -> int:
    sp = ROOT / "runs" / "sessions.csv"
    if not sp.exists():
        print("no runs/sessions.csv yet (written by tools/cycle.sh)"); return 0
    sessions = list(csv.DictReader(sp.open()))
    runs = list(csv.DictReader((ROOT / "runs" / "runs.csv").open()))
    want = argv[1] if len(argv) > 1 else None
    print(f"{'session':28} {'role':10} {'minutes':>8} {'in_tok':>9} {'out_tok':>8} {'cost_usd':>9} {'runs':>5} {'usd/run':>8}")
    for s in sessions:
        if want and s["session"] != want and not s["session"].endswith(want.split("-", 1)[1]):
            continue
        n = sum(1 for r in runs if r.get("session") == s["session"] and r.get("author") == "researcher")
        try:
            from datetime import datetime
            mins = (datetime.fromisoformat(s["ended"].replace("Z", "+00:00")) - datetime.fromisoformat(s["started"].replace("Z", "+00:00"))).total_seconds() / 60
        except Exception:
            mins = float("nan")
        cost = float(s["cost_usd"]) if s["cost_usd"] else float("nan")
        per = cost / n if n else float("nan")
        print(f"{s['session']:28} {s['role']:10} {mins:8.1f} {s['input_tokens']:>9} {s['output_tokens']:>8} {cost:9.2f} {n:5d} {per:8.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
