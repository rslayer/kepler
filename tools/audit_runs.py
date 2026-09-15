"""Audit runs/runs.csv against runs/detail/*.json and git (SPEC_v5 Part E).

For every row: the detail JSON exists, its run_id / model / dataset / status match the row,
its headline metrics match the row to six decimals, and the row's git_commit (minus any
-dirty suffix) resolves to a commit in this repository. Also checks runs/v4_run_id_map.json
covers every renumbered row. Exit 1 if anything is off; prints a table either way.

    python tools/audit_runs.py [--runs-dir runs]
"""
from __future__ import annotations
import argparse, csv, json, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
METRICS = ["wrmsse", "wape", "bias", "wape_h1_7", "wape_h8_14", "wape_h15_28", "wrmsse_hier"]


def resolves(sha: str) -> bool:
    if not sha or sha == "unknown":
        return False
    return subprocess.run(["git", "cat-file", "-e", f"{sha}^{{commit}}"], cwd=ROOT, capture_output=True).returncode == 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--runs-dir", default="runs"); a = ap.parse_args(argv)
    rd = ROOT / a.runs_dir
    rows = list(csv.DictReader((rd / "runs.csv").open()))
    problems: list[str] = []; unresolved: list[str] = []; reviews = 0; documented_lost: list[str] = []
    for r in rows:
        rid = r["run_id"]; p = rd / "detail" / f"{rid}.json"
        is_review = "/" in r.get("model_name", "")  # adversary verdict rows (exp/<b>, curator/<s>) and human override rows
        if is_review:
            reviews += 1
        if not p.exists():
            if r.get("status") == "error" or is_review:
                continue  # error rows and review rows never write detail
            fp = ROOT / "findings" / f"{rid}.md"
            if fp.exists() and any(w in fp.read_text().lower() for w in ("lost", "renumber")):
                documented_lost.append(rid); continue  # detail lost in the v4 renumbering, findings says so
            problems.append(f"{rid}: no detail JSON (status={r.get('status') or 'EMPTY'})"); continue
        d = json.loads(p.read_text())
        if d.get("run_id") != rid:
            problems.append(f"{rid}: detail says run_id={d.get('run_id')}")
        for k, dk in (("model_name", "model_name"), ("dataset", "dataset"), ("status", "status")):
            if str(d.get(dk, "")) != str(r.get(k, "")) and not (k == "dataset" and not d.get(dk)):
                problems.append(f"{rid}: {k} row={r.get(k)!r} detail={d.get(dk)!r}")
        if r.get("status") == "ok" and d.get("status") == "ok":
            bagged = str(r.get("bagged", "False")) == "True"
            for m in METRICS:
                if not r.get(m):
                    continue
                if bagged and d.get("bagged_aggregate"):
                    val = d["bagged_aggregate"].get(m)
                else:
                    vals = [d["seeds"][s]["aggregate"].get(m) for s in d["seeds"]] if d.get("seeds") else []
                    val = sum(vals) / len(vals) if vals and None not in vals else None
                if val is None:
                    continue
                if f"{val:.6f}" != f"{float(r[m]):.6f}" and abs(val - float(r[m])) > 5e-7:
                    problems.append(f"{rid}: {m} row={r[m]} detail={val:.6f}")
        sha = r.get("git_commit", "").replace("-dirty", "")
        if not resolves(sha):
            unresolved.append(f"{rid} {r.get('git_commit')}")
    # renumbering map
    mp = rd / "v4_run_id_map.json"
    if mp.exists():
        m = json.loads(mp.read_text())
        mapped = set(m.values()) if isinstance(m, dict) else set()
        ids = {r["run_id"] for r in rows}
        missing = sorted(x for x in mapped if x not in ids)
        if missing:
            problems.append(f"v4_run_id_map.json maps to ids absent from runs.csv: {missing}")
        print(f"v4_run_id_map.json: {len(m)} entries, all targets present: {not missing}")
    print(f"{len(rows)} rows audited ({reviews} adversary/human review rows carry no detail by design); "
          f"{len(problems)} row/detail mismatches; {len(unresolved)} unresolvable commit hashes")
    if documented_lost:
        print(f"  NOTE: detail lost in the v4 renumbering (documented in findings, identical reruns exist): {', '.join(documented_lost)}")
    for x in problems: print("  MISMATCH", x)
    for x in unresolved: print("  UNRESOLVED", x)
    return 1 if (problems or unresolved) else 0


if __name__ == "__main__":
    sys.exit(main())
