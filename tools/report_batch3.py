#!/usr/bin/env python3
"""Every number in BATCH3-REPORT.md, recomputed from the files in reports/.

Usage: python3 tools/report_batch3.py
"""
import json
import math
import os
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(name):
    return json.load(open(os.path.join(ROOT, name)))


def kappa(a, b):
    n = len(a)
    po = sum(x == y for x, y in zip(a, b)) / n
    pe = sum((a.count(c) / n) * (b.count(c) / n) for c in set(a) | set(b))
    return po, (po - pe) / (1 - pe) if pe < 1 else 1.0


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)


def gate(batch):
    a = [r["gate"] for r in load("reports/raters/gate_batch%d_raterA.json" % batch)]
    b = [r["gate"] for r in load("reports/raters/gate_batch%d_raterB.json" % batch)]
    po, k = kappa(a, b)
    print("batch %d gate: n=%d A pass=%d B pass=%d agree=%.1f%% kappa=%.3f" % (
        batch, len(a), a.count("pass"), b.count("pass"), 100 * po, k))


def main():
    print("== batch 1"); print(Counter(r["label"] for r in load("reports/labels.json")))
    print("== batch 2 first pass"); print(Counter(r["label"] for r in load("reports/labels_batch2.json")))
    s = load("reports/second_adjudication_batch2.json")
    print("second adjudicator (%s, blind to receipts): kappa=%.3f agree=%.1f%% labels=%s" % (
        s["model"], s["kappa"], s["agreement_pct"], Counter(p["second_label"] for p in s["pairs"])))
    gate(2)
    print("batch 2 strict:", Counter(r["label"] for r in load("reports/labels_batch2_strict.json")))
    print("== batch 3")
    rows = load("fullset_v3_batch3.json")
    print("claims=%d turns=%d sessions=%d verdicts=%s" % (
        len(rows), len({r["turn_uuid"] for r in rows}), len({r["session_id"] for r in rows}),
        Counter(r["verdict"] for r in rows)))
    print("unsupported by type:", Counter(r["type"] for r in rows if r["verdict"] == "unsupported"))
    gate(3)
    if not os.path.exists(os.path.join(ROOT, "reports", "labels_batch3.json")):
        return
    lab = load("reports/labels_batch3.json")
    c = Counter(r["label"] for r in lab)
    print("labels:", c)
    checkable = [r for r in lab if r["label"] != "fp_not_a_claim"]
    flagged = len(lab)
    oc = c["overclaim"]
    print("precision of v3 unsupported flag: %d/%d = %.1f%% (Wilson 95%% %.1f-%.1f); excluding not-a-claim %d/%d = %.1f%%" % (
        oc, flagged, 100 * oc / flagged, *[100 * x for x in wilson(oc, flagged)],
        oc, len(checkable), 100 * oc / len(checkable)))
    n_claims = len(rows)
    print("confirmed overclaims per extracted claim: %d/%d = %.1f%% (Wilson 95%% %.1f-%.1f)" % (
        oc, n_claims, 100 * oc / n_claims, *[100 * x for x in wilson(oc, n_claims)]))
    print("per type:")
    for t, k in sorted(Counter(r["type"] for r in lab).items()):
        o = sum(1 for r in lab if r["type"] == t and r["label"] == "overclaim")
        print("  %-22s flagged %3d  overclaim %3d  precision %.0f%%" % (t, k, o, 100 * o / k))
    print("per session:")
    for s_, k in sorted(Counter(r["source"] for r in lab).items()):
        o = sum(1 for r in lab if r["source"] == s_ and r["label"] == "overclaim")
        tot = sum(1 for r in rows if os.path.basename(r["source"]) == s_)
        print("  %s claims %3d flagged %3d overclaim %3d" % (s_[:8], tot, k, o))
    sec = load("reports/raters/stepB_batch3_second.json")
    prim = {r["turn_uuid"] + "|" + r["claim"]: r["label"] for r in lab}
    pairs = [(prim[p["turn_uuid"] + "|" + p["claim"]], p["label"]) for p in sec]
    po, k = kappa([p[0] for p in pairs], [p[1] for p in pairs])
    oc_or_not = lambda l: "overclaim" if l == "overclaim" else "not"  # noqa: E731
    po2, k2 = kappa([oc_or_not(x) for x, _ in pairs], [oc_or_not(y) for _, y in pairs])
    print("step B second rater: n=%d agree=%.1f%% kappa=%.3f; overclaim-vs-not agree=%.1f%% kappa=%.3f" % (
        len(pairs), 100 * po, k, 100 * po2, k2))


if __name__ == "__main__":
    main()
