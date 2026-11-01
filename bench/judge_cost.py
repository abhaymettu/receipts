"""Step 6: what a judge costs per labelled turn (wall time and the CLI's reported API-equivalent cost)."""

import json
import os
import statistics

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
out = {}
for rater, model in (("A", "opus"), ("B", "opus"), ("S", "sonnet"), ("H", "haiku")):
    d = os.path.join(ROOT, "data/label/rater_" + rater)
    rs = [json.load(open(os.path.join(d, f))) for f in os.listdir(d)]
    secs = sorted(r["duration_ms"] / 1000 for r in rs if r.get("duration_ms"))
    usd = [r["cost_usd_equiv"] for r in rs if r.get("cost_usd_equiv") is not None]
    out[rater] = {"model": model, "turns": len(rs), "seconds_median": round(statistics.median(secs), 1),
                  "seconds_p90": round(secs[int(.9 * len(secs))], 1),
                  "api_equivalent_usd_mean": round(statistics.mean(usd), 4)}
json.dump(out, open(os.path.join(ROOT, "results/judge_cost.json"), "w"), indent=1)
print(json.dumps(out, indent=1))
