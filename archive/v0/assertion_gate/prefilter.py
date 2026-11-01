"""Structural prefilter: does this message make a claim about external state?

Regex and heuristics only - no model call, target <10ms. This is the front end for
both modes: no match means the turn is dropped without any further work, so it has
to be cheap and it has to be biased toward letting borderline turns through to the
(free) deterministic checker rather than toward flagging everything.

It answers "is there a claim shape here", not "is the claim true". Truth is the
checker's and the scorer's job.
"""

import re

# Code fences, inline code and block quotes are the model quoting the world, not
# asserting about it. Stripped before matching so a pasted log line saying
# "0 tests failed" is not read as a claim.
_NOISE = re.compile(r"```.*?```|`[^`\n]+`|^\s*>.*$", re.S | re.M)

# Hedged or future-tense: an intention or a guess is not an assertion.
_HEDGE = re.compile(
    r"\b(?:i(?:'|’)?ll|i will|let me|going to|about to|should|would|"
    r"might|may|probably|likely|appears? to|seems? to|i think|i believe|not sure|"
    r"unsure|can(?:'|’)?t confirm|haven(?:'|’)?t (?:run|checked|verified)|"
    r"if (?:it|this|that)|assuming|presumably|in theory)\b", re.I)

# A named tool, claimed as used. Lives here rather than in the checker because the
# prefilter has to be a superset of it: the hook runs this first and exits on no
# match, so a shape only the checker knows about is a finding it can never reach.
# checker.py imports this same object.
TOOL_REF = re.compile(
    r"\b(?:used|using|ran|called|via|with|through)\s+(?:the\s+)?`?"
    r"(Bash|Read|Write|Edit|Glob|Grep|WebFetch|WebSearch|Task|NotebookEdit|"
    r"mcp__[a-zA-Z0-9_]+)`?(?:\s+tool)?\b")

# Claim shapes, by the class of overclaim each one tends to precede.
PATTERNS = {
    "tool": TOOL_REF,
    "ran": re.compile(
        r"\bi\s+(?:just\s+|already\s+)?(?:ran|executed|invoked|called|launched|"
        r"tested|checked|verified|confirmed|deployed|pushed|installed|fetched|"
        r"opened|queried|measured|benchmarked|timed)\b", re.I),
    "state": re.compile(
        r"\b(?:it|this|that|they|everything|all(?:\s+\w+){0,2}|the\s+\w+(?:\s+\w+)?)\s+"
        r"(?:now\s+)?(?:works|work|is working|are working|passes|pass|passed|"
        r"is fixed|are fixed|is live|is deployed|is up|is green|builds|compiles)\b", re.I),
    "verified": re.compile(
        r"\b(?:verified|confirmed|validated|double[- ]checked|tested and|"
        r"checked (?:it|this|that|twice)|as (?:i )?verified)\b", re.I),
    "done": re.compile(
        r"\b(?:fixed|deployed|pushed|shipped|installed|created|committed|merged|"
        r"published)\b(?!\s+(?:it|this|that)?\s*\?)", re.I),
    "absence": re.compile(
        r"\b(?:no (?:results|matches|output|errors|failures|occurrences|instances|"
        r"hits|files|references)|nothing (?:found|matched|returned)|"
        r"there (?:are|were|is|was) no\b|couldn(?:'|’)?t find (?:any|anything)|"
        r"(?:does|do|did) not exist|zero (?:results|matches|errors))", re.I),
    # Any number attached to a plural noun. A closed noun list missed real claims
    # ("534 turns", "984 logs") the moment the subject matter changed, and this
    # layer is allowed to over-flag: the checker and scorer decide, not this.
    "count": re.compile(
        r"\b(?:all\s+)?(\d{1,6})\s+(?:of\s+the\s+)?(?:[a-z]+\s+){0,2}"
        r"([a-z]{3,}s|entries|data)\b"),
}


def prefilter(message):
    """(flagged, hits). hits are (kind, matched_text) in order of appearance."""
    if not message:
        return False, []
    text = _NOISE.sub(" ", message)
    hits = []
    for kind, pattern in PATTERNS.items():
        for m in pattern.finditer(text):
            # A hedge in the same sentence turns an assertion into a guess.
            start = text.rfind(".", 0, m.start()) + 1
            end = text.find(".", m.end())
            sentence = text[start:end if end != -1 else len(text)]
            if _HEDGE.search(sentence):
                continue
            hits.append((kind, m.group(0).strip()))
    return bool(hits), hits
