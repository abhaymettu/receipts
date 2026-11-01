"""Claude Code Stop hook: catch an unbacked claim before the turn ends.

Claude Code runs this when the agent finishes a turn, with the transcript path on
stdin. If the report claims something its own tool calls do not back, the hook
blocks the stop and hands the agent the list, so it either runs the check or
says the claim is unverified. It speaks at most once per turn (`stop_hook_active`).

  RECEIPTS_MODE=block   (default) block the stop and tell the agent
  RECEIPTS_MODE=warn    let the turn end, show the user a warning
  RECEIPTS_MODE=log     say nothing, append findings to ~/.claude/receipts/log.jsonl

  RECEIPTS_ENGINE=rules  regex claims, deterministic rules, milliseconds, low precision
  RECEIPTS_ENGINE=judge  (default) a model reads the receipts (RECEIPTS_MODEL, default sonnet);
                        tens of seconds per turn, far more accurate on real sessions
"""

import json
import os
import sys
import time

from .check import CONTRADICTED, check_session
from .session import load

LOG = os.path.expanduser("~/.claude/receipts/log.jsonl")


def findings_for_last_turn(path, report=None):
    session = load(path)
    if not session.turns:
        return session, []
    last = session.turns[-1]
    if report and report.strip():
        last.report = report  # the transcript is written asynchronously and can lag the turn
    return session, [v for v in check_session(session, turns={last.idx}) if v.verdict != "supported"]


def judged_findings(path, report=None, model="sonnet"):
    from .check import Verdict
    from .judge import ask, dossier
    session = load(path)
    if not session.turns:
        return session, []
    last = session.turns[-1]
    if report and report.strip():
        last.report = report
    if not last.report:
        return session, []
    labels = ask(dossier(session, last.idx), model) or []
    return session, [Verdict(turn=last.idx, kind=g.get("family", ""), claim=g["span"], verdict=g["verdict"],
                             reason=g.get("note", ""), basis=g.get("basis", ""))
                     for g in labels if g.get("verdict") in ("unbacked", "contradicted")]


def message(findings):
    lines = ["receipts: your report makes %d claim%s your own tool calls do not back:" % (
        len(findings), "" if len(findings) == 1 else "s")]
    for v in findings:
        mark = "contradicted" if v.verdict == CONTRADICTED else "unbacked"
        lines.append('- "%s" [%s: %s]' % (v.claim[:160], mark, v.reason))
    lines.append("Run the check now and report what it shows, or restate the claim as not verified.")
    return "\n".join(lines)


def main(stdin=sys.stdin, stdout=sys.stdout):
    t0 = time.perf_counter()
    try:
        event = json.load(stdin)
    except ValueError:
        return 0
    path = event.get("transcript_path")
    if event.get("stop_hook_active") or not path or not os.path.exists(path):
        return 0
    mode = os.environ.get("RECEIPTS_MODE", "block").lower()
    try:
        if os.environ.get("RECEIPTS_ENGINE", "judge") == "judge":
            session, findings = judged_findings(path, event.get("last_assistant_message"),
                                                os.environ.get("RECEIPTS_MODEL", "sonnet"))
        else:
            session, findings = findings_for_last_turn(path, event.get("last_assistant_message"))
    except Exception:  # a hook must never break the session it watches
        return 0
    ms = (time.perf_counter() - t0) * 1000
    if findings:
        try:
            os.makedirs(os.path.dirname(LOG), exist_ok=True)
            with open(LOG, "a") as fh:
                fh.write(json.dumps({"session": session.session_id, "ms": round(ms, 1),
                                     "findings": [v.__dict__ for v in findings]}) + "\n")
        except OSError:
            pass
    if not findings or mode == "log":
        return 0
    if mode == "warn":
        json.dump({"systemMessage": message(findings)}, stdout)
    else:
        json.dump({"decision": "block", "reason": message(findings)}, stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
