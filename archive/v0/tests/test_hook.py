"""Behavior tests for hooks/stop_hook.py, run as a subprocess against synthetic
Claude Code transcripts.

Not testing timing (measured elsewhere) - only decision behavior: Mode A never
blocks, Mode B blocks only on a deterministic contradiction, the loop guard and
the 8-block cap hold, and a missing transcript is silent.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(REPO, "hooks", "stop_hook.py")
HOME = os.path.expanduser("~/.claude/assertion-gate")
CONFIG_PATH = os.path.join(HOME, "config.json")
BLOCKS_PATH = os.path.join(HOME, "blocks.json")

CONTRADICTION_MSG = (
    "I verified this by using the WebFetch tool and it returned 200."
)
CLEAN_MSG = "I ran `ls` and saw one file in the directory."
UNFLAGGED_MSG = "Let me know if you want anything else changed."


def _write_config(cfg):
    os.makedirs(HOME, exist_ok=True)
    with open(CONFIG_PATH, "w") as fh:
        json.dump(cfg, fh)


def _record(rec):
    return json.dumps(rec) + "\n"


def _turn(session_id, uuid, final_message, ts="2026-09-03T00:00:00Z"):
    """One synthetic turn: a user prompt, a Bash tool call/result, then the
    final assistant text. Matches the record shape assertion_gate.adapters
    .claude_code._segment expects (see that file's module docstring)."""
    lines = []
    lines.append(_record({
        "type": "user",
        "session_id": session_id,
        "timestamp": ts,
        "message": {"role": "user", "content": "please do the thing"},
    }))
    lines.append(_record({
        "type": "assistant",
        "uuid": uuid,
        "timestamp": ts,
        "message": {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": "toolu_1", "name": "Bash",
                 "input": {"command": "ls"}},
            ],
        },
    }))
    lines.append(_record({
        "type": "user",
        "timestamp": ts,
        "message": {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "toolu_1", "content": "file1\n"},
            ],
        },
        "toolUseResult": {"stdout": "file1\n", "stderr": "", "is_error": False},
    }))
    lines.append(_record({
        "type": "assistant",
        "uuid": uuid,
        "timestamp": ts,
        "message": {
            "role": "assistant",
            "content": [
                {"type": "text", "text": final_message},
            ],
        },
    }))
    return "".join(lines)


def _write_transcript(tmpdir, name, session_id, uuid, final_message):
    path = os.path.join(tmpdir, name)
    with open(path, "w") as fh:
        fh.write(_turn(session_id, uuid, final_message))
    return path


def _run_hook(transcript_path, session_id, stop_hook_active=False):
    event = {
        "session_id": session_id,
        "transcript_path": transcript_path,
        "hook_event_name": "Stop",
        "stop_hook_active": stop_hook_active,
    }
    proc = subprocess.run(
        [sys.executable, HOOK],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        timeout=30,
    )
    return proc


def _clear_blocks():
    try:
        os.remove(BLOCKS_PATH)
    except OSError:
        pass


def main():
    failures = 0
    results = []

    def report(name, ok, detail=""):
        nonlocal failures
        results.append((name, ok, detail))
        if not ok:
            failures += 1

    # --- save existing state, restore at the end ---
    saved_config = None
    had_config = os.path.exists(CONFIG_PATH)
    if had_config:
        with open(CONFIG_PATH) as fh:
            saved_config = fh.read()
    saved_blocks = None
    had_blocks = os.path.exists(BLOCKS_PATH)
    if had_blocks:
        with open(BLOCKS_PATH) as fh:
            saved_blocks = fh.read()

    tmpdir = tempfile.mkdtemp(prefix="assertion-gate-test-")
    try:
        # 1. Mode A + contradiction -> stdout empty (Mode A never blocks)
        _write_config({"mode": "A", "score": False})
        _clear_blocks()
        path = _write_transcript(tmpdir, "t1.jsonl", "sess-modeA", "uuid-1",
                                  CONTRADICTION_MSG)
        proc = _run_hook(path, "sess-modeA")
        ok = proc.returncode == 0 and proc.stdout.strip() == "" and proc.stderr.strip() == ""
        report("mode_a_never_blocks", ok,
               "returncode=%r stdout=%r stderr=%r" % (proc.returncode, proc.stdout, proc.stderr))

        # 2. Mode B + same contradiction -> block with non-empty reason
        _write_config({"mode": "B", "score": False})
        _clear_blocks()
        path = _write_transcript(tmpdir, "t2.jsonl", "sess-modeB-block", "uuid-2",
                                  CONTRADICTION_MSG)
        proc = _run_hook(path, "sess-modeB-block")
        ok = False
        detail = "returncode=%r stdout=%r stderr=%r" % (proc.returncode, proc.stdout, proc.stderr)
        if proc.returncode == 0 and proc.stderr.strip() == "":
            try:
                payload = json.loads(proc.stdout)
                ok = (payload.get("decision") == "block"
                      and bool(payload.get("reason", "").strip()))
            except ValueError:
                ok = False
        report("mode_b_blocks_contradiction", ok, detail)

        # 3. Mode B + clean, fully supported final message -> stdout empty
        _write_config({"mode": "B", "score": False})
        _clear_blocks()
        path = _write_transcript(tmpdir, "t3.jsonl", "sess-modeB-clean", "uuid-3",
                                  CLEAN_MSG)
        proc = _run_hook(path, "sess-modeB-clean")
        ok = proc.returncode == 0 and proc.stdout.strip() == "" and proc.stderr.strip() == ""
        report("mode_b_clean_message_silent", ok,
               "returncode=%r stdout=%r stderr=%r" % (proc.returncode, proc.stdout, proc.stderr))

        # 4. stop_hook_active=True + Mode B contradiction -> stdout empty (loop guard)
        _write_config({"mode": "B", "score": False})
        _clear_blocks()
        path = _write_transcript(tmpdir, "t4.jsonl", "sess-loopguard", "uuid-4",
                                  CONTRADICTION_MSG)
        proc = _run_hook(path, "sess-loopguard", stop_hook_active=True)
        ok = proc.returncode == 0 and proc.stdout.strip() == "" and proc.stderr.strip() == ""
        report("stop_hook_active_loop_guard", ok,
               "returncode=%r stdout=%r stderr=%r" % (proc.returncode, proc.stdout, proc.stderr))

        # 5. Mode B + message the prefilter does not flag at all -> stdout empty
        _write_config({"mode": "B", "score": False})
        _clear_blocks()
        path = _write_transcript(tmpdir, "t5.jsonl", "sess-unflagged", "uuid-5",
                                  UNFLAGGED_MSG)
        proc = _run_hook(path, "sess-unflagged")
        ok = proc.returncode == 0 and proc.stdout.strip() == "" and proc.stderr.strip() == ""
        report("prefilter_not_flagged_silent", ok,
               "returncode=%r stdout=%r stderr=%r" % (proc.returncode, proc.stdout, proc.stderr))

        # 6. 8-block cap: same session_id, run 10 times, expect exactly 8 blocks.
        _write_config({"mode": "B", "score": False})
        _clear_blocks()
        path = _write_transcript(tmpdir, "t6.jsonl", "sess-cap", "uuid-6",
                                  CONTRADICTION_MSG)
        block_count = 0
        cap_detail = []
        cap_ok = True
        for i in range(10):
            proc = _run_hook(path, "sess-cap")
            out = proc.stdout.strip()
            if proc.returncode != 0 or proc.stderr.strip():
                cap_ok = False
                cap_detail.append("run %d: returncode=%r stderr=%r" % (i, proc.returncode, proc.stderr))
                continue
            if out:
                try:
                    payload = json.loads(out)
                except ValueError:
                    cap_ok = False
                    cap_detail.append("run %d: unparseable stdout=%r" % (i, out))
                    continue
                if payload.get("decision") == "block":
                    block_count += 1
                else:
                    cap_ok = False
                    cap_detail.append("run %d: unexpected payload=%r" % (i, payload))
        cap_ok = cap_ok and block_count == 8
        cap_detail.insert(0, "block_count=%d (expected 8)" % block_count)
        report("eight_block_cap", cap_ok, "; ".join(cap_detail))

        # 7. Nonexistent transcript_path -> exit 0, stdout empty, no traceback
        _write_config({"mode": "B", "score": False})
        _clear_blocks()
        missing_path = os.path.join(tmpdir, "does-not-exist.jsonl")
        proc = _run_hook(missing_path, "sess-missing")
        ok = proc.returncode == 0 and proc.stdout.strip() == "" and proc.stderr.strip() == ""
        report("missing_transcript_silent", ok,
               "returncode=%r stdout=%r stderr=%r" % (proc.returncode, proc.stdout, proc.stderr))

    finally:
        # --- restore saved state ---
        if had_config:
            with open(CONFIG_PATH, "w") as fh:
                fh.write(saved_config)
        elif os.path.exists(CONFIG_PATH):
            os.remove(CONFIG_PATH)

        if had_blocks:
            with open(BLOCKS_PATH, "w") as fh:
                fh.write(saved_blocks)
        elif os.path.exists(BLOCKS_PATH):
            os.remove(BLOCKS_PATH)

        shutil.rmtree(tmpdir, ignore_errors=True)

    for name, ok, detail in results:
        print("%-4s %s" % ("PASS" if ok else "FAIL", name))
        if not ok:
            print("     %s" % detail)
    print("\n%d/%d passed" % (len(results) - failures, len(results)))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
