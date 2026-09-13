# Docket

Docket is a decision ledger for coding agents. It keeps track of what was
decided, why, and what is still open, then gives an agent that context when a
conversation resumes or gets compacted.

Records live in an append-only JSONL ledger. When a choice changes, the old
reasoning stays available.

## Start here

- [Installation](installation.md) covers install, update, and uninstall.
- [Ledger reference](ledger.md) describes the record types, states, relations,
  and file format.
- [Definitions](definitions.md) holds the formal vocabulary that the other
  documents use.

## Design notes

These documents describe the reasoning behind Docket and its proposed
direction. They are not usage instructions.

- [Decision chains](decision-chains.md) reviews the problem and the design that
  answers it.
- [Outcome formalism](outcome-formalism.md) defines outcomes, chains, and
  claims for a proposed paper.
- [Agent context goals](agent-context-goals.md) lists future goals and open
  questions for the context a Docket agent receives.
- [North star](north-star.md) gives the target system and its build order.
