"""A coding-agent session reduced to what claims get checked against.

Every harness writes its transcript differently. Adapters turn one into a
`Session`: an ordered list of turns, each holding the tool calls the agent made
(the receipts) and the report it ended the turn with. Nothing downstream knows
which harness wrote the file.
"""

import json
import re
from dataclasses import dataclass, field

# Enough of a tool's output to see a test summary or an error, which sit at the
# start and the end. The middle of a 40,000-line log never decides a claim.
HEAD, TAIL = 2500, 2500


def clip(text):
    text = text or ""
    if len(text) <= HEAD + TAIL:
        return text
    return text[:HEAD] + "\n[...]\n" + text[-TAIL:]


@dataclass
class Call:
    idx: int                 # position in the whole session, across turns
    turn: int
    tool: str                # harness tool name: Bash, Edit, apply_patch, ...
    cmd: str = ""            # shell command, when the tool runs one
    paths: list = field(default_factory=list)   # files the call wrote
    target: str = ""         # file read, url fetched, pattern searched
    output: str = ""
    is_error: bool = False
    exit_code: int = None

    @property
    def text(self):
        """Everything a claim's object could be matched against."""
        return " ".join([self.cmd, self.target, " ".join(self.paths)])


@dataclass
class Turn:
    idx: int
    prompt: str = ""
    calls: list = field(default_factory=list)
    report: str = ""         # text the agent sent after its last tool call
    model: str = ""
    uuid: str = ""


@dataclass
class Session:
    path: str
    harness: str
    session_id: str = ""
    turns: list = field(default_factory=list)

    def calls_before(self, turn_idx):
        """Every receipt the agent held when it wrote turn `turn_idx`'s report."""
        return [c for t in self.turns[:turn_idx + 1] for c in t.calls]

    @property
    def n_calls(self):
        return sum(len(t.calls) for t in self.turns)


_EXIT = re.compile(r"(?:exit(?:ed with)? code:?\s*|\"exit_code\":\s*)(-?\d+)", re.I)


def exit_code_in(text):
    m = _EXIT.search(text[:400] if text else "")
    return int(m.group(1)) if m else None


def read_jsonl(path):
    with open(path, errors="ignore") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except ValueError:
                continue


def load(path):
    """Session from a Claude Code or Codex JSONL transcript."""
    from .adapters import claude_code, codex

    for rec in read_jsonl(path):
        if rec.get("type") in ("session_meta", "response_item", "event_msg", "turn_context"):
            return codex.parse(path)
        if rec.get("type") in ("user", "assistant"):
            return claude_code.parse(path)
    return claude_code.parse(path)
