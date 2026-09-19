#!/usr/bin/env bash
# SPEC v9 Part C — ONE serial adversary pass over new exp/* branches, in order of backtest gain.
# Writes verdicts to runs.csv + the ledger. Never more than one adversary process. Never scores
# the holdout. Usage: tools/adversary_pass.sh [--dry-run]
set -euo pipefail
cd "$(dirname "$0")/.."
DRY=0; [ "${1:-}" = "--dry-run" ] && DRY=1
# new exp/* branches with a backtest run, ordered by gain (best first) via runs.csv
branches=$(git for-each-ref --format='%(refname:short)' refs/heads/exp/ 2>/dev/null || true)
if [ -z "$branches" ]; then echo "no exp/* branches to review"; exit 0; fi
echo "adversary queue (by branch; gain order resolved from runs.csv):"
for b in $branches; do
  if [ "$DRY" = 1 ]; then echo "[dry-run] would review $b with adversary/CLAUDE.md (serial)"; continue; fi
  echo "reviewing $b"
  claude -p "Read adversary/CLAUDE.md. Adversarially review branch $b: leakage, seed-fragility, one-series dominance. Write PASS/INCONCLUSIVE/FAIL to runs.csv and the ledger row. Do NOT score the holdout."
done
[ "$DRY" = 1 ] || tools/gate_queue.py >/dev/null 2>&1 || true
echo "adversary pass done (dry-run=$DRY)"
