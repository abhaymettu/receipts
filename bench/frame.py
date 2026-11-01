"""Step 0: the sampling frame. Which transcripts are in the benchmark, and why the rest are not.

Rule, applied in this order:
  1. Every main-thread Claude Code transcript under ~/.claude/projects/<project>/*.jsonl
     (subagent transcripts live in subdirectories and are not main threads) and every
     Codex rollout under ~/.codex/sessions, last written before CUTOFF.
  2. Drop test-harness sandboxes: project directories under a cache (`.cache`, swarm
     worktrees). Those are fixtures replaying other sessions.
  3. Drop any transcript that works on a private project the owner keeps out of
     public work (EXCLUDE_TERMS): the term appears in its project directory, its
     working directory, a prompt the user typed, any tool call's command or path, or the agent's own reports.
     Injected context (system reminders, memory indexes) does not count: it names
     those projects in nearly every session regardless of what the session did.
  4. Drop transcripts with no tool call or no end-of-turn report: nothing to check.

Writes data/frame.jsonl (private: local paths) and results/frame.json (counts only).
"""

import glob
import json
import os
import re
import sys
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from receipts.session import load  # noqa: E402

CUTOFF = datetime(2026, 11, 1, 10, 0, tzinfo=timezone.utc).timestamp()  # 05:00 CDT
_TERMS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "exclude_terms.txt")
EXCLUDE_TERMS = re.compile(open(_TERMS, "rb").read().strip() if os.path.exists(_TERMS) else rb"(?!x)x", re.I)  # private, gitignored
_INJECTED = re.compile(r"<system-reminder>.*?</system-reminder>|<(?:command|local-command)-\w+>.*?</(?:command|local-command)-\w+>", re.S)
SANDBOX = re.compile(r"-cache-|swarm-|/\.cache/")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def candidates():
    cc = glob.glob(os.path.expanduser("~/.claude/projects/*/*.jsonl"))
    cx = glob.glob(os.path.expanduser("~/.codex/sessions/**/*.jsonl"), recursive=True)
    return sorted(cc) + sorted(cx)


def entrypoint(path):
    with open(path, errors="ignore") as fh:
        for line in fh:
            if '"entrypoint"' in line:
                try:
                    return json.loads(line).get("entrypoint") or ""
                except ValueError:
                    return ""
    return ""


def scope_text(path, s):
    """What the session worked on: where it ran, what was asked, what it touched and said."""
    prompts = [_INJECTED.sub(" ", t.prompt) for t in s.turns]
    touched = [c.text for t in s.turns for c in t.calls] + [t.report for t in s.turns]
    return "\n".join([path, cwd(path)] + prompts + touched)


def cwd(path):
    with open(path, errors="ignore") as fh:
        for line in fh:
            m = re.search(r'"cwd":\s*"([^"]*)"', line)
            if m:
                return m.group(1)
    return ""


def inspect(path):
    row = {"path": path, "harness": "codex" if "/.codex/" in path else "claude-code"}
    if os.path.getmtime(path) >= CUTOFF:
        return dict(row, excluded="after_cutoff")
    if row["harness"] == "claude-code" and SANDBOX.search(os.path.basename(os.path.dirname(path))):
        return dict(row, excluded="test_sandbox")
    s = load(path)
    if EXCLUDE_TERMS.search(scope_text(path, s).encode()):
        return dict(row, excluded="private_project")
    reports = sum(1 for t in s.turns if t.report)
    if not s.n_calls or not reports:
        return dict(row, excluded="no_calls_or_reports")
    models = sorted({t.model for t in s.turns if t.model})
    return dict(row, excluded="", session_id=s.session_id, turns=len(s.turns), reports=reports,
                calls=s.n_calls, models=models, bytes=os.path.getsize(path),
                entrypoint=entrypoint(path) if row["harness"] == "claude-code" else "codex")


def main():
    paths = candidates()
    with ProcessPoolExecutor(max_workers=8) as pool:
        rows = list(pool.map(inspect, paths, chunksize=8))
    os.makedirs(os.path.join(ROOT, "data"), exist_ok=True)
    with open(os.path.join(ROOT, "data/frame.jsonl"), "w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    counts = {}
    for r in rows:
        key = "%s:%s" % (r["harness"], r["excluded"] or "included")
        counts[key] = counts.get(key, 0) + 1
    kept = [r for r in rows if not r["excluded"]]
    summary = {"candidates": len(rows), "included": len(kept), "by_reason": dict(sorted(counts.items())),
               "cutoff_utc": datetime.fromtimestamp(CUTOFF, timezone.utc).isoformat(),
               "included_turns": sum(r["turns"] for r in kept),
               "included_calls": sum(r["calls"] for r in kept)}
    with open(os.path.join(ROOT, "results/frame.json"), "w") as fh:
        json.dump(summary, fh, indent=2)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
