#!/usr/bin/env bash
# kepler cloud provisioning (SPEC v9 Part A). Provisions/prepares a spot box for parallel
# backtests. NEVER copies or references any holdout/ path — the holdout is scored only on the
# human's machine. Run in two phases: (1) launch a spot instance (needs YOUR cloud creds;
# left as a documented template, not auto-run), (2) on the box, `setup` then `pull-data`.
#
# Usage:
#   ./provision.sh launch        # prints the AWS spot launch command template (edit + run yourself)
#   ./provision.sh setup <commit> # on the box: install env + clone repo at <commit>
#   ./provision.sh pull-data      # on the box: rebuild m5_all + m5_screen snapshots (Kaggle creds required)
set -euo pipefail

REPO_URL="${KEPLER_REPO_URL:-git@github.com:rslayer/kepler.git}"
WORKDIR="${KEPLER_WORKDIR:-$HOME/kepler}"
# Default box: 64 vCPU / 128+ GB, cheapest general-compute spot the person is likely to have.
# c7i.16xlarge = 64 vCPU / 128 GB (Intel); r7i.16xlarge = 64 vCPU / 512 GB if memory-bound.
AWS_INSTANCE_TYPE="${KEPLER_INSTANCE_TYPE:-c7i.16xlarge}"
AWS_AMI="${KEPLER_AMI:-ami-ubuntu-2204-x86_64}"   # replace with a current Ubuntu 22.04 AMI id in your region

case "${1:-help}" in
launch)
  cat <<TXT
# ---- EDIT then run yourself (needs your AWS credentials; this script never runs it) ----
aws ec2 run-instances \\
  --image-id ${AWS_AMI} \\
  --instance-type ${AWS_INSTANCE_TYPE} \\
  --instance-market-options '{"MarketType":"spot"}' \\
  --block-device-mappings '[{"DeviceName":"/dev/sda1","Ebs":{"VolumeSize":100,"VolumeType":"gp3"}}]' \\
  --key-name YOUR_KEY --security-group-ids YOUR_SG --subnet-id YOUR_SUBNET \\
  --tag-specifications 'ResourceType=instance,Tags=[{Key=project,Value=kepler}]'
# Then: scp your ~/.kaggle/kaggle.json to the box (chmod 600), ssh in, and run:
#   ./tools/cloud/provision.sh setup <commit>  &&  ./tools/cloud/provision.sh pull-data
TXT
  ;;
setup)
  COMMIT="${2:?usage: setup <commit>}"
  sudo apt-get update -y && sudo apt-get install -y git build-essential libgomp1 curl
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
  [ -d "$WORKDIR/.git" ] || git clone "$REPO_URL" "$WORKDIR"
  cd "$WORKDIR" && git fetch --all && git checkout "$COMMIT"
  UV_SYSTEM_CERTS=1 uv sync
  echo "setup done at commit $(git rev-parse --short HEAD); vCPU=$(nproc)"
  ;;
pull-data)
  cd "$WORKDIR"
  # Rebuild snapshots from Kaggle per each dataset's MANIFEST (needs ~/.kaggle/kaggle.json, chmod 600).
  # This writes ONLY under data/<id>/snapshot/. It does NOT create or touch holdout/ (human-only).
  for ds in m5_all m5_screen; do
    UV_SYSTEM_CERTS=1 uv run -- python -m src.data --dataset "$ds"
    test -f "data/$ds/snapshot/MANIFEST.txt" && echo "snapshot ready: $ds" || { echo "FAILED: $ds"; exit 1; }
  done
  echo "NOTE: holdout/ is intentionally NOT provisioned on the cloud box. Researchers never score the holdout."
  ;;
*)
  sed -n '2,12p' "$0" ;;
esac
