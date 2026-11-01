"""Claude Code transcripts (~/.claude/projects/<project>/<session>.jsonl).

  {"type":"assistant","message":{"model":..,"content":[{"type":"tool_use","id":..,"name":..,"input":{..}}]}}
  {"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":..,"is_error":..}]},
   "toolUseResult": {...}}

A turn starts at every user record that is not a tool result: a typed prompt, a
background-task notification, a compaction summary. Each one is a point where
the Stop hook fires and the agent has just reported.
"""

import json
import re

from ..rules import shell_writes
from ..session import Call, Session, Turn, clip, exit_code_in, read_jsonl

WRITE_TOOLS = {"Edit": "file_path", "Write": "file_path", "MultiEdit": "file_path",
               "NotebookEdit": "notebook_path"}
TARGET_KEYS = ("file_path", "path", "url", "pattern", "query", "notebook_path")
_EXIT_LINE = re.compile(r"^Exit code (\d+)", re.M)


def _blocks(rec):
    content = (rec.get("message") or {}).get("content")
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    return [b for b in content or [] if isinstance(b, dict)]


def _result_text(block, structured):
    if isinstance(structured, dict) and "stdout" in structured:
        return (structured.get("stdout") or "") + "\n" + (structured.get("stderr") or "")
    content = block.get("content")
    if isinstance(content, list):
        return "\n".join(b.get("text", "") for b in content if isinstance(b, dict))
    if isinstance(content, str):
        return content
    return json.dumps(structured, default=str)[:5000] if structured else ""


def _new_call(use, idx, turn):
    name = use.get("name") or ""
    inp = use.get("input") if isinstance(use.get("input"), dict) else {}
    call = Call(idx=idx, turn=turn, tool=name)
    if isinstance(inp.get("command"), str):
        call.cmd = inp["command"]
        call.paths = shell_writes(call.cmd)
    if name in WRITE_TOOLS and isinstance(inp.get(WRITE_TOOLS[name]), str):
        call.paths = [inp[WRITE_TOOLS[name]]]
    for key in TARGET_KEYS:
        if isinstance(inp.get(key), str):
            call.target = inp[key][:500]
            break
    else:
        if not call.cmd and inp:
            call.target = json.dumps(inp, default=str)[:300]
    return call


def parse(path):
    session = Session(path=path, harness="claude-code")
    turn, parts, pending, n = None, [], {}, 0

    def close():
        if turn is not None:
            turn.report = "\n\n".join(p for p in parts if p.strip()).strip()
            session.turns.append(turn)

    for rec in read_jsonl(path):
        kind = rec.get("type")
        if kind not in ("user", "assistant") or rec.get("isSidechain"):
            continue
        session.session_id = session.session_id or rec.get("sessionId") or ""
        blocks = _blocks(rec)
        results = [b for b in blocks if b.get("type") == "tool_result"]

        if kind == "user" and not results:
            close()
            text = "\n".join(b.get("text", "") for b in blocks if b.get("type") == "text")
            turn, parts = Turn(idx=len(session.turns), prompt=text[:20000]), []
            if text.lstrip().startswith("<task-notification>"):
                # A background command finishing is a receipt in its own right.
                turn.calls.append(Call(idx=n, turn=turn.idx, tool="notification",
                                       output=clip(text), exit_code=exit_code_in(
                                           text[text.find("exit code") - 5:] if "exit code" in text else "")))
                n += 1
            continue

        if turn is None:  # transcript opens mid-turn (resumed session)
            turn, parts = Turn(idx=0), []

        if kind == "assistant":
            model = (rec.get("message") or {}).get("model") or ""
            if model and not model.startswith("<"):
                turn.model = model
            turn.uuid = rec.get("uuid") or turn.uuid
            for b in blocks:
                if b.get("type") == "text" and b.get("text", "").strip():
                    parts.append(b["text"])
                elif b.get("type") == "tool_use":
                    parts = []
                    call = _new_call(b, n, turn.idx)
                    n += 1
                    turn.calls.append(call)
                    pending[b.get("id")] = call
            continue

        structured = rec.get("toolUseResult")
        for b in results:
            call = pending.pop(b.get("tool_use_id"), None)
            if call is None:
                continue
            text = _result_text(b, structured)
            call.output = clip(text)
            call.is_error = bool(b.get("is_error")) or (
                isinstance(structured, str) and structured.startswith("Error"))
            if call.cmd:
                m = _EXIT_LINE.search(text[:200]) if call.is_error else None
                call.exit_code = int(m.group(1)) if m else (1 if call.is_error else 0)
    close()
    return session
