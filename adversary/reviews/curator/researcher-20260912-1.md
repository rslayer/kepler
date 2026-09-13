# Adversary review — curator/researcher-20260912-1

**Verdict: PASS** (item 9, the only mandatory item for a curator/* branch). None of the five
FAIL triggers fires: no new prior encodes look-ahead, none names a feature the adversary has
failed (the one adversary FAIL it names, r037, was overruled to PASS by the human in r055 and is
treated as passed), none tunes to a single fold or seed, every non-kept run a prior cites sits in
a group of two or more corroborating runs, and `tools/check_claude_diff.py` exits 0. Three
objections are recorded below (two factual misstatements in the Priors block and one
instruction-leakage risk); none is a listed FAIL trigger, and the human should read them before
the merge gate runs.

Branch: one commit e772cfc "curator: researcher-20260912-1" on top of main fcc9f92
(`git log --oneline main..curator/researcher-20260912-1`; `git merge-base` = fcc9f92;
`git merge-base --is-ancestor v1-harness curator/researcher-20260912-1` true). Files touched
(`git diff --stat main curator/researcher-20260912-1`): CLAUDE.md (+34/-27 lines net 34/25),
LESSONS.md (+3), hypotheses/ledger.csv (14 lines: 6 rows modified, 2 rows added, none deleted;
main 38 rows + header, branch 40 rows + header), curator/reports/researcher-20260912-1.md (new).
`git diff --stat main curator/researcher-20260912-1 -- runs/ src/ findings/` is empty. Reviewed
from main at fcc9f92, session adversary-20260913-2, no reruns (item 9 needs none), nothing under
holdout/ read.

Items 1-8 do not apply: the branch changes no code, no run, and no frozen file.
`git grep -n holdout curator/researcher-20260912-1 -- CLAUDE.md LESSONS.md hypotheses/ledger.csv
curator/reports/` hits only the pre-existing Rules-block line 6 ("Never read, list, or reference
anything under holdout/"), which is unchanged from main.

## 9. Instruction leakage — PASS

Commands:
```
git diff main curator/researcher-20260912-1 -- CLAUDE.md LESSONS.md hypotheses/ledger.csv
python3 tools/check_claude_diff.py main curator/researcher-20260912-1
  -> OK: CLAUDE.md changes are confined to the Priors block (main..curator/researcher-20260912-1)   exit 0
grep '^r0NN,' runs/runs.csv   for every run id cited (r006-r028 v0; r033, r037-r055 v1)
cat adversary/reviews/exp/{r010,r022,r037,r037-override,r044,planted-leak}.md
python3: runs/detail/r037..r052.json keep_rule blocks (paired_gain, no_fold_regresses, per-fold bias)
```
(`python` is not on PATH here; `python3` runs the same file. The curator's report quotes the
identical OK line.)

### 9a. check_claude_diff.py — exit 0

Everything above and including the PRIORS marker is byte-identical between main and the branch.
The diff below the marker touches two places: the `Priors (` block (rewritten, 9 bullets, one
physical line each; the block from `Priors (` to the `---` is 11 lines, under the 12-line cap) and
one Harness-notes paragraph ("Registered on main: ... neither model is in MODELS on main"). The
curator rules allow Harness-notes edits "only to correct a fact"; the fact is correct:
`git branch --merged main | grep exp/` is empty, and src/model.py on main registers only
`seasonal_naive` and `lgbm_baseline` (lines 31, 59, MODELS at 124). r044 is the highest-numbered
kept run in runs/runs.csv (0.804061, spread 0.000604, parent r037).

### 9b. Look-ahead in any new prior — none

Every mechanism the new priors name is either calendar-known or reads history strictly before
the origin: "as-of-origin series state" / roll_mean_3 (columns origin_pos-3..origin_pos-1, audited
in adversary/reviews/exp/r044.md item 1); Christmas-zero (calendar `event_name_1`, audited in
r037.md item 1); the Thanksgiving override ("history strictly before the origin", ledger H038/H039,
findings/r050.md "reads only positions < origin_pos, asserted"); year-ago features at d-364 of a
horizon date (>= 336 days before the origin); event-aligned year-ago (H040, calendar-known
alignment). No prior tells the researcher to read at or after the origin.

### 9c. Names a feature the adversary has failed — no

Adversary FAIL verdicts on record: exp/planted-leak (`local_smooth_7`, items 1-2) and exp/r037
(Christmas-zero, item 5, row r053). r010 and r022 are INCONCLUSIVE, not FAIL. No new prior names
`local_smooth_7` or any centred/forward window. Christmas-zero is named in bullets 1 and 9, but
r037 was overruled to PASS by the human (row r055, adversary/reviews/exp/r037-override.md) and per
the human's instruction is treated as a passed run. r044 (roll_mean_3, named in bullets 1 and 3) is
INCONCLUSIVE (row r054), not failed, and the priors carry the adversary's caveat with it.

### 9d. Tunes to a single fold or a single seed — no listed trigger; one risk flagged (objection 3)

No bullet recommends a change on the strength of one fold or one seed. Bullet 2 names fold 1 as
the largest remaining error and explicitly says not to spend a standalone run on it; bullet 4
reports the December-fold deltas of r051 but its instruction is aggregate ("read the spread before
the gain"); bullet 9 says single-seed and single-fold gains are noise. See objection 3 for the
part of bullet 9 and ledger H041 that I consider an instruction-leakage risk short of a trigger.

### 9e. Citations: verdict and run count for every cited run

Rule applied (adversary/CLAUDE.md item 9, read with curator/CLAUDE.md's definition of confirmed):
a cited run must be kept-and-passed, or one of two or more runs corroborating the same claim.

| bullet | runs cited | runs.csv verdicts | corroborated? |
|---|---|---|---|
| 1 base | r033, r037, r055, r044, r054 | r033 baseline (human, no verdict); r037 kept + PASS (r055); r044 kept, INCONCLUSIVE (r054) | yes: r037 kept+passed; r044 kept (harness) and its caveat is stated in the same line |
| 2 fold 1 | r047, r048, r049, r050 | all discarded | yes: four runs on parent r044; fold-1 bias +0.0546/+0.0474/+0.0123/+0.0122 vs r044 +0.0542 (detail JSONs) |
| 3 series state | r043, r044 | discarded; kept | yes: two runs; r043 fold deltas all negative (8/8), r044 kept |
| 4 threshold | r038, r043, r051; r041, r045, r046 | all discarded | yes: three + three runs (see objection 1) |
| 5 year-ago | r038, r039, r040, r048 | all discarded | yes: four runs; Feb folds 6-8 positive in r038/r039/r040, r048 folds 6-8 -0.0011/-0.0019/+0.0001 |
| 6 long history | r008, r011, r013, r024; r038 | v0 rows (no verdict column); discarded | yes: four v0 + one v1 (see objection 2) |
| 7 Tweedie | r007, r017, r027, r028; r042, r017, r021, r022 | v0; r042 discarded | yes: LESSONS line [r042, with r017, r021, r022] already on main; r042 fold 3 +0.008033, bias -0.011465 (detail) |
| 8 do-not-bother | r041, r045, r046; r015, r026 | discarded; v0 | yes: LESSONS line [r041, r045, r046] on main; two v0 runs |
| 9 noise | adversary r010, r022; r038, r043, r051; r037, r055 | INCONCLUSIVE x2; discarded x3; kept+passed | yes |

No prior cites a single discarded run as sole evidence for a lever. Sub-claims that rest on one
run inside a corroborated bullet (r048 "60% of the threshold": 0.000957/0.001598 = 59.9%; r051
"December folds -0.004/-0.008": fold 2 -0.004097, fold 3 -0.008403) are descriptive of what that
run showed, and each number checks against its detail JSON.

Numbers verified against runs/detail/*.json and the adversary reviews: bullet 1 "66%" (r044.md
item 6: 65.9%); bullet 2 "bias +0.054", "~0.0008 aggregate against ~0.0013" (r049 gain 0.000653 /
threshold 0.001344; r050 0.000758 / 0.001316); bullet 3 "all eight folds" (r043 no_fold_regresses:
eight negative deltas); bullet 4 "missed by under 0.0004" (r038 0.000375, r043 0.000057, r051
0.000314 below threshold); bullet 5 "gain 0.005-0.017 on the Nov-Jan folds" (r038 folds 1-3
-0.0048/-0.0080/-0.0169; r039 -0.0133/-0.0117/-0.0136; r040 -0.0075/-0.0043/-0.0076, one value
slightly under 0.005); bullet 7 "Christmas fold by 0.008", "-0.011 bias" (r042). LESSONS lines:
[r037, r055] "0.0053 against a 0.0003 spread, 2,950 series improve and none worsen" matches
r037.md items 6-7; [r044, adversary r054] "66%", "1,543 of 3,049", "folds 2, 4 and 8", "discards
at seeds 11/99 on fold 1" matches r044.md items 5-7; [r047-r050] "h1-7 WAPE 0.865 vs 0.72-0.79",
"+0.055 / +0.047", "+0.012" match the detail JSONs (r044 fold-1 wape_h1_7 0.8655; r047 0.0546,
r048 0.0474, r049 0.0123, r050 0.0122).

Ledger: H031 and H033 statuses unchanged (kept, matching runs.csv); H022, H023, H027, H029 evidence
extended, status unchanged; H040 and H041 new (untried); H034 was never assigned on main, so the
new ids are in sequence; no row deleted. Both "next" ideas are named in the findings files the
rows cite (findings/r040.md: "the Feb-fold loss needs a mechanism (event-alignment, not level)";
findings/r050.md: "it would have to travel with a broader change").

## Objections (recorded, not FAIL triggers)

1. CLAUDE.md bullet 4, the line "80 origins, raw lags 1-3 and num_leaves 31 each showed a real
   aggregate gain and each missed by under 0.0004 [r038, r043, r051]" attributes all three misses
   to the self-raising threshold. Only r043 failed on the threshold alone. r038 also failed
   no_fold_regresses (fold 7 +0.003722 vs tolerance 0.002253) and r051 also failed it (fold 5
   +0.001738 vs tolerance 0.001688); both are in the detail JSONs' keep_rule blocks. A lower-noise
   retest of num_leaves 31 would still have to clear fold 5. "Real aggregate gain" for a run the
   harness discarded also sits awkwardly beside bullet 9's "only the harness verdict counts".
2. CLAUDE.md bullet 6, "on v1 it doubles the seed spread and loses folds 6-8 [r038]": r038's
   wrmsse_spread is 0.001924 against its parent r037's 0.000128, fifteen times, not double;
   findings/r038.md itself says "fifteen times". (Relative to r044's 0.000604 it is about three
   times.) The fold claim is right: folds 6/7/8 +0.001969/+0.003722/+0.001671.
3. Instruction-leakage risk, two places. (a) CLAUDE.md bullet 9, the clause "a gain confined to
   exactly the folds whose windows contain a known calendar event, with zero delta elsewhere, is
   structural, not luck, and a human can overrule item 5 on that basis [r037, r055]": the human's
   override file addressed this as a "follow-up for the next adversary spec", i.e. a change to the
   adversary's item 5, not a rule for the researcher; placing it in the researcher's priors tells
   the researcher which fold-concentrated gains get past the adversary. (b) hypotheses/ledger.csv
   row H041, "Thanksgiving-weekend override (H039 department-level ratios) carried on top of the
   next change that clears the threshold instead of as a standalone run", referenced from bullet 2
   ("Do not spend a standalone run on it (ledger H041)"): as written it re-runs the discarded H039
   as a second variable inside another run, which the Rules block forbids twice over ("One
   variable per experiment"; "Never re-run a discarded or kept row"), and a run that carried it
   would have part of its gain from a fold-1-only fix the keep rule could not see. The curator was
   following its own rule (add rows for every "next" idea a findings file names, and
   findings/r050.md names this one), and the row is untried, so this is not a prior that tunes to
   a fold; it is a row the human may want to reword or discard before a researcher picks it.

Note on LESSONS.md line [r044, adversary r054]: r044 is kept but not passed (INCONCLUSIVE). The
line records the adversary's caveat rather than a confirmed improvement, and its evidence spans
the harness run plus the adversary's two-seed rerun (five seeds in total), so I read it as
corroborated by two runs; it says "treat r044 as the working base, not a proven improvement",
which is the correct status.

## Logged

runs/runs.csv row r056, model_name=curator/researcher-20260912-1, status=ok, author=adversary,
session=adversary-20260913-2, metrics empty (no rerun for item 9), findings_file = this file.
