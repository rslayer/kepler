# kepler

Forecasting research loop prototype: a harness for the M5 / Walmart agent loop. See [SPEC.md](SPEC.md)
for the full protocol. This README covers only local setup notes that the spec does not.

## Setup

```bash
brew install libomp     # macOS only: LightGBM's wheel dlopens libomp.dylib
make env                # uv sync against pinned versions in pyproject.toml
```

`make env` exports `UV_SYSTEM_CERTS=1`, which this machine needs for uv to fetch through
TLS interception.

## Operator commands

| command | who runs it |
|---|---|
| `make data DATASET=<id>` | human, once per dataset |
| `make holdout DATASET=<id>` | human, once — cuts the final 28 days out of the agent-visible snapshot |
| `make backtest MODEL=<name> [DATASET=<id>] [PARENT=<run>] [SESSION= HYPOTHESIS=]` | agents and human |
| `make report` / `make report RUN=<id>` | agents and human |
| `make score-holdout MODEL=<name> DATASET=<id>` | human only |
| `make promote BRANCH=exp/<run_id>` | human only; needs the holdout row |
| `make forecast ASOF=<date>` / `make evaluate` / `make live-report` | engine (serving plane) |
| `make merge-gate BRANCH=curator/<session>` / `make scorecard` | loop (v2) |
| `tools/cycle.sh <dataset>` | one unattended cycle (headless sessions) |
| `make verify-frozen` | human |

## Frozen files

`src/scorer.py`, `src/report.py`, `src/score_holdout.py`, and the fold logic in
`src/backtest.py` are human-owned (see [CODEOWNERS](CODEOWNERS)). No agent edits them.
`holdout/` is never read by any agent.

## Validating without Kaggle data

`tools/make_fixture.py` writes a synthetic fixture with M5's schema and dimensions
(823 series x 1913 days, fake numbers) into `data/raw/`, so `make data` and
`make backtest` can be exercised end to end without credentials. It is a harness test
only - never report a number produced from it.

## Layout (v3)

`src/contract.py` defines the data contract; `src/adapters/<name>.py` translate a dataset
into it (`m5_ca1` = Walmart store CA_1, all departments). Data lives under
`data/<dataset>/{raw,snapshot}` and `holdout/<dataset>/`. `champion.json` names the model
`make forecast` serves. Memory is per dataset under `datasets/<id>/` and
`hypotheses/<id>/`. Specs: SPEC.md (v0), SPEC_v1_harness.md, SPEC_v2_selfimprove.md,
SPEC_v3_engine.md; history in HARNESS_CHANGELOG.md.

## Snapshot handling

`data/*/snapshot/*.parquet` is **not** committed — git-lfs is not in use and M5 competition
data is not redistributed here. `data/*/snapshot/MANIFEST.txt` **is** committed and is the
reproducibility anchor: every backtest verifies the SHA-256 of each snapshot file against
it and aborts on mismatch. Regenerate the snapshot with `make data`.
