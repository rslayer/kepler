"""Champion promotion gate. Agents never run this.

    python tools/promote.py exp/<run_id> [--dataset m5_ca1]

Promote the branch's kept run to champion if and only if ALL of:
  1. runs.csv verdict is `kept` and the parent chain (keep_rule.parent in the detail JSONs)
     leads to the current champion's backtest_run - a challenger is built on the champion.
  1b. on a confirmation dataset (tiers.json), the same model was also kept on its screening
     dataset in the same session.
  2. adversary/reviews/exp/<run_id>.md says PASS, or a human override row exists in runs.csv
     (author=human, status=ok, model_name=exp/<run_id>).
  3. frozen files and the CLAUDE.md Rules block are unchanged on the branch vs the frozen tag.
  4. runs/holdout.csv has a row for (dataset, model) - produced by the human with
     `make score-holdout` - and its wrmsse is NOT WORSE than the champion's holdout_wrmsse.
     Ties promote (decided by the human 2026-09-13): the challenger already beat the
     champion on 24 backtest fits and survived the adversary; the holdout's job is to catch
     a backtest gain that does not generalise, and an exact tie is not that. Strict "better"
     would permanently block any calendar-event fix whose event lies outside the fixed
     28-day holdout window. This tool never runs the holdout.
  5. the branch touches only src/features.py, src/model.py, findings/, runs/, hypotheses/,
     LESSONS.md, datasets/ - never tools/, Makefile, instruction files, scorer, backtest -
     and merges into main without conflict.
On success: merge (ff or merge commit), tag champion/<dataset>/v<N>, update champion.json
(previous <- old entry), append runs/promotions.csv. On failure: print the condition, change
nothing.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHAMPION = ROOT / "champion.json"
RUNS = ROOT / "runs" / "runs.csv"
HOLDOUT = ROOT / "runs" / "holdout.csv"
PROMOTIONS = ROOT / "runs" / "promotions.csv"
ALLOWED_PREFIXES = ("src/features.py", "src/model.py", "findings/", "runs/", "hypotheses/", "LESSONS.md", "datasets/")


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed:\n{r.stderr.strip()}")
    return r


def frozen_tag() -> str:
    m = re.search(r"git diff (\S+) -- src/scorer\.py", (ROOT / "Makefile").read_text())
    return m.group(1) if m else "v2-loop"


def refuse(cond: int, why: str) -> int:
    print(f"REFUSED: condition {cond} failed - {why}")
    return 1


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("branch")
    ap.add_argument("--dataset", default="m5_ca1")
    a = ap.parse_args(argv[1:])
    branch, dataset = a.branch, a.dataset
    if not branch.startswith("exp/"):
        raise SystemExit("branch must be exp/<run_id>")
    run_id = branch.split("/", 1)[1]
    if git("rev-parse", "--verify", "-q", branch, check=False).returncode != 0:
        raise SystemExit(f"no such branch: {branch}")
    if git("branch", "--show-current").stdout.strip() != "main":
        raise SystemExit("run the promotion gate from main")
    if git("status", "--porcelain").stdout.strip():
        raise SystemExit("working tree must be clean")

    champions = json.loads(CHAMPION.read_text())
    if dataset not in champions:
        raise SystemExit(f"no champion entry for {dataset} in champion.json")
    champ = champions[dataset]
    runs = {r["run_id"]: r for r in csv.DictReader(RUNS.open())}
    run = runs.get(run_id)
    if run is None:
        raise SystemExit(f"{run_id} is not in runs.csv")

    # 1. kept, and chain leads to the champion
    if run.get("verdict") != "kept":
        return refuse(1, f"{run_id} verdict is '{run.get('verdict')}', not kept")
    chain, cur = [run_id], run_id
    while cur != champ["backtest_run"]:
        detail = ROOT / "runs" / "detail" / f"{cur}.json"
        if not detail.exists():
            return refuse(1, f"no detail file for {cur} while walking the parent chain")
        kr = json.loads(detail.read_text()).get("keep_rule") or {}
        parent = kr.get("parent")
        if not parent or parent in chain:
            return refuse(1, f"parent chain {' <- '.join(chain)} does not reach champion {champ['backtest_run']}")
        chain.append(parent); cur = parent
    print(f"condition 1 ok: kept; chain {' <- '.join(chain)} reaches champion {champ['backtest_run']}")

    # 1b. confirmation datasets need the same model kept on their screening dataset, same session
    tiers = json.loads((ROOT / "tiers.json").read_text()).get("tiers", {}) if (ROOT / "tiers.json").exists() else {}
    screen = tiers.get(dataset, {}).get("screen")
    if screen:
        ok = [r for r in runs.values() if r.get("dataset") == screen and r.get("model_name") == run["model_name"]
              and r.get("verdict") == "kept" and r.get("session") == run.get("session")]
        if not ok:
            return refuse(1, f"(1b) no kept run of {run['model_name']} on the screening dataset {screen} in session "
                             f"{run.get('session') or '?'}; a {dataset} candidate must win the screen and the confirmation")
        print(f"condition 1b ok: {run['model_name']} kept on {screen} in the same session ({ok[-1]['run_id']})")

    # 2. adversary PASS or human override
    review = ROOT / "adversary" / "reviews" / "exp" / f"{run_id}.md"
    verdict = None
    if review.exists():
        m = re.search(r"Verdict:\s*\**\s*(PASS|FAIL|INCONCLUSIVE)", review.read_text())
        verdict = m.group(1) if m else None
    override = any(r["author"] == "human" and r["status"] == "ok" and r["model_name"] == branch for r in runs.values())
    if verdict != "PASS" and not override:
        return refuse(2, f"adversary verdict is {verdict or 'missing'} and no human override row for {branch}")
    print(f"condition 2 ok: {'human override' if override and verdict != 'PASS' else 'adversary PASS'}")

    # 3. frozen files + Rules block on the branch
    tag = frozen_tag()
    d = git("diff", "--stat", tag, branch, "--", "src/scorer.py", "src/report.py").stdout.strip()
    if d:
        return refuse(3, f"frozen files differ from {tag}:\n{d}")
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "check_claude_diff.py"), tag, branch],
                       cwd=ROOT, capture_output=True, text=True)
    if r.returncode != 0:
        return refuse(3, f"CLAUDE.md Rules block changed on the branch:\n{r.stdout.strip()}")
    print(f"condition 3 ok: frozen files and Rules block unchanged vs {tag}")

    # 4. holdout row, human-produced, strictly better than champion
    model_name = run["model_name"]
    rows = [r for r in csv.DictReader(HOLDOUT.open()) if r.get("dataset") == dataset] if HOLDOUT.exists() else []
    mine = [r for r in rows if r["model_name"] == model_name]
    if not mine:
        return refuse(4, f"no runs/holdout.csv row for ({dataset}, {model_name}); human must run "
                         f"`make score-holdout MODEL={model_name} DATASET={dataset}` (this tool never runs it)")
    if champ.get("holdout_wrmsse") is None:
        return refuse(4, f"champion {champ['model_name']} has no holdout score for {dataset}; human must run "
                         f"`make score-holdout MODEL={champ['model_name']} DATASET={dataset}` first")
    hold = float(mine[-1]["wrmsse"])
    if hold > float(champ["holdout_wrmsse"]):
        return refuse(4, f"holdout {hold:.6f} is worse than champion's {float(champ['holdout_wrmsse']):.6f}")
    rel = "equals" if hold == float(champ["holdout_wrmsse"]) else "<"
    print(f"condition 4 ok: holdout {hold:.6f} {rel} champion {float(champ['holdout_wrmsse']):.6f} (not worse)")

    # 5. touched paths + clean merge
    base = git("merge-base", "main", branch).stdout.strip()
    touched = git("diff", "--name-only", base, branch).stdout.split()
    bad = [p for p in touched if not p.startswith(ALLOWED_PREFIXES)]
    if bad:
        return refuse(5, f"branch touches disallowed paths: {bad}")
    # Bookkeeping files (runs/, findings/, hypotheses/, datasets/, LESSONS.md) are synced from
    # the branch to main by the cycle before main appends more rows, so main's versions win;
    # only a conflict in src/ blocks promotion.
    BOOKKEEPING = ("runs/", "findings/", "hypotheses/", "datasets/", "LESSONS.md")
    trial = git("merge", "--no-commit", "--no-ff", branch, check=False)
    conflicts = git("diff", "--name-only", "--diff-filter=U").stdout.split()
    git("merge", "--abort", check=False)
    src_conflicts = [c for c in conflicts if not c.startswith(BOOKKEEPING)]
    if src_conflicts:
        return refuse(5, f"merge conflicts in {src_conflicts}")
    print(f"condition 5 ok: only allowed paths touched; merges cleanly"
          + (f" (bookkeeping conflicts resolved in main's favour: {conflicts})" if conflicts else ""))

    # promote
    if git("merge", "--ff-only", branch, check=False).returncode != 0:
        msg = f"promote {branch} to champion/{dataset} (promotion gate: all conditions met)"
        if conflicts:
            git("merge", "--no-ff", "--no-commit", branch, check=False)
            git("checkout", "--ours", "--", *conflicts)
            git("add", "--", *conflicts)
            git("commit", "-q", "-m", msg)
        else:
            git("merge", "--no-ff", "--no-edit", "-m", msg, branch)
    existing = [t for t in git("tag", "--list", f"champion/{dataset}/v*").stdout.split()]
    n = 1 + max([int(t.rsplit("v", 1)[1]) for t in existing] or [0])
    tag_name = f"champion/{dataset}/v{n}"
    git("tag", "-a", tag_name, "-m", f"champion {dataset} v{n}: {model_name} ({run_id})")
    old = dict(champ)
    champions[dataset] = {
        "dataset": dataset, "model_name": model_name, "git_tag": tag_name,
        "config_hash": run["config_hash"], "backtest_run": run_id,
        "backtest_wrmsse": float(run["wrmsse"]), "holdout_wrmsse": hold,
        "promoted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "promoted_by": "tools/promote.py (human-run)", "previous": old,
    }
    CHAMPION.write_text(json.dumps(champions, indent=2) + "\n")
    with PROMOTIONS.open("a", newline="") as fh:
        csv.writer(fh).writerow([champions[dataset]["promoted_at"], dataset, old["backtest_run"], run_id,
                                 old["backtest_wrmsse"], float(run["wrmsse"]), old.get("holdout_wrmsse"), hold,
                                 tag_name, "human"])
    git("add", "champion.json", "runs/promotions.csv")
    git("commit", "-q", "-m", f"promote: {dataset} champion v{n} = {model_name} ({run_id})")
    print(f"PROMOTED {branch}: {dataset} champion is now {model_name} ({run_id}), tag {tag_name}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
