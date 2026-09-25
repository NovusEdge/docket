# Why Docket?

I wanted Docket because I was running into all of this: agents forgetting earlier choices, agents relying on assumptions that were no longer current, and having to reconstruct the reasoning behind past work.

Remembering the choice only solves part of that. I also need to know why we chose it, what it depended on, and whether we have since changed our minds. When that context is spread across conversations, notes, and commits, picking up the work means piecing it back together.

That is the work I want Docket to reduce. It keeps choices, their grounds, and unresolved questions in a form that later sessions can retrieve and follow.

But that still leaves a fair question: why does this need a tool of its own? I can write notes. I already have Git. Docket adds a format, commands, relationships, and integrations that somebody has to maintain.

{% hint style="info" %}
Docket has to save more work recovering decisions than it costs to maintain the records. If my notes already do the job, adding a ledger buys me very little.
{% endhint %}

Start with [Markdown and ADRs](#why-not-keep-a-markdown-file) or [Git](#why-not-rely-on-git), or read on for the [reasons behind the structure](#why-these-record-types-and-relationships).

## Remembering the choice is only part of the job

Take a hypothetical service with an in-process queue for background jobs:

| At the time of the decision | Months later |
|---|---|
| The service runs in one process. | It runs across multiple workers. |
| Pending jobs may be discarded on restart. | Jobs must survive restarts. |
| The team chooses an in-process queue. | The queue choice needs another look. |

If I leave a note saying “use an in-process queue,” the next agent can remember exactly what I wrote and still carry forward a design whose assumptions no longer hold.

What I need to leave behind is the choice, its reasons, the code it applies to, and the conditions that call for another look. If we change the design, I need the replacement to be identifiable without erasing why the earlier version existed.

Docket provides fields and relationships for this information. When a recorded prerequisite becomes unavailable, it can mark a dependent decision as blocked. I still have to discover and record the changed assumption, or have an agent do that work. Docket does not inspect the running service and detect that the design has become wrong.

## Why not keep a Markdown file?

**I can put all of this in Markdown.** It is easy to read and edit, and I can explain a decision at whatever length it needs. An architecture decision record (ADR) can preserve a choice, its alternatives, its consequences, and its status. If I maintain those records and reliably retrieve the right ones, I have addressed much of the problem.

The maintenance becomes more involved when I need to connect those records:

- Identify the note that replaces the old queue decision.
- Find other choices that depend on the old assumption.
- Connect the restart-behavior question to its answer.
- Retrieve the relevant records for the next session.

I could handle this with headings, links, frontmatter, and scripts. Docket packages a particular set of conventions with validation, derived views, and retrieval. Once I record a replacement explicitly, a command can follow that link without asking a model to infer whether “we should switch queues” was a proposal or an adopted change.

**What I get is a maintained set of rules and tools.** There is no special information that JSON can express and Markdown cannot. A Markdown system with equivalent metadata, checks, and retrieval could provide the same benefits. It might also fit a team better.

I can keep long explanations in design documents and link to them from Docket. If the notes themselves remain easy to keep current and find, there may be little reason to add another format and workflow.

## Why not rely on Git?

Git already gives me committed versions, authorship, and a way to inspect when a line changed. Good commit messages and review discussions can explain why the code took its current shape. Those are useful places to look when I am investigating a decision.

**A commit and a decision are different units.** One commit can implement several choices; one choice can span many commits. An unresolved question or a rejected alternative may produce no code change at all. A choice can also be recorded before anyone commits its implementation.

Git can show me when the queue implementation changed. To find which recorded assumption became invalid, whether we explicitly replaced the old choice, and which other choices depended on it, I need conventions for recording those relationships. Git does not assign that meaning to file edits or commit messages.

Docket supplies those conventions. I can commit and share the project ledger through Git alongside the code:

| Question | Where the answer comes from |
|---|---|
| What changed between committed versions? | Git's history and diffs |
| Why was the change made? | Recorded rationale in commits, reviews, documents, or Docket |
| Which recorded choice is current? | Docket's explicit supersession links and derived view |
| Has a recorded question been answered? | Docket's answer links and resolution rules |
| Is a recorded prerequisite unavailable? | Docket's prerequisite links and recorded states |

This adds no guarantee that the rationale is complete or correct. It also does not eliminate merge problems. Branches can allocate conflicting record IDs, and conflicting choices still require a person to resolve them. See [Sharing and maintenance](maintenance.md).

## Why these record types and relationships?

These fields let me record distinctions that would otherwise need to be recovered from the prose:

| Structure | What it makes explicit |
|---|---|
| Claims | What the work assumes or asserts, with a recorded assessment |
| Decisions | What was chosen and why |
| Questions | What remains unresolved |
| Support links | Which recorded claims or decisions were given as reasons |
| Prerequisites | Which recorded conditions must remain available for a decision to apply |
| Answers | Which claim or decision answers a question |
| Supersession | Which record replaces an earlier record |

### An assumption and a commitment need different treatment

When I record “pending jobs do not need to survive a restart,” I am stating an assumption about requirements. When I record “use an in-process queue,” I am making a commitment under those requirements. Giving them different types preserves that distinction for whoever picks up the work.

### A reason is not always a prerequisite

- **Support:** familiarity with a library can be a reason to choose it without being a condition that must remain true forever.
- **Prerequisite:** a required runtime version may be a condition the decision depends on.

Making the relationship explicit lets Docket report unavailable prerequisites without treating every supporting reason as a hard requirement.

### Alternative arguments need separate support sets

Alternative support sets represent cases where either of two complete arguments supports a record. A flat list would lose the distinction between “both reasons are needed” and “either argument is sufficient.” These links record the author's reasoning; Docket does not prove that the reasoning is sound or automatically retract a decision when its support changes.

### Links need stable targets

Record IDs let me link to something without relying on its wording or a document heading. I can correct the wording and keep the same target. The identifiers do not make the record more trustworthy; they make it addressable.

## Why append-only history if Git already has history?

I can change a decision several times between commits. Adding a replacement record preserves those changes inside the ledger before Git records a snapshot. An explicit replacement also distinguishes a changed commitment from an edit to its wording.

Docket derives the current view from that history:

- **Correct wording or metadata:** append a correction and retain the record's identity.
- **Change a choice or its relationships:** add a replacement record.
- **Read the current view:** superseded records are retired, with their history still available.

That lets me retrieve the current decision and still follow why an older one existed. Git continues to provide repository history and sharing. Append-only recording is an application rule; it does not make the file tamper-proof or authenticate the author.

The costs are a growing history, more explicit updates, and tools for dealing with conflicting records. Editing a short Markdown document in place is simpler when that history has little value.

## Why a local JSONL file?

With JSONL, each record occupies a parseable line. That gives me a few practical benefits:

- **Simple parsing:** Docket validates fields and links, appends records, and reads the file with Python's standard library.
- **Local storage:** the ledger can live with the project, be inspected without a service, and travel through Git.
- **No model required:** recording and retrieval need no model API.

The costs are also concrete:

- Raw JSONL is less comfortable to edit than prose; the CLI handles routine recording.
- Reads validate the complete ledger. The format provides no database indexes.
- Concurrent writers need locking, and branches need reconciliation.

A database or structured Markdown could support the same decision model. JSONL is a storage tradeoff, not a requirement of the idea.

## Why select context instead of loading all the notes?

Writing something down does not ensure that the next session reads it. I can load all the notes, but as the history grows that gives the reader more to search and mixes current work with unrelated or retired choices. For a small, maintained set of notes, loading everything may still be easiest.

For a larger ledger, Docket selects a briefing using:

- **Task text** to find matching records.
- **File scope** to connect choices to the code being worked on.
- **Relationships** to include related grounds, prerequisites, and answers.

Configured agent integrations supply this briefing when their hooks run.

The character budget limits the initial reading load. Full records remain available for retrieval. Selection can miss relevant context, so the agent must follow up when the briefing is incomplete. The benefit depends on the records and their scopes being maintained; the presence of a ranking algorithm does not establish that its selection is good.

## How much of Docket do you need?

**Start with the choices that later work is likely to depend on.** Record the reason and relevant files. Add claims, questions, and relationships when they help explain or revisit those choices. Recording every conversational step would create more material to maintain and search.

The other tools address additional tasks:

- Feature tracking connects a piece of work to relevant records and its actual changes.
- Document extraction proposes records from existing notes for review.
- Graph views and exports help inspect relationships.

You can use the decision ledger without adopting all of these. The case for preserving decisions does not establish that every project needs every tool.

## What the ledger cannot settle

{% hint style="warning" %}
A well-formed record can still be wrong. Evidence can become stale, relationships can be missing, and a briefing can miss relevant context. Loading a decision does not guarantee that the agent will follow it.
{% endhint %}

Those limits still require judgment, checking, and maintenance.

For me, the practical test comes back to the problems that prompted Docket: am I explaining the same choice again, recovering the conditions behind it, or untangling old and current decisions? Keeping a ledger is only useful if it reduces that work. If recording costs more effort than it saves, the approach needs to be simpler or the records more selective.

To try it on one choice in your project, follow [Your first decision](quickstart.md).
