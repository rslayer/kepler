"""Scope check for curator edits to CLAUDE.md.

    python tools/check_claude_diff.py <base_ref> <head_ref>

Exit 0 if and only if the CLAUDE.md diff between the refs touches lines only inside the
Priors block: everything above and including the PRIORS marker must be byte-identical, and
both markers must be present in the head. Otherwise prints the offending hunk and exits 1.
The Rules block (identity, rules, loop) is human-owned and gated by CODEOWNERS.
"""

from __future__ import annotations

import difflib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RULES = "<!-- RULES: human-owned. Agents never edit above this line. -->"
PRIORS = "<!-- PRIORS: curator-editable below this line. -->"


def show(ref: str) -> str:
    r = subprocess.run(["git", "show", f"{ref}:CLAUDE.md"], cwd=ROOT, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"cannot read CLAUDE.md at {ref}: {r.stderr.strip()}")
    return r.stdout


def locked_part(text: str, ref: str) -> str:
    lines = text.splitlines(keepends=True)
    if sum(1 for l in lines if l.strip() == RULES) != 1 or sum(1 for l in lines if l.strip() == PRIORS) != 1:
        raise SystemExit(f"FAIL: {ref}: CLAUDE.md must contain exactly one RULES marker and one PRIORS marker")
    idx = next(i for i, l in enumerate(lines) if l.strip() == PRIORS)
    if not any(l.strip() == RULES for l in lines[:idx]):
        raise SystemExit(f"FAIL: {ref}: RULES marker must precede the PRIORS marker")
    return "".join(lines[: idx + 1])


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__); return 2
    base, head = argv[1], argv[2]
    b, h = show(base), show(head)
    lb, lh = locked_part(b, base), locked_part(h, head)
    if lb == lh:
        if b == h:
            print(f"OK: CLAUDE.md unchanged ({base}..{head})")
        else:
            print(f"OK: CLAUDE.md changes are confined to the Priors block ({base}..{head})")
        return 0
    print(f"FAIL: CLAUDE.md changes above the PRIORS marker ({base}..{head}):")
    sys.stdout.writelines(difflib.unified_diff(lb.splitlines(keepends=True), lh.splitlines(keepends=True),
                                               fromfile=f"{base}:CLAUDE.md", tofile=f"{head}:CLAUDE.md", n=1))
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
