#!/usr/bin/env python
"""Bounded parameterized self-improvement loop for kepler (v9 proxy).

Each cycle: take the next config from the search space -> write it to $KEPLER_SEARCH_CONFIG ->
run the `recipe_search` model on the m5_screen year-round proxy (the run computes the v6.1 keep
rule vs the baseline) -> read the detail and apply the SPRING-FOLD GATE (the hist3y lesson:
aggregate gain is not enough; a config must not regress the two spring folds that mirror the
holdout) -> log to the search ledger and commit. The holdout is never touched; promotion to a
yardstick shot stays a human decision. Bounded by --max-cycles and --max-hours.

Usage: python tools/search_loop.py --space tools/search_space.json --baseline r134 \
                                   --parent r134 --max-cycles 6 --max-hours 8
"""
from __future__ import annotations
import argparse, csv, json, os, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPRING_ORIGINS = ["2015-03-30", "2016-03-28"]  # v9 folds whose windows mirror the spring holdout
SEARCH_CFG = ROOT / "runs" / "search"
LEDGER = ROOT / "hypotheses" / "m5_screen" / "search_ledger.csv"


def sh(cmd, **kw):
    return subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, **kw)


def clean_tree() -> bool:
    return sh(["git", "status", "--porcelain"]).stdout.strip() == ""


def commit(msg: str):
    sh(["git", "add", "-A"]); sh(["git", "commit", "-q", "-m", msg])


def detail(run_id: str) -> dict:
    return json.load(open(ROOT / "runs" / "detail" / f"{run_id}.json"))


def fold_map(d: dict) -> dict:
    return {f["origin"]: float(f["wrmsse_hier"]) for f in d["folds"]}


def headline(d: dict) -> float:
    ba = d.get("bagged_aggregate")
    return float(ba["wrmsse_hier"]) if ba else float("nan")


def newest_run_id() -> str:
    with open(ROOT / "runs" / "runs.csv") as f:
        return list(csv.reader(f))[-1][0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--space", required=True)
    ap.add_argument("--baseline", required=True, help="run id whose fold scores define the gate")
    ap.add_argument("--parent", required=True, help="parent run id for the harness keep rule")
    ap.add_argument("--max-cycles", type=int, default=6)
    ap.add_argument("--max-hours", type=float, default=8.0)
    ap.add_argument("--spring-eps", type=float, default=0.002, help="allowed spring regression before FAIL")
    args = ap.parse_args()

    SEARCH_CFG.mkdir(parents=True, exist_ok=True)
    base = fold_map(detail(args.baseline))
    base_spring = sum(base[o] for o in SPRING_ORIGINS) / len(SPRING_ORIGINS)
    base_hd = headline(detail(args.baseline))
    space = json.load(open(args.space))
    configs = space["configs"][: args.max_cycles]

    if not LEDGER.exists():
        with open(LEDGER, "w") as f:
            csv.writer(f).writerow(["cycle", "run_id", "label", "agg_hier", "agg_gain",
                                    "spring_gain", "keep_verdict", "spring_gate", "config"])

    start = time.time()
    board = []
    for i, cfg in enumerate(configs, 1):
        if (time.time() - start) / 3600 > args.max_hours:
            print(f"[loop] max-hours reached; stopping before cycle {i}"); break
        label = cfg.get("label", f"cfg{i}")
        if not clean_tree():
            commit(f"loop: wip before cycle {i} ({label})")
        cfg_path = SEARCH_CFG / f"cfg_c{i:02d}.json"
        cfg_path.write_text(json.dumps(cfg, indent=2))
        commit(f"loop c{i}: config {label}")  # clean tree before backtest

        print(f"\n[loop] cycle {i}/{len(configs)}: {label}")
        env = {**os.environ, "KEPLER_SEARCH_CONFIG": str(cfg_path), "UV_SYSTEM_CERTS": "1"}
        r = subprocess.run(
            ["/usr/bin/caffeinate", "-i", "uv", "run", "--", "python", "-m", "src.backtest",
             "--model", "recipe_search", "--dataset", "m5_screen", "--seeds", "42,7,123",
             "--jobs", "1", "--bag-seeds", "on", "--author", "researcher",
             "--parent", args.parent, "--session", "loop-20260918-1", "--hypothesis", space["hypothesis"]],
            cwd=ROOT, env=env, text=True)
        if r.returncode != 0:
            print(f"[loop] cycle {i} backtest FAILED (rc={r.returncode}); skipping"); continue

        rid = newest_run_id()
        d = detail(rid)
        fm = fold_map(d)
        agg = headline(d)
        agg_gain = base_hd - agg
        spring = sum(fm[o] for o in SPRING_ORIGINS) / len(SPRING_ORIGINS)
        spring_gain = base_spring - spring
        kv = (d.get("keep_rule") or {}).get("verdict", "?")
        gate = "PASS" if (agg_gain > 0 and spring_gain >= -args.spring_eps) else "FAIL"
        with open(LEDGER, "a") as f:
            csv.writer(f).writerow([i, rid, label, f"{agg:.6f}", f"{agg_gain:+.6f}",
                                    f"{spring_gain:+.6f}", kv, gate, json.dumps(cfg)])
        commit(f"loop c{i} {rid}: {label} agg{agg_gain:+.4f} spring{spring_gain:+.4f} gate={gate} keep={kv}")
        board.append((rid, label, agg, agg_gain, spring_gain, kv, gate))
        print(f"[loop] {rid} {label}: hier {agg:.4f} agg{agg_gain:+.4f} spring{spring_gain:+.4f} gate={gate} keep={kv}")

    print("\n===== SEARCH LEADERBOARD (spring-gated) =====")
    print(f"baseline {args.baseline}: hier {base_hd:.4f} spring {base_spring:.4f}")
    for rid, label, agg, ag, sg, kv, gate in sorted(board, key=lambda x: x[2]):
        star = " <<< spring-gate PASS" if gate == "PASS" else ""
        print(f"  {rid} {label:28} hier {agg:.4f}  agg{ag:+.4f}  spring{sg:+.4f}  keep={kv:9} gate={gate}{star}")
    print("\nholdout was NOT touched. Promotion to a yardstick shot remains a human decision.")


if __name__ == "__main__":
    main()
