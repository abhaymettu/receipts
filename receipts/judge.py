"""Judge mode: a model reads the receipts and rules on every claim in a report.

The regex rules are instant but cannot tell whether a later command bears on a claim.
This builds the same dossier the benchmark's raters read (the turn's prompt, its
report, every tool call so far with clipped output), and asks a model, through the
local `claude` CLI with read-only tools over that one file, to list the claims and
judge each under `rubric.md`.
"""

import json
import os
import subprocess
import tempfile

from .session import load

RUBRIC = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "rubric.md")).read()
EARLIER_CLIP, CURRENT_CLIP = 700, 2000
ISOLATE = json.dumps({"claudeMdExcludes": ["**/CLAUDE.md", "**/AGENTS.md"], "autoMemoryEnabled": False,
                      "hooks": {}})


def _clip(text, n):
    text = (text or "").strip()
    if len(text) <= n:
        return text
    return text[:n * 2 // 3] + "\n[...]\n" + text[-n // 3:]


def dossier(session, turn_idx):
    t = session.turns[turn_idx]
    out = ["USER PROMPT (turn %d)" % t.idx, "=" * 20, _clip(t.prompt, 3000), "",
           "REPORT", "=" * 20, t.report, "", "RECEIPTS", "=" * 20]
    for c in session.calls_before(t.idx):
        cur = c.turn == t.idx
        head = "[#%d turn %d%s] %s" % (c.idx, c.turn, "*" if cur else "", c.tool)
        if c.cmd:
            head += " $ " + _clip(c.cmd, 600)
        elif c.target:
            head += " " + c.target[:300]
        if c.paths:
            head += "\n  writes: " + ", ".join(c.paths)[:300]
        status = "ERROR" if c.is_error else "ok"
        if c.exit_code is not None:
            status += " exit=%s" % c.exit_code
        out.append(head + "\n  status: " + status)
        body = _clip(c.output, CURRENT_CLIP if cur else EARLIER_CLIP)
        if body:
            out.append("  | " + body.replace("\n", "\n  | "))
    return "\n".join(out) + "\n"


def ask(text, model="sonnet", timeout=600):
    """[{span, family, verdict, ...}] for one dossier, or None if the call failed."""
    with tempfile.TemporaryDirectory(prefix="receipts-judge-") as ws:
        with open(os.path.join(ws, "dossier.txt"), "w") as fh:
            fh.write(text)
        prompt = RUBRIC + "\n\nThe dossier is `dossier.txt` in the current directory. Label it now."
        try:
            p = subprocess.run(
                ["claude", "-p", prompt, "--model", model, "--setting-sources", "project",
                 "--settings", ISOLATE, "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
                 "--tools", "Read,Grep,Glob", "--allowedTools", "Read,Grep,Glob"],
                cwd=ws, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
        except (OSError, subprocess.TimeoutExpired):
            return None
    out = p.stdout
    start, end = out.find("["), out.rfind("]")
    try:
        labels = json.loads(out[start:end + 1]) if start != -1 else None
    except ValueError:
        return None
    return [g for g in labels or [] if isinstance(g, dict) and g.get("span")]


def judge(path, turn_idx=None, model="sonnet"):
    session = load(path)
    reported = [t.idx for t in session.turns if t.report]
    if not reported:
        return session, None, []
    idx = reported[-1] if turn_idx is None else turn_idx
    return session, idx, ask(dossier(session, idx), model)
