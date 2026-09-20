#!/usr/bin/env python
"""Ledger gate (SPEC v9 Part B). Fails (exit 2) a run whose hypothesis is missing from the
ledger, or whose lever+mechanism duplicates a non-reopened dead row (blocking silent re-tries
of dead ends — the recursive family above all). Allows a row a human has marked `reopen`.

Usage:
  tools/ledger_check.py --hypothesis H170                 # row must exist and not be a dead re-run
  tools/ledger_check.py --propose --lever recursive --mechanism "recursive compounding bias"
  tools/ledger_check.py --hypothesis H170 --mandate horizon   # also enforce the mandate's lever
"""
from __future__ import annotations
import argparse, csv, re, sys
from pathlib import Path

LEDGER = Path(__file__).resolve().parent.parent / "hypotheses" / "m5_all" / "ledger.csv"
DEAD = {"discarded", "held", "inconclusive"}
MANDATE_LEVERS = {"horizon": {"horizon"}, "hierarchy": {"hierarchy"}, "ensemble": {"ensemble", "recursive"}}
_STOP = {"the","a","an","and","or","of","to","in","on","for","is","are","it","its","by","with","that",
         "as","at","not","no","but","so","each","per","than","vs","via","one","two","three","four"}

def _sig(text: str) -> set:
    return {w for w in re.findall(r"[a-z0-9%+\-]+", (text or "").lower()) if w not in _STOP and len(w) > 2}

def _rows():
    with open(LEDGER) as f:
        return list(csv.DictReader(f))

def _dup(lever: str, mechanism: str, rows: list, exclude_id: str | None = None):
    """Return a dead, non-reopened row with the same lever and high mechanism overlap, else None."""
    ms = _sig(mechanism)
    if not ms:
        return None
    for r in rows:
        if r["hypothesis_id"] == exclude_id: continue
        if r["lever"] != lever: continue
        if r["status"].strip().lower() == "reopen": continue
        if r["status"].strip().lower() not in DEAD: continue
        rs = _sig(r["mechanism"])
        if not rs: continue
        overlap = len(ms & rs) / len(ms | rs)
        if overlap >= 0.30 or ({"compounding","bias"} <= ms and {"compounding","bias"} <= rs):
            return r
    return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hypothesis"); ap.add_argument("--propose", action="store_true")
    ap.add_argument("--lever"); ap.add_argument("--mechanism"); ap.add_argument("--mandate")
    ap.add_argument("--dry", action="store_true", help="integrity check of the ledger")
    a = ap.parse_args()
    rows = _rows()
    by_id = {r["hypothesis_id"]: r for r in rows}

    if a.dry:
        from collections import Counter
        st = Counter(r["status"] for r in rows); lv = Counter(r["lever"] for r in rows)
        bad = [r["hypothesis_id"] for r in rows if r["status"] in DEAD and (not r["mechanism"] or r["rejected_by"] == "n/a")]
        print(f"ledger OK: {len(rows)} rows | status {dict(st)} | lever {dict(lv)}")
        print(f"rejected rows missing mechanism/rejected_by: {bad or 'none'}")
        if bad: sys.exit(2)
        return

    if a.propose:
        if not a.lever or not a.mechanism:
            print("propose needs --lever and --mechanism"); sys.exit(2)
        d = _dup(a.lever, a.mechanism, rows)
        if d:
            print(f"BLOCKED: proposed {a.lever} hypothesis duplicates dead row {d['hypothesis_id']} "
                  f"(status={d['status']}, rejected_by={d['rejected_by']}). Mechanism: {d['mechanism'][:120]}"
                  f"\nReopen {d['hypothesis_id']} (human, with a reason) to override."); sys.exit(2)
        print(f"OK: no dead {a.lever} row matches this mechanism."); return

    if not a.hypothesis:
        print("need --hypothesis or --propose"); sys.exit(2)
    r = by_id.get(a.hypothesis)
    if not r:
        print(f"BLOCKED: hypothesis {a.hypothesis} is not in the ledger. Write a pending row first "
              f"(LEDGER_RULES.md rule 3)."); sys.exit(2)
    if a.mandate:
        allowed = MANDATE_LEVERS.get(a.mandate, set())
        if r["lever"] not in allowed:
            print(f"BLOCKED: {a.hypothesis} lever '{r['lever']}' is outside mandate '{a.mandate}' "
                  f"(allowed: {sorted(allowed)})."); sys.exit(2)
    if r["status"].strip().lower() in DEAD:
        d = _dup(r["lever"], r["mechanism"], rows, exclude_id=a.hypothesis)
        # a dead row itself may not be re-run unless reopened
        print(f"BLOCKED: {a.hypothesis} is {r['status']} (rejected_by={r['rejected_by']}); "
              f"mark it `reopen` with a reason to re-run (LEDGER_RULES.md rule 1)."); sys.exit(2)
    print(f"OK: {a.hypothesis} ({r['status']}, lever={r['lever']}) may run.")

if __name__ == "__main__":
    main()
