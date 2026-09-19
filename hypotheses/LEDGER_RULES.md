# Ledger rules (SPEC v9 Part B) — the ledger is the loop's memory

The consolidated ledger is `hypotheses/m5_all/ledger.csv`. Columns:
`hypothesis_id, status, lever, summary, mechanism, first_run, last_run, best_wrmsse_hier,
holdout_wrmsse, rejected_by, evidence`.

`status`: kept | discarded | inconclusive | held | skipped | pending | reopen.
`lever`: feature | target | objective | architecture | horizon | hierarchy | ensemble |
recursive | data | other.
`rejected_by`: keep_rule | adversary | holdout | human | n/a.

## Rules
1. **No silent re-tries.** A hypothesis may not be re-run with the same `lever` + `mechanism`
   as an existing `discarded`/`held`/`inconclusive` row unless a human sets that row's status to
   `reopen` and appends a reason to its evidence. `tools/ledger_check.py` enforces this.
2. **Recombinations are new rows** that cite their parent hypothesis ids in `evidence`
   (e.g. "recombines H011 + H022"). They are not re-runs and are allowed.
3. **Session discipline.** Every researcher session opens by reading this file, the ledger, the
   champion row, and the calm-month diagnostic, and writes its chosen hypothesis as a `pending`
   row BEFORE running anything. Session end writes the verdict and one-line mechanism.
4. **The recursive dead-end is closed.** lever=`recursive` with a compounding-bias mechanism
   (H161, H161a/b/c, H163) is discarded and blocked. Reopen only with a genuinely new mechanism
   that does not rely on recursive 1-step compounding (a human decision).
5. **Holdout budget** (also enforced socially; see Part C `gate_queue`): at most **2 holdout
   scorings per week** across all mandates. Every holdout score is logged with the candidate's
   hypothesis id. A candidate that fails the holdout is marked `held`; its lever+mechanism cannot
   be re-scored without a `reopen`.
6. **Mandate scoping (Part C).** A researcher may only run hypotheses whose `lever` belongs to its
   mandate (A=horizon, B=hierarchy, C=ensemble). `ledger_check.py --mandate` enforces it.
