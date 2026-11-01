"""Step 5: the benchmark numbers.

  1. Prevalence from hand labels: of the claims in a uniform random sample of reported
     turns, what share are not backed by the agent's own receipts? Gold labels on the
     test split, rater A on the dev split. 95% intervals from a bootstrap that resamples
     sessions, since claims in one session are not independent.
  2. The checker at scale: its verdicts on every claim it extracts from every session in
     the frame, broken down the same ways.

Writes results/benchmark.json. Aggregates only; no claim text leaves data/.
"""

import json
import os
import random
import sys
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "bench"))
import score  # noqa: E402

SEED, B = 7, 2000


def length_bucket(n):
    return "1-9 calls" if n < 10 else "10-49 calls" if n < 50 else "50-199 calls" if n < 200 else "200+ calls"


def model_family(m):
    m = m or "unknown"
    for k in ("fable", "opus", "sonnet", "haiku"):
        if k in m:
            return "claude-" + k + ("-4.x" if "-4-" in m else "")
    return "gpt (codex)" if m.startswith("gpt") else m


def boot(units, rng):
    """units: [(flagged, total)] per session -> (rate, lo, hi)."""
    k, n = sum(u[0] for u in units), sum(u[1] for u in units)
    if not n:
        return None
    draws = []
    for _ in range(B):
        s = [units[rng.randrange(len(units))] for _ in units]
        tot = sum(x[1] for x in s)
        if tot:
            draws.append(sum(x[0] for x in s) / tot)
    draws.sort()
    return {"rate": round(k / n, 4), "ci95": [round(draws[int(.025 * len(draws))], 4),
                                              round(draws[int(.975 * len(draws)) - 1], 4)],
            "claims": n, "flagged": k, "sessions": len(units)}


def grouped(rows, key, rng, min_claims=20):
    by = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    for r in rows:
        u = by[key(r)][r["session"]]
        u[0] += r["flag"]
        u[1] += 1
    out = {}
    for g, sessions in sorted(by.items()):
        res = boot(list(map(tuple, sessions.values())), rng)
        if res and res["claims"] >= min_claims:
            out[g] = res
    return out


def label_rows():
    turns = {(t["session"], t["turn"]): t for t in map(json.loads, open(os.path.join(ROOT, "data/turns.jsonl")))}
    sample = [json.loads(l) for l in open(os.path.join(score.LABEL, "sample.jsonl"))]
    gold, a = score.load_rater("gold"), score.load_rater("A")
    rows, n_turns, verdicts, basis = [], 0, Counter(), Counter()
    for s in sample:
        labels = gold.get(s["id"]) if s["split"] == "test" else a.get(s["id"])
        if labels is None:
            continue
        n_turns += 1
        t = turns[(s["session"], s["turn"])]
        for g in labels:
            verdicts[g["verdict"]] += 1
            if g["verdict"] != "supported":
                basis[g.get("basis") or "unknown"] += 1
            rows.append({"session": s["session"], "family": g["family"], "flag": int(g["verdict"] != "supported"),
                         "model": model_family(t["model"]), "length": length_bucket(t["calls_before"]),
                         "harness": t["harness"], "split": s["split"]})
    return rows, n_turns, verdicts, basis


def main():
    rng = random.Random(SEED)
    rows, n_turns, verdicts, basis = label_rows()
    labels = {
        "turns_labelled": n_turns, "claims": len(rows), "claims_per_turn": round(len(rows) / max(1, n_turns), 2),
        "verdicts": dict(verdicts), "not_supported_basis": dict(basis),
        "not_supported": grouped(rows, lambda r: "all", rng, 1).get("all"),
        "by_family": grouped(rows, lambda r: r["family"], rng),
        "by_model": grouped(rows, lambda r: r["model"], rng),
        "by_length": grouped(rows, lambda r: r["length"], rng),
        "by_split": grouped(rows, lambda r: r["split"], rng),
    }
    claims = [json.loads(l) for l in open(os.path.join(ROOT, "data/claims.jsonl"))]
    crow = [{"session": c["session"], "family": c["kind"], "flag": int(c["verdict"] != "supported"),
             "model": model_family(c["model"]), "length": length_bucket(c["calls_before"]),
             "harness": c["harness"]} for c in claims]
    turns = [json.loads(l) for l in open(os.path.join(ROOT, "data/turns.jsonl"))]
    checker = {
        "sessions": len({c["session"] for c in claims}), "sessions_in_frame": len({t["session"] for t in turns}),
        "reported_turns": len(turns), "claims": len(claims),
        "verdicts": dict(Counter(c["verdict"] for c in claims)),
        "not_backed_basis": dict(Counter(c["basis"] for c in claims if c["verdict"] != "supported")),
        "not_backed": grouped(crow, lambda r: "all", rng, 1).get("all"),
        "by_kind": grouped(crow, lambda r: r["family"], rng),
        "by_model": grouped(crow, lambda r: r["model"], rng),
        "by_length": grouped(crow, lambda r: r["length"], rng),
        "by_harness": grouped(crow, lambda r: r["harness"], rng, 1),
    }
    out = {"labels": labels, "checker_at_scale": checker, "bootstrap": {"resamples": B, "seed": SEED, "unit": "session"}}
    with open(os.path.join(ROOT, "results/benchmark.json"), "w") as fh:
        json.dump(out, fh, indent=1)
    print(json.dumps({"labels_not_supported": labels["not_supported"], "checker_not_backed": checker["not_backed"]}, indent=1))


if __name__ == "__main__":
    main()
