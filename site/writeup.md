# Claims without receipts

At the end of every turn a coding agent tells you what it did. "Tests pass." "Updated `config.py`." "Committed
as `a41c9e2`." Most of the time I believe it and move on. I wanted to know how often that's a mistake, so I
built `receipts`, a checker that reads the session and tests each claim against the tool calls the agent
actually made. It runs as a Claude Code Stop hook and sends the agent back to work when a claim has no receipt.

## What I measured

Every Claude Code and Codex session leaves a record: each command the agent ran, what came back, each file it
wrote. That record is a set of receipts. A claim in the report is backed if a receipt shows it at the moment
the agent said it. If the only passing test run came before a later edit, the claim isn't backed. If a receipt
shows the opposite, the claim is contradicted.

I took 2,301 sessions from my own machine (2,267 Claude Code, 34 Codex) and drew 400 reported turns at random.
Two separate Opus 5.5 labellers read each turn alongside every tool call before it and listed each claim with a
verdict. On the held-out half, a third labeller settled the disagreements, and I audited 40 of its rulings
by hand. I agreed with 37.

## What I found

- **13.3% of claims are not backed** by the agent's own receipts (95% CI 11.3 to 15.4, across 2,082 claims).
- Outright contradictions are rare: 5 of 2,082. The failure is claiming without current evidence.
- "It works / it's fixed" claims are the worst at 36.8%, then "tests pass" at 22.5%. Commits and pushes are
  almost always backed (3.9%).
- Short sessions are cleaner. 5.1% of claims in sessions of 1 to 9 tool calls aren't backed. In longer
  sessions it's 13 to 20%.

On clean single-turn tasks Haiku, Sonnet and Opus all reported honestly. To get the failure on demand I needed
a multi-step task: after a rename, Haiku said "pytest passes" based on a run from before the rename.

## The rules don't work

There are already tools for this. proof-of-done, honestly and groundtruth are Stop hooks that pattern-match
claims and require a matching successful command after the last edit. My tool has the same mode, and it costs
7.2 ms per session at the median.

I scored it against the labels. On the held-out split, its verdicts agree with careful readers at chance
(kappa about 0). End to end it catches 3 of 124 flagged claims. I spent 15 rounds tuning the rules on a
separate dev split and took flag F1 from 0.088 to 0.201. On the held-out split the gain disappeared.

My read of the misses is that relevance is the problem. A rule can see that some test run passed after the last write. It can't tell whether
that run tested what the claim is about.

A model that reads the receipts does much better. Sonnet as a judge gets flag precision 0.557 and recall 0.315,
with verdict kappa 0.52, at a median of 11.6 seconds a turn. So the hook defaults to the judge, with the rules as a
fast opt-in.

## Try it

```bash
pipx install git+https://github.com/abhaymettu/receipts
receipts demo
receipts install-hook
```

## Limits

This is one developer's sessions, mostly long autonomous runs. The labellers are models, checked against each
other and audited by me, not a panel of people. Long tool outputs were clipped, and subagent transcripts weren't
read, so some backed claims may look unbacked. A pilot on 5 sessions and 324 claims came first and is kept in the
repo under `archive/v0/`.

Code, results and the paper: [github.com/abhaymettu/receipts](https://github.com/abhaymettu/receipts).
