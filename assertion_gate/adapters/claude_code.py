"""Claude Code JSONL session logs -> receipt ledger + final assistant message per turn.

Claude Code writes a full transcript to ~/.claude/projects/<slug>/<session>.jsonl.
Records we care about:

  {"type":"assistant", "message":{"content":[{"type":"tool_use","id":...,"name":...,"input":{...}}]}}
  {"type":"user",      "message":{"content":[{"type":"tool_result","tool_use_id":...}]},
                       "toolUseResult": <structured result>}

Turns are segmented on real user prompts (a user record carrying no tool_result).
Main-thread and sidechain (subagent) records are segmented separately, matching the
Stop / SubagentStop split.
"""

import json

from ..ledger import make_receipt


def _blocks(rec):
    content = (rec.get("message") or {}).get("content")
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    return [b for b in content or [] if isinstance(b, dict)]


def _ts(rec):
    """ISO8601 timestamp -> epoch ms, without importing datetime on the hook path."""
    t = rec.get("timestamp") or ""
    try:
        import calendar
        import time
        return int(calendar.timegm(time.strptime(t[:19], "%Y-%m-%dT%H:%M:%S")) * 1000)
    except Exception:
        return 0


def summarize(tool_name, tool_input, result):
    """(output_text, result_count, facts, is_error) for one tool result.

    result_count is the number of items the tool actually returned, or None when
    the tool has no countable result. It is what count-mismatch and false-absence
    claims get checked against, so it stays conservative: unknown is None, never 0.
    facts are deterministic key-values pulled from the call, per nabaos's rule that
    each tool adapter defines which fields count as facts.
    """
    facts = {}
    inp = tool_input if isinstance(tool_input, dict) else {}
    for key in ("command", "file_path", "pattern", "path", "url", "query", "prompt"):
        if isinstance(inp.get(key), str):
            facts[key] = inp[key][:400]

    # A tool result that is a bare string is Claude Code's error channel.
    if isinstance(result, str):
        is_error = result.startswith("Error:") or result.startswith("User rejected")
        return result, (None if is_error else _lines(result)), facts, is_error

    if isinstance(result, list):  # MCP-style content blocks
        text = "\n".join(b.get("text", "") for b in result if isinstance(b, dict))
        return text, len(result), facts, False

    if not isinstance(result, dict):
        return "" if result is None else str(result), None, facts, False

    r = result
    if "stdout" in r:  # Bash
        text = (r.get("stdout") or "") + (r.get("stderr") or "")
        facts["stderr_empty"] = not (r.get("stderr") or "").strip()
        return text, _lines(r.get("stdout") or ""), facts, bool(r.get("is_error"))
    if r.get("type") == "text" and isinstance(r.get("file"), dict):  # Read
        f = r["file"]
        facts["file_path"] = f.get("filePath", facts.get("file_path", ""))
        content = f.get("content") or ""
        return content, f.get("numLines", _lines(content)), facts, False
    for key in ("filenames", "results", "matches", "files"):  # Glob / Grep / WebSearch
        if isinstance(r.get(key), list):
            return json.dumps(r[key])[:20000], len(r[key]), facts, False
    for key in ("numFiles", "numMatches", "numLines"):
        if isinstance(r.get(key), int):
            return json.dumps(r)[:20000], r[key], facts, False
    if "result" in r and "code" in r:  # WebFetch
        facts["http_code"] = r.get("code")
        facts["url"] = r.get("url", facts.get("url", ""))
        return str(r.get("result") or ""), None, facts, r.get("code") not in (200, None)
    if "structuredPatch" in r:  # Edit / Write
        facts["file_path"] = r.get("filePath", facts.get("file_path", ""))
        return json.dumps(r.get("structuredPatch"))[:20000], None, facts, False
    return json.dumps(r, default=str)[:20000], None, facts, False


def _lines(text):
    text = text.strip("\n")
    return 0 if not text else text.count("\n") + 1


def _segment(records, previews=0):
    """Records in file order -> list of turns, split on real user prompts.

    previews > 0 attaches that many characters of each tool's output text to its
    receipt. The hook path leaves it at 0 - hashes are enough to contradict a
    count - and the async scorer sets it, because judging a fact claim needs the
    text the tool actually returned.
    """
    turns, pending = [], {}
    cur = None

    def start():
        return {"final_message": "", "receipts": [], "uuid": None,
                "session_id": None, "timestamp_ms": 0}

    for rec in records:
        kind = rec.get("type")
        blocks = _blocks(rec)
        is_tool_result = any(b.get("type") == "tool_result" for b in blocks)

        if kind == "user" and not is_tool_result:
            if cur is not None:
                turns.append(cur)
            cur = start()
            cur["session_id"] = rec.get("session_id") or rec.get("sessionId")
            cur["timestamp_ms"] = _ts(rec)
            continue

        if cur is None:  # transcript opens mid-turn (resume, compaction)
            cur = start()
            cur["session_id"] = rec.get("sessionId")

        if kind == "assistant":
            cur["uuid"] = rec.get("uuid")
            for b in blocks:
                if b.get("type") == "text" and b.get("text", "").strip():
                    cur["final_message"] = b["text"]
                elif b.get("type") == "tool_use":
                    pending[b.get("id")] = (b, cur, _ts(rec))
        elif kind == "user" and is_tool_result:
            for b in blocks:
                call = pending.pop(b.get("tool_use_id"), None)
                if call is None:
                    continue
                use, owner, ts = call
                result = rec.get("toolUseResult")
                if result is None:
                    result = b.get("content")
                out, count, facts, err = summarize(use.get("name"), use.get("input"), result)
                receipt = make_receipt(
                    use.get("id"), use.get("name"), use.get("input"), out,
                    count, facts, ts, err or b.get("is_error", False))
                if previews:
                    receipt["preview"] = out[:previews]
                owner["receipts"].append(receipt)

    # Tool calls whose result never came back (interrupt, crash) still happened.
    for use, owner, ts in pending.values():
        owner["receipts"].append(make_receipt(
            use.get("id"), use.get("name"), use.get("input"), "", None,
            {}, ts, False))
    if cur is not None:
        turns.append(cur)
    for r in turns:
        r["receipts"].sort(key=lambda x: x["timestamp_ms"])
    return turns


def parse(path, previews=0):
    """Parse one session log. Returns (main_turns, sidechain_turns)."""
    main, side = [], []
    with open(path, errors="ignore") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if rec.get("type") not in ("user", "assistant"):
                continue
            (side if rec.get("isSidechain") else main).append(rec)
    return _segment(main, previews), _segment(side, previews)


def count_tool_calls(path):
    """Independent count of tool_use blocks in the file - the check on parse()."""
    n = 0
    with open(path, errors="ignore") as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if rec.get("type") != "assistant":
                continue
            for b in _blocks(rec):
                if b.get("type") == "tool_use":
                    n += 1
    return n
