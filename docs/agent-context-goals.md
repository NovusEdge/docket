# Future goals for agent context

Docket should give an agent a compact, understandable view of the decisions,
premises, and open questions that affect its work. The agent should be able to
retrieve the exact records behind that view and recognize when information is
missing or needs another check.

This document describes future goals and open design questions. It carries no
release dates or implementation commitments. The [ledger reference](ledger.md)
describes current behavior; the [north star](north-star.md) covers the broader
execution-ledger direction.

## Starting point

Docket 0.8.1 provides typed records, support alternatives, decision prerequisites,
supersession, evidence references, and derived states. Its context renderer
selects records by query and file scope, includes bounded direct neighbors, and
fits whole record blocks into a character budget. It reports omissions and
provides a command to retrieve individual records.

The next improvements should help agents select, understand, and use that data
throughout a task.

## Preserve meaning within a compact view

A fixed context budget can hold only part of a growing ledger. Preserve the
complete ledger and make the boundaries of each briefing explicit.

- Keep selected propositions, choices, and relationship formulas exact.
- Preserve the distinction between recorded state, currentness, and applicability.
- Identify deferred records and fields, with a direct way to retrieve them.
- Keep full records available at the revision used to produce the briefing.
- Give any exact interchange format a round-trip guarantee for the selected
  records, including provenance and defaults.

A reference makes information recoverable. The agent must fetch it before
relying on details that the briefing leaves out. Any generated summary should
identify itself as a summary and point to its source records.

## Lead with what affects the task

A briefing should make these items easy to find:

- Applicable decisions relevant to the requested work.
- Blocked decisions and the prerequisites causing the blockage.
- Relevant disputed premises and unresolved questions.
- Changes since the agent's previous briefing.
- Missing information that requires retrieval before proceeding.

Use task text, affected files, explicit record IDs, and relationships to select
records. Make selection reasons inspectable so an agent can refine an unhelpful
query. Keep historical explanations available without allowing old defect
reports to crowd out current commitments.

## Explain dependencies and coverage

Follow prerequisite chains far enough to explain the decisions being used. For
example, if `d12` depends on `d8`, which depends on disputed claim `c3`, show the
blocking path alongside the relevant record text:

```text
d12 blocked: d8 -> c3 disputed
```

Keep support alternatives explicit as complete AND sets joined by OR. Support
records remain declared grounds; prerequisite relationships determine decision
applicability under the ledger's rules.

Report coverage in terms an agent can act on:

| Coverage | Meaning |
| --- | --- |
| No matches found | Retrieval found no matching records. |
| Partial coverage | Relevant records or fields were deferred. |
| Selected prerequisites covered | The selected records' prerequisite chains were included. |

If an explanation exceeds the budget, identify the gap and offer targeted
retrieval. Coverage describes the selected ledger data. Unrecorded knowledge and
missed matches remain possible.

## Spend context on useful information

Use a small shared legend, consistent field names, and explicit references for
repeated metadata. Keep record identity and state close to the text they qualify.

Compare readable structured formats against today's output using actual model
tokenizers and comprehension tests. Measure total context use, including legends
and follow-up retrieval. Fewer characters alone do not establish a token saving.

The preferred format should preserve meaning and remain understandable without
a large decoding guide.

## Capture conditions and evidence that help review

Extend existing scope, evidence, attribution, and revisit metadata where concrete
agent failures show a need.

| Potential information | What it helps establish |
| --- | --- |
| Environment and version conditions | Where a decision applies. |
| Evidence artifact, revision, check method, and result | What was actually checked. |
| Revalidation triggers | Which changes call for another check. |
| Explicit exceptions | Where a general commitment stops applying. |
| Recorded challenges or contradictions | Which premises need review. |
| Decision owner and attribution source | Who made the commitment and how that attribution was recorded. |

Keep additions optional until their semantics and retrieval value are clear.
A changed evidence artifact should trigger review without automatically
falsifying its claim. Attribution records do not authenticate an identity or
grant authority over current user instructions.

## Deliver context when the agent needs it

Aim for a small initial briefing, followed by scoped retrieval as work develops.

- Refresh when the task or affected files change.
- Rebuild the briefing after compaction or when its retained baseline is unknown.
- During uninterrupted work, deliver revision-based changes, including newly
  blocked decisions and retired records.
- Support targeted expansion before an agent acts on an incomplete explanation.
- Let delegated agents retrieve context for their own task and report the
  revision they used.

Updates need an identifiable baseline, ledger, and scope. A missing or mismatched
baseline should lead to a fresh briefing. Harness integration will determine
which refresh events can run automatically.

Keep instructions for using Docket in the harness guidance and identify ledger
content as project data. Clear formatting and timely delivery should help models
use the briefing; effectiveness needs measurement on the models being supported.

## Evaluate use, comprehension, and cost

Evaluate whether agents:

- Respect applicable decisions and notice disputed prerequisites.
- Interpret support alternatives correctly.
- Recognize incomplete coverage and retrieve missing details.
- Adjust their behavior after supersession or compaction.
- Distinguish supplied evidence from a fresh verification result.

Compare against the current renderer across tasks, budgets, record positions,
and models. Track task correctness, relevant-record recall, token use, retrieval
calls, and latency. Include large records, deep prerequisite chains, changing
ledgers, and irrelevant history.

## Questions to resolve through experiments

- Which readable format gives the best comprehension per token?
- Which fields must travel with a decision, and which can be deferred safely?
- How should relevance and prerequisite coverage share a limited budget?
- How should explicit challenges be represented without treating inferred
  disagreement as an established contradiction?
- Which refresh events improve behavior enough to justify their context cost?
- How should revision-specific retrieval behave when the ledger changes mid-task?

A useful first area to explore is compact briefings with prerequisite
explanations and explicit coverage reporting. Results should guide richer
metadata and delivery mechanisms.
