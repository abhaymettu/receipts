# Selective-reuse memo: nabaos/nabaos

Date: 2026-09-03. Source: https://github.com/nabaos/nabaos @ MIT, Rust, single crate `nabaos`
v0.3.7 (edition 2024). Files read in full: `src/runtime/receipt.rs` (385L),
`src/pea/pramana.rs` (462L), `src/llm_router/nyaya_block.rs` (1401L), plus `Cargo.toml`.
Paper: arXiv:2603.10060.

Decision for each candidate piece: **reuse as a library** (link the Rust against a transcript
adapter), **port** (reimplement the idea in our hook layer), or **skip**.

---

## 0. Threshold question: can we link the Rust at all?

**Skip — no library reuse of any module.** `nabaos` is one monolithic crate, not a workspace.
There is no per-module `Cargo.toml`, so nothing is separable at the build-target level without
manual extraction. The crate's dependency list includes tokio, axum, tower-http, reqwest,
wasmtime, bollard, rusqlite (bundled SQLite), ort/tokenizers, teloxide, serenity, postgres,
ratatui. `receipt.rs` and `nyaya_block.rs` also import the crate-local `crate::core::error`,
so even hand-lifting a single file is a port, not a link.

Against that: the hook path has a hard <50ms/turn budget and must spawn on every turn. A Rust
shim would be fast once built, but the build pulls a self-hosted agent OS to obtain ~400 lines
of hashing and string comparison, and it puts a compiled artifact and a toolchain between the
user and a gate that is supposed to be a few hundred lines of stdlib. Measured Python 3.14
cold start on this machine with `json`/`re`/`hashlib` imported is 10-20ms, which fits.

So every "adopt" below means a clean port of the idea into Python. The MIT license permits
either; this is an engineering call, not a licensing one.

---

## 1. Receipt schema — **PORT the field set, SKIP the signature and the store**

What they have: `ToolReceipt { id, tool_name, input_hash, output_hash, result_count:
Option<u32>, facts: HashMap<String,String>, timestamp_ms, duration_ms, signature }`.
Signature is HMAC-SHA256 (ring) over
`id|tool_name|input_hash|output_hash|timestamp_ms|result_count-or-"none"|facts_json`, with
facts canonicalized through a `BTreeMap` before serializing. `duration_ms` is deliberately
outside the signed message. Key is a random 32 bytes persisted at 0o600 via `load_or_generate`.
`verify_receipt` rejects receipts older than `MAX_RECEIPT_AGE_MS = 5 * 60 * 1000` before doing
any HMAC work. `ReceiptStore` is a `rusqlite` table with `lookup(id)` and
`list_by_tool(tool_name, limit)`.

**Port the field set.** `id, tool_name, input_hash, output_hash, result_count, facts,
timestamp_ms` becomes our receipt, one per tool call, so our ledger is field-comparable to
theirs and to the paper's numbers. Facts are canonicalized the same way (sorted keys) — and
we canonicalize the *input* too, which their code does not: `receipt.rs`'s doc comment says
"SHA-256 hash of the canonical JSON input parameters" but the function hashes whatever string
the caller hands it, with no key sorting anywhere in the file. Ours sorts keys before hashing
so identical calls hash identically.

**Skip the HMAC signature and the key file.** Their unforgeability property is real but it
buys a specific thing: the *runtime* mints receipts, the LLM sees only receipt IDs and never
the key, so a cited ID that does not exist proves a fabricated tool call. Our receipts are
derived post-hoc from a transcript the harness already wrote, and the model never cites
receipt IDs at all — we match claims against the ledger ourselves. There is no gap between
mint and check for a forger to sit in, and anything that can rewrite the JSONL can rewrite a
key file sitting in the same home directory. A signature here would be ceremony that costs
hook latency and proves nothing.

**Skip `ReceiptStore` / SQLite.** A ledger is a list built once per session parse and thrown
away, or appended as JSONL when we want it on disk. `lookup` and `list_by_tool` are a dict and
a list comprehension. Adding a database to a hook that must spawn in under 50ms is the wrong
trade.

**Skip `duration_ms` and the 5-minute staleness window.** Duration is not in any check we run.
The staleness window exists to stop receipt replay against a live runtime; offline scoring of
a month-old session log is a feature here, not an attack.

## 2. Pramana taxonomy — **PORT the labels, SKIP the validators and the aggregation**

**Port the six labels** — `pratyaksha` (direct observation), `anumana` (inference), `upamana`
(comparison), `shabda` (cited source), `abhava` (absence), `ungrounded` — as the scorer's
per-claim vocabulary, using their names so results stay comparable to the paper. The payoff is
the one the paper claims: a valid inference gets labeled inference instead of being scored as
either verified-as-fact or a hallucination. That distinction is the whole reason to carry a
six-way label instead of a boolean, and it is worth carrying.

**Skip the validator implementations.** They do not survive contact with real prose:
`pratyaksha()` is `observation.contains(expectation)`, a raw substring test.
`anumana()`'s Viruddha ("contradictory reason") check builds the literal string
`"not " + conclusion` and substring-searches the evidence for it. `upamana()` ignores its
`current_task` argument entirely (it is `_current_task`) and just picks the past episode with
the highest pre-supplied score, so there is no similarity computation at all.
`shabda_request()` has no code path that ever sets `pending: false`. `Savyabhichara`, one of
the three Hetvabhasa fallacy variants, is declared and `Display`-formatted but never
constructed by any validator. Our equivalent work is done by the deterministic checker (for
the checkable classes) and by an LLM pass (for the judgment classes); neither is a substring
test against a hand-passed expectation string.

**Skip the weighted aggregation and the 0.7 threshold.** `aggregate()` scores pratyaksha
1.0/0.0, anumana 1.0/0.2, upamana as a raw relevance float, shabda 0.9-if-answered, takes a
weighted mean with all weights defaulting to 1.0, and calls it validated at >= 0.7. Those
constants are not calibrated against anything in the repo. Collapsing per-claim labels into
one scalar also destroys exactly the information the taxonomy was adopted for. v1 reports
per-claim labels and per-claim verdicts; no aggregate score.

## 3. The six hallucination types — **PORT verbatim, names included**

Fabricated Tool Call, Count Mismatch, Fact Mismatch, Inference-as-Fact, False Absence, Source
Fabrication. Adopted as the scoring vocabulary with their exact names, so if this project's
real-world numbers ever sit next to NyayaVerifyBench's author-reported per-type detection rates
(94.2 / 87.6 / 89.1 / 82.3 / 91.3 / 78.4), the columns line up. This is the cheapest piece of
comparability available and there is no reason to invent different names.

## 4. Deterministic check ideas — **PORT. This is the most valuable piece.**

The paper's own per-type results argue for it: the receipt-lookup and count-comparison classes
score highest (94.2% fabricated tool call, 91.3% false absence) at the lowest cost, and they
need no model cooperation. Our four checks are the same class, retargeted from
receipt-ID-citation to trace-vs-prose:

- **Fabricated tool call** — the message names a tool that has no receipt in the ledger.
- **Count mismatch** — a stated number contradicts a receipt's `result_count`.
- **False absence** — "no results" / "nothing found" against a receipt with a non-empty result.
- **Unrun assertion** — "I ran/verified/tested X" with no invocation matching X.

Only these may block in Mode B. That deterministic-blocks / judgment-logs split is theirs and
is adopted whole.

## 5. Verifier shape and trust levels — **PARTIAL: port the reporting shape, defer the levels**

Their five trust levels (Fully Verified, Mostly Verified, Partial, Unreliable, Ungrounded) are
a good reporting shape, and their calibration table is the right template for how to report our
own numbers. But a trust level is only meaningful with a calibration behind it — "Fully
Verified" is worth something because they measured it correct 98.7% of the time. We have no
calibration until the first measurement lands, and shipping the labels before the numbers would
be asserting a confidence we have not observed, which is the exact failure this project exists
to catch. **Defer to v1.1**, after the hand-labeled precision spot check gives the levels a
number to stand on. v1 emits per-claim verdicts and a flag count.

## 6. `nyaya_block.rs` self-tagging channel — **SKIP entirely**

1401 lines parsing a `<nyaya>...</nyaya>` block the model is prompted to emit, with six modes,
a YAML chain compiler, and a hand-rolled quote-recovery heuristic. Two reasons to skip:

- It requires the self-tagging prompt to ride every LLM call. That is prompt weight on every
  turn and it puts verification on the response path, which is the thing this design exists to
  avoid.
- It depends on model cooperation, at their own measured compliance of ~92% (Claude), ~88%
  (GPT-4), ~85% (open-weight), with non-compliant responses conservatively treated as entirely
  ungrounded. The paper lists the resulting inequity between commercial and open models as
  future work. An offline scorer that runs its own classifier over the trace does not need the
  model's cooperation at all, which is the better answer to their own stated limitation.

Two defensive details from that file are worth stealing even though the parser is not:
`parse_response` locates the **last** `<nyaya>` tag rather than the first, so a model cannot
smuggle a fake block into what reads as user-facing text, and nested tags inside an extracted
block are stripped. If the scorer ever asks a model for structured output inside delimiters,
use last-tag-wins and strip nested delimiters. Noted, not ported.

---

## Summary table

| Piece | Decision | One-line reason |
| --- | --- | --- |
| Rust modules as a linked library | Skip | Monolithic crate, ~60 deps, crate-local error type; nothing separable |
| Receipt field set | Port | Field-comparable ledger, cheap; we also canonicalize input, which they do not |
| HMAC signature + key persistence | Skip | Receipts are derived from the trace post-hoc; no mint/check gap to forge in |
| `ReceiptStore` (SQLite) | Skip | A dict and a list; a DB fails the <50ms hook budget |
| Pramana labels | Port | Keeps valid inference labeled as inference instead of verified-as-fact |
| Pramana validators | Skip | Substring tests (`contains`, literal `"not X"`); dead `Savyabhichara` variant |
| Weighted aggregation, 0.7 threshold | Skip | Uncalibrated constants, and it collapses the labels we adopted it for |
| Six hallucination types | Port | Verbatim names so results line up with the paper's per-type table |
| Deterministic checks | Port | Highest detection, lowest cost, no model cooperation; the Mode B core |
| Trust levels + calibration table | Partial / defer | Right reporting shape, but needs our own calibration before it means anything |
| `nyaya_block` self-tagging | Skip | Prompt weight on every turn, and depends on model compliance |

## What we do not take from the paper's numbers

Every NabaOS detection figure is author-reported on NyayaVerifyBench, which is not released
(no dataset repo, no HuggingFace entry, no benchmark directory in the tree, checked
2026-09-03). The architecture is verifiable in the repo; the eval is not. They are cited here
as design evidence, never as a baseline this project has reproduced.
