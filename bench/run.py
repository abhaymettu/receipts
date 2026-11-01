"""Step 1: run the checker over every session in the frame.

Writes data/claims.jsonl, one row per claim (private: it holds claim text), and
data/turns.jsonl, one row per turn with a report (for sampling and denominators).
"""

import hashlib
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from receipts.check import check_session  # noqa: E402
from receipts.session import load  # noqa: E402


def sid(path):
    return hashlib.sha1(path.encode()).hexdigest()[:12]


def run(row):
    s = load(row["path"])
    base = {"session": sid(row["path"]), "harness": row["harness"], "entrypoint": row["entrypoint"],
            "session_calls": s.n_calls, "session_turns": len(s.turns)}
    turns, claims = [], []
    before = 0
    for t in s.turns:
        before += len(t.calls)
        if t.report:
            turns.append(dict(base, turn=t.idx, model=t.model, turn_calls=len(t.calls),
                              calls_before=before, report_chars=len(t.report)))
    for v in check_session(s):
        t = s.turns[v.turn]
        claims.append(dict(base, turn=v.turn, model=t.model, kind=v.kind, verdict=v.verdict,
                           basis=v.basis, reason=v.reason, claim=v.claim, turn_calls=len(t.calls),
                           calls_before=sum(len(x.calls) for x in s.turns[:v.turn + 1])))
    return turns, claims


def main():
    rows = [json.loads(l) for l in open(os.path.join(ROOT, "data/frame.jsonl"))]
    rows = [r for r in rows if not r["excluded"]]
    with ProcessPoolExecutor(max_workers=8) as pool:
        out = list(pool.map(run, rows, chunksize=4))
    with open(os.path.join(ROOT, "data/turns.jsonl"), "w") as ft, \
            open(os.path.join(ROOT, "data/claims.jsonl"), "w") as fc:
        for turns, claims in out:
            for t in turns:
                ft.write(json.dumps(t) + "\n")
            for c in claims:
                fc.write(json.dumps(c) + "\n")
    n_t = sum(len(t) for t, _ in out)
    n_c = sum(len(c) for _, c in out)
    print("sessions %d, reported turns %d, claims %d" % (len(rows), n_t, n_c))


if __name__ == "__main__":
    main()
