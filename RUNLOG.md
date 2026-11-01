# RUNLOG

Lane: receipts (2026-11-01). Turn assertion-gate into an installable claim checker, a benchmark on hundreds of real sessions, and a paper.

## 2026-11-01 05:10 CST
- Moved the v0 dataset (5 sessions, 324 claims) and its tooling to `archive/v0/`; history kept.
- New package `receipts/`: adapters (Claude Code, Codex) -> Session; `claims.py` extractor; `rules.py` command classifiers; `check.py` verdicts (supported / contradicted / unbacked, with stale as a basis).
- `bench/frame.py`: 5,922 candidate transcripts -> 2,301 in frame (2,267 Claude Code, 34 Codex). Private-project rule narrowed to what a session works on (cwd, typed prompts, tool calls, reports), because injected memory names those projects in nearly every transcript.
- `bench/run.py`: 5,216 claims, 5,180 reported turns; raw checker: 4,203 supported, 938 unbacked, 75 contradicted. Unvalidated.
- Next: turn-level hand labels (two raters, dev/test split by session), score extractor + checker, hill-climb on dev, report on test.

## 2026-11-01 05:40 CST
- Labels: 400 uniformly sampled reported turns (seed 20261101), dev/test split by session hash (225/175). Rater A (Opus 5.5, isolated `claude -p`, Read/Grep over a per-turn dossier) on all 400; rater B on the 175 test turns (done). Adjudicator C running on test disputes (`bench/adjudicate.py rule`).
- Raters list ~5 claims per turn. Regex extractor: precision 0.79, recall 0.15. LLM extractor (`receipts/llm.py`, Haiku, report-only): precision 0.79, recall 0.74.
- Verdict rules are now the bottleneck: works/verified are too lenient (any run after the last edit counts), files cuts both ways. Hill climb on branch `hill-climb/checker`, setup in `.hillclimb/HILLCLIMB.md`, score = dev end-to-end flag F1 with LLM extraction.
- Live Stop hook catch recorded in `docs/live-hook/` (Haiku, stale "pytest passes" after a rename; hook 2.1 ms; agent re-ran tests). Hero: `docs/hero.png`.
- Hook cost over 2,301 sessions: p50 7.2 ms, p99 43 ms (`results/hook_cost.json`).
- Partial label prevalence: 13.3% of claims not backed (565 claims).
- Next: finish climb, adjudicate test, `bench/score.py test` + `agreement`, `bench/stats.py`, paper, README, site files, rename repo to receipts, push.

## 2026-11-01 06:10 CST (handoff point)
- Test gold: 175 turns, 950 claims (A and B agreed on 745; adjudicator C ruled 239 disputes; author audited 40 rulings, agreed with 37, reversed 3 scope errors: `data/label/overrides.json`, `results/adjudication_audit.json`).
- Inter-rater (A vs B, test): claim-set F1 0.888, verdict kappa 0.739, flag kappa 0.757 (`results/validity_agreement.json`).
- Prevalence from labels (400 turns, 2,082 claims, 293 sessions): 13.3% not backed, 95% CI 11.3 to 15.4 (session bootstrap). works 36.8%, tests 22.5%, verified 14.3%, files 11.9%, ran 5.5%, git 3.9%. 1-9 calls 5.1% vs 10+ calls 13 to 20%. Contradicted only 5 of 2,082 (`results/benchmark.json`).
- Rules climb (15 rounds, `.hillclimb/results.tsv`): dev flag F1 0.088 -> 0.201 (LLM extraction). On TEST the rules do not hold: flag precision 0.083, recall 0.153, verdict kappa ~0 (`results/validity_test_llm.json`; regex extraction `results/validity_test.json`). Main finding: deterministic receipt rules (the mechanism of proof-of-done, honestly, groundtruth) do not find unbacked claims in real sessions.
- Added `receipts judge` (model reads the dossier under `receipts/rubric.md`) and `RECEIPTS_ENGINE=judge` for the hook. Sonnet judge (rater S) and Haiku judge (rater H) running on test; score with `python3 bench/score.py judge:S` / `judge:H`.
- Next: judge scores -> decide hook default; `bench/stats.py`; writer subagent for paper (tectonic), README, site/*, SUBMIT.md; humanizer + inmyvoice; gitleaks; rename repo to receipts; push; fresh-clone proof.
