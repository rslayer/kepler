# Running the loop

An operator's guide: setup, the commands, the agent roles, and how a research cycle runs from
hypothesis to champion.

## Setup

Requirements: Python 3.11 or 3.12, [uv](https://docs.astral.sh/uv/), a Kaggle account with the
M5 Forecasting competition rules accepted, and 16 GB of RAM or more for the full panel.

```bash
brew install libomp     # macOS only: LightGBM's wheel needs libomp.dylib
make env                # uv sync against the pinned versions in pyproject.toml
```

Put your Kaggle API token at `~/.kaggle/access_token` with mode 600 (the legacy `kaggle.json`
also works). The harness never reads, prints or moves it; the Kaggle CLI handles authentication.

**Behind a TLS-intercepting proxy?** uv and Python HTTPS calls may fail certificate checks. The
Makefile already exports `UV_SYSTEM_CERTS=1`; `make data` uses `truststore` so Python trusts the
system certificate store.

**Optional, for the foundation-model experiments only:** `uv pip install chronos-forecasting`.
It is not needed for the champion or any other model.

**No Kaggle account?** `python tools/make_fixture.py` writes synthetic data with M5's schema so
you can exercise the harness end to end. Never report a number produced from it.

## Commands

| Command | What it does | Who runs it |
|---|---|---|
| `make data DATASET=<id>` | Download M5, build the snapshot and SHA-256 manifest | Human, once per dataset |
| `make holdout DATASET=<id>` | Move the evaluation period out of the agent-visible snapshot into `holdout/` | **Human only**, once |
| `make backtest MODEL=<name> DATASET=<id>` | Rolling-origin backtest; appends to `runs/runs.csv` | Agents and human |
| `make report` / `make report RUN=<id>` | Ranked table of runs / error breakdown for one run | Anyone |
| `make score-holdout MODEL=<name> DATASET=<id>` | Score the frozen holdout once | **Human only** |
| `make promote BRANCH=exp/<run_id> DATASET=<id>` | Promotion gate; updates `champion.json` | **Human only** |
| `make verify-frozen` | Check that frozen files match the tagged baseline | Anyone |
| `make forecast ASOF=<date>` / `make evaluate` / `make live-report` | Serve the champion and track live accuracy | Anyone |
| `make scorecard` | Per-session keep and repeat rates → `LOOP_SCORECARD.md` | Anyone |

Useful `make backtest` options:

| Option | Effect |
|---|---|
| `PARENT=<run_id>` | Evaluate the keep rule against a parent run and write a verdict |
| `FIT_JOBS=<n>` | Parallel fit workers (default floor(vCPU / 4)); results are identical |
| `SEEDS=42,7,123` | Override the seed list |
| `BAG=off` | Score seeds separately instead of their averaged forecast |
| `AUTHOR=researcher SESSION=<id> HYPOTHESIS=<H###>` | Required for researcher runs |

The fold layout and season weighting are command-line options of the backtest module:

```bash
uv run python -m src.backtest --model recipe6_calendar_l2_cap511 --dataset m5_screen \
    --folds-scheme holdout_mirror --fold-weights season_match --parent <run_id>
```

Models are classes in `src/model.py`, registered in the `MODELS` dictionary. Adding a model is
adding a class and a dictionary entry.

## The agent roles

Each role is an AI agent session with its own instruction file. They do not share context; the
repository (runs, findings, ledger) is the only shared state.

**Researcher** (`CLAUDE.md`). Reads the ledger, the champion's error report and recent findings;
picks one hypothesis; writes it to the ledger as `pending`; implements it in `src/features.py` or
`src/model.py`; runs the backtest with the champion as parent; writes a findings file; updates the
ledger with the verdict and a one-line mechanism. One variable per experiment. It can never edit
the scorer, the fold logic or anything under `holdout/`.

**Adversary** (`adversary/CLAUDE.md`). Started fresh, without the researcher's reasoning. Reviews
each candidate against the eight-item checklist in [methodology.md](methodology.md#6-the-adversary),
reruns it on unseen seeds, and writes PASS, FAIL or INCONCLUSIVE to `adversary/reviews/`. It
never edits `src/`.

**Curator** (`curator/CLAUDE.md`). Rewrites the per-dataset priors (`datasets/<id>/PRIORS.md`)
from confirmed findings. Its changes merge only through `make merge-gate`, which an adversary
review must pass.

**Human.** Cuts the holdout, decides which queued candidates to score, scores the holdout, and
promotes champions. Owns the frozen files (`CODEOWNERS`).

## A research cycle, end to end

1. **Propose.** The researcher writes a `pending` ledger row and runs
   `python tools/ledger_check.py --hypothesis H###`. The check fails if the row is missing or if
   the same lever and mechanism already failed (unless a human reopened it).
2. **Screen.** Backtest on `m5_screen` with `holdout_mirror` folds and `season_match`, parent =
   the champion's screen run. A positive mean gain makes the candidate promising.
3. **Confirm.** Backtest on `m5_all`. Only `verdict=kept` advances.
4. **Adversary.** `tools/adversary_pass.sh` reviews new candidates one at a time.
5. **Queue.** `python tools/gate_queue.py` writes `runs/GATE_QUEUE.md`: candidates that cleared
   the screen, the strict keep rule and the adversary, ranked by gain.
6. **Holdout (human).** Score at most a couple of candidates per week with `make score-holdout`.
   Score only if the backtest gain is large enough to survive the noise floor.
7. **Promote (human).** `make promote` checks every condition and updates `champion.json`.

### Automation

- **Configuration search.** `tools/search_loop.py` runs a batch of model configurations from a
  JSON search space (`tools/search_space.json`) through the screen with a spring-fold gate, and
  logs each one:

  ```bash
  uv run python tools/search_loop.py --space tools/search_space.json \
      --baseline <run_id> --parent <run_id> --max-cycles 6 --max-hours 8
  ```

- **Unattended cycle.** `tools/cycle.sh <dataset>` runs researcher → adversary → curator →
  merge gate → scorecard as headless sessions and lists challengers ready for a holdout decision.
- **Parallel researchers.** `tools/orchestrate.sh --mandates A,B,C --hours 4` launches
  researchers with separate mandates (A: horizon, B: hierarchy, C: ensemble), each restricted to
  its own lever by `ledger_check.py --mandate`. Use `--dry-run` to see what it would launch.
  The adversary and the holdout stay serial.

## Auditing

| Tool | Checks |
|---|---|
| `make verify-frozen` | Frozen files and the rules block of `CLAUDE.md` are unchanged |
| `python tools/audit_runs.py` | Every run row matches its detail file and resolves to a commit |
| `python tools/ledger_check.py --dry` | The ledger is consistent; every rejected row has a mechanism |
| `python tools/validate_keeprule.py` | Re-evaluates the run history under the current keep rule |
| `python tools/cost_report.py` | Agent cost per run from `runs/sessions.csv` |

## Costs and timing

On a 14-core laptop, one full-panel backtest (8 folds × 3 seeds) takes from about 30 minutes
(the baseline, 3 workers) to 2–3.5 hours (the recipe and the 511-leaf champion). The screen takes about a
third of that, and the 4-fold `holdout_mirror` layout about half. Measured agent cost was about
$0.70 per researcher run. `tools/cloud/` has provisioning scripts and a benchmark template for
running on a larger cloud machine, which was planned but not used.
