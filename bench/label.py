"""Step 2: hand labels. A uniform sample of reported turns, labelled by independent raters.

Labels are per turn, not per extracted claim: each rater reads the whole report and
lists every claim in it with a verdict. That way any version of the extractor can be
scored against the same labels, and recall is measurable.

  python3 bench/label.py sample            # data/label/sample.jsonl, dev/test split by session
  python3 bench/label.py dossiers          # data/label/dossiers/<id>.txt
  python3 bench/label.py rate A [--only test] [--jobs 6]   # data/label/rater_A/<id>.json

Raters are Claude Code sessions (`claude -p`, Opus 5.5), isolated from this machine's
settings, hooks, memory and MCP servers, with read-only tools over one dossier each.
"""

import hashlib
import json
import os
import random
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from receipts.session import load  # noqa: E402

OUT = os.path.join(ROOT, "data/label")
SEED = 20261101
N_TURNS = 400
RUBRIC = open(os.path.join(ROOT, "bench/rubric.md")).read()
EARLIER_CLIP, CURRENT_CLIP = 700, 2000


def split_of(session):
    return "test" if int(hashlib.sha1(("split" + session).encode()).hexdigest(), 16) % 2 else "dev"


def sample():
    turns = [json.loads(l) for l in open(os.path.join(ROOT, "data/turns.jsonl"))]
    frame = {hashlib.sha1(json.loads(l)["path"].encode()).hexdigest()[:12]: json.loads(l)["path"]
             for l in open(os.path.join(ROOT, "data/frame.jsonl"))}
    rng = random.Random(SEED)
    picked = rng.sample(turns, N_TURNS)
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "sample.jsonl"), "w") as fh:
        for i, t in enumerate(picked):
            fh.write(json.dumps({"id": "t%03d" % i, "session": t["session"], "turn": t["turn"],
                                 "path": frame[t["session"]], "split": split_of(t["session"])}) + "\n")
    print("sampled %d turns from %d; test %d" % (
        len(picked), len(turns), sum(split_of(t["session"]) == "test" for t in picked)))


def _clip(text, n):
    text = (text or "").strip()
    if len(text) <= n:
        return text
    return text[:n * 2 // 3] + "\n[...]\n" + text[-n // 3:]


def dossier(row):
    s = load(row["path"])
    t = s.turns[row["turn"]]
    out = ["USER PROMPT (turn %d)" % t.idx, "=" * 20, _clip(t.prompt, 3000), "",
           "REPORT", "=" * 20, t.report, "", "RECEIPTS", "=" * 20]
    for c in s.calls_before(t.idx):
        cur = c.turn == t.idx
        head = "[#%d turn %d%s] %s" % (c.idx, c.turn, "*" if cur else "", c.tool)
        if c.cmd:
            head += " $ " + _clip(c.cmd, 600)
        elif c.target:
            head += " " + c.target[:300]
        if c.paths:
            head += "\n  writes: " + ", ".join(c.paths)[:300]
        status = "ERROR" if c.is_error else "ok"
        if c.exit_code is not None:
            status += " exit=%s" % c.exit_code
        out.append(head + "\n  status: " + status)
        body = _clip(c.output, CURRENT_CLIP if cur else EARLIER_CLIP)
        if body:
            out.append("  | " + body.replace("\n", "\n  | "))
    return "\n".join(out) + "\n"


def dossiers():
    rows = [json.loads(l) for l in open(os.path.join(OUT, "sample.jsonl"))]
    os.makedirs(os.path.join(OUT, "dossiers"), exist_ok=True)
    for r in rows:
        with open(os.path.join(OUT, "dossiers", r["id"] + ".txt"), "w") as fh:
            fh.write(dossier(r))
    print("wrote %d dossiers" % len(rows))


ISOLATE = json.dumps({"claudeMdExcludes": ["**/CLAUDE.md", "**/AGENTS.md"], "autoMemoryEnabled": False,
                      "hooks": {}})


def rate_one(rater, row, model):
    dest = os.path.join(OUT, "rater_" + rater, row["id"] + ".json")
    if os.path.exists(dest):
        return "cached"
    ws = os.path.join(OUT, "ws", rater, row["id"])
    os.makedirs(ws, exist_ok=True)
    shutil.copy(os.path.join(OUT, "dossiers", row["id"] + ".txt"), os.path.join(ws, "dossier.txt"))
    prompt = RUBRIC + "\n\nThe dossier is `dossier.txt` in the current directory. Label it now."
    try:
        p = subprocess.run(
            ["claude", "-p", prompt, "--model", model, "--setting-sources", "project",
             "--settings", ISOLATE, "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
             "--tools", "Read,Grep,Glob", "--allowedTools", "Read,Grep,Glob",
             "--output-format", "json"],
            cwd=ws, capture_output=True, text=True, timeout=900, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return "timeout"
    try:
        meta = json.loads(p.stdout)
        text = meta.get("result", "")
    except ValueError:
        return "bad_output"
    start, end = text.find("["), text.rfind("]")
    try:
        labels = json.loads(text[start:end + 1]) if start != -1 else None
    except ValueError:
        labels = None
    if labels is None:
        return "unparsed"
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "w") as fh:
        json.dump({"id": row["id"], "rater": rater, "model": model, "labels": labels,
                   "cost_usd_equiv": meta.get("total_cost_usd"), "turns": meta.get("num_turns"),
                   "duration_ms": meta.get("duration_ms")}, fh, indent=1)
    return "ok"


def rate(rater, only=None, jobs=6, model="opus", limit=None):
    rows = [json.loads(l) for l in open(os.path.join(OUT, "sample.jsonl"))]
    if only:
        rows = [r for r in rows if r["split"] == only]
    rows = rows[:limit] if limit else rows
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        results = list(pool.map(lambda r: rate_one(rater, r, model), rows))
    print({k: results.count(k) for k in set(results)})


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "sample":
        sample()
    elif cmd == "dossiers":
        dossiers()
    elif cmd == "rate":
        args = sys.argv[2:]
        opt = dict(zip(args[1::2], args[2::2])) if len(args) > 1 else {}
        rate(args[0], only=opt.get("--only"), jobs=int(opt.get("--jobs", 6)),
             model=opt.get("--model", "opus"), limit=int(opt["--limit"]) if "--limit" in opt else None)
