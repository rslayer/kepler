"""Merge gate for curator branches. Replaces the human approval on Priors-block edits.

    python tools/merge_gate.py curator/<session>

Exit 0 and merge the branch into main (fast-forward if possible, else a merge commit) if
and only if ALL of:
  1. tools/check_claude_diff.py main <branch> exits 0 (edits confined to the Priors block).
  2. adversary/reviews/curator/<session>.md exists on the branch or on main with verdict PASS.
  3. Every LESSONS.md line the branch adds cites at least one run whose runs.csv verdict is
     `kept`, or cites two or more distinct runs; every cited run must exist in runs.csv.
  4. The scorecard's most recent researcher session is not worse than the one before it on
     both keep_rate and repeat_rate (skipped with a notice when fewer than two sessions).
Otherwise print which condition failed and change nothing.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import scorecard  # noqa: E402


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed:\n{r.stderr.strip()}")
    return r


def fail(cond: int, why: str) -> int:
    print(f"REFUSED: condition {cond} failed - {why}")
    return 1


def main(argv: list[str]) -> int:
    if len(argv) != 2 or not argv[1].startswith("curator/"):
        print(__doc__); return 2
    branch = argv[1]
    session = branch.split("/", 1)[1]
    if git("rev-parse", "--verify", "-q", branch, check=False).returncode != 0:
        raise SystemExit(f"no such branch: {branch}")
    if git("branch", "--show-current").stdout.strip() != "main":
        raise SystemExit("run the merge gate from main")
    if git("status", "--porcelain").stdout.strip():
        raise SystemExit("working tree must be clean")

    # 1. scope
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "check_claude_diff.py"), "main", branch],
                       cwd=ROOT, capture_output=True, text=True)
    print(r.stdout.strip())
    if r.returncode != 0:
        return fail(1, "CLAUDE.md edits are not confined to the Priors block")

    # 2. adversary PASS
    rel = f"adversary/reviews/curator/{session}.md"
    text = None
    for ref in (branch, "main"):
        s = git("show", f"{ref}:{rel}", check=False)
        if s.returncode == 0:
            text = s.stdout; break
    if text is None and (ROOT / rel).exists():
        text = (ROOT / rel).read_text()
    if text is None:
        return fail(2, f"no adversary review at {rel}")
    m = re.search(r"\*\*Verdict:\s*(PASS|FAIL|INCONCLUSIVE)\*\*|Verdict:\s*(PASS|FAIL|INCONCLUSIVE)", text)
    verdict = (m.group(1) or m.group(2)) if m else None
    if verdict != "PASS":
        return fail(2, f"adversary verdict is {verdict or 'missing'}, not PASS")
    print(f"condition 2 ok: adversary review {rel} says PASS")

    # 3. evidence
    diff = git("diff", f"main...{branch}", "--", "LESSONS.md").stdout
    added = [l[1:] for l in diff.splitlines() if l.startswith("+- [")]
    runs_csv = (ROOT / "runs" / "runs.csv").read_text().splitlines()
    header = runs_csv[0].split(",")
    vi, ii = header.index("verdict"), header.index("run_id")
    verdicts = {row.split(",")[ii]: row.split(",")[vi] for row in runs_csv[1:] if row}
    for line in added:
        cited = sorted(set(re.findall(r"\br\d{3}\b", line.split("]")[0])))
        missing = [c for c in cited if c not in verdicts]
        if missing:
            return fail(3, f"lesson cites unknown run(s) {missing}: {line[:80]}")
        if not (any(verdicts[c] == "kept" for c in cited) or len(cited) >= 2):
            return fail(3, f"lesson has neither a kept run nor two corroborating runs: {line[:80]}")
    print(f"condition 3 ok: {len(added)} added lesson line(s), all with kept or corroborated evidence")

    # 4. scorecard trend
    df = scorecard.compute()
    if len(df) < 2:
        print("condition 4 skipped: fewer than two researcher sessions in the log")
    else:
        a, b = df.iloc[-2], df.iloc[-1]
        if b.keep_rate < a.keep_rate or b.repeat_rate > a.repeat_rate:
            return fail(4, f"scorecard worse: keep_rate {a.keep_rate:.2f}->{b.keep_rate:.2f}, "
                           f"repeat_rate {a.repeat_rate:.2f}->{b.repeat_rate:.2f}")
        print(f"condition 4 ok: keep_rate {a.keep_rate:.2f}->{b.keep_rate:.2f}, repeat_rate {a.repeat_rate:.2f}->{b.repeat_rate:.2f}")

    # Fast-forward when possible; otherwise a merge commit. main normally moves after a
    # curator branch is cut (the adversary's review of that branch is committed on main),
    # so a strict fast-forward would refuse every real curator branch.
    if git("merge", "--ff-only", branch, check=False).returncode == 0:
        how = "fast-forward"
    else:
        git("merge", "--no-ff", "--no-edit", "-m", f"merge {branch} (merge gate: all conditions met)", branch)
        how = "merge commit"
    print(f"MERGED {branch} into main ({how}):")
    print(git("diff", "--stat", f"HEAD@{{1}}", "HEAD").stdout.strip())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
