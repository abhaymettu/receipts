"""OpenAI Codex CLI rollouts (~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl).

  {"type":"response_item","payload":{"type":"message","role":"user"|"assistant",...}}
  {"type":"response_item","payload":{"type":"function_call","name":"shell","arguments":"{..}","call_id":..}}
  {"type":"response_item","payload":{"type":"custom_tool_call","name":"apply_patch","input":"*** Begin Patch.."}}
  {"type":"response_item","payload":{"type":"function_call_output","call_id":..,"output":".."}}
"""

import json
import re

from ..rules import shell_writes
from ..session import Call, Session, Turn, clip, exit_code_in, read_jsonl

_PATCH_FILE = re.compile(r"^\*\*\* (?:Update|Add|Delete) File: (.+)$", re.M)
_INJECTED = ("<environment_context>", "<user_instructions>", "<permissions",
             "# AGENTS.md", "<turn_aborted>")


def _text(content):
    return "\n".join(c.get("text", "") for c in content or []
                     if isinstance(c, dict) and c.get("type") in ("input_text", "output_text", "text"))


def _command(name, payload):
    raw = payload.get("arguments") if "arguments" in payload else payload.get("input")
    if name == "apply_patch" or (isinstance(raw, str) and raw.startswith("*** Begin Patch")):
        return "", _PATCH_FILE.findall(raw or "")
    try:
        args = json.loads(raw) if isinstance(raw, str) and raw.startswith("{") else raw
    except ValueError:
        args = raw
    if isinstance(args, dict):
        cmd = args.get("cmd") or args.get("command") or ""
        if isinstance(cmd, list):
            cmd = " ".join(str(c) for c in cmd)
            cmd = re.sub(r"^(?:bash|zsh|sh) -l?c ", "", cmd)
        return str(cmd), []
    if isinstance(args, str) and name == "exec":
        # The JS exec tool wraps one or more exec_command calls.
        return "; ".join(re.findall(r"cmd:\s*\"((?:[^\"\\]|\\.)*)\"", args)), []
    return "", []


def parse(path):
    session = Session(path=path, harness="codex")
    turn, parts, pending, n, model = None, [], {}, 0, ""

    def close():
        if turn is not None:
            turn.report = "\n\n".join(p for p in parts if p.strip()).strip()
            session.turns.append(turn)

    for rec in read_jsonl(path):
        p = rec.get("payload") if isinstance(rec.get("payload"), dict) else {}
        if rec.get("type") == "session_meta":
            session.session_id = p.get("id") or p.get("session_id") or ""
            continue
        if rec.get("type") == "turn_context":
            model = p.get("model") or model
            continue
        if rec.get("type") != "response_item":
            continue
        kind = p.get("type")

        if kind == "message" and p.get("role") == "user":
            text = _text(p.get("content"))
            if text.lstrip().startswith(_INJECTED):
                continue
            close()
            turn, parts = Turn(idx=len(session.turns), prompt=text[:20000], model=model), []
            continue
        if turn is None:
            turn, parts = Turn(idx=0, model=model), []
        turn.model = model or turn.model

        if kind == "message" and p.get("role") == "assistant":
            parts.append(_text(p.get("content")))
        elif kind in ("function_call", "custom_tool_call", "local_shell_call"):
            name = p.get("name") or kind
            if name in ("update_plan",):
                continue
            cmd, patched = _command(name, p)
            call = Call(idx=n, turn=turn.idx, tool=name, cmd=cmd,
                        paths=patched or shell_writes(cmd))
            n += 1
            parts = []
            turn.calls.append(call)
            pending[p.get("call_id")] = call
        elif kind in ("function_call_output", "custom_tool_call_output"):
            call = pending.pop(p.get("call_id"), None)
            if call is None:
                continue
            out = p.get("output")
            if isinstance(out, dict):
                out = out.get("content") or json.dumps(out)
            out = str(out or "")
            call.output = clip(out)
            call.exit_code = exit_code_in(out)
            call.is_error = (call.exit_code not in (None, 0)) or out.startswith(
                ("apply_patch verification failed", "error", "Error"))
    close()
    return session
