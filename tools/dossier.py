#!/usr/bin/env python3
"""Adjudication dossier: everything a rater must read before labelling one claim.

Usage: python3 tools/dossier.py VERDICTS.jsonl OUT_DIR [--only unsupported]

For every row in the verdict log (one per claim) this writes OUT_DIR/<n>.md with
the claim, the agent's message, every receipt in the flagged turn untruncated
(call and result), and every receipt in every earlier turn of that session with
a preview. This is the protocol in rubric.json made mechanical: the rater reads
the dossier, not the scorer's rationale.
"""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from assertion_gate.adapters.claude_code import parse  # noqa: E402

FULL = 200000        # flagged-turn receipt output, effectively untruncated
PRIOR = 1500         # per-receipt preview for earlier turns


def find_session(basename):
    hits = glob.glob(os.path.expanduser("~/.claude/projects/*/" + basename))
    return hits[0] if hits else None


def receipt_lines(receipts, limit):
    out = []
    for i, r in enumerate(receipts, 1):
        facts = ", ".join("%s=%r" % kv for kv in sorted(r["facts"].items()))
        head = "%d. %s(%s)" % (i, r["tool_name"], facts[:2000])
        if r["result_count"] is not None:
            head += " -> %d result(s)" % r["result_count"]
        if r["is_error"]:
            head += " [ERROR]"
        out.append(head)
        prev = (r.get("preview") or "").strip()
        if prev:
            out.append("   | " + prev[:limit].replace("\n", "\n   | "))
    return "\n".join(out) or "(no tool calls)"


def main(argv):
    log, out_dir = argv[0], argv[1]
    only = argv[argv.index("--only") + 1] if "--only" in argv else None
    rows = [json.loads(l) for l in open(log) if l.strip()]
    if only:
        rows = [r for r in rows if r["verdict"] == only]
    os.makedirs(out_dir, exist_ok=True)
    cache = {}
    index = []
    for n, row in enumerate(rows, 1):
        base = os.path.basename(row["source"])
        if base not in cache:
            path = find_session(base)
            cache[base] = None
            if path:
                named = [t for t in parse(path, previews=FULL)[0] if t["final_message"].strip()]
                cache[base] = {t["uuid"]: (i, t, named) for i, t in enumerate(named)}
        entry = {"n": n, "turn_uuid": row["turn_uuid"], "claim": row["claim"],
                 "type": row["type"], "source": base, "tool_calls": row["tool_calls"],
                 "dossier": "%s/%d.md" % (out_dir, n)}
        index.append(entry)
        parts = ["# Claim %d" % n, "", "CLAIM: %s" % row["claim"], "TYPE: %s" % row["type"],
                 "SESSION: %s   TURN: %s" % (base, row["turn_uuid"]), ""]
        hit = (cache[base] or {}).get(row["turn_uuid"])
        if not hit:
            parts.append("SESSION FILE OR TURN NOT FOUND ON DISK - receipts unavailable.")
            entry["turn_found"] = False
        else:
            i, t, named = hit
            entry["turn_found"] = True
            parts += ["## Message the agent sent (turn %d of %d)" % (i + 1, len(named)), "",
                      t["final_message"], "",
                      "## Receipts in this turn (%d, untruncated)" % len(t["receipts"]), "",
                      receipt_lines(t["receipts"], FULL), "",
                      "## Receipts in earlier turns (newest first, previews)", ""]
            for j in range(i - 1, -1, -1):
                p = named[j]
                parts.append("### Earlier turn %d (%d receipts)" % (j + 1, len(p["receipts"])))
                parts.append(receipt_lines(p["receipts"], PRIOR))
                parts.append("")
        open(entry["dossier"], "w").write("\n".join(parts))
    json.dump(index, open(os.path.join(out_dir, "index.json"), "w"), indent=1)
    print("%d dossiers in %s (%d with turn found)" % (
        len(index), out_dir, sum(e["turn_found"] for e in index)))


if __name__ == "__main__":
    main(sys.argv[1:])
