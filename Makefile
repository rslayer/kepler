# Forecast Research Loop — operator entry points.
# Agents use `make backtest` and `make report`. Everything else is human-run.

SHELL := /bin/bash
UV := UV_SYSTEM_CERTS=1 uv
PY := UV_SYSTEM_CERTS=1 uv run --

MODEL ?=
RUN ?=
SEED ?= 42
AUTHOR ?= human

.PHONY: help env data holdout backtest report score-holdout verify-frozen clean

help:
	@echo "make env                     install pinned dependencies"
	@echo "make data                    download M5, build CA_1/FOODS_3 snapshot + MANIFEST"
	@echo "make holdout                 HUMAN ONLY: cut final 28 days out of the snapshot"
	@echo "make backtest MODEL=<name>   rolling-origin backtest, appends to runs/runs.csv"
	@echo "make report                  table of all runs sorted by WRMSSE"
	@echo "make report RUN=<run_id>     error breakdown for one run"
	@echo "make score-holdout MODEL=<n> HUMAN ONLY: one shot against holdout/"
	@echo "make verify-frozen           diff frozen files against tag v0-harness"
	@echo "KEPLER_RUNS_DIR=<dir> make backtest ...   log to <dir> instead of runs/ (adversary reruns)"

env:
	$(UV) sync --extra data
	$(PY) python -c "import lightgbm, pandas, numpy, sklearn, statsmodels, pyarrow; print('lightgbm', lightgbm.__version__); print('env ok')"

data:
	$(PY) python -m src.data

holdout:
	$(PY) python -m src.data --cut-holdout

backtest:
	@if [ -z "$(MODEL)" ]; then echo "usage: make backtest MODEL=<name>"; exit 2; fi
	$(PY) python -m src.backtest --model $(MODEL) --seed $(SEED) --author $(AUTHOR)

report:
ifeq ($(strip $(RUN)),)
	$(PY) python -m src.report
else
	$(PY) python -m src.report --run $(RUN)
endif

score-holdout:
	@if [ -z "$(MODEL)" ]; then echo "usage: make score-holdout MODEL=<name>"; exit 2; fi
	$(PY) python -m src.score_holdout --model $(MODEL)

verify-frozen:
	@echo "--- diff vs v0-harness on frozen files (empty output = clean) ---"
	@git diff v0-harness -- src/scorer.py src/report.py

clean:
	rm -rf .venv __pycache__ src/__pycache__
