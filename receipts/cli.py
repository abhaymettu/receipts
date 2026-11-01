"""receipts: check what a coding agent says it did against what it actually did.

  receipts demo                      run on the bundled sample session
  receipts check [TRANSCRIPT] [--all] [--json]
                                     one session; default is the newest Claude Code
                                     transcript for the current directory
  receipts scan [DIR ...] [--days N] [--json]
                                     many sessions; default ~/.claude/projects and ~/.codex/sessions
  receipts hook                      Stop hook entry point (reads the hook event on stdin)
  receipts install-hook [--project] [--mode block|warn|log]
                                     add the Stop hook to Claude Code settings
"""

import argparse
import glob
import json
import os
import shlex
import sys
import time
from collections import Counter

from . import __version__
from .check import CONTRADICTED, SUPPORTED, UNBACKED, as_dict, check_session
from .session import load

SAMPLE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "samples", "demo_session.jsonl")
MARK = {SUPPORTED: "ok", UNBACKED: "UNBACKED", CONTRADICTED: "CONTRADICTED"}
COLOR = {SUPPORTED: "\033[32m", UNBACKED: "\033[33m", CONTRADICTED: "\033[31m"}


def _paint(verdict, text):
    if not sys.stdout.isatty() or os.environ.get("NO_COLOR"):
        return text
    return COLOR[verdict] + text + "\033[0m"


def newest_transcript(cwd=None):
    cwd = os.path.abspath(cwd or os.getcwd())
    slug = cwd.replace("/", "-").replace(".", "-").replace("_", "-")
    here = glob.glob(os.path.expanduser("~/.claude/projects/%s/*.jsonl" % slug))
    pool = here or glob.glob(os.path.expanduser("~/.claude/projects/*/*.jsonl"))
    return max(pool, key=os.path.getmtime) if pool else None


def print_session(path, show_all=False, as_json=False):
    session = load(path)
    verdicts = check_session(session)
    if as_json:
        json.dump([as_dict(v, session) for v in verdicts], sys.stdout, indent=1)
        print()
        return verdicts
    counts = Counter(v.verdict for v in verdicts)
    print("%s  (%s, %d turns, %d tool calls)" % (path, session.harness, len(session.turns), session.n_calls))
    for v in verdicts:
        if v.verdict == SUPPORTED and not show_all:
            continue
        print("  turn %-3d %-14s %-14s %s" % (v.turn, _paint(v.verdict, MARK[v.verdict]), v.kind, v.claim[:110]))
        print("  %s-> %s" % (" " * 9, v.reason))
    print("%d claims: %d supported, %d unbacked, %d contradicted" % (
        len(verdicts), counts[SUPPORTED], counts[UNBACKED], counts[CONTRADICTED]))
    return verdicts


def scan(dirs, days=None, as_json=False):
    dirs = dirs or [os.path.expanduser("~/.claude/projects"), os.path.expanduser("~/.codex/sessions")]
    files = []
    for d in dirs:
        files += glob.glob(os.path.join(d, "*/*.jsonl")) if "/.claude" in d else \
            glob.glob(os.path.join(d, "**/*.jsonl"), recursive=True)
    if days:
        cutoff = time.time() - days * 86400
        files = [f for f in files if os.path.getmtime(f) >= cutoff]
    by_kind = {}
    total = Counter()
    for f in files:
        try:
            verdicts = check_session(load(f))
        except Exception:
            continue
        for v in verdicts:
            by_kind.setdefault(v.kind, Counter())[v.verdict] += 1
            total[v.verdict] += 1
    if as_json:
        json.dump({"sessions": len(files), "total": total, "by_kind": by_kind}, sys.stdout, indent=1)
        print()
        return
    n = sum(total.values())
    print("%d sessions, %d claims" % (len(files), n))
    print("%-16s %7s %9s %9s %13s" % ("kind", "claims", "unbacked", "contra.", "not backed %"))
    for kind, c in sorted(by_kind.items(), key=lambda kv: -sum(kv[1].values())):
        m = sum(c.values())
        print("%-16s %7d %9d %9d %12.1f%%" % (kind, m, c[UNBACKED], c[CONTRADICTED],
                                              100.0 * (c[UNBACKED] + c[CONTRADICTED]) / m))
    if n:
        print("%-16s %7d %9d %9d %12.1f%%" % ("all", n, total[UNBACKED], total[CONTRADICTED],
                                              100.0 * (total[UNBACKED] + total[CONTRADICTED]) / n))


def install_hook(project=False, mode="block"):
    path = os.path.join(".claude", "settings.json") if project else os.path.expanduser("~/.claude/settings.json")
    try:
        with open(path) as fh:
            settings = json.load(fh)
    except (OSError, ValueError):
        settings = {}
    exe = shlex.quote(sys.executable)
    command = "RECEIPTS_MODE=%s %s -m receipts.hook" % (mode, exe)
    stop = settings.setdefault("hooks", {}).setdefault("Stop", [])
    ours = [h for group in stop for h in group.get("hooks", []) if "receipts.hook" in h.get("command", "")]
    for h in ours:
        h["command"] = command
    if not ours:
        stop.append({"hooks": [{"type": "command", "command": command, "timeout": 30}]})
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w") as fh:
        json.dump(settings, fh, indent=2)
    print("Stop hook (%s mode) written to %s" % (mode, path))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="receipts", description=__doc__.split("\n")[0])
    ap.add_argument("--version", action="version", version="receipts " + __version__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("demo")
    c = sub.add_parser("check")
    c.add_argument("transcript", nargs="?")
    c.add_argument("--all", action="store_true", help="show supported claims too")
    c.add_argument("--json", action="store_true")
    s = sub.add_parser("scan")
    s.add_argument("dirs", nargs="*")
    s.add_argument("--days", type=float)
    s.add_argument("--json", action="store_true")
    sub.add_parser("hook")
    i = sub.add_parser("install-hook")
    i.add_argument("--project", action="store_true", help="write .claude/settings.json here, not ~/.claude")
    i.add_argument("--mode", choices=["block", "warn", "log"], default="block")
    a = ap.parse_args(argv)

    if a.cmd == "demo":
        print_session(SAMPLE, show_all=True)
    elif a.cmd == "check":
        path = a.transcript or newest_transcript()
        if not path:
            print("no transcript found; pass one", file=sys.stderr)
            return 2
        verdicts = print_session(path, a.all, a.json)
        return 1 if any(v.verdict != SUPPORTED for v in verdicts) else 0
    elif a.cmd == "scan":
        scan(a.dirs, a.days, a.json)
    elif a.cmd == "hook":
        from .hook import main as hook_main
        return hook_main()
    elif a.cmd == "install-hook":
        install_hook(a.project, a.mode)
    return 0


if __name__ == "__main__":
    sys.exit(main())
