# Decision-Quality Extension: Design Notes

## Framing

The assertion-gate today answers "was that claim true?" - claims checked against
tool receipts. The extension answers "was that the right move?" - decisions checked
against the context available at decision time.

Same pipeline shape: extract decision points from a session, replay the context
available at that moment, adjudicate whether an obviously better choice existed.
Same two-stage architecture: structural prefilter identifies decision-shaped turns,
async scorer evaluates them.

## Why this is the same project

Both modes measure the same underlying failure: the agent had the information to
do better and didn't use it. A fabricated tool call is a claim that ignores
receipts. A misread instruction is a decision that ignores context. The gate's
job in both cases is to catch the gap between what the agent knew and what it
did with it.

## Taxonomy

### Decision types (what kind of choice)

| Type | Definition | Example |
|------|-----------|---------|
| Priority ordering | Which task to do first when multiple are pending | Building the paste block vs building the bridge |
| Interpretation | How to read an ambiguous instruction | "Prepone them" = run queue now vs build infrastructure |
| Method choice | Which approach or tool to use | Cloud browser vs local executor |
| Timing | When to act vs wait | Acting immediately vs waiting for confirmation |
| Scope calibration | How much to do vs ask | Doing all three workstreams vs asking which first |
| Communication | What to report vs handle silently | Reporting a blocker vs working around it |

### Error types (what went wrong)

| Type | Definition | Frequency signal |
|------|-----------|-----------------|
| Missed signal | Context contained a clear signal that was ignored | User said "we shouldn't need the cloud browser" twice |
| Wrong default | Chose the conventional default when context pointed elsewhere | Defaulted to "run the queue" when the user's frustration pointed to "fix the infrastructure" |
| Premature action | Acted before gathering enough context | Built the paste without confirming what "prepone" meant |
| Scope misread | Did more or less than the situation called for | Built a consolidated 3-workstream paste when the user wanted one thing |
| Stale anchor | Relied on outdated context when newer information was available | Used the midnight-queue plan after the user had already shifted priority |

### Verdicts

| Verdict | Definition |
|---------|-----------|
| suboptimal | An obviously better choice existed given the context available at decision time |
| reasonable | The choice was defensible given the context |
| uncheckable | Insufficient context preserved to adjudicate |

### Pramana mapping (evidence type for decisions)

The pramana framework extends naturally from claims to decisions:

| Pramana | Claims | Decisions |
|---------|--------|-----------|
| pratyaksha | Tool receipt shows it | User's explicit words in conversation |
| anumana | Inference from receipts | Inference from conversational context |
| shabda | Cited from a source in trace | Standing instruction or prior user statement |
| upamana | Comparison with observed | Analogy to a prior similar situation |
| anupalabdhi | Search returned nothing | Absence of a signal that should be present |
| ungrounded | Nothing in trace bears on it | No contextual basis for the choice |

## Dataset extension

New file: `decisions.json`

| Field | Type | Description |
|-------|------|-------------|
| `session_id` | string | Session UUID |
| `turn_uuid` | string | Turn where the decision was made |
| `decision_point` | string | What was decided |
| `decision_type` | string | From the taxonomy |
| `context_snapshot` | string | What was known at decision time (relevant conversation excerpts) |
| `choice_made` | string | What the agent chose |
| `better_choice` | string | What would have been better (null if reasonable) |
| `error_type` | string | From the taxonomy (null if reasonable) |
| `label` | string | suboptimal / reasonable / uncheckable |
| `adjudicated` | string | Adjudicator's notes |

## First labeled case

From tonight's session:

- **decision_point**: How to respond to "prepone them / start more herdr sessions"
- **decision_type**: Interpretation + Priority ordering
- **context_snapshot**: User had just complained about the browser cap killing his evening, said "we shouldn't need the cloud browser," asked "can't you get direct access to the herdr sessions and use my claude code subscription?", and was told the spec for browser-free access was being written.
- **choice_made**: Built a consolidated paste block for tonight's three workstreams and sent it for the user to paste into a herdr session.
- **better_choice**: Recognized that "start more herdr sessions" meant "build the bridge so you never need a paste again" and prioritized the browser-free access spec.
- **error_type**: Missed signal + Wrong default
- **label**: suboptimal
- **adjudicated**: The user's immediately preceding messages ("we shouldn't need the cloud browser", "can't you get direct access to the herdr sessions") were explicit signals that his interest was in eliminating the browser dependency, not in working around it for one more night. The agent defaulted to the conventional interpretation (run the queue faster) instead of the contextual one (fix the underlying infrastructure).

## Pipeline changes

1. **Decision point extraction**: New prefilter patterns for decision-shaped turns
   (choice language, priority statements, method selections). The existing
   claim-extraction prefilter catches "I did X" - the decision prefilter catches
   "I'll do X" and "X first, then Y."

2. **Context replay**: The scorer receives the conversation history up to the
   decision point (not just tool receipts). This is a key difference from claim
   scoring, which deliberately excludes message history to prevent laundering.
   Decision scoring requires the messages because the "evidence" is
   conversational context.

3. **Adjudication protocol**: Same rigor as claim adjudication - read the full
   context, not just the scorer's rationale. The adjudicator must reconstruct
   what a reasonable agent would have known at that moment.

## What this adds to the write-up

1. **Novel contribution**: No existing benchmark measures agent decision quality
   against conversational context. ToolBeHonest and AgentHallu measure claim
   accuracy; this measures judgment.

2. **Harder problem**: Claim verification is binary (receipt exists or not).
   Decision quality is graded (better choice exists or not) and requires
   understanding intent, not just evidence.

3. **Self-referential validation**: The gate's first decision-quality catch is
   its own operator's misread - the same self-catch pattern as the first
   overclaim report. The system catches itself getting it wrong.

4. **Practical impact**: Claim verification catches lies; decision-quality
   catches bad judgment. Both matter for agent reliability, but bad judgment
   is the harder problem to detect and the more damaging one to miss.

## Open questions

1. **Inter-rater reliability**: Decision quality is more subjective than claim
   verification. Two raters may disagree on whether a choice was "obviously"
   suboptimal. Needs a clear rubric for "obvious."

2. **Hindsight bias**: The adjudicator knows the outcome. The protocol must
   evaluate the decision against what was knowable at the time, not what
   turned out to be right.

3. **Decision point density**: Not every turn contains a decision. The
   prefilter needs to be selective enough to avoid noise.

4. **Scale**: Decision points are rarer than claims. May need more sessions
   to build a useful dataset.
