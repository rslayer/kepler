#!/usr/bin/env bash
# SPEC v9 Part C — launch mandate-scoped researcher sessions in parallel. Each gets a CLAUDE.md
# overlay pinning its mandate + allowed levers, its own findings subfolder, branch namespace
# exp/<mandate>/<run_id>, an hour budget, and a share of --fit-jobs so the box is not
# oversubscribed. The adversary and the human holdout gate stay SERIAL (not launched here).
# Researchers NEVER score the holdout.
#
# Usage: tools/orchestrate.sh [--mandates A,B,C] [--hours 4] [--fit-jobs-total N] [--dry-run]
set -euo pipefail
cd "$(dirname "$0")/.."
MANDATES="A"; HOURS=4; FJ_TOTAL=$(( $(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 4) )); DRY=0
while [ $# -gt 0 ]; do case "$1" in
  --mandates) MANDATES="$2"; shift 2;; --hours) HOURS="$2"; shift 2;;
  --fit-jobs-total) FJ_TOTAL="$2"; shift 2;; --dry-run) DRY=1; shift;; *) echo "unknown $1"; exit 2;; esac; done

lever_of(){ case "$1" in A) echo horizon;; B) echo hierarchy;; C) echo ensemble;; *) echo other;; esac; }
desc_of(){ case "$1" in A) echo "multi-horizon direct models";; B) echo "level-aware modeling & reconciliation";; C) echo "fold-robust ensembling";; *) echo "unscoped";; esac; }
IFS=',' read -ra MS <<< "$MANDATES"
N=${#MS[@]}; FJ=$(( FJ_TOTAL / (N*4) )); [ "$FJ" -lt 1 ] && FJ=1   # fits keep 4 threads each
mkdir -p .orchestrate

for m in "${MS[@]}"; do
  lever="$(lever_of "$m")"; DESC_M="$(desc_of "$m")"; overlay=".orchestrate/CLAUDE_$m.md"
  cat > "$overlay" <<OV
# Mandate $m overlay (SPEC v9 Part C) — READ WITH root CLAUDE.md
You are Researcher $m. Your mandate is **$DESC_M**; your ONLY allowed lever is \`$lever\`.
Before any backtest: write a \`pending\` ledger row and run
\`tools/ledger_check.py --hypothesis <id> --mandate $m\` (it blocks other levers and dead re-runs).
Branch as \`exp/$m/<run_id>\`; write findings to \`findings/$m/\`. Use \`FIT_JOBS=$FJ\`.
NEVER read, list, or write under holdout/. You do not score the holdout; queue candidates for the human.
OV
  prompt="Read CLAUDE.md and $overlay. Work your mandate for up to ${HOURS}h: propose hypotheses on lever '$lever', screen then confirm on m5_all, log each in the ledger. Do not score the holdout."
  cmd=(claude -p "$prompt" --append-system-prompt "$(cat "$overlay")")
  if [ "$DRY" = 1 ]; then
    echo "[dry-run] Researcher $m (lever=$lever, fit-jobs=$FJ, ${HOURS}h): ${cmd[*]:0:3} ... [overlay $overlay]"
  else
    echo "launching Researcher $m (lever=$lever, fit-jobs=$FJ)"; timeout "${HOURS}h" "${cmd[@]}" &
  fi
done
[ "$DRY" = 1 ] || wait
echo "orchestrate done (mandates=$MANDATES, dry-run=$DRY)"
