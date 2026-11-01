# Micro-overclaims in AI agent output: a receipt-verified dataset from organic coding-agent sessions

## What this is

A dataset of 324 claims extracted from 5 real Claude Code sessions (44 turns), each claim verified against the actual tool receipts from the session. 50 claims hand-adjudicated. Labels scaling to 100+.

## The numbers

- v1 scorer (no history): 38.9% of claims flagged unsupported. 26.5% precision, 100% recall.
- v3 scorer (with history): 28.1% flagged. 39.1% precision [22.2, 59.2], 69.2% recall [42.4, 87.3]. McNemar's test: significantly more accurate than v1 (chi2=11.115, p<0.05).
- Estimated true overclaim rate: ~11% (range 6-17%) of extracted claims.

One in nine claims the agent makes about the world is not supported by its own tool receipts.

## The self-catch

The first report claimed a 60% confirmed-overclaim rate and showcased four examples. Re-adjudication against full session receipts retracted three of the four. The report itself was overclaiming. The corrected rate is 26.0%. The gate's first catch was its own report.

## How it works

A Stop hook captures agent sessions. A regex prefilter (<10ms, no model call) identifies claim-shaped final messages (49.3% of 534 turns). Flagged turns are scored by a Sonnet-class model that receives the turn's final message and its tool receipts - never the message history, which would let the agent launder overclaims into established facts.

v3 adds receipts from up to 8 earlier turns (6000 char cap, newest first), fixing the dominant false-positive cause: evidence in an earlier turn the scorer couldn't see.

## Taxonomy

Six claim types (ported from NyayaVerifyBench): Fabricated Tool Call, Count Mismatch, Fact Mismatch, Inference-as-Fact, False Absence, Source Fabrication. Six pramana labels (Navya-Nyaya epistemology): pratyaksha, anumana, upamana, shabda, anupalabdhi, ungrounded. 100% of 324 real claims fall within the 6 types.

## Error analysis

v3's 14 false positives: 6 turn-scope, 6 evidence-miss, 2 not-a-claim. v3's 4 false negatives: 3 extraction failures, 1 uncheckable. 16% no-match rate is the primary recall bottleneck. Source Fabrication has 50% no-match; Inference-as-Fact 33%.

## Prior art

NabaOS (arXiv 2603.10060) is the direct predecessor: receipts-based detection, deterministic mode at 94.2% (fab-call) and 91.3% (false-absence), NyayaVerifyBench as its benchmark (synthetic, unreleased). did-it (Erick Shepherd) does deterministic per-claim reconciliation on 400 real Claude Code sessions - a tool, not a dataset. Transluce/Docent measures overselling at session level on 8,600 real sessions - LLM-judge flags, not claim-level receipt-verified labels. The false-success paper (ICML FAGEN 2026) contributes 616 human-validated labels on benchmark trajectories. Notre Dame's 20,574-session study finds 22.58% inaccurate self-reporting - anchored on developer pushback, missing uncaught overclaims.

The contribution: a released, claim-level, receipt-adjudicated dataset from organic coding-agent sessions, with a formal claim taxonomy. That conjunction is unclaimed as of September 2026.

## Limitations

Single operator, single machine, single harness. 13 confirmed overclaims in 50 labels. Ground truth has been wrong twice - the 60% to 26% re-adjudication swing demonstrates label instability. Single adjudicator; intra-rater and inter-rater reliability unmeasured (second blind adjudication in progress). 16% no-match rate. Receipts verify claims against tool outputs, not tool outputs against the world. The LLM-judge ceiling (0.65 AUROC on false-success detection) applies to non-deterministic claim types.

## Access

- Repo: github.com/abhaymettu/assertion-gate
- Dataset: huggingface.co/datasets/abhaymettu/assertion-gate
- Rubric: rubric.json (standalone - taxonomy works without the pipeline)
