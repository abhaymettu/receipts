#!/usr/bin/env python3
"""Recompute every number in reports/first-overclaim-report.md from the raw log.

The report is only worth anything if its figures can be re-derived rather than
trusted, so it quotes this script's output and nothing else.

    python3 tools/report_stats.py [--log PATH] [--labels reports/labels.json]
                                  [--ab reports/ab_v2.json reports/ab_v3.json]
"""
import argparse
import collections
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from assertion_gate.scorer import DEFAULT_LOG                      # noqa: E402


def pct(n, d):
    return "%d (%.1f%%)" % (n, 100.0 * n / d) if d else "%d (n/a)" % n


def ab_table(labels, paths):
    """Precision and recall for each saved variant, against the CURRENT labels.

    The A/B files embed the labels they were scored under, and those copies go
    stale the moment a label is adjudicated. They are ignored: rows are joined
    back positionally to labels.json, which is the only ground truth.
    """
    tot_tp = sum(1 for l in labels if l["label"] == "overclaim")
    print("\n== variants, re-scored against the current labels ==")
    print("  %-28s %7s %5s %6s %10s %8s" % ("variant", "flagged", "true", "false",
                                            "precision", "recall"))
    print("  %-28s %7d %5d %6d %9.1f%% %7.1f%%" % (
        "v1 (no history)", len(labels), tot_tp, len(labels) - tot_tp,
        100.0 * tot_tp / len(labels), 100.0))
    for path in paths:
        ab = json.load(open(path))
        assert len(ab) == len(labels), "%s has %d rows, labels has %d" % (
            path, len(ab), len(labels))
        tp = fp = 0
        for l, a in zip(labels, ab):
            assert a["claim"] == l["claim"], "%s row order does not match labels" % path
            if a["v2_verdict"] != "unsupported":
                continue
            if l["label"] == "overclaim":
                tp += 1
            else:
                fp += 1
        print("  %-28s %7d %5d %6d %9s %7.1f%%" % (
            os.path.basename(path), tp + fp, tp, fp,
            "%.1f%%" % (100.0 * tp / (tp + fp)) if tp + fp else "n/a",
            100.0 * tp / tot_tp if tot_tp else 0.0))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", default=DEFAULT_LOG)
    ap.add_argument("--labels", default=os.path.join(ROOT, "reports/labels.json"))
    ap.add_argument("--ab", nargs="*", default=[],
                    help="saved A/B outputs to re-score against the current labels")
    args = ap.parse_args()

    rows = [json.loads(l) for l in open(args.log) if l.strip()]
    labels = json.load(open(args.labels))

    print("== scored sample ==")
    print("verdict rows      : %d" % len(rows))
    print("turns             : %d" % len({r["turn_uuid"] for r in rows}))
    print("sessions          : %d" % len({r["source"] for r in rows}))
    print("verdicts          : %s" % dict(collections.Counter(r["verdict"] for r in rows)))

    print("\n== flags per session ==")
    per = collections.defaultdict(collections.Counter)
    turns_per = collections.defaultdict(set)
    for r in rows:
        key = os.path.basename(r["source"])[:8]
        per[key][r["verdict"]] += 1
        turns_per[key].add(r["turn_uuid"])
    for s, c in sorted(per.items(), key=lambda kv: -sum(kv[1].values())):
        print("  %s  turns %2d  claims %3d  unsupported %s" % (
            s, len(turns_per[s]), sum(c.values()), pct(c["unsupported"], sum(c.values()))))

    print("\n== zero-receipt turns ==")
    z = collections.Counter((r["verdict"], r.get("tool_calls", 0) == 0) for r in rows)
    for v in ("supported", "unsupported", "uncheckable"):
        print("  %-12s 0 calls %3d   >0 calls %3d" % (v, z[(v, True)], z[(v, False)]))

    print("\n== hand-labelled sample of %d unsupported rows ==" % len(labels))
    lc = collections.Counter(l["label"] for l in labels)
    n = len(labels)
    print("  confirmed overclaim   : %s" % pct(lc["overclaim"], n))
    print("  FP: turn-scoping      : %s" % pct(lc["fp_turn_scope"], n))
    print("  FP: not a state claim : %s" % pct(lc["fp_not_a_claim"], n))
    print("  FP: evidence missed   : %s" % pct(lc["fp_evidence_missed"], n))
    fps = n - lc["overclaim"]
    print("  turn-scoping share of all FPs: %s" % pct(lc["fp_turn_scope"], fps))

    print("\n== labelled precision by claim type ==")
    byt = collections.defaultdict(lambda: [0, 0])
    for l in labels:
        byt[l["type"]][0] += l["label"] == "overclaim"
        byt[l["type"]][1] += 1
    for t, (tp, tot) in sorted(byt.items(), key=lambda kv: -kv[1][1]):
        print("  %-22s %s" % (t, pct(tp, tot)))

    print("\n== labelled precision by receipt count ==")
    for zero in (True, False):
        sub = [l for l in labels if (l["tool_calls"] == 0) == zero]
        tp = sum(1 for l in sub if l["label"] == "overclaim")
        print("  %-10s %s" % ("0 calls" if zero else ">0 calls", pct(tp, len(sub))))

    if args.ab:
        ab_table(labels, args.ab)

    est = lc["overclaim"] / float(n) * sum(1 for r in rows if r["verdict"] == "unsupported")
    print("\nprojected confirmed overclaims in the %d unsupported rows: %.0f"
          % (sum(1 for r in rows if r["verdict"] == "unsupported"), est))
    return 0


if __name__ == "__main__":
    sys.exit(main())
