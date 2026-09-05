"""herdr adapter: a locator, not a parser.

herdr keeps no structured transcript of its own. Its scrollback is an in-memory,
size-capped raw ANSI byte buffer inside the running server, and Claude Code's TUI
draws on the alternate screen, which never enters host scrollback at all. Parsing
that would be building on sand.

What herdr does have is the pane's identity: which agent kind runs there, its cwd,
and the terminal title Claude Code set. Claude Code writes its own JSONL under
~/.claude/projects/<slugged cwd>/, and stamps an `ai-title` record with the same
title. That pair is an exact mapping, so this module resolves pane -> transcript
and hands off to the Claude Code adapter. Nothing here re-implements parsing.
"""

import glob
import json
import os
import subprocess

from .claude_code import parse

PROJECTS = os.path.expanduser("~/.claude/projects")


def panes():
    """Agent-hosting panes herdr currently knows about. [] if herdr is not up."""
    try:
        out = subprocess.run(["herdr", "pane", "list"], capture_output=True,
                             text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return []
    try:
        listed = json.loads(out.stdout)["result"]["panes"]
    except (ValueError, KeyError, TypeError):
        return []
    return [p for p in listed if p.get("agent") == "claude"]


def _slug(cwd):
    return cwd.replace("/", "-").replace(".", "-").replace("_", "-")


def title_of(path):
    """The transcript's most recent ai-title, or ''."""
    title = ""
    with open(path, errors="ignore") as fh:
        for line in fh:
            if '"ai-title"' not in line:
                continue
            try:
                title = json.loads(line).get("aiTitle") or title
            except ValueError:
                continue
    return title


def locate(pane):
    """Pane -> its Claude Code transcript path, or None.

    Title first, because two panes can share a cwd - w3 and w5 both did during
    this build. Modification time is only the fallback when no title matches.
    """
    cwd = pane.get("cwd") or ""
    candidates = glob.glob(os.path.join(PROJECTS, _slug(cwd), "*.jsonl"))
    if not candidates:
        return None
    wanted = (pane.get("terminal_title_stripped") or "").strip()
    if wanted:
        for path in candidates:
            if title_of(path) == wanted:
                return path
    return max(candidates, key=os.path.getmtime)


def turns(pane, previews=0):
    """(main_turns, sidechain_turns) for a pane, or ([], []) if not resolvable."""
    path = locate(pane)
    return parse(path, previews) if path else ([], [])
