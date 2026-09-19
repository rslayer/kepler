#!/usr/bin/env bash
# SPEC v9 Part C — one unattended nightly cycle on the cloud box:
#   orchestrate (mandate-scoped researchers) -> ONE adversary pass -> gate queue for the human.
# The holdout is never scored. Intended for cron on the cloud box.
set -euo pipefail
cd "$(dirname "$0")/../.."
export UV_SYSTEM_CERTS=1
tools/orchestrate.sh --mandates "${KEPLER_MANDATES:-A,B,C}" --hours "${KEPLER_HOURS:-4}"
tools/adversary_pass.sh
uv run -- python tools/gate_queue.py
echo "nightly cycle complete; human reviews runs/GATE_QUEUE.md"
