"""Step 4: what the Stop hook costs. Times the hook's own work (parse the transcript,
check the last turn's report) on every session in the frame, one at a time, in one
process, as if each session had just ended.

Writes results/hook_cost.json: latency percentiles overall and by transcript size.
"""

import json
import os
import statistics
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from receipts.hook import findings_for_last_turn  # noqa: E402


def pct(xs, q):
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, int(q * len(xs)))], 1)


def main():
    rows = [json.loads(l) for l in open(os.path.join(ROOT, "data/frame.jsonl"))]
    rows = [r for r in rows if not r["excluded"]]
    times, by_size, fired = [], {}, 0
    for r in rows:
        t0 = time.perf_counter()
        _, findings = findings_for_last_turn(r["path"])
        ms = (time.perf_counter() - t0) * 1000
        times.append(ms)
        fired += bool(findings)
        mb = r["bytes"] / 1e6
        bucket = "<1MB" if mb < 1 else "1-10MB" if mb < 10 else ">=10MB"
        by_size.setdefault(bucket, []).append(ms)
    out = {"sessions": len(times), "ms_p50": pct(times, .5), "ms_p90": pct(times, .9),
           "ms_p99": pct(times, .99), "ms_max": round(max(times), 1), "ms_mean": round(statistics.mean(times), 1),
           "last_turn_flagged_share": round(fired / len(times), 4),
           "by_size": {k: {"n": len(v), "ms_p50": pct(v, .5), "ms_p99": pct(v, .99)} for k, v in sorted(by_size.items())},
           "machine": os.uname().machine, "python": sys.version.split()[0]}
    with open(os.path.join(ROOT, "results/hook_cost.json"), "w") as fh:
        json.dump(out, fh, indent=1)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
