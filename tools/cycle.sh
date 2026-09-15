#!/bin/bash
# One unattended research cycle on one dataset (SPEC_v3 Part E):
#   researcher -> adversary (exp/* of that session) -> curator -> adversary (curator branch)
#   -> merge gate -> scorecard -> list of challengers ready for a human holdout decision.
# Promotion is NOT part of the cycle: it needs the human's `make score-holdout`.
#
#   tools/cycle.sh <dataset> [researcher_hours]
#
# Each role runs as a fresh headless session (`claude -p`), so every session starts cold.
# After every session the cycle re-checks the frozen files and the Rules block and aborts
# on any violation. Start/end/tokens/cost per session go to runs/sessions.csv.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"
DATASET="${1:-m5_ca1}"
HOURS="${2:-3}"
LOCK="$REPO/runs/.cycle.lock"
SESSIONS="$REPO/runs/sessions.csv"
DATE="$(date -u +%Y%m%d)"
export UV_SYSTEM_CERTS=1

# ---------------------------------------------------------------- preconditions
if [ -e "$LOCK" ]; then
  echo "REFUSED: lock $LOCK exists (a cycle is running, or one died; remove it deliberately)"; exit 3
fi
if [ -n "$(git status --porcelain)" ]; then
  echo "REFUSED: working tree is dirty; commit or stash first"; exit 3
fi
if [ "$(git branch --show-current)" != "main" ]; then
  echo "REFUSED: not on main"; exit 3
fi
git fetch -q origin main
if [ "$(git rev-list --count HEAD..origin/main)" != "0" ]; then
  echo "REFUSED: main is behind origin/main; pull first"; exit 3
fi
command -v claude >/dev/null || { echo "REFUSED: claude CLI not on PATH"; exit 3; }

mkdir "$LOCK"
trap 'rmdir "$LOCK" 2>/dev/null || true' EXIT
[ -s "$SESSIONS" ] || echo "session,role,dataset,started,ended,input_tokens,output_tokens,cost_usd,exit_code,num_turns" > "$SESSIONS"

# next index for today's researcher session
N=$(( $(grep -c "^researcher-$DATE-" "$SESSIONS" || true) + 1 ))
RS="researcher-$DATE-$N"; AS1="adversary-$DATE-$((2*N-1))"; CS="curator-$DATE-$N"; AS2="adversary-$DATE-$((2*N))"
OUT="$REPO/runs/cycle-logs/$RS"; mkdir -p "$OUT"
echo "cycle $RS on $DATASET (researcher cap ${HOURS}h); logs in runs/cycle-logs/$RS/"

# ---------------------------------------------------------------- helpers
GUARD='Do not read, list, or reference anything under holdout/, or the evaluation-label files under data/*/raw/ (sales_train_evaluation.csv, sample_submission.csv, any column d_1914+); those are the held-out answers. Never edit any frozen file (run `make verify-frozen` to see the set: scorer.py, report.py, score_holdout.py, scorer_hier.py, backtest.py, scoring.py, data.py, contract.py, adapters/m5.py), tools/, Makefile, or anything above the RULES marker in CLAUDE.md. Never commit to main. Nobody else is working in this repository. Each `make backtest` takes about five minutes: run it and wait for it to finish before doing anything else.'
# Permission patterns match the command's first word, so env-var-prefixed forms need their
# own entries (the adversary's rerun is `KEPLER_RUNS_DIR=adversary/reruns make backtest ...`).
COMMON_TOOLS='Read,Glob,Grep,Edit,Write,Bash(make:*),Bash(KEPLER_RUNS_DIR=*),Bash(UV_SYSTEM_CERTS=*),Bash(git:*),Bash(python:*),Bash(python3:*),Bash(.venv/bin/python:*),Bash(uv:*),Bash(ls:*),Bash(cat:*),Bash(head:*),Bash(tail:*),Bash(grep:*),Bash(wc:*),Bash(awk:*),Bash(sed:*),Bash(sort:*),Bash(cut:*),Bash(date:*),Bash(diff:*),Bash(mkdir:*),Bash(cp:*),Bash(rm:*),Bash(for:*),Bash(cd:*)'

run_session() {  # role session_id prompt
  local role="$1" sid="$2" prompt="$3" started ended rc json
  started="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "--- $sid start $started"
  set +e
  # keep the laptop awake for the whole session (idle sleep killed an overnight run); no-op off macOS
  CAFF=$(command -v caffeinate 2>/dev/null) || CAFF=""
  ${CAFF:+$CAFF -i} claude -p "$prompt" --output-format json --permission-mode acceptEdits \
    --allowedTools "$COMMON_TOOLS" > "$OUT/$sid.json" 2> "$OUT/$sid.stderr"
  rc=$?
  set -e
  ended="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  json="$OUT/$sid.json"
  python3 - "$json" "$sid" "$role" "$DATASET" "$started" "$ended" "$rc" >> "$SESSIONS" <<'PY'
import json, sys
p, sid, role, ds, st, en, rc = sys.argv[1:8]
try:
    d = json.load(open(p)); u = d.get("usage", {}) or {}
    it = u.get("input_tokens", "") ; ot = u.get("output_tokens", "")
    cost = d.get("total_cost_usd", ""); turns = d.get("num_turns", "")
except Exception:
    it = ot = cost = turns = ""
print(f"{sid},{role},{ds},{st},{en},{it},{ot},{cost},{rc},{turns}")
PY
  echo "--- $sid end $ended (exit $rc)"
  python3 -c "import json,sys; d=json.load(open('$json')); print((d.get('result') or '')[:1500])" 2>/dev/null > "$OUT/$sid.result.txt" || true
  # a session that errored before doing any work (auth, CLI) aborts the whole cycle
  if python3 -c "import json,sys; d=json.load(open('$json')); sys.exit(0 if d.get('is_error') and d.get('num_turns',0) <= 1 else 1)" 2>/dev/null; then
    echo "ABORT: $sid failed before doing any work: $(cat "$OUT/$sid.result.txt")"
    echo "       (if this is an auth error, run \`claude login\` in a terminal and relaunch)"
    exit 5
  fi
  # integrity after every session
  git checkout -q main
  make verify-frozen || { echo "ABORT: frozen files or Rules block changed after $sid"; exit 4; }
  return $rc
}

# ---------------------------------------------------------------- 1. researcher
run_session researcher "$RS" "Read CLAUDE.md and run the loop for $HOURS hours on dataset $DATASET. Your session id is $RS. $GUARD Stop when $HOURS hours have elapsed since you started or when CLAUDE.md tells you to; do the end-of-session steps first. Reply with the one-paragraph report CLAUDE.md asks for, the number of runs logged, the current best run_id and WRMSSE, and the exp/* branches you created." || true

# sync the session's log/findings/memory to main (the researcher commits on exp/* branches)
LAST_EXP="$(git for-each-ref --sort=-committerdate --format='%(refname:short)' 'refs/heads/exp/*' | head -1)"
if [ -n "$LAST_EXP" ] && git log -1 --format=%s "$LAST_EXP" | grep -q . ; then
  git checkout -q "$LAST_EXP" -- runs/runs.csv runs/detail findings hypotheses datasets LESSONS.md 2>/dev/null || true
  if [ -n "$(git status --porcelain)" ]; then
    git add -A runs findings hypotheses datasets LESSONS.md
    git commit -q -m "chore: sync $RS run log, findings, memory to main"
  fi
fi
BRANCHES="$(grep ",$RS," runs/runs.csv | awk -F, '$NF~/kept/ || $0~/,kept,/ {print $1}' | sed 's/^/exp\//' | tr '\n' ' ')"
echo "kept branches from $RS: ${BRANCHES:-none}"

# ---------------------------------------------------------------- 2. adversary on exp/*
if [ -n "$BRANCHES" ]; then
  run_session adversary "$AS1" "You are the adversary. Read adversary/CLAUDE.md and review every exp/* branch from $RS (branches: $BRANCHES). Your session id is $AS1. $GUARD Write only under adversary/reviews/ and the review rows in runs/runs.csv; restore src/ from main after every rerun." || true
  git add -A adversary/reviews runs/runs.csv && git commit -q -m "adversary: $AS1 reviews" || true
  if ! grep -q ",$AS1" adversary/reruns/runs.csv 2>/dev/null; then
    echo "WARNING: $AS1 logged no reruns (adversary/reruns/runs.csv); items 7-8 were not executed - review verdicts are provisional"
  fi
fi

# ---------------------------------------------------------------- 3. curator
run_session curator "$CS" "You are the curator. Read curator/CLAUDE.md and curate session $RS (dataset $DATASET). Your session id is $CS. $GUARD Commit on branch curator/$RS only." || true
git checkout -q main

# ---------------------------------------------------------------- 4. adversary on curator branch
if git rev-parse --verify -q "curator/$RS" >/dev/null; then
  run_session adversary "$AS2" "You are the adversary. Read adversary/CLAUDE.md and review the branch curator/$RS (checklist item 9). Your session id is $AS2. $GUARD Write only the review file under adversary/reviews/curator/ and one row in runs/runs.csv." || true
  git add -A adversary/reviews runs/runs.csv && git commit -q -m "adversary: $AS2 item-9 review of curator/$RS" || true
  # ------------------------------------------------------------ 5. merge gate
  make merge-gate BRANCH="curator/$RS" || echo "merge gate refused curator/$RS (see above)"
fi

# ---------------------------------------------------------------- 6. scorecard + ready list
make scorecard | tail -3
git add -A LOOP_SCORECARD.md && git commit -q -m "chore: scorecard after $RS" || true
echo
echo "READY FOR HOLDOUT DECISION (kept + adversary PASS, promotion is human-only):"
python3 - "$RS" <<'PY'
import csv, re, sys, pathlib
sid = sys.argv[1]; rows = list(csv.DictReader(open("runs/runs.csv")))
kept = [r for r in rows if r.get("session") == sid and r.get("verdict") == "kept"]
for r in kept:
    rev = pathlib.Path(f"adversary/reviews/exp/{r['run_id']}.md")
    v = re.search(r"Verdict:\s*\**\s*(PASS|FAIL|INCONCLUSIVE)", rev.read_text()).group(1) if rev.exists() else "no review"
    print(f"  exp/{r['run_id']}  {r['model_name']}  WRMSSE {r['wrmsse']}  adversary: {v}" + ("  -> make score-holdout MODEL=%s DATASET=%s ; make promote BRANCH=exp/%s" % (r['model_name'], r['dataset'], r['run_id']) if v == "PASS" else ""))
if not kept: print("  none")
PY
python3 tools/cost_report.py "$RS" || true
echo "cycle $RS done"
