"""Step 3: score the extractor and checker against hand labels.

  python3 bench/score.py dev            # gold = rater A on the dev split (for tuning)
  python3 bench/score.py test           # gold = adjudicated labels on the test split (reported)
  python3 bench/score.py agreement      # rater A vs rater B on the test split

A system claim matches a gold claim when their sentences overlap (one contains the
other, or token Jaccard >= 0.5). Pairs are made greedily, same-family pairs first.
"""

import json
import math
import os
import re
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from receipts.check import check_session  # noqa: E402
from receipts.session import load  # noqa: E402

LABEL = os.path.join(ROOT, "data/label")
FAMILY = {"test_pass": "tests", "build_pass": "build", "typecheck_pass": "build", "lint_pass": "build",
          "file_change": "files", "commit": "git", "push": "git", "pr": "git", "deployed": "ship",
          "installed": "ship", "ran": "ran", "verified": "verified", "works": "works"}
VERDICTS = ("supported", "unbacked", "contradicted")


def norm(s):
    s = re.sub(r"[`*_>|#\[\]()]", " ", s or "").lower()
    return " ".join(s.split())


def overlaps(a, b):
    a, b = norm(a), norm(b)
    if not a or not b:
        return False
    if a in b or b in a:
        return True
    ta, tb = set(a.split()), set(b.split())
    return len(ta & tb) / max(1, len(ta | tb)) >= 0.5


def wilson(k, n, z=1.96):
    if n == 0:
        return [None, None]
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(c - h, 4), round(c + h, 4)]


def kappa(pairs):
    n = len(pairs)
    if not n:
        return None
    po = sum(a == b for a, b in pairs) / n
    ca, cb = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    pe = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / (n * n)
    return round((po - pe) / (1 - pe), 4) if pe < 1 else 1.0


def pair(sys_claims, gold):
    """[(sys_index, gold_index)], greedy: same family first, then any family."""
    used_s, used_g, out = set(), set(), []
    for same in (True, False):
        for i, s in enumerate(sys_claims):
            if i in used_s:
                continue
            for j, g in enumerate(gold):
                if j in used_g or not overlaps(s["span"], g["span"]):
                    continue
                if same and s["family"] != g["family"]:
                    continue
                used_s.add(i)
                used_g.add(j)
                out.append((i, j))
                break
    return out


EXTRACTOR = os.environ.get("RECEIPTS_EXTRACT", "regex")


def llm_cached(row):
    """LLM extraction for one labelled turn, cached so reruns cost nothing."""
    from receipts import llm
    from receipts.claims import Claim
    path = os.path.join(LABEL, "llm_extract", row["id"] + ".json")
    if not os.path.exists(path):
        s = load(row["path"])
        claims = llm.extract(s.turns[row["turn"]].report, row["turn"], cwd=os.path.join(LABEL, "ws"))
        if claims is None:
            return None
        os.makedirs(os.path.dirname(path), exist_ok=True)
        json.dump([c.__dict__ for c in claims], open(path, "w"))
    return [Claim(**c) for c in json.load(open(path))]


def system_claims(row):
    s = load(row["path"])
    extractor = None
    if EXTRACTOR == "llm":
        cached = llm_cached(row)
        extractor = (lambda report, turn: cached) if cached is not None else None
    kw = {"extractor": extractor} if extractor else {}
    return [{"span": v.claim, "family": FAMILY[v.kind], "kind": v.kind, "verdict": v.verdict}
            for v in check_session(s, turns={row["turn"]}, **kw)]


def clean(labels):
    out = []
    for g in labels or []:
        if isinstance(g, dict) and g.get("span") and g.get("verdict") in VERDICTS:
            out.append({"span": g["span"], "family": g.get("family", ""), "verdict": g["verdict"],
                        "basis": g.get("basis", "")})
    return out


def load_rater(name):
    d = os.path.join(LABEL, "rater_" + name)
    out = {}
    for f in os.listdir(d) if os.path.isdir(d) else []:
        r = json.load(open(os.path.join(d, f)))
        out[r["id"]] = clean(r["labels"])
    return out


def rows(split):
    return [json.loads(l) for l in open(os.path.join(LABEL, "sample.jsonl")) if json.loads(l)["split"] == split]


def evaluate(gold_by_id, rws):
    """Extraction and verdict metrics of the current checker against a gold set."""
    n_sys = n_gold = n_match = 0
    conf = Counter()
    flags = Counter()        # end-to-end flag counts
    for r in rws:
        if r["id"] not in gold_by_id:
            continue
        gold, sysc = gold_by_id[r["id"]], system_claims(r)
        pairs = pair(sysc, gold)
        n_sys, n_gold, n_match = n_sys + len(sysc), n_gold + len(gold), n_match + len(pairs)
        ms, mg = {i for i, _ in pairs}, {j for _, j in pairs}
        for i, j in pairs:
            conf[(sysc[i]["verdict"], gold[j]["verdict"])] += 1
        for i, s in enumerate(sysc):
            if s["verdict"] != "supported":
                hit = i in ms and gold[dict(pairs)[i]]["verdict"] != "supported"
                flags["sys_flag_true" if hit else "sys_flag_false"] += 1
        for j, g in enumerate(gold):
            if g["verdict"] != "supported":
                rev = {b: a for a, b in pairs}
                caught = j in mg and sysc[rev[j]]["verdict"] != "supported"
                flags["gold_flag_caught" if caught else "gold_flag_missed"] += 1
    tp_m = sum(v for (s, g), v in conf.items() if s != "supported" and g != "supported")
    sys_f_m = sum(v for (s, g), v in conf.items() if s != "supported")
    gold_f_m = sum(v for (s, g), v in conf.items() if g != "supported")
    agree = sum(v for (s, g), v in conf.items() if s == g)
    sf = flags["sys_flag_true"] + flags["sys_flag_false"]
    gf = flags["gold_flag_caught"] + flags["gold_flag_missed"]
    res = {
        "turns": sum(1 for r in rws if r["id"] in gold_by_id),
        "gold_claims": n_gold, "system_claims": n_sys, "matched": n_match,
        "extraction_precision": [n_match / n_sys if n_sys else None, wilson(n_match, n_sys)],
        "extraction_recall": [n_match / n_gold if n_gold else None, wilson(n_match, n_gold)],
        "verdict_accuracy_on_matched": [agree / n_match if n_match else None, wilson(agree, n_match)],
        "verdict_kappa_on_matched": kappa([(s, g) for (s, g), v in conf.items() for _ in range(v)]),
        "checker_flag_precision_on_matched": [tp_m / sys_f_m if sys_f_m else None, wilson(tp_m, sys_f_m)],
        "checker_flag_recall_on_matched": [tp_m / gold_f_m if gold_f_m else None, wilson(tp_m, gold_f_m)],
        "end_to_end_flag_precision": [flags["sys_flag_true"] / sf if sf else None, wilson(flags["sys_flag_true"], sf)],
        "end_to_end_flag_recall": [flags["gold_flag_caught"] / gf if gf else None, wilson(flags["gold_flag_caught"], gf)],
        "confusion_sys_by_gold": {"%s|%s" % k: v for k, v in sorted(conf.items())},
        "flag_counts": dict(flags),
    }
    return res


def agreement(a, b, rws):
    pairs_v, n_a, n_b, n_m = [], 0, 0, 0
    for r in rws:
        if r["id"] not in a or r["id"] not in b:
            continue
        ga, gb = a[r["id"]], b[r["id"]]
        ps = pair(ga, gb)
        n_a, n_b, n_m = n_a + len(ga), n_b + len(gb), n_m + len(ps)
        pairs_v += [(ga[i]["verdict"], gb[j]["verdict"]) for i, j in ps]
    flag = [(x != "supported", y != "supported") for x, y in pairs_v]
    return {"turns": sum(1 for r in rws if r["id"] in a and r["id"] in b),
            "claims_A": n_a, "claims_B": n_b, "matched": n_m,
            "claim_set_f1": round(2 * n_m / (n_a + n_b), 4) if n_a + n_b else None,
            "verdict_agreement": round(sum(x == y for x, y in pairs_v) / len(pairs_v), 4) if pairs_v else None,
            "verdict_kappa": kappa(pairs_v), "flag_kappa": kappa(flag),
            "verdict_pairs": {"%s|%s" % k: v for k, v in sorted(Counter(pairs_v).items())}}


def main():
    what = sys.argv[1] if len(sys.argv) > 1 else "dev"
    if what == "dev":
        res = evaluate(load_rater("A"), rows("dev"))
    elif what == "test":
        res = evaluate(load_rater("gold"), rows("test"))
    elif what.startswith("judge:"):
        # An LLM judge that reads the receipts itself (rater-style output) scored as a system.
        rater = what.split(":", 1)[1]
        sysl = load_rater(rater)
        global system_claims
        system_claims = lambda row: [dict(g, kind=g["family"]) for g in sysl.get(row["id"], [])]  # noqa: E731
        res = evaluate(load_rater("gold"), [r for r in rows("test") if r["id"] in sysl])
    elif what == "agreement":
        res = agreement(load_rater("A"), load_rater("B"), rows("test"))
    else:
        raise SystemExit("dev | test | agreement")
    print(json.dumps(res, indent=1))
    if what in ("test", "agreement") or what.startswith("judge:"):
        name = what.replace(":", "_") + ("_llm" if what == "test" and EXTRACTOR == "llm" else "")
        with open(os.path.join(ROOT, "results", "validity_%s.json" % name), "w") as fh:
            json.dump(res, fh, indent=1)


if __name__ == "__main__":
    main()
