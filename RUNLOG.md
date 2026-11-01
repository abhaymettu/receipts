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

## 2026-11-01 06:40 CST (finish)
- Judge scores on test: Sonnet e2e flag P 0.557 R 0.315, verdict kappa 0.52; Haiku P 0.307 R 0.524. Hook default is now the judge engine; rules stay as `--engine rules`.
- Paper: `paper/main.tex` -> `paper/main.pdf` (tectonic, 9 pages), "Claims Without Receipts: How Often Coding Agents' Reports Go Unbacked, and Why Receipt Rules Cannot Tell". `paper/NUMBERS.md` maps each number to a results key; `paper/SUBMIT.md` has the arXiv steps (not submitted).
- README, `site/writeup.md`, `site/meta.json`, `site/launch-post.md` (draft, not posted). humanizer pass, then inmyvoice: README 90 -> 100 (fixed a colon reveal and a trailing rhythm line), writeup 100, launch post 100.
- Privacy: `bench/frame.py` named the excluded private projects in its regex. Moved the terms to gitignored `data/exclude_terms.txt` and rewrote the 15 unpushed commits so no public commit carries them; pushed history was already clean. `.hillclimb/` added to .gitignore. gitleaks: no leaks. Added LICENSE (MIT).
- Tests: 33 passed.

## 2026-11-01 06:39 CST: fresh-clone proof
Published: main fast-forwarded from receipts-v1, then merged the old remote main tip (ef33807) with the ours strategy so its history stays reachable without a force push. Repo renamed assertion-gate -> receipts, description and topics set.
Clean clone into a new temp dir, pipx with PIPX_HOME and PIPX_BIN_DIR inside it (PATH notice trimmed; tests run with the clone installed editable):

```
$ git clone https://github.com/abhaymettu/receipts
$ pipx install git+https://github.com/abhaymettu/receipts
creating virtual environment...
determining package name from 'git+https://github.com/abhaymettu/receipts'...
creating virtual environment...
installing receipts from spec 'git+https://github.com/abhaymettu/receipts'...
done! ✨ 🌟 ✨
  installed package receipts 1.0.0, installed using Python 3.14.7
  These apps are now available
    - receipts
$ receipts --version
receipts 1.0.0
$ receipts demo
<tmp>/pipx/venvs/receipts/lib/python3.14/site-packages/receipts/samples/demo_session.jsonl  (claude-code, 2 turns, 6 tool calls)
  turn 0   UNBACKED       works          Fixed the off-by-one in `tinyparse/ranges.py`: ranges are now inclusive, and reversed ranges count down.
           -> nothing was run after the last code change
  turn 0   ok             file_change    Updated `ranges.py` to step in either direction.
           -> a receipt writes ranges.py
  turn 0   CONTRADICTED   test_pass      All 12 tests pass.
           -> last test run failed: `python -m pytest -q` -> FAILED tests/test_ranges.py::test_reverse - assert [] == [3, 2, 1]
  turn 0   UNBACKED       commit         Committed the fix as `a41c9e2`.
           -> commit a41c9e2 appears in no receipt
  turn 1   ok             test_pass      Now 12 passed in 0.03s, and the fix is committed as `a41c9e2`.
           -> `python -m pytest -q` passed after the last code change
  turn 1   ok             commit         Now 12 passed in 0.03s, and the fix is committed as `a41c9e2`.
           -> commit a41c9e2 appears in a receipt
6 claims: 3 supported, 2 unbacked, 1 contradicted
$ python -m pytest -q tests
33 passed in 1.11s
```
