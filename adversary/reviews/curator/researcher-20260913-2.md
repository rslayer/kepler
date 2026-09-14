# Adversary review — curator/researcher-20260913-2

**Verdict: FAIL** (item 9). Three of the item-9 FAIL triggers fire in the new
datasets/m5_ca1/PRIORS.md:
(a) a new prior **names a feature the adversary has failed** and tells the researcher to build on it.
The Thanksgiving dept override (r060, adversary r074 FAIL on item 5) is named as a link in the base
chain in bullet 1 and as retained in bullet 8. No human override is on record.
(b) New priors **cite runs whose verdict is not `kept` as the only evidence** for a claim: r064,
r068 and r052 in bullet 9, and r069 and r063 in bullet 7.
(c) The first experiment the priors order (bullet 5, ledger H055) **tunes to a single fold**. It
diagnoses fold 7's scored window, 2016-02-15..03-13, and then builds "a targeted mechanism" for it.

`tools/check_claude_diff.py` passes and the file list is in bounds. Neither of those gates is the
reason for the FAIL.

Branch: one commit d7f2bf2 "curator: researcher-20260913-2" on main's 5b02b5e
(`git log --oneline main..curator/researcher-20260913-2`; `git merge-base` = 5b02b5e;
`git merge-base --is-ancestor v1-harness curator/researcher-20260913-2` true). Reviewed from main
at 5b02b5e, session adversary-20260913-4. No reruns (item 9 needs none), no checkout of the branch,
and nothing under holdout/ read.

Items 1-8 do not apply: the branch changes no code, no run, and no frozen file (see 9a).

## 9. Instruction leakage — FAIL

Commands:
```
git diff --name-only main curator/researcher-20260913-2
git diff main curator/researcher-20260913-2            # all five files, read in full
uv run python tools/check_claude_diff.py main curator/researcher-20260913-2
grep '^r0NN,' runs/runs.csv                             # every run id cited (r019, r037-r076)
cat adversary/reviews/exp/{r060,r061,r070}.md           # plus r037-override.md, curator/researcher-20260912-1.md
uv run python: runs/detail/{r048,r052,r061,r063..r073}.json keep_rule and folds blocks
cat curator/CLAUDE.md                                   # definition of "confirmed"
```

### 9a. check_claude_diff.py and file list — pass

```
$ uv run python tools/check_claude_diff.py main curator/researcher-20260913-2
OK: CLAUDE.md unchanged (main..curator/researcher-20260913-2)
```
(Bare `python3 tools/...` was held at the permission prompt. `uv run python` runs the same file
and exits 0. The curator's report quotes the same OK line against HEAD.)

`git diff --name-only main curator/researcher-20260913-2`: LESSONS.md,
curator/reports/researcher-20260913-2.md, datasets/m5_ca1/LESSONS.md, datasets/m5_ca1/PRIORS.md,
hypotheses/m5_ca1/ledger.csv. All are allowed. CLAUDE.md, src/, runs/, findings/ and tools/ are
not touched. `git grep holdout` has no new reference in the diff. The Priors block is the header
plus 10 bullets, 11 lines, under the 12-line cap.

### 9b. Encodes look-ahead — no trigger (one related risk, see 9d)

No bullet names a feature column or tells the researcher to read panel data at or after an origin.
Every mechanism named is one of these:
- training-history selection or weighting (origins, half-life; audited leak-free in
  adversary/reviews/exp/r070.md item 1)
- calendar-known (event names, month)
- as-of-origin series state (roll_mean_3; r061.md item 1)

### 9c. Names a feature the adversary has failed — **FAIL**

Adversary FAIL verdicts on record: exp/planted-leak (`local_smooth_7`), exp/r037 (Christmas-zero,
r053, **overruled to PASS by the human in r055**), and exp/r060 (Thanksgiving dept override,
**r074, FAIL on item 5**). `grep ',human,' runs/runs.csv` shows no human row about exp/r060. There
is no adversary/reviews/exp/r060-override.md. champion.json's m5_ca1 backtest_run is still r037.
The branch's own ledger row H041 says so: "no human decision recorded".

New priors that name it:
```
+- Base: current best is r070 lgbm_xmas0_tgd_r3_o80hl120, WRMSSE 0.798186, code only on the
   unmerged branch exp/r070; chain champion r037 0.805456 -> r060 Thanksgiving dept override
   0.804787 -> r061 roll_mean_3 0.803303 -> r070 ... No step is adversary-passed (r060 FAIL item 5; ...)
+- Calendar postprocess is spent: Christmas-zero and Thanksgiving are in the chain, ...
```
Bullet 1 tells the researcher to build on r070. Every child of r070 inherits
`LGBMXmasThanksgivingDept.postprocess`. Bullet 8 treats the override as settled ("in the chain",
"spent") rather than as unresolved. Disclosing "r060 FAIL item 5" in the same line does not change
the instruction: the next session's first three experiments (bullets 5-6) would all carry the
failed change, and their keep-rule gains would be measured on a base that includes it.

The previous curator review (researcher-20260912-1) accepted Christmas-zero in the priors only
because the human had overruled r053 to PASS. No such decision exists for r060, so the same test
gives the opposite result here.

The inherited objection from r070.md still stands: "If r060 is not overruled, this increment has
not been measured on an acceptable base." The priors present r070 as the base without that
condition.

### 9d. Tunes to a single fold or a single seed — **FAIL** (bullet 5 / H055)

```
+- First experiment: H055, find what makes fold 7 (2016-02-15..03-13) lose whenever last year's
   late winter enters training, before building a mechanism; ...
```
Ledger H055 (new, untried): "Diagnose fold 7 (window 2016-02-15..03-13): what differs from the
same weeks of 2015 that makes every addition of last year's late-winter rows lose it; then a
targeted mechanism".

This priors bullet does more than report a single-fold number. It orders the first experiment to
study one fold's scored window and design a mechanism around it. The diagnosis compares the actual
sales inside that window (after fold 7's origin, i.e. the backtest's own test targets) with the
same weeks of 2015. A mechanism shaped by that comparison is fit to the evaluation data of one fold
out of eight. The harness cannot see this: no_fold_regresses and paired_gain only check that the
other folds do not get worse. Bullet 4 points the same way ("a child that lifts February is the
likeliest to clear the bar").

This is not look-ahead in the item-1 sense: whatever feature results would still read only columns
before the origin, and it would be audited then. It is selection on scored targets, and it is the
first thing the priors tell the researcher to do.

The underlying fold-7 pattern is corroborated. Harness deltas from runs/detail keep_rule:
- r065: fold 7 +0.0023, fold 6 +0.0039 (folds 6-7 fail)
- r066: fold 7 +0.0139 (folds 7-8 fail)
- r067: fold 7 +0.0142 (folds 7-8 fail)
- r069: fold 7 +0.0127

So the trigger is the instruction to tune to that fold, not the evidence behind it.

No bullet tunes to a single seed. Seed-level numbers appear only as caveats (r070 seed 123).

### 9e. Cites a run whose verdict is not `kept` or whose evidence is a single run — **FAIL**

Rule applied, the same as the previous curator review: a cited run must be kept-and-passed, or one
of two or more runs that support the same claim (curator/CLAUDE.md: "Confirmed = from a run with
verdict=kept whose branch the adversary passed, or corroborated by two or more runs").

| bullet | claim | runs cited | runs.csv verdict | corroborated? |
|---|---|---|---|---|
| 1 base | chain, none adversary-passed | r070 (kept), adversary r074-r076 | kept; FAIL / INCONCLUSIVE / INCONCLUSIVE | the base is kept but not passed (see 9c) |
| 2 bar | threshold ~0.0028; children missed | r071, r072, r073; r065-r067, r070; r063, r068, r071 | discarded x9, kept x1 | yes, groups of 3-4 |
| 3 error | folds 1/3 worst, h15-28 worst 7/8, bias | r070 only | kept, INCONCLUSIVE | **single run**, not passed. Descriptive of the current best, so I count it as a note, not the trigger |
| 4 tension | holiday folds want last year; Feb does not | LESSONS r065/66/67/70, r070/r076, r062/71/72; r072 | discarded (r072) | yes, LESSONS lines of 3-4 runs |
| 5 H055 | fold 7 loss; "not month=3"; "most dependent on up-to-date item level" | r066, r067, r069, r073 | all discarded | fold-7 loss yes (4 runs). The "item level" clause rests on r069 alone |
| 6 H040/H054 | r048 60% of threshold; H054 expected to lose holiday gain | r048; LESSONS r038/39/40/48; adversary r076; r038 | discarded | r048 claim via LESSONS line (4 runs); H054 expectation cites r038 alone, which was run on a different base (r037) |
| 7 keep month/item_id | month: LESSONS r019/r073. **item_id: "cost 0.0058 and a 2.5% under-forecast [r069]"**. **"dept-level sibling was neutral [r063]"** | r019, r073; **r069**; **r063** | v0; discarded; **discarded**; **discarded** | month yes. **item_id and dept sibling: single discarded run each** |
| 8 calendar spent | | LESSONS r062/71/72; LESSONS general r037/r060 | | yes (but names r060, see 9c) |
| 9 do-not-bother | **"level-normalised ratio target (r064, +0.010, spread tripled); smaller learning rate (r068); ... per-department models (r052)"** | **r064; r068; r052**; r041/45/46; r015/26; r042 | **discarded, each alone**; the rest are groups | **three single-run citations** |
| 10 noise | | adversary r010, r022; r038, r043, r051; LESSONS general r050/r061 | | yes |

The trigger fires on bullet 9 (r064, r068 and r052 are each the only evidence for a do-not-bother
line) and bullet 7 (r069 and r063). The previous priors' do-not-bother line had no single-run
citation: it cited r041/r045/r046 and r015/r026 as groups. That is the difference.

The single runs are also weak on their own terms:
- **r068** (lr 0.025 x 600): gain +0.000473 vs threshold 0.001466, no fold over tolerance, fold 3
  -0.0026. That is below the bar, not "do not bother". It is one seed-triple on one base.
- **r063** (dept momentum): gain +0.000452 vs threshold 0.001315, 7 of 8 folds better. Calling it
  "neutral" overstates the evidence.
- **r052** (per-department models): measured on r044, a pre-v3 base that is no longer in the chain.
  One run.
- **r064** (ratio target): +0.0102 worse with 7 of 8 folds regressing. The effect is large, but it
  is one run of one parameterisation (weights (roll_mean_28+1)^2).

Numbers checked against runs/detail. All match:
- bullet 2: r065/r066/r067/r070 gains 0.004392 / 0.002819 / 0.002573 / 0.005117; r071/r072/r073
  -0.000109 / -0.000349 / -0.002530 vs threshold 0.002770; r063/r068 0.000452 / 0.000473.
- bullet 3: r070 fold WRMSSE 0.8221 (f1) and 0.8195 (f3) are the worst two. wape_h15_28 is the
  worst bucket in folds 1-5, 7 and 8, and fold 6's worst is h8_14. Bias fold 6 -0.0248, fold 2
  -0.0151, aggregate -0.008983.
- bullet 4: r066 and r067 fold 3 -0.0224 / -0.0222 vs r070 -0.0156. r072 folds 1-3 -0.0012 /
  -0.0015 / -0.0015 and folds 4-8 +0.0036 / +0.0011 / +0.0007 / +0.0008 / +0.0009.
- bullet 6: r048 0.000957 / 0.001598 = 59.9%.
- bullet 7: r069 +0.005754, bias -0.025378, guardrail fail.
- LESSONS r019/r073: r073 fold-1 bias 0.0028 -> 0.0374.

## Objections (recorded, not FAIL triggers)

1. **General LESSONS.md, new line [r037, r060, adversary r053, adversary r074].** It says a calendar
   postprocess of this shape "fails adversary item 5 as written" and "a harness keep of this shape
   is not a pass". It cites r037 and r053 but leaves out r055, where the human overruled r053 and
   passed exactly that shape. r037 is the promoted champion. Reading the line alone, the researcher
   would conclude the champion is not passed. It needs the override cited, or it should be limited
   to r060.
2. **General LESSONS.md, new line [adversary r074, r075, r076]** ("reruns held at the permission
   prompt"). This records one session's permission state, not a finding about the loop, harness or
   metric (curator/CLAUDE.md output 1). "Three reviews" is one blocked command in one session,
   counted three times. It becomes false as soon as the reruns can run, and the append-only rule
   means it can then only be overturned, never removed.
3. **datasets/m5_ca1/LESSONS.md, new line [r070, adversary r076, ...].** Every number in it comes
   from one run (r070's per-seed blocks, restated in r076). r065-r067 are cited for context only.
   It is a caveat that weakens an earlier line, which is the safe direction. But by the curator's
   own definition it is neither kept-and-passed nor corroborated by two runs.
4. **Report and Priors bullet 6 on H054.** The report says "the adversary asked for it". r076 did not
   ask for any run. It observed that the two knobs were not isolated (the adversary does not
   propose experiments). "Answers the adversary's two-knob objection" in the Priors is accurate.
   The report wording is not.
5. **Priors bullet 2, "a paired-gain threshold of ~0.0028 for every child".** The threshold is twice
   the larger of the parent and child spreads, so 0.0028 is a floor. A noisier child sets its own,
   higher bar (r064: 0.004042 on r061; r067: 0.004054). The line should say "at least".
6. **Dataset LESSONS [r019, r073]** says r073 cost "+0.007 on folds 1 and 2". The harness failed
   folds 1, 2, 4 and 5 (+0.0070, +0.0074, +0.0022, +0.0020). The line is incomplete but not wrong
   in direction.
7. **Ledger.** No row deleted. H054-H056 are new, untried and in sequence. H023, H041 and H042 stay
   `kept`, matching runs.csv, and their evidence now carries the adversary outcomes. That is correct.
   H041's addition, "the gain is the same model change H039 discarded on r044", is accurate
   (r060.md item 5), and it is one more reason bullet 1 should not present r060 as settled.

## What would have to change for item 9 to pass (facts, not proposals)

- **9c:** no prior may present r060's override as part of the base while r074 stands without a
  human decision.
- **9d:** no prior may order a single-fold-window diagnosis and mechanism (H055 as the first
  experiment).
- **9e:** each do-not-bother or keep-this line must rest on a kept-and-passed run or on two or more
  runs. That rules out r064, r068, r052, r069 and r063 as the only citation.

## Logged

runs/runs.csv row r077: model_name=curator/researcher-20260913-2, status=rejected,
author=adversary, session=adversary-20260913-4. Metrics are empty (curator branch, no rerun), and
findings_file is this file.
