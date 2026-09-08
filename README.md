# forecast-research-loop

Prototype harness for the M5 / Walmart forecasting research loop. See [SPEC.md](SPEC.md)
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
| `make data` | human, once |
| `make holdout` | human, once — cuts the final 28 days out of the agent-visible snapshot |
| `make backtest MODEL=<name>` | agents and human |
| `make report` / `make report RUN=<id>` | agents and human |
| `make score-holdout MODEL=<name>` | human only |
| `make verify-frozen` | human |

## Frozen files

`src/scorer.py`, `src/report.py`, `src/score_holdout.py`, and the fold logic in
`src/backtest.py` are human-owned (see [CODEOWNERS](CODEOWNERS)). No agent edits them.
`holdout/` is never read by any agent.

## Snapshot handling

`data/snapshot/*.parquet` is **not** committed — git-lfs is not in use and M5 competition
data is not redistributed here. `data/snapshot/MANIFEST.txt` **is** committed and is the
reproducibility anchor: every backtest verifies the SHA-256 of each snapshot file against
it and aborts on mismatch. Regenerate the snapshot with `make data`.
