#!/usr/bin/env python3
"""Full-set re-score: all 44 turns from the v1 log, re-scored under v3 (history block).

Reads the v1 verdict log to find every scored turn, resolves each back to its
session file, re-scores with the current scorer (v3, with history), and writes
reports/fullset_v3.json. Prints a v1-vs-v3 comparison table.
"""
import collections
import difflib
import glob
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from assertion_gate.adapters.claude_code import parse
from assertion_gate.scorer import PREVIEW_CHARS, score

V1_LOG = os.path.expanduser("~/.claude/assertion-gate/verdicts.jsonl")
OUT = os.path.join(ROOT, "reports", "fullset_v3.json")


def norm(s):
    return " ".join(s.lower().split())


def best_match(claim, verdicts):
    target, best, ratio = norm(claim), None, 0.0
    for v in verdicts:
        r = difflib.SequenceMatcher(None, target, norm(v["claim"])).ratio()
        if r > ratio:
            best, ratio = v, r
    return best if ratio >= 0.6 else None


def main():
    v1_rows = [json.loads(l) for l in open(V1_LOG)]
    turn_src = {}
    for r in v1_rows:
        turn_src[r["turn_uuid"]] = r["source"]
    print(f"v1 log: {len(v1_rows)} rows, {len(turn_src)} unique turns")

    allfiles = {os.path.basename(p): p for p in
                glob.glob(os.path.expanduser("~/.claude/projects/*/*.jsonl"))}

    turns_by_uuid, prior_by_uuid = {}, {}
    needed_srcs = {os.path.basename(s) for s in turn_src.values()}
    for base in needed_srcs:
        if base not in allfiles:
            print(f"  WARNING: session file {base} not found, skipping")
            continue
        named = [t for t in parse(allfiles[base], previews=PREVIEW_CHARS)[0]
                 if t["final_message"].strip()]
        for i, t in enumerate(named):
            if t["uuid"] in turn_src:
                turns_by_uuid[t["uuid"]] = t
                prior_by_uuid[t["uuid"]] = named[:i]

    wanted = sorted(turns_by_uuid.keys())
    print(f"resolved {len(wanted)} of {len(turn_src)} turns")

    def run(uuid):
        return uuid, score(turns_by_uuid[uuid], "sonnet", prior_by_uuid[uuid])

    v3 = {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        for n, (uuid, verdicts) in enumerate(pool.map(run, wanted), 1):
            v3[uuid] = verdicts
            if n % 5 == 0:
                print(f"  {n}/{len(wanted)} turns scored")

    # Build comparison rows
    out_rows = []
    for r in v1_rows:
        uuid = r["turn_uuid"]
        if uuid not in v3:
            continue
        m = best_match(r["claim"], v3[uuid])
        out_rows.append({
            "turn_uuid": uuid,
            "session_id": r["session_id"],
            "source": os.path.basename(r["source"]),
            "claim": r["claim"],
            "type": r["type"],
            "pramana": r["pramana"],
            "v1_verdict": r["verdict"],
            "v1_why": r["why"],
            "v3_verdict": m["verdict"] if m else None,
            "v3_why": m["why"] if m else None,
        })

    with open(OUT, "w") as fh:
        json.dump(out_rows, fh, indent=2)

    # Summary
    v1c = collections.Counter(r["v1_verdict"] for r in out_rows)
    v3c = collections.Counter(r["v3_verdict"] for r in out_rows)
    print(f"\n=== verdict distribution ===")
    for k in sorted(set(list(v1c) + list(v3c))):
        print(f"  {k:15s}  v1={v1c.get(k,0):4d}  v3={v3c.get(k,0):4d}")

    flips = collections.Counter()
    for r in out_rows:
        if r["v1_verdict"] != r["v3_verdict"]:
            flips[f"{r['v1_verdict']}->{r['v3_verdict']}"] += 1
    if flips:
        print(f"\n=== flips ===")
        for k, n in flips.most_common():
            print(f"  {k}: {n}")

    # Against ground truth
    labels = json.load(open(os.path.join(ROOT, "reports", "labels.json")))
    gt = {(l["turn_uuid"], norm(l["claim"])): l["adjudicated"] for l in labels}
    tp = fp = fn = tn = 0
    for r in out_rows:
        key = (r["turn_uuid"], norm(r["claim"]))
        if key not in gt:
            continue
        actual = "unsupported" in gt[key].lower() or "overclaim" in gt[key].lower()
        v3_flagged = r["v3_verdict"] == "unsupported"
        if v3_flagged and actual: tp += 1
        elif v3_flagged and not actual: fp += 1
        elif not v3_flagged and actual: fn += 1
        else: tn += 1
    total_labelled = tp + fp + fn + tn
    prec = tp / (tp + fp) if (tp + fp) else 0
    rec = tp / (tp + fn) if (tp + fn) else 0
    print(f"\n=== v3 vs ground truth ({total_labelled} labelled claims) ===")
    print(f"  TP={tp} FP={fp} FN={fn} TN={tn}")
    print(f"  precision={prec:.1%}  recall={rec:.1%}")

    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
