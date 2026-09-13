"""Loop scorecard: is the research loop getting better session over session?

    python tools/scorecard.py

For each researcher session in runs/runs.csv prints
  session, runs, kept, keep_rate, runs_per_kept, repeats, repeat_rate, best_wrmsse, wall_minutes
and writes LOOP_SCORECARD.md (table, newest session last, plus one trend line).

Definitions
- runs: rows with author=researcher and status=ok in the session on screening datasets;
  confirm_runs are rows on confirmation datasets (tiers.json) and confirmed counts those
  that are kept where the same model was also kept on the screen in the session.
- kept: verdict=kept. v0 rows predate the verdict column; for them the findings file's
  own "Verdict: keep" line plus an existing exp/<run_id> branch is used, and rows with an
  empty session are assigned to the v0 session id below.
- repeat: the run's hypothesis_id had status `discarded` or `kept` in the ledger AS OF
  THE START OF THE SESSION, which CLAUDE.md forbids re-running. The start-of-session
  ledger is read from git: the last commit on main before the session's first logged
  timestamp. Re-running an `inconclusive` row is allowed and never counts, even if the
  session then changes its status. Sessions that predate the ledger have 0 repeats.
- wall_minutes: last logged timestamp minus first, within the session (log span).
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs" / "runs.csv"
LEDGER_DIR = ROOT / "hypotheses"  # <dataset>/ledger.csv; pre-v3 commits had hypotheses/ledger.csv
FINDINGS = ROOT / "findings"
OUT = ROOT / "LOOP_SCORECARD.md"
V0_SESSION = "researcher-20260911-1"


def v0_kept(run_id: str) -> bool:
    """v0 rows have no harness verdict: kept = findings says keep AND an exp/<run_id> branch
    exists (CLAUDE.md: every kept improvement is committed on a branch). r004 said keep but
    was a refactor with no branch, so it does not count."""
    f = FINDINGS / f"{run_id}.md"
    if not f.exists():
        return False
    m = re.search(r"\*\*Verdict:\*\*\s*(\w+)", f.read_text())
    if not (m and m.group(1).lower() == "keep"):
        return False
    r = subprocess.run(["git", "rev-parse", "--verify", "-q", f"exp/{run_id}"], cwd=ROOT, capture_output=True)
    return r.returncode == 0


def hypothesis_map(ledger: pd.DataFrame) -> dict[str, str]:
    """run_id -> hypothesis_id from the ledger's first_run/last_run (v0 fallback)."""
    out: dict[str, str] = {}
    for _, r in ledger.iterrows():
        for run in (r.get("first_run"), r.get("last_run")):
            if isinstance(run, str) and run:
                out.setdefault(run, r["hypothesis_id"])
    return out


def compute() -> pd.DataFrame:
    runs = pd.read_csv(RUNS, dtype=str).fillna("")
    res = runs[runs["author"] == "researcher"].copy()
    if res.empty:
        return pd.DataFrame()
    res["session"] = res["session"].where(res["session"] != "", V0_SESSION)
    res["dataset"] = res.get("dataset", "").replace("", "m5_ca1") if "dataset" in res else "m5_ca1"
    ledgers = {}
    for dataset in res["dataset"].unique():
        p_ = LEDGER_DIR / dataset / "ledger.csv"
        if not p_.exists():
            p_ = LEDGER_DIR / "ledger.csv"
        ledgers[dataset] = pd.read_csv(p_, dtype=str).fillna("") if p_.exists() else pd.DataFrame(columns=["hypothesis_id", "status", "first_run", "last_run", "sessions"])
    ledger = pd.concat(ledgers.values(), ignore_index=True) if ledgers else pd.DataFrame()
    res["ts"] = pd.to_datetime(res["timestamp"], utc=True, errors="coerce")
    hmap = hypothesis_map(ledger)
    res["hyp"] = [h if h else hmap.get(r, "") for h, r in zip(res["hypothesis_id"], res["run_id"])]
    res["kept_flag"] = [
        v == "kept" or (v == "" and v0_kept(r)) for v, r in zip(res["verdict"], res["run_id"])
    ]
    def ledger_status_at(first_ts: pd.Timestamp, dataset: str = "m5_ca1") -> dict[str, str]:
        """Ledger status per hypothesis as committed on main just before `first_ts`."""
        if pd.isna(first_ts):
            return {}
        before = first_ts.strftime("%Y-%m-%dT%H:%M:%S%z")
        sha = subprocess.run(["git", "rev-list", "-1", f"--before={before}", "main"],
                             cwd=ROOT, capture_output=True, text=True).stdout.strip()
        if not sha:
            return {}
        shown = None
        for rel in (f"hypotheses/{dataset}/ledger.csv", "hypotheses/ledger.csv"):
            r_ = subprocess.run(["git", "show", f"{sha}:{rel}"], cwd=ROOT, capture_output=True, text=True)
            if r_.returncode == 0:
                shown = r_; break
        if shown is None:
            return {}  # ledger did not exist yet
        import io
        old = pd.read_csv(io.StringIO(shown.stdout), dtype=str).fillna("")
        return dict(zip(old["hypothesis_id"], old["status"]))

    tiers = {}
    tp = ROOT / "tiers.json"
    if tp.exists():
        import json
        tiers = {k: v["screen"] for k, v in json.loads(tp.read_text()).get("tiers", {}).items()}
    confirm_sets = set(tiers)  # datasets that are confirmation tiers

    rows = []
    for session, g in res.groupby("session", sort=True):
        ok = g[g["status"] == "ok"]
        conf = ok[ok["dataset"].isin(confirm_sets)]
        ok = ok[~ok["dataset"].isin(confirm_sets)]  # screening runs drive the loop metrics
        n = len(ok)
        kept = int(ok["kept_flag"].sum())
        confirmed = int(sum(1 for _, r in conf.iterrows() if r["kept_flag"] and
                            ((ok["model_name"] == r["model_name"]) & ok["kept_flag"]).any()))
        status_at_start = ledger_status_at(g["ts"].min(), g["dataset"].iloc[0])
        repeats = sum(1 for h in ok["hyp"] if h and status_at_start.get(h) in ("discarded", "kept"))
        wall = (g["ts"].max() - g["ts"].min()).total_seconds() / 60 if g["ts"].notna().any() else float("nan")
        best = pd.to_numeric(ok["wrmsse"], errors="coerce").min()
        rows.append({
            "session": session, "runs": n, "kept": kept, "confirm_runs": len(conf), "confirmed": confirmed,
            "keep_rate": kept / n if n else 0.0,
            "runs_per_kept": (n / kept) if kept else float("inf"),
            "repeats": repeats, "repeat_rate": repeats / n if n else 0.0,
            "best_wrmsse": best, "wall_minutes": wall,
        })
    return pd.DataFrame(rows)


def trend_line(df: pd.DataFrame) -> str:
    if len(df) < 2:
        return "Trend: fewer than two researcher sessions; no comparison yet."
    a, b = df.iloc[-2], df.iloc[-1]
    kr = "improved" if b.keep_rate > a.keep_rate else ("unchanged" if b.keep_rate == a.keep_rate else "worse")
    rr = "improved" if b.repeat_rate < a.repeat_rate else ("unchanged" if b.repeat_rate == a.repeat_rate else "worse")
    return (f"Trend ({a.session} -> {b.session}): keep_rate {a.keep_rate:.2f} -> {b.keep_rate:.2f} ({kr}); "
            f"repeat_rate {a.repeat_rate:.2f} -> {b.repeat_rate:.2f} ({rr}).")


def main() -> int:
    df = compute()
    if df.empty:
        print("no researcher runs logged"); return 0
    show = df.copy()
    show["runs_per_kept"] = show["runs_per_kept"].map(lambda x: "inf" if x == float("inf") else f"{x:.1f}")
    print(show.to_string(index=False, float_format=lambda x: f"{x:.4f}" if abs(x) < 10 else f"{x:.1f}"))
    trend = trend_line(df)
    print(trend)
    md = ["# LOOP SCORECARD", "", "Per researcher session, computed by `tools/scorecard.py` from runs/runs.csv and",
          "hypotheses/ledger.csv. Definitions in the script docstring. Newest session last.", "",
          "| session | runs | kept | confirm_runs | confirmed | keep_rate | runs_per_kept | repeats | repeat_rate | best_wrmsse | wall_minutes |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for _, r in show.iterrows():
        md.append(f"| {r.session} | {r.runs} | {r.kept} | {r.confirm_runs} | {r.confirmed} | {r.keep_rate:.2f} | {r.runs_per_kept} | {r.repeats} | "
                  f"{r.repeat_rate:.2f} | {r.best_wrmsse:.6f} | {r.wall_minutes:.1f} |")
    md += ["", trend, ""]
    OUT.write_text("\n".join(md))
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
