# Forecast Research Loop — operator entry points.
# Agents use `make backtest` and `make report`. Everything else is human-run.

SHELL := /bin/bash
UV := UV_SYSTEM_CERTS=1 uv
PY := UV_SYSTEM_CERTS=1 uv run --

MODEL ?=
DATASET ?= m5_ca1
RUN ?=
SEEDS ?= 42,7,123
JOBS ?= 1
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
	@echo "  ... PARENT=<run_id>        evaluate the keep rule against a v1 run; writes verdict"
	@echo "  ... SESSION=<id> HYPOTHESIS=<H###>   required when AUTHOR=researcher"
	@echo "make report                  table of all runs sorted by WRMSSE"
	@echo "make report RUN=<run_id>     error breakdown for one run"
	@echo "make score-holdout MODEL=<n> HUMAN ONLY: one shot against holdout/"
	@echo "make verify-frozen           diff frozen files against tag v3-engine + CLAUDE.md Rules-block integrity"
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
	$(PY) python -m src.backtest --model $(MODEL) --dataset $(DATASET) --seeds $(SEEDS) --jobs $(JOBS) --author $(AUTHOR) $(if $(PARENT),--parent $(PARENT),) $(if $(SESSION),--session $(SESSION),) $(if $(HYPOTHESIS),--hypothesis $(HYPOTHESIS),)

report:
ifeq ($(strip $(RUN)),)
	$(PY) python -m src.report
else
	$(PY) python -m src.report --run $(RUN)
endif

score-holdout:
	@if [ -z "$(MODEL)" ]; then echo "usage: make score-holdout MODEL=<name>"; exit 2; fi
	$(PY) python -m src.score_holdout --model $(MODEL) --dataset $(DATASET)

verify-frozen:
	@echo "--- diff vs v3-engine on frozen files (empty output = clean) ---"
	@git diff v3-engine -- src/scorer.py src/report.py src/score_holdout.py
	@$(PY) python tools/check_claude_diff.py v3-engine HEAD

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
