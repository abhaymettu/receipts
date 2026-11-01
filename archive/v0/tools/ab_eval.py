#!/usr/bin/env python3
"""Re-score the hand-labelled claims with session history and compare to v1.

reports/labels.json is ground truth for 50 claims the scorer called unsupported
without a history block. This re-scores those same turns with one, matches the
verdicts back by claim text, and reports whether precision actually moved. The
v1 log is left alone; v2 rows go to their own file.

    python3 tools/ab_eval.py [--workers 6] [--out reports/ab_v2.json]
"""
import argparse
import collections
import difflib
import glob
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from assertion_gate.adapters.claude_code import parse                # noqa: E402
from assertion_gate.scorer import PREVIEW_CHARS, score               # noqa: E402


def norm(s):
    return " ".join(s.lower().split())


def best_match(claim, verdicts):
    """The v2 verdict for the same claim, or None if v2 stopped extracting it."""
    target, best, score_ = norm(claim), None, 0.0
    for v in verdicts:
        r = difflib.SequenceMatcher(None, target, norm(v["claim"])).ratio()
        if r > score_:
            best, score_ = v, r
    return best if score_ >= 0.6 else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--model", default="sonnet")
    ap.add_argument("--out", default=os.path.join(ROOT, "reports/ab_v2.json"))
    args = ap.parse_args()

    labels = json.load(open(os.path.join(ROOT, "reports/labels.json")))
    sources = {l["source"] for l in labels}

    # resolve each label's source basename back to a full path, once
    allfiles = {os.path.basename(p): p for p in
                glob.glob(os.path.expanduser("~/.claude/projects/*/*.jsonl"))}
    turns_by_uuid, prior_by_uuid = {}, {}
    for base in sources:
        named = [t for t in parse(allfiles[base], previews=PREVIEW_CHARS)[0]
                 if t["final_message"].strip()]
        for i, t in enumerate(named):
            turns_by_uuid[t["uuid"]] = t
            prior_by_uuid[t["uuid"]] = named[:i]

    wanted = sorted({l["turn_uuid"] for l in labels})
    print("re-scoring %d turns behind %d labelled claims" % (len(wanted), len(labels)))

    def run(uuid):
        return uuid, score(turns_by_uuid[uuid], args.model, prior_by_uuid[uuid])

    v2 = {}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for n, (uuid, verdicts) in enumerate(pool.map(run, wanted), 1):
            v2[uuid] = verdicts
            if n % 5 == 0:
                print("  %d/%d turns" % (n, len(wanted)))

    out, counts = [], collections.Counter()
    for l in labels:
        m = best_match(l["claim"], v2.get(l["turn_uuid"], []))
        new = m["verdict"] if m else "dropped"
        out.append(dict(l, v2_verdict=new, v2_why=(m or {}).get("why", "")))
        counts[(l["label"], new)] += 1
    json.dump(out, open(args.out, "w"), indent=1)

    tp = [o for o in out if o["label"] == "overclaim"]
    fp = [o for o in out if o["label"] != "overclaim"]
    still = lambda rows: sum(1 for o in rows if o["v2_verdict"] == "unsupported")
    tp_keep, fp_keep = still(tp), still(fp)
    print("\n== v1 (no history) ==")
    print("  flagged unsupported : %d   true %d   false %d   precision %.1f%%"
          % (len(out), len(tp), len(fp), 100.0 * len(tp) / len(out)))
    print("== v2 (with history) ==")
    print("  still unsupported   : %d   true %d   false %d   precision %s"
          % (tp_keep + fp_keep, tp_keep, fp_keep,
             "%.1f%%" % (100.0 * tp_keep / (tp_keep + fp_keep))
             if tp_keep + fp_keep else "n/a"))
    print("  false positives cleared : %d of %d" % (len(fp) - fp_keep, len(fp)))
    print("  true overclaims lost    : %d of %d" % (len(tp) - tp_keep, len(tp)))

    print("\n== where each label went ==")
    for (lab, new), n in sorted(counts.items(), key=lambda kv: (kv[0][0], -kv[1])):
        print("  %-20s -> %-12s %d" % (lab, new, n))

    by_fp = collections.Counter(o["label"] for o in fp if o["v2_verdict"] != "unsupported")
    print("\n== cleared false positives by species ==")
    for k, n in by_fp.most_common():
        print("  %-22s %d" % (k, n))
    print("\nwrote %s" % args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
