# AGENTS.md

Notes for coding agents working in this repo.

## What this is

`receipts` checks the claims a coding agent makes in its end-of-turn report ("tests pass", "committed
as abc123", "I updated config.py") against the tool calls recorded in the same session. Verdicts are
`supported`, `contradicted` or `unbacked`. It is stdlib-only Python 3.9+, with no runtime dependencies.

## Layout

| Path | What it holds |
|---|---|
| `receipts/session.py` | `Call`, `Turn`, `Session`; `load()` picks the adapter |
| `receipts/adapters/` | Claude Code JSONL and Codex rollout parsers. Add a harness here. |
| `receipts/claims.py` | Regex claim extractor: claim families, hedges, negations |
| `receipts/llm.py` | Optional extractor that asks a small model to list claims. It never decides verdicts. |
| `receipts/rules.py` | Command classifiers (test, build, lint, commit, deploy, writes) and the pass/fail reader |
| `receipts/check.py` | One rule per claim kind, which turns receipts into a verdict |
| `receipts/hook.py` | Claude Code Stop hook |
| `receipts/cli.py` | `receipts demo / check / scan / hook / install-hook` |
| `bench/` | The benchmark pipeline: frame, run, label, adjudicate, score, stats, hook_cost |
| `results/` | Aggregate outputs of `bench/`. Generated, never edited by hand. |
| `paper/` | LaTeX source and the built PDF |
| `archive/v0/` | The earlier 5-session assertion-gate study, kept for the record |

## Commands

```bash
python -m pytest -q tests          # unit tests (pytest is the only dev dependency)
python -m receipts.cli demo        # run on the bundled sample session
python tests/make_demo.py          # regenerate the sample session
```

The benchmark reads the owner's private session logs, so it reruns only on a machine that has them.
`data/` is gitignored and must stay that way: it holds transcript paths and claim text.

## Rules

- Never commit anything under `data/`, raw transcripts, or claim text from private sessions.
- A change to `claims.py`, `rules.py` or `check.py` must keep `pytest` green. Score it with
  `python3 bench/score.py dev` before and after, on the dev split only. The test split is for the
  final number.
- No em dashes in prose or comments.
