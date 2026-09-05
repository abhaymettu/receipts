#!/usr/bin/env python3
"""Score many real turns at once, for measurement rather than for the hook.

The hook scores one turn per Stop. Getting a sample big enough to say anything
about overclaim rates means driving the scorer over whole sessions, which is a
different shape: bounded concurrency, a turn cap, and a resumable log so a run
that dies partway is not wasted.

Usage:
    python3 tools/score_batch.py --sessions 5 --max-turns 40 [--log PATH]

Only prefiltered turns are scored; unflagged turns cost nothing and are the
overwhelming majority of any real session.
"""

import argparse
import glob
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from itertools import zip_longest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from assertion_gate.adapters.claude_code import parse       # noqa: E402
from assertion_gate.prefilter import prefilter              # noqa: E402
from assertion_gate.scorer import DEFAULT_LOG, PREVIEW_CHARS, score_and_log  # noqa: E402


def already_scored(path):
    """turn uuids already in the log, so a re-run resumes instead of duplicating."""
    seen = set()
    try:
        with open(path) as fh:
            for line in fh:
                try:
                    seen.add(json.loads(line).get("turn_uuid"))
                except ValueError:
                    continue
    except OSError:
        pass
    return seen


def candidates(sessions, seen):
    """(turn, source, prior) for prefiltered, unscored turns in the N largest logs.

    `prior` is every earlier turn in that session, which the scorer renders as a
    second evidence block: without it a turn summarising earlier work has no
    receipts of its own and scores unsupported.

    Round-robin across files rather than draining each in turn: the largest
    session alone supplies more prefiltered turns than any sane --max-turns, so
    a straight walk returns a sample of one session and per-session rates are
    then unmeasurable.
    """
    files = glob.glob(os.path.expanduser("~/.claude/projects/*/*.jsonl"))
    files.sort(key=os.path.getsize, reverse=True)
    per_file = []
    for path in files[:sessions]:
        main, _ = parse(path, previews=PREVIEW_CHARS)
        named = [t for t in main if t["final_message"].strip()]
        per_file.append([(t, path, named[:i]) for i, t in enumerate(named)
                         if t["uuid"] not in seen and prefilter(t["final_message"])[0]])
    return [item for row in zip_longest(*per_file) for item in row if item]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sessions", type=int, default=5)
    ap.add_argument("--max-turns", type=int, default=40)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--model", default="sonnet")
    ap.add_argument("--log", default=DEFAULT_LOG)
    args = ap.parse_args()

    seen = already_scored(args.log)
    todo = candidates(args.sessions, seen)[:args.max_turns]
    print("%d turns to score (%d already in %s)" % (len(todo), len(seen), args.log))

    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(score_and_log, t, s, args.model, args.log, prior)
                   for t, s, prior in todo]
        for i, fut in enumerate(futures, 1):
            try:
                done += fut.result()
            except Exception as exc:            # one bad turn must not kill the run
                print("  turn %d failed: %s" % (i, exc))
            if i % 5 == 0:
                print("  %d/%d turns, %d verdicts" % (i, len(todo), done))
    print("wrote %d verdict rows to %s" % (done, args.log))
    return 0


if __name__ == "__main__":
    sys.exit(main())
