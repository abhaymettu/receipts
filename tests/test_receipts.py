import io
import json
import os

import pytest

from receipts import cli, hook
from receipts.check import check_session
from receipts.claims import extract
from receipts.session import load

SAMPLE = cli.SAMPLE


def _write(tmp_path, records, name="s.jsonl"):
    p = tmp_path / name
    p.write_text("\n".join(json.dumps(r) for r in records) + "\n")
    return str(p)


class Transcript:
    """Builds a Claude Code transcript one event at a time."""

    def __init__(self):
        self.rows, self.n = [], 0

    def user(self, text):
        self.rows.append({"type": "user", "sessionId": "s", "cwd": "/w", "message": {"content": text}})
        return self

    def say(self, text):
        self.rows.append({"type": "assistant", "message": {"model": "m", "content": [{"type": "text", "text": text}]}})
        return self

    def tool(self, name, inp, out="", err=False):
        self.n += 1
        tid = "t%d" % self.n
        self.rows.append({"type": "assistant", "message": {"model": "m", "content": [
            {"type": "tool_use", "id": tid, "name": name, "input": inp}]}})
        self.rows.append({"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": tid, "content": out, "is_error": err}]}})
        return self

    def bash(self, cmd, out="", code=0):
        return self.tool("Bash", {"command": cmd}, ("Exit code %d\n" % code if code else "") + out, bool(code))

    def edit(self, path, err=False):
        return self.tool("Edit", {"file_path": path}, "String to replace not found" if err else "updated", err)


def verdicts(tmp_path, t):
    return [(v.kind, v.verdict) for v in check_session(load(_write(tmp_path, t.rows)))]


def test_demo_session_has_all_three_verdicts():
    vs = check_session(load(SAMPLE))
    assert sorted(v.verdict for v in vs) == ["contradicted", "supported", "supported", "supported",
                                             "unbacked", "unbacked"]


@pytest.mark.parametrize("text", [
    "I'll run the tests next.", "Tests should pass now.", "I did not run the tests.",
    "Do the tests pass?", "[ ] Tests pass", "The user says tests pass.",
])
def test_non_claims_are_not_extracted(text):
    assert extract(text) == []


@pytest.mark.parametrize("text,kind", [
    ("All 12 tests pass.", "test_pass"), ("[x] Tests pass", "test_pass"),
    ("The build succeeds.", "build_pass"), ("Committed as `a41c9e2`.", "commit"),
    ("Pushed to origin.", "push"), ("I updated `config.py`.", "file_change"),
    ("The bug is fixed.", "works"), ("I verified the endpoint returns 200.", "verified"),
])
def test_claims_are_extracted(text, kind):
    assert [c.kind for c in extract(text)] == [kind]


def test_tests_pass_after_last_edit_is_supported(tmp_path):
    t = Transcript().user("fix").edit("/w/a.py").bash("pytest -q", "3 passed").say("All tests pass.")
    assert verdicts(tmp_path, t) == [("test_pass", "supported")]


def test_edit_after_last_test_run_is_stale(tmp_path):
    t = Transcript().user("fix").bash("pytest -q", "3 passed").edit("/w/a.py").say("All tests pass.")
    vs = check_session(load(_write(tmp_path, t.rows)))
    assert (vs[0].verdict, vs[0].basis) == ("unbacked", "stale")


def test_docs_edit_does_not_make_tests_stale(tmp_path):
    t = Transcript().user("fix").bash("pytest -q", "3 passed").edit("/w/README.md").say("All tests pass.")
    assert verdicts(tmp_path, t) == [("test_pass", "supported")]


def test_failing_last_run_contradicts(tmp_path):
    t = Transcript().user("fix").bash("pytest -q | tail -1", "1 failed, 2 passed").say("All tests pass.")
    assert verdicts(tmp_path, t) == [("test_pass", "contradicted")]


def test_no_test_run_is_unbacked(tmp_path):
    t = Transcript().user("fix").edit("/w/a.py").say("All tests pass.")
    assert verdicts(tmp_path, t) == [("test_pass", "unbacked")]


def test_earlier_turn_receipts_count(tmp_path):
    t = (Transcript().user("fix").edit("/w/a.py").bash("pytest", "3 passed").say("Done.")
         .user("summary?").say("All tests pass."))
    assert verdicts(tmp_path, t) == [("test_pass", "supported")]


def test_nothing_to_commit_contradicts(tmp_path):
    t = Transcript().user("commit").bash("git commit -am x", "nothing to commit, working tree clean", 1).say(
        "Committed the change.")
    assert verdicts(tmp_path, t) == [("commit", "contradicted")]


def test_failed_edit_contradicts_file_claim(tmp_path):
    t = Transcript().user("x").edit("/w/config.py", err=True).say("I updated `config.py`.")
    assert verdicts(tmp_path, t) == [("file_change", "contradicted")]


def test_codex_rollout(tmp_path):
    def item(payload):
        return {"type": "response_item", "payload": payload}
    rows = [
        {"type": "session_meta", "payload": {"id": "c1", "cwd": "/w"}},
        {"type": "turn_context", "payload": {"model": "gpt-x"}},
        item({"type": "message", "role": "user", "content": [{"type": "input_text", "text": "fix it"}]}),
        item({"type": "custom_tool_call", "name": "apply_patch", "call_id": "1",
              "input": "*** Begin Patch\n*** Update File: src/a.py\n@@\n-x\n+y\n*** End Patch"}),
        item({"type": "custom_tool_call_output", "call_id": "1", "output": "Success."}),
        item({"type": "function_call", "name": "shell", "call_id": "2",
              "arguments": json.dumps({"command": ["bash", "-lc", "pytest -q"]})}),
        item({"type": "function_call_output", "call_id": "2", "output": "Exit code: 1\n1 failed, 4 passed"}),
        item({"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "All tests pass."}]}),
    ]
    s = load(_write(tmp_path, rows))
    assert s.harness == "codex" and s.turns[0].model == "gpt-x"
    assert [(v.kind, v.verdict) for v in check_session(s)] == [("test_pass", "contradicted")]


def _run_hook(event, mode="block"):
    os.environ["RECEIPTS_MODE"] = mode
    out = io.StringIO()
    hook.main(io.StringIO(json.dumps(event)), out)
    return json.loads(out.getvalue()) if out.getvalue() else None


def test_hook_blocks_on_unbacked_claim(tmp_path, monkeypatch):
    monkeypatch.setattr(hook, "LOG", str(tmp_path / "log.jsonl"))
    t = Transcript().user("fix").bash("pytest", "3 passed").edit("/w/a.py").say("All tests pass.")
    out = _run_hook({"transcript_path": _write(tmp_path, t.rows)})
    assert out["decision"] == "block" and "code changed after the last test run" in out["reason"]
    assert _run_hook({"transcript_path": _write(tmp_path, t.rows), "stop_hook_active": True}) is None
    assert "systemMessage" in _run_hook({"transcript_path": _write(tmp_path, t.rows)}, mode="warn")


def test_hook_is_silent_when_backed(tmp_path, monkeypatch):
    monkeypatch.setattr(hook, "LOG", str(tmp_path / "log.jsonl"))
    t = Transcript().user("fix").edit("/w/a.py").bash("pytest", "3 passed").say("All tests pass.")
    assert _run_hook({"transcript_path": _write(tmp_path, t.rows)}) is None


def test_install_hook_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cli.install_hook(project=True, mode="warn")
    cli.install_hook(project=True, mode="block")
    stop = json.loads((tmp_path / ".claude" / "settings.json").read_text())["hooks"]["Stop"]
    cmds = [h["command"] for g in stop for h in g["hooks"]]
    assert len(cmds) == 1 and "RECEIPTS_MODE=block" in cmds[0]


def test_install_by_copying_into_place_is_supported(tmp_path):
    t = Transcript().user("ship").bash("cp build/tool ~/bin/tool && chmod +x ~/bin/tool").say("I installed the tool.")
    assert verdicts(tmp_path, t) == [("installed", "supported")]


def test_heredoc_body_is_not_a_test_run(tmp_path):
    t = Transcript().user("log").bash("cat >> RUNLOG.md <<'EOF'\nran pytest, all green\nEOF").say("All tests pass.")
    assert verdicts(tmp_path, t) == [("test_pass", "unbacked")]


def test_works_needs_a_run_that_bears_on_the_claim(tmp_path):
    t = Transcript().user("fix").edit("/w/a.py").bash("git add -A", "").say("The bug is fixed.")
    assert verdicts(tmp_path, t) == [("works", "unbacked")]
    t = Transcript().user("fix").edit("/w/a.py").bash("pytest -q", "3 passed").say("The bug is fixed.")
    assert verdicts(tmp_path, t) == [("works", "supported")]
