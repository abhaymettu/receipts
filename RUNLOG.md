# RUNLOG

Lane: receipts (2026-11-01). Turn assertion-gate into an installable claim checker, a benchmark on hundreds of real sessions, and a paper.

## 2026-11-01 05:10 CST
- Moved the v0 dataset (5 sessions, 324 claims) and its tooling to `archive/v0/`; history kept.
- New package `receipts/`: adapters (Claude Code, Codex) -> Session; `claims.py` extractor; `rules.py` command classifiers; `check.py` verdicts (supported / contradicted / unbacked, with stale as a basis).
- `bench/frame.py`: 5,922 candidate transcripts -> 2,301 in frame (2,267 Claude Code, 34 Codex). Private-project rule narrowed to what a session works on (cwd, typed prompts, tool calls, reports), because injected memory names those projects in nearly every transcript.
- `bench/run.py`: 5,216 claims, 5,180 reported turns; raw checker: 4,203 supported, 938 unbacked, 75 contradicted. Unvalidated.
- Next: turn-level hand labels (two raters, dev/test split by session), score extractor + checker, hill-climb on dev, report on test.
