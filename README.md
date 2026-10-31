---
license: mit
task_categories:
  - text-classification
tags:
  - llm-evaluation
  - hallucination-detection
  - agent-reliability
  - overclaim-detection
  - tool-use-verification
size_categories:
  - n<1K
---

# assertion-gate: Real-world overclaim detection in AI agent sessions

**One in nine claims an AI agent makes about the world is not backed by its own tool receipts.** 324 claims from 5 real Claude Code sessions, each checked against that session's receipts, give an estimated true overclaim rate near 11%. [claimcheck](https://abhaymettu.com/research/claimcheck/) runs the same check live, as a proxy in front of the model.

Write-up: [abhaymettu.com/research/assertion-gate](https://abhaymettu.com/research/assertion-gate/) · Dataset: [Hugging Face](https://huggingface.co/datasets/abhaymettu/assertion-gate)

## Dataset description

This dataset contains claim-level verdicts from scoring 534 real Claude Code sessions
(5 sessions, 44 scored turns, 324 extracted claims) with an assertion-gate scorer.
It includes hand-adjudicated ground truth labels for 50 claims, a full-set
comparison of two scorer variants with Wilson confidence intervals and McNemar's
significance test, per-type error analysis, and the scoring rubric as a standalone
artifact.

The dataset measures how often production AI agents assert things about external
state they never verified - "micro-overclaims" - using real session logs rather
than synthetic benchmarks with injected errors.

## What makes this different

Every published number on agent hallucination comes from synthetic injection:
take a fixed scenario, insert a fake error, measure whether the detector catches
the insertion. ToolBeHonest (Zhang et al., EMNLP 2024) and AgentHallu (Liu et al.,
ICLR 2026) both construct controlled scenarios with known hallucinations. HaluEval
(Li et al., EMNLP 2023) generates hallucinated responses to existing QA pairs.
This dataset measures the real thing - agents doing actual work, making actual
claims, some of which are unsupported by their own tool receipts.

The dataset's own construction illustrates the problem: the first report claimed
a 60% confirmed-overclaim rate and showcased four examples. Re-adjudication
against full session receipts retracted three of the four showcases as
overclaims of the report itself. The corrected rate is 26.0%.

## Data files

| File | Description | Rows |
|------|-------------|------|
| `labels.json` | Hand-adjudicated ground truth for 50 flagged claims | 50 |
| `fullset_v3.json` | Full-set comparison: v1 (no history) vs v3 (history) scorer verdicts on all 324 claims | 324 |
| `ab_v2.json` | A/B arm: v2 scorer (history + leniency sentence) on the 22 turns behind the 50 labelled claims | ~50 |
| `ab_v3.json` | A/B arm: v3 scorer (history alone) on the same 22 turns | ~50 |
| `rubric.json` | Standalone scoring rubric: claim types, pramana labels, verdict definitions, adjudication protocol | - |
| `analysis.json` | Computed statistics: CIs, McNemar's test, per-type breakdown, error analysis | - |
| `fullset_v3_batch2.json` | Batch 2: v3 verdicts on 4 headless sessions (see "Batches 2 and 3") | 35 |
| `reports/labels_batch2.json` | Batch 2 first-pass labels, superseded: assigned from scorer rationale, all `overclaim` | 31 |
| `reports/second_adjudication_batch2.json` | Batch 2 second rater, blind to receipts; the kappa = 0 result | 31 |
| `reports/labels_batch2_strict.json` | Batch 2 re-labelled under `docs/adjudication-strict.md` | 31 |
| `fullset_v3_batch3.json` | Batch 3: v3 verdicts on 6 interactive coding sessions, 39 turns | 544 |
| `label_candidates_batch3.json` | Batch 3 rows the scorer flagged `unsupported` | 119 |
| `reports/labels_batch3.json` | Batch 3 labels: two-rater gate, receipt adjudication, 30-claim second rating | 119 |
| `reports/raters/` | Every rater's raw output for batches 2 and 3, so each kappa is recomputable | - |
| `reports/frozen_labels.json` | Batch 1 + first-pass batch 2 as frozen on 2026-09-05; kept for the record, the batch 2 rows are superseded | 81 |

## Schema

### labels.json

Each row is one hand-adjudicated claim:

| Field | Type | Description |
|-------|------|-------------|
| `turn_uuid` | string | UUID of the turn containing the claim |
| `claim` | string | The claim text as scored |
| `type` | string | Claim type from the rubric (e.g. "Inference-as-Fact") |
| `tool_calls` | int | Number of tool calls in the flagged turn |
| `source` | string | Session file basename (anonymized) |
| `label` | string | Ground truth: `"overclaim"`, `"fp_turn_scope"`, `"fp_evidence_missed"`, or `"fp_not_a_claim"` |
| `adjudicated` | string | Adjudicator's notes explaining the label |

### fullset_v3.json

Each row is one claim scored by both v1 and v3:

| Field | Type | Description |
|-------|------|-------------|
| `turn_uuid` | string | Turn UUID |
| `session_id` | string | Session UUID |
| `source` | string | Session file basename |
| `claim` | string | Claim text |
| `type` | string | Claim type |
| `pramana` | string | Epistemic support category |
| `v1_verdict` | string | v1 verdict: supported / unsupported / uncheckable |
| `v1_why` | string | v1 rationale |
| `v3_verdict` | string | v3 verdict (null if v3 did not extract this claim) |
| `v3_why` | string | v3 rationale |

## Methodology

### Claim extraction and scoring

A Claude Code Stop hook captures agent sessions. A regex prefilter (<10ms, no
model call) identifies claim-shaped final messages (49.3% of 534 turns). Flagged
turns are scored by a Sonnet-class model that receives the turn's final message,
its tool receipts (never the message history), and optionally the receipts of up
to 8 earlier turns in the same session.

### Ground truth adjudication

50 claims flagged as unsupported by v1 were hand-adjudicated by reading every
receipt in the flagged turn untruncated, every receipt in every earlier turn of
that session, and tool calls as well as their results. This protocol was adopted
after two earlier passes produced incorrect labels (60%, then 54%, then 26.0%
confirmed) because they read only the scorer's rationale or only in-turn
receipts.

Ground truth labels distinguish four outcomes:
- **overclaim** (13/50): the claim is genuinely unsupported by any receipt
- **fp_turn_scope** (25/50): the checker flagged it, but evidence exists in an
  earlier turn the scorer did not see (v1) or mis-weighted (v3)
- **fp_evidence_missed** (9/50): the checker had the evidence in-turn but
  failed to match it to the claim
- **fp_not_a_claim** (3/50): the extracted text is not a verifiable assertion

### Scorer variants

- **v1**: No history. Scorer sees only the current turn's receipts.
- **v2**: History + a leniency sentence instructing the scorer to say "I cannot
  tell" when evidence is ambiguous.
- **v3** (adopted): History alone. Receipts of up to 8 earlier turns, capped at
  6000 characters, newest first. Prior messages excluded to prevent laundering
  overclaims into established facts.

## Results

### A/B on 50 labelled claims (22 turns)

| Variant | Flagged | TP | FP | Precision | Recall | F1 |
|---------|---------|----|----|-----------|--------|-----|
| v1 (no history) | 50 | 13 | 37 | 26.0% [16.2, 40.3] | 100% [77.2, 100] | 0.419 |
| v2 (history + leniency) | 15 | 7 | 8 | 46.7% | 53.8% | 0.500 |
| v3 (history alone) | 24 | 8 | 16 | 33.3% | 61.5% | 0.432 |

### Full-set (324 claims, 44 turns, 5 sessions)

| Variant | Unsupported | Supported | Uncheckable | No match |
|---------|-------------|-----------|-------------|----------|
| v1 | 126 (38.9% [33.7, 44.3]) | 102 | 96 | - |
| v3 | 91 (28.1% [23.5, 33.2]) | 122 | 59 | 52 (16.0%) |

v3 flags 10.8 percentage points fewer rows than v1.

### Ground truth comparison (44 claims matched between labels and full-set)

| Metric | v1 | v3 |
|--------|----|----|
| Precision | 26.5% [16.2, 40.3] | 39.1% [22.2, 59.2] |
| Recall | 100% [77.2, 100] | 69.2% [42.4, 87.3] |
| F1 | 0.419 | 0.500 |
| Accuracy | 26.5% | 63.3% |

McNemar's test (with continuity correction): chi2 = 11.115, p < 0.05.
v3 is significantly more accurate than v1 on labelled claims.

### Per-type v3 performance (on labelled claims)

| Type | n | TP | FP | FN | Precision | Recall |
|------|---|----|----|----|-----------|--------|
| Fabricated Tool Call | 14 | 2 | 3 | 1 | 40% | 67% |
| Fact Mismatch | 19 | 3 | 5 | 1 | 38% | 75% |
| False Absence | 4 | 2 | 2 | 0 | 50% | 100% |
| Inference-as-Fact | 6 | 2 | 0 | 1 | 100% | 67% |
| Count Mismatch | 4 | 0 | 2 | 1 | 0% | 0% |
| Source Fabrication | 2 | 0 | 2 | 0 | 0% | 0% |

### Error analysis

**v3 false positives (n=14)**: The dominant failure modes are turn-scope errors
(6/14, evidence exists in earlier turns but was mis-weighted) and evidence-miss
errors (6/14, evidence was in-turn but not matched to the claim). Two flags were
on text that is not a verifiable claim.

**v3 false negatives (n=4)**: Three of four missed overclaims were not extracted
by v3 at all (no_match), indicating a coverage gap in the claim extraction step
rather than a scoring error. One was scored uncheckable due to ambiguous evidence.

**Estimated true overclaim rate**: Adjusting the full-set v3 flag rate (28.1%)
by the measured precision (39.1%), the estimated true overclaim rate is
approximately 11.0% (range 6.2-16.6%) of extracted claims.

## Batches 2 and 3 (added 2026-09-11)

Full detail, with every number recomputable by `tools/report_batch3.py`, is in
`BATCH3-REPORT.md`. The short version:

**Batch 2 measured the wrong population and its kappa measured nothing.** All
four batch 2 sessions were headless one-turn `claude -p` jobs (a nudge
generator, a daily-summary merger, a text-ack classifier) with zero tool calls
anywhere. The first-pass labels transcribed the scorer's rationale and set all
31 candidates to `overclaim`. A second adjudicator that saw only claim text
returned kappa = 0.000 at 54.8% agreement; kappa against a single-class rater is
zero by construction, whatever the second rater says. Re-labelled under
`docs/adjudication-strict.md` (two blind gate raters, kappa 0.723, then a third
read with the user prompt visible): 27 `fp_not_a_claim`, 4
`unadjudicable_missing_source`, zero confirmed overclaims. The batch 2 rows in
`frozen_labels.json` are superseded by `reports/labels_batch2_strict.json`.

**Batch 3: 6 interactive coding sessions, 39 turns, 544 claims, 119 flagged.**
Two-rater gate (kappa 0.905), receipt adjudication with complete session
history, a 30-claim receipt-visible second rating (agreement 90%, kappa
0.845). Final: 11 `overclaim`, 47
`fp_turn_scope`, 37 `fp_evidence_missed`, 18 `uncheckable`, 6
`fp_not_a_claim`. Flag precision 9.2% (Wilson 95% 5.2-15.8%); confirmed
overclaims 2.0% of extracted claims (1.1-3.6%).

**Why batch 3 precision is a quarter of batch 1's.** Adjudication surfaced a
history bug: the batch tooling carried only turns that ended in assistant text
as history, so receipts in turns that ended in a tool call were invisible to the
scorer and, at first, to the adjudicators. On long autonomous sessions that is
most receipts. Re-reading with complete history moved 17 of 38 first-read
overclaims to `fp_turn_scope`. The scorer's flags were produced with the same
gap plus its own 8-turn / 6000-character cap, and 42% of its checkable flags are
`fp_turn_scope`. The fix is in the scorer and batch driver; the batches have not
yet been re-scored under it.

**Distribution-shift caveat.** Three batches are three populations: mid-length
interactive coding (precision 38%), headless no-tool jobs (nothing checkable),
long autonomous lanes with hundreds of receipts (9%). No single overclaim rate
for "Claude Code sessions" is supported by this data; rates are per population,
and the population must be named.

## Related work

**Synthetic hallucination benchmarks.** HaluEval (Li et al., EMNLP 2023) generates
hallucinated responses to QA pairs. ToolBeHonest (Zhang et al., EMNLP 2024)
diagnoses hallucination in tool-augmented LLMs across multiple levels. AgentHallu
(Liu et al., ICLR 2026) attributes hallucinations in multi-step agent trajectories.
All three use controlled scenarios with known ground truth; this dataset uses
uncontrolled real sessions.

**Consistency-based detection.** SelfCheckGPT (Manakul et al., EMNLP 2023) detects
hallucination by sampling multiple responses and measuring consistency. The
assertion-gate approach is complementary: it checks claims against tool receipts
rather than against other samples.

**RAG evaluation.** RAGAS (Es et al., EACL 2024) includes a faithfulness metric
that checks generated answers against retrieved context. The assertion-gate
extends this idea from RAG to agent tool-use traces, where the "context" is the
full receipt history rather than retrieved documents.

**Receipt-based verification.** The closest prior work is the tool-receipts
approach (arxiv 2603.10060), which also verifies agent claims against tool
outputs. The assertion-gate differs in using a two-stage architecture (structural
prefilter + async scorer) and in the pramana taxonomy for classifying the
epistemic support a claim would need.

**Epistemic taxonomy.** The pramana labels are adapted from Navya-Nyaya
epistemology as formalized for LLMs in the Pramana fine-tuning work
(arxiv 2604.04937). The six claim types are ported from NyayaVerifyBench.

## Limitations

1. **Single operator, single machine, single harness.** Every transcript is one
   person's work in one environment (Claude Code on macOS). False-positive causes
   found during calibration were environment-specific.

2. **Small labelled sample.** 13 confirmed overclaims in 50 labels. The ground
   truth has been wrong twice (60%, then 54%, then 26.0%). The current pass
   rests on receipts earlier passes did not read, which is a reason to prefer
   it, not a guarantee. Wilson CIs are wide: precision [22.2%, 59.2%] for v3.

3. **Single adjudicator for batch 1.** All 50 batch 1 labels were assigned by
   one person. Batches 2 and 3 use two blind gate raters (kappa 0.723 and
   0.905) and, for batch 3, a receipt-visible second rater on a 30-claim
   subset; see `BATCH3-REPORT.md`. Raters for batches 2 and 3 were model
   sessions following `docs/adjudication-strict.md`, not people.

4. **Subagent turns excluded.** Subagent transcripts are separate files; the
   measurement covers main session turns only.

5. **Receipts verify claims against tool outputs, not tool outputs against the
   world.** A tool that lies produces receipt-valid misinformation.

6. **History window.** Through batch 3 the scorer's history block omitted
   every earlier turn that ended in a tool call rather than text, on top of its
   8-turn / 6000-character cap. On long sessions most support lives there; 42%
   of batch 3 flags were `fp_turn_scope`. Fixed in the scorer and batch driver
   on 2026-09-11; not yet re-scored.

7. **16% no-match rate.** v3 did not produce a verdict for 52 of 324 claims
   that v1 extracted. Three of four v3 false negatives were no-match, indicating
   this is the primary recall bottleneck.

8. **No cross-harness validation.** All sessions are Claude Code. The herdr
   adapter exists but has not been used to produce labelled data.

## Ethical considerations

All session data is from the dataset author's own machine and work sessions.
Private project names have been anonymized (replaced with generic placeholders)
while preserving all quantitative data. No third-party data is included.

## Reproducing

The scorer, prefilter, checker, adapters, and evaluation tooling are at
[github.com/abhaymettu/assertion-gate](https://github.com/abhaymettu/assertion-gate)
(currently private pending further validation). The scorer requires the Claude
CLI and a Sonnet-class model. See `REUSE-MEMO.md` in the repo for adapter
instructions for other harnesses.

## Citation

```
@misc{mettu2026assertiongate,
  author = {Mettu, Abhay},
  title = {assertion-gate: Real-world overclaim detection in AI agent sessions},
  year = {2026},
  publisher = {Hugging Face},
  howpublished = {\url{https://huggingface.co/datasets/abhaymettu/assertion-gate}}
}
```
