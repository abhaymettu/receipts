"""Optional LLM extractor: a model finds the claims, the receipts still decide them.

Regex extraction is instant and free but misses paraphrase ("the video now fades in
instead of wiping"). This asks a small model, through the local `claude` CLI, to list
the claims in a report. It sees only the report, never the receipts, and has no say
in any verdict: each claim it returns goes through the same rules as a regex claim.
"""

import json
import re
import subprocess

from .claims import _OBJ_FILE, _OBJ_PATH, _SHA, Claim

PROMPT = """List every claim in the REPORT below in which an AI coding agent asserts, as done or as true
now, something about its own work in this session that a tool log could back or refute.

Families:
  tests     tests pass ("all 42 tests green")
  build     build, typecheck or lint passes ("compiles cleanly")
  files     a file was created, changed or removed ("updated config.py")
  git       commit, push, pull request ("committed as abc1234", "pushed")
  ship      deployed, installed, published ("installed the launch agent")
  ran       a command, script or job was run ("ran the migration")
  verified  something was checked or confirmed ("verified the endpoint returns 200")
  works     a fix or behaviour now works ("the bug is fixed", "the page renders")

Not claims: plans, offers, hedges ("should pass"), questions, admissions of what was not done,
facts about the world rather than the agent's own work, restatements of what someone else said,
and findings or numbers read off tool output (results tables, measured values).

Copy each claim's sentence exactly. A sentence with claims in two families appears twice.
Reply with only a JSON array: [{"span": "<exact sentence>", "family": "<family>"}], or [].

REPORT:
\"\"\"
%s
\"\"\""""

ISOLATE = json.dumps({"claudeMdExcludes": ["**/CLAUDE.md", "**/AGENTS.md"], "autoMemoryEnabled": False})


def _kind(family, span):
    s = span.lower()
    if family == "tests":
        return "test_pass"
    if family == "build":
        return "lint_pass" if re.search(r"\blint", s) else "typecheck_pass" if re.search(r"type", s) else "build_pass"
    if family == "git":
        return "pr" if re.search(r"\b(pr|pull request)\b", s) else "push" if "push" in s else "commit"
    if family == "ship":
        return "installed" if "install" in s else "deployed"
    return {"files": "file_change", "ran": "ran", "verified": "verified", "works": "works"}.get(family)


def ask(report, model="haiku", timeout=120, cwd=None):
    try:
        p = subprocess.run(
            ["claude", "-p", PROMPT % report, "--model", model, "--setting-sources", "project",
             "--settings", ISOLATE, "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
             "--tools", ""],
            capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL, cwd=cwd)
    except (OSError, subprocess.TimeoutExpired):
        return None
    text = p.stdout
    start, end = text.find("["), text.rfind("]")
    try:
        return json.loads(text[start:end + 1]) if start != -1 else None
    except ValueError:
        return None


def extract(report, turn=0, model="haiku", cwd=None):
    """[Claim], or None when the model call failed (callers fall back to regex)."""
    if not report.strip():
        return []
    raw = ask(report, model, cwd=cwd)
    if raw is None:
        return None
    out = []
    for item in raw:
        if not isinstance(item, dict) or not isinstance(item.get("span"), str):
            continue
        kind = _kind(item.get("family"), item["span"])
        if not kind:
            continue
        span = item["span"].strip()
        sha = _SHA.search(span) if kind in ("commit", "push", "pr") else None
        out.append(Claim(turn=turn, kind=kind, text=span[:400],
                         files=[a or b for a, b in _OBJ_FILE.findall(span)] + _OBJ_PATH.findall(span),
                         sha=sha.group(1) if sha and re.search(r"\d", sha.group(1)) else ""))
    return out
