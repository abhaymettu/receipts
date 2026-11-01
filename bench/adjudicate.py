"""Step 2b: gold labels for the test split.

Claims both raters list with the same verdict go straight to gold. Everything else
(a claim only one rater listed, or a verdict they disagree on) is a dispute. A third
rater, C, reads the same dossier plus both raters' notes and rules on each dispute.
The author then reviewed every ruling; reversals live in data/label/overrides.json.

  python3 bench/adjudicate.py rule [--jobs 4]   # data/label/rater_C/<id>.json
  python3 bench/adjudicate.py review            # print every ruling for the human pass
  python3 bench/adjudicate.py build             # data/label/rater_gold/<id>.json + results/adjudication.json
"""

import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "bench"))
sys.path.insert(0, ROOT)
import label  # noqa: E402
import score  # noqa: E402

OUT = label.OUT


def disputes(a, b):
    agreed, out = [], []
    pairs = score.pair(a, b)
    for i, j in pairs:
        if a[i]["verdict"] == b[j]["verdict"]:
            agreed.append(a[i])
        else:
            out.append({"kind": "verdict", "span": a[i]["span"], "family": a[i]["family"],
                        "A": a[i]["verdict"], "B": b[j]["verdict"],
                        "A_note": a[i].get("note", ""), "B_note": b[j].get("note", "")})
    for i, g in enumerate(a):
        if i not in {x for x, _ in pairs}:
            out.append({"kind": "only_A", "span": g["span"], "family": g["family"], "A": g["verdict"],
                        "A_note": g.get("note", "")})
    for j, g in enumerate(b):
        if j not in {y for _, y in pairs}:
            out.append({"kind": "only_B", "span": g["span"], "family": g["family"], "B": g["verdict"],
                        "B_note": g.get("note", "")})
    return agreed, out


PROMPT = """%s

## Adjudication

Two raters labelled this dossier independently under the rubric above and disagreed on the items
below. For each item decide, from the receipts:
- `is_claim`: is the span a claim under the rubric (true/false)?
- if it is, its `verdict` (supported | contradicted | unbacked) and `family`.

Items:
%s

Reply with only a JSON array, one object per item, in the same order:
[{"item": <n>, "is_claim": true|false, "family": "...", "verdict": "...", "note": "<one sentence>"}]

The dossier is `dossier.txt` in the current directory."""


def notes_raw(rater):
    d = os.path.join(OUT, "rater_" + rater)
    return {json.load(open(os.path.join(d, f)))["id"]: [
        g for g in json.load(open(os.path.join(d, f)))["labels"] if isinstance(g, dict)]
        for f in os.listdir(d)}


def rule_one(row, items):
    dest = os.path.join(OUT, "rater_C", row["id"] + ".json")
    if os.path.exists(dest) or not items:
        return "skip"
    import shutil
    import subprocess
    ws = os.path.join(OUT, "ws", "C", row["id"])
    os.makedirs(ws, exist_ok=True)
    shutil.copy(os.path.join(OUT, "dossiers", row["id"] + ".txt"), os.path.join(ws, "dossier.txt"))
    listing = "\n".join("%d. %s" % (n, json.dumps(it)) for n, it in enumerate(items))
    p = subprocess.run(
        ["claude", "-p", PROMPT % (label.RUBRIC, listing), "--model", "opus", "--setting-sources", "project",
         "--settings", label.ISOLATE, "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
         "--tools", "Read,Grep,Glob", "--allowedTools", "Read,Grep,Glob", "--output-format", "json"],
        cwd=ws, capture_output=True, text=True, timeout=900, stdin=subprocess.DEVNULL)
    try:
        text = json.loads(p.stdout).get("result", "")
        rulings = json.loads(text[text.find("["):text.rfind("]") + 1])
    except ValueError:
        return "unparsed"
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    json.dump({"id": row["id"], "items": items, "rulings": rulings}, open(dest, "w"), indent=1)
    return "ok"


def plan():
    a, b = notes_raw("A"), notes_raw("B")
    out = []
    for row in score.rows("test"):
        if row["id"] in a and row["id"] in b:
            ga = [dict(g, **{"note": g.get("note", "")}) for g in score.clean(a[row["id"]])]
            gb = [dict(g, **{"note": g.get("note", "")}) for g in score.clean(b[row["id"]])]
            for g, raw in ((ga, a[row["id"]]), (gb, b[row["id"]])):
                notes = {x.get("span"): x.get("note", "") for x in raw}
                for x in g:
                    x["note"] = notes.get(x["span"], "")
            agreed, items = disputes(ga, gb)
            out.append((row, agreed, items))
    return out


def main():
    cmd = sys.argv[1]
    if cmd == "rule":
        jobs = int(sys.argv[3]) if len(sys.argv) > 3 else 4
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            res = list(pool.map(lambda t: rule_one(t[0], t[2]), plan()))
        print({k: res.count(k) for k in set(res)})
    elif cmd == "review":
        for row, _, _ in plan():
            f = os.path.join(OUT, "rater_C", row["id"] + ".json")
            if not os.path.exists(f):
                continue
            r = json.load(open(f))
            for it, ru in zip(r["items"], r["rulings"]):
                print("%s #%s %-8s A=%-12s B=%-12s -> %s %s | %s\n    span: %s\n    C: %s" % (
                    row["id"], ru.get("item"), it["kind"], it.get("A", "-"), it.get("B", "-"),
                    "CLAIM" if ru.get("is_claim") else "not-claim", ru.get("verdict", ""), ru.get("family", ""),
                    it["span"][:150], ru.get("note", "")[:200]))
    elif cmd == "build":
        overrides = {}
        op = os.path.join(OUT, "overrides.json")
        if os.path.exists(op):
            overrides = json.load(open(op))
        stats = {"turns": 0, "agreed": 0, "disputes": 0, "ruled_claim": 0, "ruled_not_claim": 0, "overridden": 0}
        os.makedirs(os.path.join(OUT, "rater_gold"), exist_ok=True)
        for row, agreed, items in plan():
            gold = [dict(g) for g in agreed]
            f = os.path.join(OUT, "rater_C", row["id"] + ".json")
            rulings = json.load(open(f))["rulings"] if items and os.path.exists(f) else []
            for n, it in enumerate(items):
                ru = next((x for x in rulings if x.get("item") == n), None)
                key = "%s#%d" % (row["id"], n)
                if key in overrides:
                    ru = dict(ru or {}, **overrides[key])
                    stats["overridden"] += 1
                if ru and ru.get("is_claim") and ru.get("verdict") in score.VERDICTS:
                    gold.append({"span": it["span"], "family": ru.get("family") or it["family"],
                                 "verdict": ru["verdict"], "basis": ""})
                    stats["ruled_claim"] += 1
                else:
                    stats["ruled_not_claim"] += 1
            stats["turns"] += 1
            stats["agreed"] += len(agreed)
            stats["disputes"] += len(items)
            json.dump({"id": row["id"], "rater": "gold", "labels": gold},
                      open(os.path.join(OUT, "rater_gold", row["id"] + ".json"), "w"), indent=1)
        json.dump(stats, open(os.path.join(ROOT, "results", "adjudication.json"), "w"), indent=1)
        print(stats)


if __name__ == "__main__":
    main()
