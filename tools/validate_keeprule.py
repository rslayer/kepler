"""Validate the v6 keep rule (SPEC_v6 Part C).

Read-only: re-evaluates recorded runs against the current keep_rule by reading their
detail JSONs and runs.csv rows. Writes nothing to runs/ (no fabricated rows in the
canonical ledger; that is why this is a script, not a --reparent that would append). Also
constructs one synthetic POSITIVE CONTROL — a uniform improvement over a real baseline — and
asserts the rule keeps it, proving the gate can still say yes.

    uv run -- python tools/validate_keeprule.py

Exit 1 if any known-bad flips to kept, or the positive control is not kept.
"""
from __future__ import annotations
import csv, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src import backtest as bt  # noqa: E402

RUNS = {r["run_id"]: r for r in csv.DictReader((ROOT / "runs" / "runs.csv").open())}


def detail(rid: str) -> dict:
    return json.loads((ROOT / "runs" / "detail" / f"{rid}.json").read_text())


def child_row(rid: str) -> dict:
    r = {c: "" for c in bt.RUN_COLUMNS}
    r.update(RUNS[rid])
    return r


def deciding(kr: dict) -> str:
    names = {"paired_gain": "1 gain/SE", "no_fold_regresses": "2 fold-regress",
             "bias_guardrail": "3 bias", "median_gain": "4 median"}
    failed = [names[k] for k in names if isinstance(kr.get(k), dict) and not kr[k]["pass"]]
    return "kept" if kr["verdict"] == "kept" else "discarded on " + ", ".join(failed)


# (child, parent, metric, must_stay_discarded)
CORPUS = [
    ("r115", "r114", "wrmsse_hier", True),   # recipe vs baseline (m5_3)
    ("r119", "r115", "wrmsse_hier", True),   # per-store vs recipe (m5_3)
    ("r117", "r115", "wrmsse_hier", True),   # correction ON vs OFF
    ("r109", "r107", "wrmsse_hier", True),   # ratio target
    ("r113", "r107", "wrmsse_hier", True),   # store x dept calibration
    ("r120", "r118", "wrmsse_hier", True),   # per-store on m5_all
]


def main() -> int:
    problems = []
    print("== corpus re-evaluation (recorded verdict -> v6 verdict) ==")
    for child, parent, metric, must_discard in CORPUS:
        old = detail(child).get("keep_rule", {}).get("verdict", "?")
        kr = bt.keep_rule(child_row(child), detail(child)["folds"], detail(parent), metric)
        pg = kr["paired_gain"]; mg = kr["median_gain"]
        print(f"  {child} vs {parent}: recorded={old:9s} -> v6={kr['verdict']:9s}  "
              f"[{deciding(kr)}]  gain={pg['gain']:+.4f} se={pg['se']:.4f} median={mg['median_gain']:+.4f}")
        if must_discard and kr["verdict"] == "kept":
            problems.append(f"{child} flipped to kept (was to stay discarded)")

    print("\n== positive control (uniform +0.010 improvement over r114 baseline) ==")
    par = detail("r114")
    delta = 0.010
    folds = [{**f, "wrmsse_hier": f["wrmsse_hier"] - delta} for f in par["folds"]]
    row = child_row("r114")  # copy the baseline row shape
    row["wrmsse_hier"] = f"{float(RUNS['r114']['wrmsse_hier']) - delta:.6f}"
    row["wrmsse_hier_spread"] = RUNS["r114"]["wrmsse_hier_spread"]
    row["bias"] = RUNS["r114"]["bias"]; row["bagged"] = "True"
    kr = bt.keep_rule(row, folds, par, "wrmsse_hier")
    pg = kr["paired_gain"]; mg = kr["median_gain"]
    print(f"  synthetic vs r114: v6={kr['verdict']}  gain={pg['gain']:+.4f} se={pg['se']:.4f} "
          f"median={mg['median_gain']:+.4f}  c1={pg['pass']} c2={kr['no_fold_regresses']['pass']} "
          f"c3={kr['bias_guardrail']['pass']} c4={mg['pass']}")
    if kr["verdict"] != "kept":
        problems.append("positive control was not kept — the rule cannot say yes")

    print()
    if problems:
        for p in problems:
            print("  FAIL:", p)
        return 1
    print("OK: every known-bad stays discarded; the positive control is kept.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
