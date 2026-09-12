# SPEC v2 — Self-improving loop (kepler, Step 3)

Purpose: make each researcher session start smarter than the last one did, without a human
rewriting its instructions. The mechanism is memory the researcher must read and write, a
curator agent that turns findings into priors, and mechanical gates that let a curator edit
merge without a human. Nothing in this spec changes how models are built or scored.

Hand this file to Claude Code at the repo root and say: "Read SPEC_v2_selfimprove.md and
execute Parts A through E in order. Stop after each part and report against the acceptance
criteria. Do not run any researcher, adversary, or curator session." Part F is run by the
human.

Frozen for this session: `src/scorer.py`, `src/report.py`, `src/score_holdout.py`, the fold
logic and keep rule in `src/backtest.py`, `src/features.py`, `src/model.py`. `make
verify-frozen` compares against `v1-harness` throughout and against `v2-loop` after Part E.

Definitions used below:
- **Session**: one launch of one agent role (researcher, adversary, curator). Every run and
  every file an agent writes carries its session id, `<role>-<YYYYMMDD>-<n>`.
- **Hypothesis id**: `H###`, assigned in `hypotheses/ledger.csv`. Every researcher run names
  exactly one.
- **Repeat**: a researcher run whose hypothesis id already had status `discarded` or `kept`
  in the ledger before that session started.

---

## Part A — Memory the researcher reads first and writes last

### Tasks
- Create `LESSONS.md`: one line per confirmed finding, format
  `- [<run_id>] <finding>. Evidence: <one clause>.` A lesson is confirmed when it comes from
  a `kept` run, or is corroborated by two or more runs. Seed it from the 25 v0 findings
  (r004–r028) and the three adversary reviews; expect roughly 8–12 lines, not 25.
- Create `hypotheses/ledger.csv` with columns exactly:
  `hypothesis_id, status, summary, first_run, last_run, sessions, evidence`
  where `status` is `untried`, `discarded`, `kept`, or `inconclusive`. Seed it with every
  distinct hypothesis the v0 researcher tried (one row each, status from its outcome under
  the v0 rule, marked `inconclusive` where the adversary rejected a kept run) plus every
  "next" idea named in a v0 findings file as `untried`. Expect roughly 20–30 rows.
- Add `session` and `hypothesis_id` columns to `runs/runs.csv`, appended after `verdict`.
  Extend `tools/migrate_runs_v1.py` (rename to `tools/migrate_runs.py`) to backfill both as
  empty for existing rows; idempotent as before. `make backtest` takes `SESSION=` and
  `HYPOTHESIS=` and refuses to log a researcher run without both.
- Update the Loop section of `CLAUDE.md`:
  step 1 becomes "Read LESSONS.md, then hypotheses/ledger.csv, then the last five findings
  files"; step 3 becomes "Pick an `untried` row from the ledger or add a new row; never
  re-run a `discarded` or `kept` row"; step 6 adds "Update the ledger row's status, last_run,
  and evidence"; a new final step: "Before stopping, append any confirmed finding to
  LESSONS.md, one line, citing the run."
- Replace the 25-run cap in step 8 with a time cap: "until told to stop or three hours have
  elapsed." (v1 backtests take ~5 minutes; 25 runs is ~2.5 hours of compute alone.)

### Acceptance
- `LESSONS.md` exists with 8–12 seeded lines, each citing a run id that exists in runs.csv.
- `hypotheses/ledger.csv` exists; every `discarded`/`kept`/`inconclusive` row cites a run id
  that exists; every v0 researcher run (r004–r028) maps to exactly one row.
- `runs.csv` has the two new columns; all existing rows carry empty values; the migration
  script is a no-op on a second run.
- `make backtest MODEL=seasonal_naive AUTHOR=researcher` without `SESSION` and `HYPOTHESIS`
  exits non-zero with a message naming both; with both it logs them.
- `CLAUDE.md` Loop section reads as specified; `make verify-frozen` is clean.

---

## Part B — Split CLAUDE.md into a locked block and a learnable block

### Tasks
- Insert two marker lines into `CLAUDE.md`:
  `<!-- RULES: human-owned. Agents never edit above this line. -->` after the Rules list, and
  `<!-- PRIORS: curator-editable below this line. -->` before the Domain notes.
  Everything above the first marker (identity, Rules, Loop) is the **Rules block**.
  Everything below the second marker (Domain notes, a new **Priors** section, Harness notes)
  is the **Priors block**. The Priors section starts as a short list distilled from
  LESSONS.md: what to try first, what not to bother with, and why.
- `tools/check_claude_diff.py <base_ref> <head_ref>`: exits 0 if and only if the diff to
  `CLAUDE.md` between the refs touches lines only inside the Priors block and both markers
  are unchanged. Prints the offending hunk otherwise.
- CODEOWNERS: `/CLAUDE.md @rslayer` stays, with a comment that the human gate applies to the
  Rules block; Priors-block merges are gated by Part D and Part E instead.

### Acceptance
- `tools/check_claude_diff.py` returns 0 for a synthetic branch that edits one Priors line,
  and non-zero for a branch that edits one Rules line, one that moves a marker, and one that
  edits both blocks. (Make the branches in a scratch clone; do not leave them in the repo.)
- `CLAUDE.md` renders with both markers and a Priors section of 4–8 lines.

---

## Part C — Curator

### Tasks
- Write `curator/CLAUDE.md`:

```
You are the curator for this repository. You turn what the researcher and adversary
found into better starting instructions for the next researcher session. You never
run experiments, never edit src/, never edit findings/, never edit the Rules block of
CLAUDE.md, and never touch holdout/.

Inputs, in order: runs/runs.csv (rows from the session you were given), the findings
files for those rows, adversary/reviews/ for any branch from that session, LESSONS.md,
hypotheses/ledger.csv.

Outputs, all on a branch named curator/<session>:
1. LESSONS.md: append confirmed findings only. Confirmed = from a run with verdict=kept
   whose branch the adversary passed, or corroborated by two or more runs. Cite the runs.
2. hypotheses/ledger.csv: reconcile every row the session touched; add rows for any
   "next" idea a findings file names; never delete a row.
3. CLAUDE.md, Priors block only: rewrite the Priors section so a fresh researcher
   would choose its first three experiments well. Every line cites a run id or a
   LESSONS.md line. Keep it under 12 lines. Do not touch anything above the PRIORS marker.
4. curator/reports/<session>.md: what you changed and why, one paragraph, plus the
   list of runs you treated as evidence.

Then run `python tools/check_claude_diff.py main HEAD` and include its output in the
report. Commit on the branch. Never commit to main.
```

- `curator/reports/` directory with `.gitkeep`.

### Acceptance
- `curator/CLAUDE.md` exists with the text above plus harness notes (paths, the exact
  `git`/`make` commands it needs, the session-id format).
- A dry run by the harness owner, using the v0 findings as the "session", produces a
  `curator/curator-dryrun` branch whose only `CLAUDE.md` change passes
  `check_claude_diff.py`, whose LESSONS.md additions all cite runs, and whose report exists.
  Delete the branch afterwards; the seeded files from Part A already reflect v0.

---

## Part D — Adversary v2

### Tasks
- Rewrite the harness notes in `adversary/CLAUDE.md` for the v1 harness: `SEEDS=` not
  `SEED=`; spreads are logged, so item 7 reads the `*_spread` columns and item 8 compares
  the rerun's means and spreads; `PARENT=` and the `verdict` column exist; a review may
  quote the harness's keep-rule block from `runs/detail/<run_id>.json` as evidence for
  item 5.
- Add checklist item 9, mandatory for every `curator/*` branch:
  "Instruction leakage: read the CLAUDE.md diff. FAIL if any new prior encodes look-ahead,
  names a feature the adversary has failed, tunes to a single fold or a single seed, or
  cites a run whose verdict is not `kept` or whose evidence is a single run. FAIL if
  `tools/check_claude_diff.py` is non-zero. Otherwise PASS."
- Adversary reviews of `curator/*` branches go to `adversary/reviews/curator/<session>.md`
  and are logged in runs.csv with `model_name=<branch>`, `author=adversary`, and
  `status=ok` (PASS) or `rejected`, as for `exp/*`.

### Acceptance
- `adversary/CLAUDE.md` has nine items; the `SEED=` text is gone; every `make` command in
  its harness notes runs without error against `v1-harness` (dry-run the commands with
  `KEPLER_RUNS_DIR` pointed at a scratch directory).

---

## Part E — Scorecard and merge gate, then tag

### Tasks
- `tools/scorecard.py`: for each researcher session in runs.csv, print
  `session, runs, kept, keep_rate, runs_per_kept, repeats, repeat_rate, best_wrmsse,
  wall_minutes`. Repeats are computed against the ledger state at session start (use the
  ledger's `sessions` column). Writes `LOOP_SCORECARD.md` as a table, newest session last,
  and one line: whether keep_rate and repeat_rate improved versus the previous session.
- `tools/merge_gate.py <curator-branch>`: exits 0 if and only if all of:
  (1) `check_claude_diff.py main <branch>` is 0;
  (2) an adversary review for the branch exists with verdict PASS;
  (3) every run id cited in the branch's LESSONS.md additions has verdict `kept` in
      runs.csv, or appears in two or more rows;
  (4) the scorecard's most recent session is not worse than the one before it on both
      keep_rate and repeat_rate (skipped, with a printed notice, when fewer than two
      sessions exist).
  On 0 it fast-forward-merges the branch into main and prints what merged. On non-zero it
  prints which condition failed and does nothing.
- HARNESS_CHANGELOG.md: add a v2 section, one paragraph.
- Commit on main as `feat: loop v2 (memory, curator, instruction gate, scorecard)`. Tag
  `v2-loop`. Point `make verify-frozen` at `v2-loop`; add `CLAUDE.md` Rules-block integrity
  to it: `python tools/check_claude_diff.py v2-loop HEAD` must be 0.

### Acceptance
- `python tools/scorecard.py` runs on the existing log and prints one row for the v0
  researcher session (25 runs, 2 kept, 0 repeats) and no rows for harness-owner runs.
- `tools/merge_gate.py` on a scratch branch with a PASS review and valid citations merges;
  on the same branch with the review verdict edited to FAIL it refuses and names condition 2.
- Tag exists; `make verify-frozen` is clean and includes the CLAUDE.md check.

---

## Part F — First cycle (human-launched, three fresh sessions)

1. Researcher: "Read CLAUDE.md and run the loop for three hours. Your session id is
   researcher-<date>-1." Human records start and end.
2. Adversary: "You are the adversary. Read adversary/CLAUDE.md and review every exp/*
   branch from researcher-<date>-1."
3. Curator: "You are the curator. Read curator/CLAUDE.md and curate session
   researcher-<date>-1."
4. Adversary again, on the curator branch only.
5. Human: `python tools/merge_gate.py curator/<session>`; then `python tools/scorecard.py`.
6. Repeat 1–5 twice more, on different days.

### Success criterion for v2
After three cycles, in `LOOP_SCORECARD.md`: repeat_rate is 0 in cycles 2 and 3, and
keep_rate or runs_per_kept is better in cycle 3 than in cycle 1. If neither improves, the
loop is not learning and the curator's merged diffs are the place to look.

### Human gates, permanently
- `make holdout` and `make score-holdout`; `runs/holdout.csv`.
- Any edit above the RULES marker in `CLAUDE.md`; any edit to frozen files; any change to
  keep-rule thresholds or fold design (a new spec, as v1 was).
- A weekly ten-minute read of `LOOP_SCORECARD.md` and the curator diffs merged since the
  last read. This is the only check for the loop optimizing the wrong thing; no script does it.

---

## Out of scope for v2
- Cron / unattended scheduling of the cycle (Step 4, after Part F's criterion is met once).
- Any change to `src/features.py`, `src/model.py`, the scorer, the keep rule, or the folds.
- Hermes Agent or any other runtime for the researcher (a separate A/B spec).
- RL on trajectories.
