# Forecast Research Loop — operator entry points.
# Agents use `make backtest` and `make report`. Everything else is human-run.

SHELL := /bin/bash
UV := UV_SYSTEM_CERTS=1 uv
# macOS: this laptop idle-sleeps after 1 minute unless a process holds it awake (pmset -g);
# a backtest lost a night's benchmark to that. caffeinate -i keeps the machine awake for the
# duration of the command; no-op where caffeinate does not exist (Linux boxes).
CAFF := $(shell command -v caffeinate 2>/dev/null)
PY := UV_SYSTEM_CERTS=1 $(if $(CAFF),$(CAFF) -i,) uv run --

MODEL ?=
DATASET ?= m5_screen
RUN ?=
SEEDS ?= 42,7,123
JOBS ?= 1
FIT_JOBS ?=            # SPEC v9: fits in parallel; empty -> backtest default floor(vCPU/4)
BAG ?= on
PARENT ?=
SESSION ?=
HYPOTHESIS ?=
AUTHOR ?= human

.PHONY: help env data holdout backtest report score-holdout verify-frozen scorecard merge-gate forecast evaluate live-report promote clean

help:
	@echo "make env                     install pinned dependencies"
	@echo "make data DATASET=<id>       download + build snapshot + MANIFEST (default m5_ca1)"
	@echo "make holdout                 HUMAN ONLY: cut final 28 days out of the snapshot"
	@echo "make backtest MODEL=<name>   rolling-origin backtest (8 folds x 3 seeds), appends to runs/runs.csv"
	@echo "  ... SEEDS=42,7,123         override the seed list"
	@echo "  ... JOBS=3                 parallel worker processes for the fits (results identical)"
	@echo "  ... BAG=off                score seeds separately (v1-v4 behaviour); default on = seed-averaged forecast"
	@echo "  ... PARENT=<run_id>        evaluate the keep rule against a v1 run; writes verdict"
	@echo "  ... SESSION=<id> HYPOTHESIS=<H###>   required when AUTHOR=researcher"
	@echo "make report                  table of all runs sorted by WRMSSE"
	@echo "make report RUN=<run_id>     error breakdown for one run"
	@echo "make score-holdout MODEL=<n> HUMAN ONLY: one shot against holdout/"
	@echo "make verify-frozen           diff frozen files against tag v4-partc + CLAUDE.md Rules-block integrity"
	@echo "make forecast ASOF=<date>    champion forecast -> forecasts/<dataset>/<asof>/"
	@echo "make evaluate                score past forecasts whose actuals exist -> runs/live.csv"
	@echo "make live-report             live WRMSSE per champion vs its backtest"
	@echo "make promote BRANCH=exp/<id> HUMAN ONLY: promotion gate (needs a holdout row)"
	@echo "make scorecard               per-session keep/repeat rates -> LOOP_SCORECARD.md"
	@echo "make merge-gate BRANCH=curator/<session>   gated fast-forward merge of a curator branch"
	@echo "KEPLER_RUNS_DIR=<dir> make backtest ...   log to <dir> instead of runs/ (adversary reruns)"

env:
	$(UV) sync --extra data
	$(PY) python -c "import lightgbm, pandas, numpy, sklearn, statsmodels, pyarrow; print('lightgbm', lightgbm.__version__); print('env ok')"

data:
	$(PY) python -m src.data --dataset $(DATASET)

holdout:
	$(PY) python -m src.data --dataset $(DATASET) --cut-holdout

backtest:
	@if [ -z "$(MODEL)" ]; then echo "usage: make backtest MODEL=<name>"; exit 2; fi
	$(PY) python -m src.backtest --model $(MODEL) --dataset $(DATASET) --seeds $(SEEDS) $(if $(FIT_JOBS),--fit-jobs $(FIT_JOBS),) --bag-seeds $(BAG) --author $(AUTHOR) $(if $(PARENT),--parent $(PARENT),) $(if $(SESSION),--session $(SESSION),) $(if $(HYPOTHESIS),--hypothesis $(HYPOTHESIS),)

report:
ifeq ($(strip $(RUN)),)
	$(PY) python -m src.report
else
	$(PY) python -m src.report --run $(RUN)
endif

score-holdout:
	@if [ -z "$(MODEL)" ]; then echo "usage: make score-holdout MODEL=<name>"; exit 2; fi
	$(PY) python -m src.score_holdout --model $(MODEL) --dataset $(DATASET)

# Frozen baseline: the ref whose frozen-file contents are authoritative. Move it
# (re-tag) whenever the human legitimately changes a frozen file, e.g.
#   git tag -f v8-screen <commit-with-the-new-frozen-state>
# v5-parta (2026-09-14) supersedes the stale v4-partc: score_holdout.py's wrmsse_hier
# yardstick column, the evaluation-label quarantine in adapters/m5.py, and backtest.py's
# --reparent path, per-dataset budgets and v5 seed bagging are all in the baseline now.
FROZEN_REF ?= v10-mirror

# Every file whose contents the harness's integrity depends on. This must include not
# just the scorer but everything that FEEDS it: the fold logic + keep rule (backtest),
# the frames handed to the frozen scorer (scoring), the loader + manifest gate (data),
# the structural leak check (contract), and the adapter that defines the holdout cut,
# the hierarchy levels, and the dollar weights (adapters/m5).
FROZEN_FILES := src/scorer.py src/report.py src/score_holdout.py src/scorer_hier.py \
                src/backtest.py src/scoring.py src/data.py src/contract.py src/adapters/m5.py

verify-frozen:
	@echo "--- frozen files must match $(FROZEN_REF); any diff FAILS this target ---"
	@git diff --exit-code $(FROZEN_REF) -- $(FROZEN_FILES)
	@$(PY) python tools/check_claude_diff.py $(FROZEN_REF) HEAD
	@echo "frozen: clean (files match $(FROZEN_REF), CLAUDE.md Rules block unchanged)"

forecast:
	@if [ -z "$(ASOF)" ]; then echo "usage: make forecast ASOF=<YYYY-MM-DD> [DATASET=<id>] [HORIZON=28]"; exit 2; fi
	$(PY) python -m src.forecast --dataset $(DATASET) --asof $(ASOF) --horizon $(or $(HORIZON),28)

evaluate:
	$(PY) python -m src.evaluate --dataset $(DATASET)

live-report:
	$(PY) python tools/live_report.py --dataset $(DATASET)

promote:
	@if [ -z "$(BRANCH)" ]; then echo "usage: make promote BRANCH=exp/<run_id> [DATASET=<id>]   (HUMAN ONLY)"; exit 2; fi
	$(PY) python tools/promote.py $(BRANCH) --dataset $(DATASET)

scorecard:
	$(PY) python tools/scorecard.py

merge-gate:
	@if [ -z "$(BRANCH)" ]; then echo "usage: make merge-gate BRANCH=curator/<session>"; exit 2; fi
	$(PY) python tools/merge_gate.py $(BRANCH)

clean:
	rm -rf .venv __pycache__ src/__pycache__
