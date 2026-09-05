# First overclaim measurement

Status: draft, numbers filled in from the run described below. Every figure here
comes from a command executed in this repo, not from recall.

## What was measured

The scorer was run over prefiltered turns from the largest real Claude Code
transcripts on this machine, and each resulting verdict row was hand-labelled
against the turn's own receipt ledger as either a true overclaim or a false
positive.

Only turns that pass the structural prefilter are scored. Unflagged turns are
the large majority of any session and cost nothing.

- Driver: `tools/score_batch.py --sessions 5 --max-turns 20 --workers 6`, run twice
  (the log is resumable by turn uuid, so the second run appended rather than repeated)
- Stats: `tools/report_stats.py`, which recomputes every figure below from the log
- Model: `claude -p --strict-mcp-config --allowed-tools '' --model sonnet`
- Log: `~/.claude/assertion-gate/verdicts.jsonl`

## Prefilter and checker baseline

From `tests/test_acceptance.py`, part B, over the 10 largest transcripts:

| | |
|---|---|
| session logs | 10 |
| assistant turns with text | 534 |
| prefiltered | 263 (49.3%) |
| deterministic findings | 0 |

The prefilter is deliberately wide and the deterministic checker deliberately
narrow. The checker is the only layer permitted to block, so it stays silent
under doubt; nearly half of all turns are claim-shaped, and none of them could
be positively contradicted by their own ledger.

## Results

Driver run twice (`--sessions 5 --max-turns 20`, then again to widen coverage),
scoring **44 turns from 5 sessions into 324 claim verdicts**:

| verdict | rows |
|---|---|
| unsupported | 126 |
| supported | 102 |
| uncheckable | 96 |

Per session, flag rate varies by a factor of four, so a single global rate would
be misleading:

| session | turns | claims | unsupported |
|---|---|---|---|
| f9592926 | 24 | 192 | 91 (47.4%) |
| 52cd0d82 | 5 | 29 | 17 (58.6%) |
| 734deff3 | 5 | 29 | 6 (20.7%) |
| 530c32a3 | 5 | 34 | 6 (17.6%) |
| 5ce0755a | 5 | 40 | 6 (15.0%) |

### Confirmed overclaim rate

50 of the 126 unsupported rows were drawn at random (seed 11, spanning all five
sessions) and hand-labelled against the turn's ledger and the session before it:

| label | rows |
|---|---|
| confirmed overclaim | 13 (26.0%) |
| false positive: turn-scoping | 25 (50.0%) |
| false positive: in-turn evidence missed | 9 (18.0%) |
| false positive: not a state claim | 3 (6.0%) |

**`unsupported` is right 26% of the time.** Projected over all 126 unsupported
rows, roughly 33 are real overclaims. Three quarters of what the scorer flags is
noise, which settles the design question this project opened with: nothing here
is fit to block on, and the deterministic checker rather than the scorer remains
the only layer permitted to block.

**Correction, and it is a large one.** Two earlier versions of this report put
this figure at 60.0% and then 54.0%. Both were wrong. Every one of the 50 labels
was then re-adjudicated against two things the first pass did not read: the
receipts of *earlier* turns in the same session, and the *untruncated* receipts
of the flagged turn itself. **20 of 50 labels changed** and the confirmed rate
fell from 54.0% to 26.0%.

The cause is worth stating plainly, because it is the same failure the project
exists to measure. The first labels were assigned partly by reading the scorer's
own `why` field, which only ever describes the current turn. The ground truth
inherited exactly the blind spot it was supposed to audit. The second pass was
better but read receipts through a 400-character preview, so in-turn evidence
that sat past the clip looked absent.

Corrections ran in **both** directions: 17 rows moved from `overclaim` to a false
positive, and 3 moved the other way (rows 0, 6 and 24, where a claim that looked
supported was not). Every changed row carries an `adjudicated` field in
`reports/labels.json` recording the receipt that settled it.

Three findings the earlier drafts reported are now withdrawn:

- **The NIH example was itself an overclaim.** The report previously offered "row
  104 cites an NIH URL that appears in no search result" as its showcase
  fabrication. The URL `nih.gov/news-events/nih-research-matters/decoding-inner-speech`
  appears in that same turn's own WebSearch receipts. It is a false positive.
- **The "20 lines to one" example was wrong in both directions.** The report said
  the claim ran "against a diff showing 36 lines replaced by 15". The actual
  in-turn diff is 28 lines removed and 7 added, and the new line is exactly the
  `Path(roundedRect:cornerRadius:style:.continuous)` form the claim describes. The
  claim's "20 lines" is a loose count of a 28-line removal; the report's "36 and
  15" came from neither.
- **The "backed out and parked" example is turn-scoped, not fabricated.** That
  turn's own evidence does show `git branch -D squashed` failing with "branch not
  found" — but failing because the branch was already gone, which is consistent
  with the back-out rather than contradicting it. The "parked" half is supported
  by an earlier bundle receipt.

### The dominant false positive is still turn-scoping

**68% of all false positives (25 of 37) are one species.** A turn that summarises
work finished several turns earlier carries no receipts of its own, and the
scorer, which sees a single turn, calls the summary a fabrication.

The second species is now large enough to matter on its own: **9 rows (18%) had
the evidence in the flagged turn all along**, and were missed on the first pass
because the receipt preview was clipped before the supporting line. Two of those
are screenshot claims, where the evidence is the `Read` call itself — an image
read returns no text, so no amount of scanning result bodies will ever find it.

The receipt-count split reported earlier **does not survive re-adjudication**:

| turn | labelled precision |
|---|---|
| >0 tool calls | 10 of 38 (26.3%) |
| 0 tool calls | 3 of 12 (25.0%) |

The earlier draft read this as a sharp separation (63.2% against 25.0%) and drew
a conclusion from it. Once the labels were corrected the two populations are
indistinguishable. Receipt count does not predict whether a flag is real; it only
predicted the old labelling error, which had systematically marked receipt-rich
summary turns as overclaims.

What does survive is the raw scorer behaviour: no turn with zero receipts ever
scored `supported` in the whole run (0 of 44 rows). With an empty ledger the
scorer has nothing to affirm against, so a receipt-free turn can only come back
unsupported or uncheckable.

### By claim type

| type | labelled precision |
|---|---|
| Inference-as-Fact | 3 of 6 (50.0%) |
| False Absence | 2 of 4 (50.0%) |
| Count Mismatch | 1 of 4 (25.0%) |
| Fact Mismatch | 4 of 19 (21.1%) |
| Fabricated Tool Call | 3 of 15 (20.0%) |
| Source Fabrication | 0 of 2 (0.0%) |

The earlier draft claimed the three types checkable against something concrete —
a number, a claimed absence, a cited source — were "right every time". They are
not. `Source Fabrication` is now 0 for 2: both rows were cited sources that the
turn's own search receipts contained. On counts this small no type is
distinguishable from any other, and the honest summary is that the type label
does not tell you whether to trust the flag.

The 13 surviving overclaims are the species worth catching:

- **A count with no ledger behind it.** "9 modified + 7 new files" — no `git
  status` or `--porcelain` receipt exists anywhere in that session, in-turn or
  earlier, in either the commands or their output.
- **A claimed absence never searched for.** "That's the only animation left",
  against 203 `withAnimation` occurrences still in the tree at that moment.
- **A search that did not cover what it is said to cover.** "I looked and did not
  find this framed as a measurement problem anywhere in the adjacent literature",
  when none of the seven searches that turn mentioned measurement.
- **A compound list where only part is real.** Four named LaunchAgents check out
  against receipts; `tunnel`, `digest` and `~/bin/backup` appear nowhere in the
  session at all.
- **A claim about pixels with no image ever read.** "It shows the old UI with none
  of the new sections", about a screenshot that was never opened.

### The fix, measured

The scorer now receives a second evidence block: the receipts (never the
messages) of up to 8 earlier turns in the same session, newest first, capped at
6000 characters. Prior messages are excluded deliberately — they are the agent's
own claims, and letting one summary be supported by an earlier summary would
launder an overclaim into an established fact.

Re-scoring the 22 turns behind the 50 labelled claims, against the corrected
labels:

| variant | flagged | true | false | precision | recall |
|---|---|---|---|---|---|
| v1 (no history) | 50 | 13 | 37 | 26.0% | 100% |
| v2 (history + leniency sentence) | 15 | 7 | 8 | 46.7% | 53.8% |
| v3 (history alone) | 24 | 8 | 16 | 33.3% | 61.5% |

**The history block helps much less than the earlier draft claimed.** Against
corrected ground truth it moves precision from 26.0% to 33.3%, not from 54% to
75%. Both numbers in that earlier sentence were artefacts of the bad labels.

**v3 remains adopted**, but the argument for it is now weaker and worth stating
honestly. v2 scores higher precision (46.7% against 33.3%) while losing one more
true overclaim (6 of 13 against 5 of 13). The earlier draft rejected v2 on the
grounds that it "buys precision by teaching evasion", citing 9 true overclaims
parked in `uncheckable` with 44% of them pleading truncation. Recomputed, those
figures are 4 parked and 1 pleading truncation for v2, against 3 and 0 for v3.
The direction is unchanged; the evidence for it is now four rows against three
and does not carry the weight the earlier draft put on it.

The defensible reading is narrower: at 13 confirmed overclaims in the sample, v2
and v3 are not distinguishable on precision, and v3 is preferred because it does
not instruct the model to answer "I cannot tell" when an honest answer is
available. Neither is remotely fit to gate.

### Full-set re-score

The A/B above covers only the 22 turns behind the 50 hand-labelled claims.
Running v3 over the full scored set (all 44 turns, 324 verdict rows, 5
sessions) gives the headline rate:

| variant | unsupported | supported | uncheckable | no match |
|---|---|---|---|---|
| v1 (no history) | 126 (38.9%) | 102 | 96 | -- |
| v3 (history) | 91 (28.1%) | 122 | 59 | 52 (16.0%) |

v3 flags 10.8 percentage points fewer rows. The 52 "no match" rows are claims
v1 extracted that v3 did not produce a verdict for at all -- the history block
gave the scorer enough context to skip them rather than flag them. On the 44
labelled claims that match full-set rows, v1 scores 27.3% precision at 100%
recall; v3 scores 38.1% precision at 66.7% recall.

Projected to the full set: 91 flagged rows across 5 sessions, about 18 flags
per session. Applying the labelled subset's v3 precision (38.1%), roughly 35
of the 91 would hold up as confirmed overclaims -- about 7 per session. That
projection rests on 8 true positives and should be read as an order of
magnitude, not a point estimate.

The raw comparison is in `reports/fullset_v3.json`.

### How labels were assigned

Labels are hand-assigned and recorded in `reports/labels.json`; every figure above
is recomputed from that file plus the raw log by `tools/report_stats.py`.

Adjudicating a row means reading, for one claim: every receipt in the flagged
turn untruncated, every receipt in every earlier turn of that session, and the
tool *calls* as well as their results. That last point is not incidental. Two
rows in this pass turned on evidence that exists only in a command — a `rm
App/Views/Avatar/AnimatedAvatarView.swift` and twenty `xcodebuild -configuration
Release` invocations — and a search over result text alone concludes, wrongly,
that no such receipt exists.

Two mechanical assists were tried and **neither is usable**:

1. Identifier-shaped tokens (paths, SHAs, PIDs, camelCase names) extracted from
   each claim and looked up anywhere in the session before the flagged turn. All
   43 token-bearing claims matched. A control matching the same claims against a
   randomly chosen *different* session still scored 15 of 43 (34.9%).
2. The same lookup restricted to earlier **tool results** only, which is the
   principled version — prior receipts are evidence, prior prose is not. On the
   then-labelled overclaims it found full token coverage 6 times; the
   different-session control found 8. The control scores higher than the real
   thing.

Token overlap does not discriminate at this claim length. Adjudication has to
read the receipt.

## Scope limits

Three limits on how far these numbers generalise:

1. **Single operator, single machine.** Every transcript is one person's work in
   one environment. The false-positive causes found during checker calibration
   were environment-specific (file writes routed through Bash heredocs rather
   than the Write tool), and a different operator would produce a different mix.

2. **The ground truth has been wrong twice.** The confirmed rate has now been
   reported as 60.0%, then 54.0%, now 26.0%. All 50 rows have been adjudicated
   against earlier-turn and untruncated in-turn receipts, which the first two
   passes had not been, so this pass rests on evidence the others did not read.
   That is a reason to prefer it, not a guarantee. Corrections this time ran in
   both directions (17 one way, 3 the other), so the remaining error is no longer
   obviously biased toward over-counting overclaims — but with 13 confirmed rows
   the sample is small, and one adjudicator labelled all of them.

3. **Subagent turns are excluded.** Subagent transcripts are not inline in the
   session log; they are separate `agent-*.jsonl` files. Of 1326 transcript
   files on this machine, 306 carry `"isSidechain": true` records and all 306 of
   those are `agent-*.jsonl`; zero main session logs contain any. The adapter's
   sidechain branch was verified against one of those files (1 sidechain turn,
   24 receipts, non-empty final message), but the measurement below covers main
   turns only.

