# Batch 3 report, and the batch 2 re-label

Date: 2026-09-11. Every number below is printed by `python3 tools/report_batch3.py`
from the files in `reports/`; nothing here is typed from memory.

## What was done

1. **Batch 3 scored** in a fresh workspace: six interactive coding sessions from
   `~/code` project slugs (one per project), the 40 largest prefiltered turns
   round-robin across them, v3 scorer (Sonnet, history block), 4 workers. The
   model call ran with `cwd` set to an empty directory
   (`ASSERTION_GATE_WORKSPACE`) and a log file that started empty, so no prior
   verdicts, project instructions, or memory could leak in. The `claude -p`
   sessions that scoring itself creates landed under one project slug, which
   was deleted afterwards so they cannot be sampled as "sessions" later. (Batch
   2's aborted first attempt at batch 3, two rows from the same headless
   population, is superseded by this run.)
2. **Batch 2 re-labelled** under a written protocol, `docs/adjudication-strict.md`:
   a checkability gate applied blind by two raters, then receipt adjudication
   for whatever passes.
3. **Batch 3 labelled** under the same protocol, with a receipt-reading second
   rater on a random 30-claim subset.
4. **Write-up updated** (`README.md`, the dataset card, and
   `reports/first-overclaim-report.md`) with the kappa finding and a
   distribution-shift caveat.

## Batch 3 numbers

| | |
|---|---|
| Sessions / turns / claims | 6 / 39 / 544 |
| Scorer verdicts | supported 229, uncheckable 196, unsupported 119 (21.9%) |
| Gate (two raters, blind) | 113 pass, 6 not a claim; agreement 118/119, kappa 0.905 |
| Final labels on the 119 flagged | overclaim 11, fp_turn_scope 47, fp_evidence_missed 37, uncheckable 18, fp_not_a_claim 6 |
| Precision of the v3 `unsupported` flag | 11/119 = 9.2%, Wilson 95% 5.2-15.8% |
| Confirmed overclaims per extracted claim | 11/544 = 2.0%, Wilson 95% 1.1-3.6% |

Per type (flagged / confirmed): Count Mismatch 19/5, Fabricated Tool Call 25/3,
Fact Mismatch 49/2, False Absence 9/1, Inference-as-Fact 11/0, Source
Fabrication 6/0. Per session, confirmed overclaims run 0 to 4.

Batch 1 (interactive coding sessions, 50 labels) put v3 precision at 38.1% and
the estimated true overclaim rate at about 11% of extracted claims. Batch 3 is
9.2% and 2.0%. That gap is the main finding, and most of it is explained below.

## The history bug, found during adjudication

The batch driver, the full-set re-scorer, the A/B tool, and the first version
of the dossier builder all built a turn's history from **named** turns only:
turns that ended in assistant text. In long autonomous sessions most turns end
in a tool call with no text, and every receipt in those turns was invisible to
the scorer's history block and to the adjudicator's dossier. One panel-build
turn showed 11 earlier receipts in its dossier; the session has 205.

Consequences, in order:

- The first receipt-adjudication pass, on the incomplete dossiers, labelled 38
  of 113 claims `overclaim`. After the fix, all 48 rows labelled `overclaim` or
  `uncheckable` were re-read against complete dossiers: 17 moved to
  `fp_turn_scope`, 9 to `uncheckable`, 1 to `fp_evidence_missed`, 11 stayed
  `overclaim`. The rows that had already found support (65) were left as read,
  since more evidence cannot remove support. Both reads are in
  `reports/raters/` and each re-read row carries its `first_read_label`.
- The v3 scorer that produced the 119 flags ran with the same incomplete
  history, plus its own 8-turn, 6000-character cap. 47 of 113 checkable flags
  (42%) are `fp_turn_scope`: the support exists, and the scorer never saw it.
  In batch 1 the same label was 25 of 50. The precision collapse from 38% to 9%
  is mostly a long-session effect on the history window, not a change in how
  often the agent overclaims.
- Batch 1's v3 numbers were produced by `tools/fullset_v3.py` and
  `tools/ab_eval.py`, which still carry the named-turn history; they are left
  as the record of what ran. Batch 1's labels were assigned by hand from raw
  files, so they are not affected. The fix is in `scorer.py`, `score_batch.py`,
  and `dossier.py`; a re-score of all three batches with complete history is
  the obvious next run and was not done here.

The 18 `uncheckable` rows are mostly one thing: the receipt schema caps tool
inputs at 400 characters, so the body of a heredoc write is not in any receipt.
Raising the cap for the dossier (not for the hook) would settle most of them.

## Second rater on batch 3

Receipt-visible second rating of a seeded random 30-claim subset. First round,
on the incomplete dossiers: agreement 66.7%, kappa 0.536 four-way, 0.569 on
overclaim-versus-not. Re-read round on complete dossiers: agreement 90.0%,
kappa 0.845 four-way, 0.783 on overclaim-versus-not (one of three overclaims
in the subset was called `fp_turn_scope` by the second rater). Complete
evidence raised agreement by 23 points; that is the same lesson as batch 1's
three adjudication passes, now with a number on it.

## Batch 2: what it was, and the kappa

All four batch 2 sessions came from the `-` project slug, which is where
headless `claude -p` jobs land: a body-state nudge generator, a daily-summary
merger ("fold the conversation below into the running structured summary"), and
a text-ack classifier. Every one of the 31 candidates came from a turn with zero
tool calls, and no session had a tool call anywhere. The scorer, told "(no tool
calls this turn)", flagged every declarative sentence.

The first-pass labels transcribed the scorer's rationale and set all 31 to
`overclaim`. The second adjudicator saw only the claim text and a tool-call
count, never a receipt, and returned 17 `overclaim`, 13 `fp_not_a_claim`, 1
`fp_turn_scope`. Its kappa against the first pass was 0.000 at 54.8% agreement.
That zero is structural: when one rater assigns a single label to every row,
expected agreement equals observed agreement and kappa is zero whatever the
second rater does. The number measured that the first pass had no variance,
not that the labels were bad or good.

Strict re-label: gate rater A passed 9, rater B passed 13, agreement 27/31,
kappa 0.723. (Rater A's prompt carried two worked examples beyond the protocol
text; rater B's did not. All four disagreements are on exactly the kind of row
the examples covered, so the kappa is an upper bound on protocol-only
agreement.) Third read with the user prompt visible, which the raters did not
have: every gate-passing row with a session on disk is a line the summariser
merged from user-supplied text. Final: 27 `fp_not_a_claim`, 4
`unadjudicable_missing_source` (the session file is gone; not guessed). Zero
confirmed overclaims. The 31 batch 2 rows in `reports/frozen_labels.json` are
superseded.

## Distribution shift

Three batches, three populations, three precisions:

| batch | population | flag precision |
|---|---|---|
| 1 | interactive coding sessions, mid-length | 38.1% |
| 2 | headless one-turn jobs, no tools | 0% (nothing checkable) |
| 3 | long autonomous coding lanes, hundreds of receipts | 9.2% |

The scorer's behaviour is a function of what it is pointed at. A headline
overclaim rate for "Claude Code sessions" is not a number this data supports;
a rate per population, with the population named, is.

Label set after this pass: batch 1 (50) + batch 2 strict (31) + batch 3 (119)
= 200 rows, 24 confirmed overclaims (13 + 0 + 11).

## Before any push

Nothing was pushed. Two things are his call first:

- Batch 2 labels (already public on the HF dataset) contain two personal names
  in claim text. Batch 3 claim text names four project directories and the
  author's own handle in 10 rows. The scrub in this pass only rewrote home-dir
  paths and session sources.
- `reports/labels_batch2.json` and the batch 2 rows of `frozen_labels.json` are
  kept as the record of the superseded pass; the dataset card says so.

## Commits (local only)

See `git log` from `5d9f1fd` forward: tooling, batch 3 data and batch 2
re-label, history fix, labels and write-up.
