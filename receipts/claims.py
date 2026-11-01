"""Claims an agent makes about its own work, pulled out of its end-of-turn report.

A claim is one sentence (or bullet, or table row) asserting, as done or true,
something a receipt could back: tests pass, the build is clean, a file was
changed, a commit was made, something was verified or now works. Plans, hedges,
questions and admissions ("I did not run the tests") are not claims.

One sentence can carry claims from different families ("fixed the parser and
tests pass" is a fix claim and a test claim), but at most one per family.
"""

import re
from dataclasses import dataclass, field

_FENCE = re.compile(r"```.*?(?:```|\Z)", re.S)
_QUOTE = re.compile(r"^\s*>.*$", re.M)
_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z`*\"(\[])|\n+")
_MARKUP = re.compile(r"^\s*(?:[-*+]|\d+[.)]|#+)\s+|\*\*|__")

HEDGE = re.compile(
    r"\b(?:will|I'll|you'll|going to|should|would|could|might|may|probably|likely|perhaps|"
    r"maybe|plan(?:ned)? to|need(?:s|ed)? to|want(?:s|ed)? to|next step|todo|to do|"
    r"if|unless|once|when you|let me|can you|you can|try|hopefully|expect(?:ed)?|"
    r"in case|whether|needs?|pending|remaining|left to)\b", re.I)
NEGATION = re.compile(
    r"\b(?:not|never|no longer|unverified|untested|unable|cannot|nothing (?:was|has been))\b|n't\b|"
    r"\bwithout (?:running|testing|verifying|checking)\b", re.I)
REPORTED = re.compile(
    r"\b(?:the (?:lane|subagent|agent|worker|report|readme|docs?|issue|user|ticket|log)|you|they|he|she)"
    r"\s+(?:says?|said|claims?|claimed|reports?|reported|mentioned|noted|wrote)\b", re.I)

OK_WORDS = r"pass(?:es|ed|ing)?|green|succeed(?:s|ed)?|clean(?:ly)?|OK|all good"
_P = r"(?:%s)" % OK_WORDS
KINDS = [
    # family, kind, pattern. Order within a family is priority.
    ("test", "test_pass", re.compile(
        r"\b(?:tests?|test suite|suites?|specs?|pytest|vitest|jest|unittest|cargo test|go test|"
        r"tests\.R|e2e|smoke tests?)\b[^.;]{0,60}?\b" + _P + r"\b|"
        r"\b\d+\s*/\s*\d+\s+(?:\w+\s+)?(?:tests?\s+|checks?\s+)?pass|\b\d+\s+(?:\w+\s+)?(?:tests?\s+)?passed\b|"
        r"\ball\s+(?:\d+\s+)?(?:\w+\s+)?(?:tests?|checks|assertions)\s+(?:now\s+)?pass", re.I)),
    ("typecheck", "typecheck_pass", re.compile(
        r"\b(?:typechecks?|typechecking|type-?check(?:s|ing)?|tsc|mypy|pyright|types)\b[^.;]{0,30}?"
        r"\b(?:" + OK_WORDS + r"|no (?:type )?errors|0 errors)\b|\bno type errors\b", re.I)),
    ("lint", "lint_pass", re.compile(
        r"\b(?:lint(?:s|er|ing)?|eslint|ruff|clippy|flake8|shellcheck|swiftlint)\b[^.;]{0,30}?"
        r"\b(?:" + OK_WORDS + r"|no (?:errors|warnings|issues)|0 (?:errors|warnings))\b", re.I)),
    ("build", "build_pass", re.compile(
        r"\b(?:build|builds|built|compiles?|compiled|compilation)\b[^.;]{0,40}?"
        r"\b(?:" + OK_WORDS + r"|success(?:fully)?|without (?:errors|warnings)|fine)\b|"
        r"\b(?:it|everything|the (?:app|project|site|package|binary|paper|pdf)) (?:now )?(?:builds|compiles)\b", re.I)),
    ("git", "pr", re.compile(
        r"\b(?:opened|created|filed|raised|merged)\s+(?:a\s+|the\s+|draft\s+)*(?:PR|pull request)\b|"
        r"\bPR\s+#?\d+\s+(?:is\s+)?(?:open|up|opened|created|merged)\b", re.I)),
    ("git", "push", re.compile(r"\bpushed\b|\bpush(?:ed)? to (?:origin|main|master|remote)\b", re.I)),
    ("git", "commit", re.compile(
        r"\bcommitted\b|\bcommit(?:ted)? (?:as|in)\b|\bin commit\b|\bnew commit\b|"
        r"\bcommit\s+`?[0-9a-f]{7,40}\b|\b(?:landed|lands) (?:in|as)\b", re.I)),
    ("ship", "deployed", re.compile(
        r"\b(?:deployed|is (?:now )?live|went live|published|released)\b", re.I)),
    ("ship", "installed", re.compile(r"\binstalled\b", re.I)),
    ("work", "works", re.compile(
        r"\b(?:now works|works now|works (?:correctly|as expected|end[- ]to[- ]end)|is working|are working|"
        r"(?:it|this|that|everything|all of (?:it|them)) works|"
        r"(?:is|are|was|were|now) (?:fixed|resolved)|fixed\b|resolved\b)", re.I)),
    ("work", "verified", re.compile(
        r"\b(?:verified|confirmed|double-checked|validated|smoke-tested|sanity-checked|tested)\b", re.I)),
    ("work", "ran", re.compile(
        r"\bI\s+(?:just\s+|also\s+|then\s+|first\s+)?(?:ran|re-?ran|executed|invoked)\b|"
        r"^(?:Ran|Re-?ran|Executed)\b", re.I)),
    ("work", "file_change", re.compile(
        r"\b(?:updated|edited|modified|changed|created|added|wrote|rewrote|removed|deleted|renamed|"
        r"moved|refactored|replaced|patched)\b", re.I)),
]

FILE_EXT = r"(?:py|pyi|ts|tsx|js|jsx|mjs|cjs|rs|go|swift|java|kt|rb|php|c|h|cc|cpp|hpp|m|cs|r|R|sql|sh|" \
           r"css|scss|html|vue|svelte|astro|json|toml|yaml|yml|md|mdx|txt|tex|bib|ipynb|lock|cfg|ini|env|xml|plist)"
_OBJ_FILE = re.compile(r"`([^`\s]+?\." + FILE_EXT + r")`|(?<![\w/.])((?:[\w.~-]+/)*[\w-]+\." + FILE_EXT + r")\b")
_OBJ_PATH = re.compile(r"`((?:[\w.~-]+/)+[\w.-]*)`")
_SHA = re.compile(r"(?<![\w-])([0-9a-f]{7,40})(?![\w-])")


@dataclass
class Claim:
    turn: int
    kind: str
    text: str
    files: list = field(default_factory=list)
    sha: str = ""


def sentences(report):
    text = _QUOTE.sub(" ", _FENCE.sub(" ", report or ""))
    for raw in _SPLIT.split(text):
        s = _MARKUP.sub("", raw).strip(" |\t")
        if len(s) >= 8:
            yield s


def is_assertion(s):
    return not (s.rstrip().endswith("?") or HEDGE.search(s) or NEGATION.search(s)
                or REPORTED.search(s))


def extract(report, turn=0):
    claims = []
    for s in sentences(report):
        if not is_assertion(s):
            continue
        seen = set()
        for family, kind, rx in KINDS:
            if family in seen or not rx.search(s):
                continue
            files = [a or b for a, b in _OBJ_FILE.findall(s)] + _OBJ_PATH.findall(s)
            if kind == "file_change" and not files and not re.match(r"\s*I\b", s):
                continue  # "the format changed" is not a claim about the agent's own edit
            seen.add(family)
            sha = _SHA.search(s) if family == "git" else None
            claims.append(Claim(turn=turn, kind=kind, text=s[:400], files=files,
                                sha=sha.group(1) if sha and re.search(r"\d", sha.group(1)) else ""))
    return claims
