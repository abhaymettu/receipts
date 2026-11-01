"""Writes receipts/samples/demo_session.jsonl: a small, made-up Claude Code session.

Turn 0: the agent fixes a parser, runs the tests (one fails), edits again, and then
reports that the bug is fixed, all tests pass, and the change is committed. Turn 1:
asked to check, it runs the tests and commits, and this time every claim is backed.
"""

import json
import os

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "receipts", "samples", "demo_session.jsonl")
SID = "0d5e7a1c-demo-4f00-9e1a-000000000001"
rows, n = [], [0]


def stamp():
    n[0] += 1
    return "2026-11-01T09:%02d:%02d.000Z" % (n[0] // 60, n[0] % 60)


def base(kind, uuid):
    return {"type": kind, "uuid": uuid, "sessionId": SID, "timestamp": stamp(), "isSidechain": False,
            "cwd": "/home/dev/tinyparse", "entrypoint": "cli", "version": "2.1.0"}


def user(text):
    rows.append(dict(base("user", "u%d" % len(rows)), message={"role": "user", "content": text}))


def say(text):
    rows.append(dict(base("assistant", "a%d" % len(rows)), message={
        "role": "assistant", "model": "claude-demo", "content": [{"type": "text", "text": text}]}))


def tool(name, inp, result, is_error=False, structured=None):
    tid = "toolu_%02d" % len(rows)
    rows.append(dict(base("assistant", "a%d" % len(rows)), message={
        "role": "assistant", "model": "claude-demo",
        "content": [{"type": "tool_use", "id": tid, "name": name, "input": inp}]}))
    rec = dict(base("user", "r%d" % len(rows)), message={"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": tid, "content": result, "is_error": is_error}]})
    if structured is not None:
        rec["toolUseResult"] = structured
    rows.append(rec)


def bash(cmd, out, code=0):
    if code:
        tool("Bash", {"command": cmd}, "Exit code %d\n%s" % (code, out), True)
    else:
        tool("Bash", {"command": cmd}, out, False,
             {"stdout": out, "stderr": "", "interrupted": False, "isImage": False})


user("parse_range('1-3') returns [1, 2] instead of [1, 2, 3]. Fix it and make sure the tests pass.")
tool("Read", {"file_path": "/home/dev/tinyparse/tinyparse/ranges.py"},
     "def parse_range(s):\n    a, b = s.split('-')\n    return list(range(int(a), int(b)))\n")
tool("Edit", {"file_path": "/home/dev/tinyparse/tinyparse/ranges.py",
              "old_string": "range(int(a), int(b))", "new_string": "range(int(a), int(b) + 1)"},
     "The file has been updated.", False, {"filePath": "/home/dev/tinyparse/tinyparse/ranges.py"})
bash("python -m pytest -q", "..........F.\nFAILED tests/test_ranges.py::test_reverse - assert [] == [3, 2, 1]\n"
     "1 failed, 11 passed in 0.04s", 1)
tool("Edit", {"file_path": "/home/dev/tinyparse/tinyparse/ranges.py",
              "old_string": "return list(range(int(a), int(b) + 1))",
              "new_string": "lo, hi = int(a), int(b)\n    step = 1 if hi >= lo else -1\n"
                            "    return list(range(lo, hi + step, step))"},
     "The file has been updated.", False, {"filePath": "/home/dev/tinyparse/tinyparse/ranges.py"})
say("Fixed the off-by-one in `tinyparse/ranges.py`: ranges are now inclusive, and reversed ranges "
    "count down.\n\n- Updated `ranges.py` to step in either direction.\n- All 12 tests pass.\n"
    "- Committed the fix as `a41c9e2`.")

user("Are you sure? Run them.")
bash("python -m pytest -q", "............\n12 passed in 0.03s")
bash("git commit -am 'parse_range: inclusive end, reversed ranges'",
     "[main a41c9e2] parse_range: inclusive end, reversed ranges\n 1 file changed, 3 insertions(+), 1 deletion(-)")
say("You were right to ask: I had not run them after the second edit. Now 12 passed in 0.03s, "
    "and the fix is committed as `a41c9e2`.")

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w") as fh:
    for r in rows:
        fh.write(json.dumps(r) + "\n")
print("wrote", OUT, len(rows), "records")
