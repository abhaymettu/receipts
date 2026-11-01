#!/usr/bin/env python3
"""Stop / SubagentStop hook. Mode A by default: it never blocks.

Budget is under 50ms per turn, which rules out parsing the whole transcript -
a large session costs 30-170ms to parse in full. This reads only the tail of
the JSONL, enough to reconstruct the last turn, and hands anything expensive to
a detached process that runs after the turn has already been delivered.

Mode B (config "mode": "B") lets the deterministic checker block, and only the
deterministic checker. A model-judged claim never blocks anything.
"""

import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from assertion_gate.adapters.claude_code import _segment  # noqa: E402
from assertion_gate.checker import check                  # noqa: E402
from assertion_gate.prefilter import prefilter            # noqa: E402

HOME = os.path.expanduser("~/.claude/assertion-gate")
CONFIG = os.path.join(HOME, "config.json")
BLOCKS = os.path.join(HOME, "blocks.json")
TAIL_BYTES = 400_000   # comfortably more than one turn, bounded regardless of size
MAX_BLOCKS = 8         # never argue with the model more than this in one session


def config():
    try:
        with open(CONFIG) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def last_turn(path):
    """Reconstruct the final turn from the tail of the transcript."""
    with open(path, "rb") as fh:
        fh.seek(0, os.SEEK_END)
        size = fh.tell()
        fh.seek(max(0, size - TAIL_BYTES))
        chunk = fh.read()
    lines = chunk.split(b"\n")
    if size > TAIL_BYTES:
        lines = lines[1:]  # first line is a fragment
    records = []
    for line in lines:
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if rec.get("type") in ("user", "assistant") and not rec.get("isSidechain"):
            records.append(rec)
    turns = _segment(records)
    return turns[-1] if turns else None


def block_state():
    try:
        with open(BLOCKS) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def main():
    try:
        event = json.load(sys.stdin)
    except ValueError:
        return 0
    if event.get("stop_hook_active"):
        return 0  # we already spoke this turn; speaking again is a loop
    path = event.get("transcript_path")
    if not path or not os.path.exists(path):
        return 0

    turn = last_turn(path)
    if not turn or not turn["final_message"].strip():
        return 0
    if not prefilter(turn["final_message"])[0]:
        return 0

    cfg = config()
    if cfg.get("score", True) and turn["uuid"]:
        subprocess.Popen(
            [sys.executable, "-m", "assertion_gate.scorer", path,
             "--uuid", turn["uuid"], "--model", cfg.get("model", "sonnet")],
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, start_new_session=True)

    findings = check(turn["final_message"], turn["receipts"])
    if not findings or cfg.get("mode", "A").upper() != "B":
        return 0

    session = event.get("session_id") or ""
    state = block_state()
    used = state.get(session, 0)
    if used >= MAX_BLOCKS:
        return 0
    state[session] = used + 1
    os.makedirs(HOME, exist_ok=True)
    with open(BLOCKS, "w") as fh:
        json.dump(state, fh)

    reason = "The transcript contradicts this message:\n" + "\n".join(
        "- %s (%s): %s" % (f["claim"], f["check"], f["detail"]) for f in findings)
    print(json.dumps({"decision": "block", "reason": reason}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
