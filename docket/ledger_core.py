"""Names that ledger, corrections, reviews and rebase all depend on.

This module imports none of them. ledger validates correction and review lines
by calling into those modules, and they need ledger's error type, the schema
version, and the prefix index; keeping those here lets each side import at the
top of the file.
"""

from __future__ import annotations

import re
from typing import Any

SCHEMA = 3
KIND_LETTER = {"claim": "c", "decision": "d", "question": "q"}
CORRECTION_KIND = "correction"
REVIEW_KIND = "review"
CORRECTION_RE = re.compile(r"([cdq](?:0|[1-9][0-9]*))\.([1-9][0-9]*)")
REVIEW_RE = re.compile(r"([cdq](?:0|[1-9][0-9]*))\.r([1-9][0-9]*)")


class LedgerError(ValueError):
    """A human-actionable schema, reference, or storage error."""


class SchemaTooOld(LedgerError):
    """A line written under an older schema. ``docket migrate`` converts the file.

    ``version`` is the schema the line carries, 1 when it carries none. read()
    and validate_entries() let it through unwrapped so a caller can tell it from
    corruption and offer the migration.
    """

    def __init__(self, version: int) -> None:
        self.version = version
        super().__init__(
            f"docket: schema: this ledger is schema {version}; run 'docket migrate' "
            f"to convert it to schema {SCHEMA}"
        )


def error(where: str, message: str) -> LedgerError:
    return LedgerError(f"docket: {where}: {message}")


def require_current(record: dict[str, Any]) -> None:
    schema = record.get("schema")
    if schema is None:
        raise SchemaTooOld(1)
    if type(schema) is not int or schema > SCHEMA:
        raise error("schema", f"expected schema {SCHEMA}, got {schema!r}")
    if schema < SCHEMA:
        raise SchemaTooOld(max(schema, 1))


def _normalized(value: str) -> str:
    return " ".join(value.split()).casefold()


def reject_empty_reasoning(record: dict[str, Any], changed: frozenset[str] | None = None) -> None:
    """Refuse a decision whose text or reasoning fields only echo the choice.

    Requiring the choice to appear in ``alternatives`` made a one-element list
    the shortest valid answer, and 38 of the first 56 decisions took it. The
    fields then read as filled while carrying nothing. An empty list is a
    legitimate answer here, so neither field is mandatory; only the echo is
    refused, which leaves no reason to invent an alternative that never existed.

    This runs when a record is written, never when one is read. A ledger
    recorded under the old rule stays readable. ``changed`` names the fields a
    correction replaces, and each check then runs only when its own field
    changed: 27 migrated decisions carry a rationale equal to their choice,
    and a scope correction must not fail on it.
    """

    def touched(*names: str) -> bool:
        return changed is None or any(name in changed for name in names)

    choice = _normalized(record.get("choice", ""))
    alternatives = [_normalized(item) for item in record.get("alternatives", [])]
    if (
        touched("alternatives")
        and choice
        and alternatives
        and all(item == choice for item in alternatives)
    ):
        raise error(
            "record",
            "decision alternatives must name an option the choice beat; leave "
            "--alternative off when the decision had no contender",
        )
    text = _normalized(record.get("text", ""))
    if touched("text") and choice and text == choice:
        raise error(
            "record",
            "decision text must carry more than the choice; name what the "
            "decision commits to and leave the option detail in --choice",
        )
    rationale = _normalized(record.get("rationale", ""))
    if touched("rationale"):
        against: tuple[str, ...] = (choice, text)
    elif touched("text"):
        against = (text,)
    else:
        against = ()
    if rationale and rationale in against:
        raise error(
            "record",
            "decision rationale must say why the choice won; leave --rationale off "
            "when the choice line already carries the reason",
        )


def reject_question_text(record: dict[str, Any]) -> None:
    """Refuse a claim or decision whose text asks rather than states.

    81 of the first 82 decisions were recorded as the question they settled,
    with the answer in choice. A reader scanning kinds then sees a commitment
    that reads as an open inquiry, and graph_payload labels the node with the
    question. The question belongs in a question record, linked by --answers.

    This runs when a record is written, never when one is read. A ledger
    recorded under the old rule stays readable.
    """
    if record["kind"] == "question":
        return
    if record["text"].rstrip().endswith("?"):
        raise error(
            "record",
            f"a {record['kind']} must state the commitment, not ask it; record the "
            "question with 'docket question' and link it with --answers",
        )


class Prefix:
    """The id map, sequence maximum, retirement map, and correction counters
    of the records so far.

    Validating a whole ledger walks the prefix once per record. Deriving these
    from the prefix list each time made a read cost O(n squared), so a caller
    that validates in order updates one of these instead.
    """

    __slots__ = ("by_id", "max_number", "retired", "corrections", "reviews")

    def __init__(self, entries: list[dict[str, Any]]) -> None:
        self.by_id: dict[str, dict[str, Any]] = {}
        self.max_number: dict[str, int] = {}
        self.retired: dict[str, str] = {}
        self.corrections: dict[str, int] = {}
        self.reviews: dict[str, int] = {}
        for entry in entries:
            self.add(entry)

    def add(self, entry: dict[str, Any]) -> None:
        if entry.get("kind") == REVIEW_KIND:
            self._count(self.reviews, REVIEW_RE, entry["id"])
            return
        # A correction is no relation target and carries no supersedes.
        if entry.get("kind") == CORRECTION_KIND:
            self._count(self.corrections, CORRECTION_RE, entry["id"])
            return
        ident = entry["id"]
        self.by_id[ident] = entry
        self.max_number[ident[0]] = max(self.max_number.get(ident[0], 0), int(ident[1:]))
        for target in entry["supersedes"]:
            self.retired[target] = ident

    @staticmethod
    def _count(counters: dict[str, int], pattern: re.Pattern[str], ident: str) -> None:
        match = pattern.fullmatch(ident)
        if match is None:
            raise ValueError(f"not a correction or review id: {ident!r}")
        target, number = match.group(1), int(match.group(2))
        counters[target] = max(counters.get(target, 0), number)
