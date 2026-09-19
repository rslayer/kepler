#!/usr/bin/env python
"""Gate queue (SPEC v9 Part C). Lists candidates that have cleared the serial gate's automated
stages — (1) m5_screen directional filter, (2) strict m5_all keep rule, (3) adversary PASS — in
order of m5_all gain, with their ledger rows, so the HUMAN can choose which (if any) to score on
the holdout. This tool NEVER reads, lists, or scores anything under holdout/. Writes
runs/GATE_QUEUE.md.
"""
from __future__ import annotations
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHAMPION_HIER = 0.6666  # recipe v9 m5_all baseline (r145)

def rows():
    with open(ROOT / "runs" / "runs.csv") as f:
        return list(csv.DictReader(f))

def ledger():
    with open(ROOT / "hypotheses" / "m5_all" / "ledger.csv") as f:
        return {r["hypothesis_id"]: r for r in csv.DictReader(f)}

def main():
    rs = rows(); led = ledger()
    m5all = [r for r in rs if r.get("dataset") == "m5_all" and r.get("status") == "ok"]
    kept = [r for r in m5all if r.get("verdict") == "kept"]
    # adversary verdicts live in runs.csv author=adversary rows or a verdict marker; treat
    # verdict=="adversary_pass" or an adversary review row as cleared. (None yet -> awaiting.)
    adv = {r["run_id"]: r.get("verdict") for r in rs if r.get("author") == "adversary"}

    cand = []
    for r in kept:
        rid = r["run_id"]; hid = r.get("hypothesis_id", "")
        hier = float(r["wrmsse_hier"]) if r.get("wrmsse_hier") else None
        gain = (CHAMPION_HIER - hier) if hier else None
        adv_state = adv.get(rid, "awaiting-adversary")
        cand.append((gain or 0, rid, hid, hier, adv_state, led.get(hid, {})))
    cand.sort(reverse=True)

    lines = ["# Gate queue (SPEC v9) — human holdout decision\n",
             "Candidates that cleared the m5_all strict keep rule, ordered by gain vs the champion",
             f"(recipe v9 baseline hier {CHAMPION_HIER}). The holdout is scored ONLY by the human,",
             "at most 2/week (LEDGER_RULES.md). No tool in this repo scores the holdout.\n"]
    ready = [c for c in cand if c[4] not in ("awaiting-adversary",) and str(c[4]).lower().find("pass") >= 0]
    if not cand:
        lines.append("_No m5_all-kept candidates yet._")
    for gain, rid, hid, hier, adv_state, lrow in cand:
        badge = "READY FOR HOLDOUT" if (adv_state and "pass" in str(adv_state).lower()) else f"blocked: {adv_state}"
        lines.append(f"## {rid}  ({hid or 'no-hypothesis'})  —  {badge}")
        lines.append(f"- m5_all wrmsse_hier: **{hier:.4f}**  (gain vs champion **{gain:+.4f}**)")
        lines.append(f"- gates: screen ✓ (directional) · m5_all keep ✓ · adversary: {adv_state}")
        if lrow:
            lines.append(f"- lever: {lrow.get('lever','?')} · mechanism: {lrow.get('mechanism','')[:160]}")
        lines.append("")
    lines.append("---")
    lines.append(f"READY for a human holdout shot: {', '.join(c[1] for c in ready) or 'none (all awaiting adversary)'}")
    (ROOT / "runs" / "GATE_QUEUE.md").write_text("\n".join(lines) + "\n")
    print(f"wrote runs/GATE_QUEUE.md: {len(cand)} m5_all-kept candidate(s), {len(ready)} ready for holdout")
    for c in cand:
        print(f"  {c[1]} {c[2]} hier={c[3]:.4f} gain={c[0]:+.4f} adversary={c[4]}")

if __name__ == "__main__":
    main()
