"""Typed, append-only JSONL ledger primitives.

The module deliberately has no dependency on the command line interface.  It
is also the single validation boundary for records read from disk and records
about to be appended, so callers cannot accidentally treat a damaged ledger
as a partially valid one.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from docket import corrections, reviews, support

SCHEMA = 2
KINDS = ("claim", "decision", "question")
STATES = {
    "claim": ("unassessed", "accepted", "disputed", "rejected"),
    "decision": ("adopted", "revoked"),
    "question": ("open", "resolved"),
}
ID_RE = re.compile(r"([cdq])(0|[1-9][0-9]*)$")
ID_TOKEN = re.compile(r"\b([cdq])(0|[1-9][0-9]*)\b")
COMMON_DEFAULTS: dict[str, Any] = {
    "scope": [],
    "rationale": "",
    "supports": [],
    "depends_on": [],
    "answers": [],
    "supersedes": [],
    "evidence": [],
    "revisit": "",
    "cost_if_wrong": "",
    "pinned": False,
}
COMMON_FIELDS = frozenset(
    {"schema", "kind", "id", "text", "state", "ts", "author", "session", "branch", *COMMON_DEFAULTS}
)
DECISION_FIELDS = frozenset({"choice", "alternatives", "decided_by"})
AUDIT_FIELDS = frozenset({"legacy", "migrated_from"})
ALLOWED_FIELDS = COMMON_FIELDS | DECISION_FIELDS | AUDIT_FIELDS | {"supersede_reason"}
_LINE_FIELDS = {
    **dict.fromkeys(KINDS, ALLOWED_FIELDS),
    corrections.KIND: corrections.LINE_FIELDS,
    reviews.KIND: reviews.LINE_FIELDS,
}


class LedgerError(ValueError):
    """A human-actionable schema, reference, or storage error."""


def _error(where: str, message: str) -> LedgerError:
    return LedgerError(f"docket: {where}: {message}")


def _is_string_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) and item for item in value)


def _normalized(value: str) -> str:
    return " ".join(value.split()).casefold()


def _reject_empty_reasoning(record: dict[str, Any], changed: frozenset[str] | None = None) -> None:
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
        raise _error(
            "record",
            "decision alternatives must name an option the choice beat; leave "
            "--alternative off when the decision had no contender",
        )
    text = _normalized(record.get("text", ""))
    if touched("text") and choice and text == choice:
        raise _error(
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
        raise _error(
            "record",
            "decision rationale must say why the choice won; leave --rationale off "
            "when the choice line already carries the reason",
        )


def _reject_question_text(record: dict[str, Any]) -> None:
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
        raise _error(
            "record",
            f"a {record['kind']} must state the commitment, not ask it; record the "
            "question with 'docket question' and link it with --answers",
        )


def reasoning_hints(record: dict[str, Any]) -> list[str]:
    """Fields left empty that usually carry something, worst first.

    These are hints, never refusals. Each field is legitimately empty for some
    records, so a reader of the hint decides. Scope leads: a record with no
    scope competes for room in every briefing, which is how twenty installer
    decisions came to brief a session editing documentation.
    """
    hints = []
    if not record.get("scope"):
        hints.append("no --scope: this record competes for room in every briefing")
    if record.get("kind") == "decision" and not record.get("alternatives"):
        hints.append("no --alternative: name what the choice beat, if anything did")
    if not record.get("rationale"):
        hints.append("no --rationale: say why, when the text does not")
    if not record.get("cost_if_wrong"):
        hints.append("no --cost: say what breaks if this turns out wrong")
    return hints


def make_record(
    kind: str,
    text: str,
    *,
    state: str | None = None,
    choice: str | None = None,
    alternatives: list[str] | None = None,
    scope: list[str] | None = None,
    rationale: str = "",
    supports: list[list[str]] | None = None,
    depends_on: list[str] | None = None,
    answers: list[str] | None = None,
    supersedes: list[str] | None = None,
    supersede_reason: str | None = None,
    evidence: list[dict[str, str]] | None = None,
    revisit: str = "",
    cost_if_wrong: str = "",
    pinned: bool = False,
    author: str = "unknown",
    session: str = "",
    branch: str = "",
    decided_by: str | None = None,
    ts: str | None = None,
    record_id: str | None = None,
) -> dict[str, Any]:
    """Build an unnumbered or explicitly numbered schema 2 record."""
    if kind not in KINDS:
        raise _error("record", f"unknown kind {kind!r}; expected claim, decision, or question")
    if not isinstance(text, str) or not text.strip():
        raise _error("record", "text must be a non-empty string")
    if state is None:
        state = {"claim": "unassessed", "decision": "adopted", "question": "open"}[kind]
    record: dict[str, Any] = {
        "schema": SCHEMA,
        "kind": kind,
        "id": record_id if record_id is not None else "",
        "text": text,
        "state": state,
        "ts": ts if ts is not None else datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "author": author,
        "session": session,
        "branch": branch,
        "scope": scope if scope is not None else [],
        "rationale": rationale,
        "supports": supports if supports is not None else [],
        "depends_on": depends_on if depends_on is not None else [],
        "answers": answers if answers is not None else [],
        "supersedes": supersedes if supersedes is not None else [],
        "evidence": evidence if evidence is not None else [],
        "revisit": revisit,
        "cost_if_wrong": cost_if_wrong,
        "pinned": pinned,
    }
    if supersede_reason is not None:
        record["supersede_reason"] = supersede_reason
    _reject_question_text(record)
    if kind == "decision":
        if alternatives is not None and not isinstance(alternatives, list):
            raise _error("record", "alternatives must be a list")
        if choice is not None and not isinstance(choice, str):
            raise _error("record", "choice must be a string")
        record["choice"] = choice if choice is not None else ""
        record["alternatives"] = (
            alternatives.copy()
            if isinstance(alternatives, list)
            else (alternatives if alternatives is not None else [])
        )
        record["decided_by"] = decided_by if decided_by is not None else ""
        _reject_empty_reasoning(record)
    elif choice is not None or alternatives is not None or decided_by is not None:
        raise _error("record", "choice, alternatives, and decided_by are decision-only fields")
    # Validate the complete shape before append allocates the global ID.  The
    # temporary ID is never serialized and is replaced while holding the lock.
    if not record["id"]:
        record["id"] = {"claim": "c", "decision": "d", "question": "q"}[kind] + "1"
        validate_record(record)
        record["id"] = ""
    else:
        validate_record(record)
    return record


class _Prefix:
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
        if entry.get("kind") == reviews.KIND:
            target, number = reviews.parts_of(entry["id"])
            self.reviews[target] = max(self.reviews.get(target, 0), number)
            return
        # A correction is no relation target and carries no supersedes.
        if entry.get("kind") == corrections.KIND:
            target, number = corrections.parts_of(entry["id"])
            self.corrections[target] = max(self.corrections.get(target, 0), number)
            return
        ident = entry["id"]
        self.by_id[ident] = entry
        self.max_number[ident[0]] = max(self.max_number.get(ident[0], 0), int(ident[1:]))
        for target in entry["supersedes"]:
            self.retired[target] = ident


def validate_record(
    record: Any,
    *,
    previous: list[dict[str, Any]] | None = None,
    prefix: _Prefix | None = None,
    copy_result: bool = True,
) -> dict[str, Any]:
    """Validate and return a record without mutating the caller's object.

    ``previous`` enables the ordering and cross-record relation checks used by
    both reads and appends. ``prefix`` supplies the same information already
    indexed, for a caller that validates many records in sequence.
    ``copy_result=False`` returns the object itself, for read(), whose input
    json.loads just built and nobody else holds; the copy was half its cost.
    """
    if not isinstance(record, dict):
        raise _error("record", "each JSONL line must be an object")
    if any(not isinstance(key, str) for key in record):
        raise _error("record", "field names must be strings")
    if record.get("kind") == corrections.KIND:
        if prefix is not None and previous is not None:
            raise _error("record", "pass previous or prefix, not both")
        if prefix is None and previous is not None:
            prefix = _Prefix(previous)
        return corrections.validate(record, prefix)
    if record.get("kind") == reviews.KIND:
        if prefix is not None and previous is not None:
            raise _error("record", "pass previous or prefix, not both")
        if prefix is None and previous is not None:
            prefix = _Prefix(previous)
        return reviews.validate(record, prefix)
    if record.get("schema") in (None, 1):
        raise _error(
            "schema", "legacy format is unsupported; run 'docket migrate' to convert it to schema 2"
        )
    unknown_fields = sorted(set(record) - ALLOWED_FIELDS)
    if unknown_fields:
        raise _error("record", f"unknown field(s): {', '.join(unknown_fields)}")
    if type(record.get("schema")) is not int or record.get("schema") != SCHEMA:
        raise _error("schema", f"expected schema 2, got {record.get('schema')!r}")
    kind = record.get("kind")
    if kind not in KINDS:
        raise _error("record", f"kind must be one of {', '.join(KINDS)}")
    record_id = record.get("id")
    if not isinstance(record_id, str) or not ID_RE.fullmatch(record_id):
        raise _error("record", "id must match cN, dN, or qN with a positive sequence number")
    id_prefix, number = record_id[0], int(record_id[1:])
    expected_prefix = {"claim": "c", "decision": "d", "question": "q"}[kind]
    if id_prefix != expected_prefix or number < 1:
        raise _error("record", f"{kind} id {record_id!r} has the wrong prefix or sequence")
    if not isinstance(record.get("text"), str) or not record["text"].strip():
        raise _error(record_id, "text must be a non-empty string")
    state = record.get("state")
    if state not in STATES[kind]:
        raise _error(record_id, f"invalid {kind} state {state!r}")
    for field in ("ts", "author", "session", "branch", "rationale", "revisit", "cost_if_wrong"):
        if not isinstance(record.get(field), str):
            raise _error(record_id, f"{field} must be a string")
    if not isinstance(record.get("pinned"), bool):
        raise _error(record_id, "pinned must be boolean")
    if not _is_string_list(record.get("scope")):
        raise _error(record_id, "scope must be a list of non-empty strings")
    for field in ("depends_on", "answers", "supersedes"):
        if not _is_string_list(record.get(field)):
            raise _error(record_id, f"{field} must be a list of non-empty ID strings")
    supports = record.get("supports")
    if not isinstance(supports, list) or any(
        not _is_string_list(group) or not group for group in supports
    ):
        raise _error(record_id, "supports must be a list of conjunctive ID lists")
    evidence = record.get("evidence")
    if not isinstance(evidence, list):
        raise _error(record_id, "evidence must be a list of objects")
    for item in evidence:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("ref"), str)
            or not item["ref"].strip()
        ):
            raise _error(record_id, "each evidence object needs a non-empty ref")
        for field in ("checked_at", "commit"):
            if field in item and not isinstance(item[field], str):
                raise _error(record_id, f"evidence {field} must be a string")
        if any(key not in {"ref", "checked_at", "commit"} for key in item):
            raise _error(record_id, "evidence only permits ref, checked_at, and commit")
    if kind == "decision":
        if not isinstance(record.get("choice"), str) or not record["choice"].strip():
            raise _error(record_id, "decision choice must be a non-empty string")
        if not _is_string_list(record.get("alternatives")):
            raise _error(record_id, "decision alternatives must be a list of non-empty strings")
        if not isinstance(record.get("decided_by", ""), str):
            raise _error(record_id, "decision decided_by must be a string")
    elif "choice" in record or "alternatives" in record:
        raise _error(record_id, "choice and alternatives are decision-only fields")
    elif "decided_by" in record:
        raise _error(record_id, "decided_by is a decision-only field")
    # legacy is the schema 1 migration's audit trail. Nothing reads it, so its
    # shape is checked once, by the migration that writes it, and a rebase
    # carries it through untouched: its mapped_* lists keep the ids the
    # migration assigned.
    if "legacy" in record and not isinstance(record["legacy"], dict):
        raise _error(record_id, "legacy must be an object")
    if "migrated_from" in record:
        origin = record["migrated_from"]
        if not isinstance(origin, str) or not ID_RE.fullmatch(origin):
            raise _error(record_id, "migrated_from must be a record id such as 'd12'")
    if kind == "question" and state != "open":
        raise _error(
            record_id, "questions have recorded state open; resolution is derived from answers"
        )
    if kind == "question" and record["answers"]:
        raise _error(record_id, "questions cannot answer other questions")
    if kind != "decision" and record["depends_on"]:
        raise _error(record_id, "only decisions may have depends_on")
    if "supersede_reason" in record:
        if record["supersede_reason"] not in support.REASONS:
            raise _error(record_id, f"supersede_reason must be one of {', '.join(support.REASONS)}")
        if not record["supersedes"]:
            raise _error(record_id, "supersede_reason needs supersedes")

    if prefix is not None and previous is not None:
        raise _error(record_id, "pass previous or prefix, not both")
    if prefix is None and previous is not None:
        prefix = _Prefix(previous)
    if prefix is not None:
        known = prefix.by_id
        if record_id in known:
            raise _error(record_id, "duplicate ID")
        if number <= prefix.max_number.get(id_prefix, 0):
            raise _error(record_id, "per-kind sequence must increase; gaps are allowed")
        for field in ("supports", "depends_on", "answers", "supersedes"):
            ids = (
                [ref for group in supports for ref in group]
                if field == "supports"
                else record[field]
            )
            for ref in ids:
                if ref == record_id:
                    raise _error(record_id, f"{field} cannot refer to itself")
                target = known.get(ref)
                if target is None:
                    raise _error(record_id, f"{field} refers to unknown or later ID {ref!r}")
                if field == "supports" and target["kind"] not in ("claim", "decision"):
                    raise _error(record_id, f"supports target {ref!r} is not a claim or decision")
                if field == "depends_on" and target["kind"] not in ("claim", "decision"):
                    raise _error(record_id, f"depends_on target {ref!r} is not a claim or decision")
                if field == "answers" and target["kind"] != "question":
                    raise _error(record_id, f"answers target {ref!r} is not a question")
                if field == "supersedes" and target["kind"] != kind:
                    raise _error(record_id, f"supersedes target {ref!r} is a different kind")
                if field == "supersedes" and ref in prefix.retired:
                    raise _error(record_id, f"supersedes target {ref!r} is already retired")
    return copy.deepcopy(record) if copy_result else record


def validate_entries(entries: Any) -> list[dict[str, Any]]:
    if not isinstance(entries, list):
        raise _error("ledger", "entries must be a list")
    validated: list[dict[str, Any]] = []
    prefix = _Prefix([])
    for index, entry in enumerate(entries, 1):
        try:
            record = validate_record(entry, prefix=prefix)
        except LedgerError as exc:
            raise _error(f"line {index}", str(exc).removeprefix("docket: ")) from exc
        validated.append(record)
        prefix.add(record)
    return validated


def _torn_tail(text: str) -> int | None:
    """Where an interrupted append's partial last line starts, or None.

    Every append ends its line with a newline, so an unparseable last line
    without one is a write that died midway. A bad line followed by a newline
    is corruption from somewhere else and stays an error.
    """
    if not text or text.endswith("\n"):
        return None
    start = text.rfind("\n") + 1
    try:
        json.loads(text[start:])
    except json.JSONDecodeError:
        return start
    return None


def _newer_than_us(value: Any) -> tuple[str, frozenset[str]] | None:
    """What a newer docket added to this line: its unknown kind or fields.

    Returns None for a line this version fully understands, or one too broken
    to tell, which validation then reports.
    """
    if not isinstance(value, dict) or value.get("schema") in (None, 1):
        return None
    kind = value.get("kind")
    if not isinstance(kind, str):
        return None
    allowed = _LINE_FIELDS.get(kind)
    if allowed is None:
        return f"unknown kind {kind!r}", frozenset()
    extra = frozenset(k for k in value if isinstance(k, str)) - allowed
    if extra:
        return f"unknown field(s): {', '.join(sorted(extra))}", extra
    return None


def read(path: Path | str, lock: bool = True, strict: bool = False) -> list[dict[str, Any]]:
    """Read and validate a ledger, raising on corruption.

    ``lock`` takes a shared lock for the duration of the file read, so a reader
    never sees a partially written line. Callers already holding the exclusive
    lock pass False.

    A line from a newer docket, with a kind or field this version does not
    know, is skipped or stripped with a warning so an older client can still
    brief and list. ``strict`` refuses it instead: every caller that writes
    records derived from this read passes it, because writing back a stripped
    copy would destroy what the newer version recorded.
    """
    path = Path(path)
    if not path.exists():
        return []
    try:
        if lock:
            with _ledger_lock(path, exclusive=False):
                text = path.read_text(encoding="utf-8")
        else:
            text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise _error("read", f"cannot read {path}: {exc}") from exc
    torn = _torn_tail(text)
    if torn is not None:
        print(
            f"docket: {path}: skipped a torn final line; the next append removes it",
            file=sys.stderr,
        )
        text = text[:torn]
    lines = text.splitlines()
    entries: list[dict[str, Any]] = []
    prefix = _Prefix([])
    newer = 0
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise _error(f"line {line_number}", f"invalid JSON: {exc.msg}") from exc
        unknown = _newer_than_us(value)
        if unknown is not None:
            reason, extra = unknown
            if strict:
                raise _error(
                    f"line {line_number}",
                    f"{reason}; a newer docket wrote this line, so run 'docket update' "
                    "before writing to this ledger",
                )
            newer += 1
            if not extra:
                continue
            value = {k: v for k, v in value.items() if k not in extra}
        try:
            record = validate_record(value, prefix=prefix, copy_result=False)
        except LedgerError as exc:
            raise _error(f"line {line_number}", str(exc).removeprefix("docket: ")) from exc
        entries.append(record)
        prefix.add(record)
    if newer:
        print(
            f"docket: {path}: {newer} line(s) come from a newer docket and were read "
            "partially; run 'docket update' before writing",
            file=sys.stderr,
        )
    return entries


def next_id(entries: list[dict[str, Any]], kind: str) -> str:
    """The next number for ``kind``; each kind counts on its own from 1."""
    letter = {"claim": "c", "decision": "d", "question": "q"}[kind]
    numbers = []
    for entry in entries:
        match = ID_RE.fullmatch(str(entry.get("id", "")))
        if match and match.group(1) == letter:
            numbers.append(int(match.group(2)))
    return str(max(numbers, default=0) + 1)


def allocate_id(entries: list[dict[str, Any]], kind: str) -> str:
    if kind not in KINDS:
        raise _error("record", f"unknown kind {kind!r}")
    return {"claim": "c", "decision": "d", "question": "q"}[kind] + next_id(entries, kind)


def retired_by(entries: list[dict[str, Any]]) -> dict[str, str]:
    result: dict[str, str] = {}
    for entry in entries:
        for target in entry["supersedes"]:
            result[target] = entry["id"]
    return result


def resolved_by(entries: list[dict[str, Any]]) -> dict[str, list[str]]:
    active = {entry["id"]: entry for entry in entries}
    retired = retired_by(entries)
    applicability, _ = _decision_applicability(entries, retired)
    result: dict[str, list[str]] = {entry["id"]: [] for entry in entries}
    for entry in entries:
        if entry["kind"] not in ("claim", "decision"):
            continue
        if retired.get(entry["id"]):
            continue
        acceptable = (entry["kind"] == "claim" and entry["state"] == "accepted") or (
            entry["kind"] == "decision"
            and entry["state"] == "adopted"
            and applicability.get(entry["id"], False)
        )
        if not acceptable:
            continue
        for question_id in entry["answers"]:
            if question_id in active:
                result[question_id].append(entry["id"])
    return result


def _decision_applicability(
    entries: list[dict[str, Any]],
    retired: dict[str, str] | None = None,
) -> tuple[dict[str, bool], dict[str, list[str]]]:
    """Evaluate decision prerequisites without changing recorded state."""
    retired = retired if retired is not None else retired_by(entries)
    by_id = {entry["id"]: entry for entry in entries}
    applicable: dict[str, bool] = {}
    blocked: dict[str, list[str]] = {}
    reason_of = {
        entry["id"]: entry.get("supersede_reason", support.DEFAULT_REASON) for entry in entries
    }

    # Validation refuses a reference to a later id, so a validated ledger is
    # acyclic. project(validated=True) skips that check, and a cycle there would
    # otherwise recurse until the stack ends. One shared set costs nothing.
    visiting: set[str] = set()
    hops = 0

    class _ForwardCycle(Exception):
        pass

    def check(entry_id: str) -> tuple[bool, list[str]]:
        if entry_id in visiting:
            # A cycle in the recorded depends_on graph is a corrupt ledger. One
            # that closes only through a supersession hop is valid, because every
            # record cites earlier ids; there the prerequisite rests on itself and
            # holds nothing, so the decision is blocked (least fixed point). A
            # `supports` cycle is flagged circular instead.
            if hops:
                raise _ForwardCycle
            raise _error(entry_id, "depends_on forms a cycle")
        visiting.add(entry_id)
        try:
            return _check(entry_id)
        finally:
            visiting.discard(entry_id)

    def _check(entry_id: str) -> tuple[bool, list[str]]:
        if entry_id in applicable:
            return applicable[entry_id], blocked[entry_id]
        entry = by_id[entry_id]
        if entry["kind"] == "claim":
            ok = entry["state"] == "accepted" and entry_id not in retired
            return ok, [] if ok else [entry_id]
        if entry["kind"] != "decision":
            return False, [entry_id]
        if entry["state"] != "adopted" or entry_id in retired:
            applicable[entry_id] = False
            blocked[entry_id] = [entry_id]
            return False, [entry_id]
        blockers: list[str] = []
        seen: set[str] = set()
        for dependency in entry["depends_on"]:
            head, crossed = support.head_of(dependency, retired, reason_of)
            if "reverse" in crossed:
                ok, reasons = False, [head]
            elif head == dependency:
                ok, reasons = check(head)
            else:
                nonlocal hops
                hops += 1
                try:
                    ok, reasons = check(head)
                except _ForwardCycle:
                    ok, reasons = False, [head]
                finally:
                    hops -= 1
            if not ok:
                for reason in [dependency, *reasons]:
                    if reason not in seen:
                        seen.add(reason)
                        blockers.append(reason)
        applicable[entry_id] = not blockers
        blocked[entry_id] = blockers
        return not blockers, blockers

    for entry in entries:
        if entry["kind"] == "decision":
            check(entry["id"])
    return applicable, blocked


def project(entries: list[dict[str, Any]], *, validated: bool = False) -> list[dict[str, Any]]:
    """Add derived retirement/resolution fields while preserving history.

    Pass ``validated`` for a list that came straight from ``read``, which has
    already crossed the validation boundary. Re-validating it doubled the cost
    of every CLI command.
    """
    if not validated:
        entries = validate_entries(entries)
    entries = corrections.fold(entries)
    entries = reviews.fold(entries)
    retired = retired_by(entries)
    answers = resolved_by(entries)
    applicability, blocked = _decision_applicability(entries, retired)
    statuses = support.evaluate(entries, retired, applicability)
    result = []
    for entry in entries:
        # Shallow by design. Only top-level keys are added below, and the two
        # list fields are rebuilt with list(). On the validated=True path the
        # nested values stay shared with the caller's records, so a caller that
        # mutates them after projecting sees the change in both.
        projected = dict(entry)
        projected["recorded_state"] = entry["state"]
        if entry["kind"] == "question" and answers[entry["id"]]:
            projected["state"] = "resolved"
        projected["retired_by"] = retired.get(entry["id"], "")
        projected["resolved_by"] = list(answers[entry["id"]])
        if entry["kind"] == "decision":
            projected["applicable"] = applicability.get(entry["id"], False)
            projected["blocked_by"] = list(blocked.get(entry["id"], []))
        if entry["id"] in statuses:
            projected.update(statuses[entry["id"]])
        result.append(projected)
    return result


def record_key(entry: dict[str, Any]) -> str:
    """A record's identity that survives renumbering.

    A merge or rebase gives the other branch's records fresh ids, so an id
    cited outside the ledger can come to name a different record. Text is the
    as-written text, from ``original`` once a correction has rewritten it in
    the projection; ts alone collides whenever two branches record within one
    second, which every scripted run does.
    """
    text = (entry.get("original") or {}).get("text", entry.get("text", ""))
    fields = (entry.get("kind"), entry.get("ts"), entry.get("author"), entry.get("session"), text)
    raw = "\0".join(str(value or "") for value in fields)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def rebind(ids: list[str], keys: dict[str, str], entries: list[dict[str, Any]]) -> list[str]:
    """``ids`` with each one whose key now belongs to another record repointed.

    An id with no stored key, or whose record still carries the key, stays.
    So does one whose key matches no record or more than one: two records
    written in the same second by one session share a key, and guessing
    between them would be worse than reporting the id as it was written.
    """
    if not keys:
        return list(ids)
    by_id = {str(entry.get("id")): entry for entry in entries}
    holders: dict[str, list[str]] = {}
    for entry in entries:
        holders.setdefault(record_key(entry), []).append(str(entry.get("id")))
    out = []
    for ident in ids:
        key = keys.get(ident)
        current = by_id.get(ident)
        if key is None or (current is not None and record_key(current) == key):
            out.append(ident)
            continue
        found = holders.get(key, [])
        out.append(found[0] if len(found) == 1 else ident)
    return out


def graph_payload(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Return the graph viewer's version 2 wire representation."""
    # CLI filters may pass a projected subset whose relation targets are not
    # present in that subset.  It has already crossed the validation boundary.
    projected = (
        copy.deepcopy(entries)
        if all(
            isinstance(entry, dict) and "recorded_state" in entry and "retired_by" in entry
            for entry in entries
        )
        else project(entries)
    )
    result = []
    for entry in projected:
        sets = copy.deepcopy(entry["supports"])
        union: list[str] = []
        for group in sets:
            for ref in group:
                if ref not in union:
                    union.append(ref)
        node = copy.deepcopy(entry)
        node.update(
            {
                "question": entry["text"],
                "answer": entry.get("choice", entry.get("rationale", "")),
                "cost": entry["cost_if_wrong"],
                "sets": sets,
                "supports": union,
            }
        )
        result.append(node)
    return {"version": 2, "entries": result}


@contextmanager
def _ledger_lock(path: Path, exclusive: bool = True) -> Iterator[None]:
    lock_path = Path(str(path) + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+") as lock:
        if os.name == "nt":
            # msvcrt has no shared mode, so a reader takes the exclusive lock.
            # LK_LOCK retries ten times over one second and then raises, so a
            # Windows reader that races a long append fails where a POSIX one
            # waits. The alternative is a torn read.
            import msvcrt

            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(lock.fileno(), fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
            try:
                yield
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


# The migration replaces the whole file and needs the lock an append takes.
ledger_lock = _ledger_lock


def append(path: Path | str, record: dict[str, Any], *, dry_run: bool = False) -> dict[str, Any]:
    """Validate and append one record under a process lock.

    The caller may supply an empty id; the record id, or a correction's
    `<target>.<n>`, is then allocated while holding the lock, preventing
    duplicate IDs between writers. A correction's write-time refusals, and its
    no-op field drop, run on the projection read under the same lock, but only
    for a correction that arrived with no id: that is the CLI path. A
    pre-numbered correction, arriving through rebase, skips them, the same way
    a pre-numbered record does.
    """
    return append_many(path, [record], dry_run=dry_run)[0]


_BATCH_REF = re.compile(r"@([1-9][0-9]*)$")


def _batch_refs(record: dict[str, Any], written: list[dict[str, Any]]) -> dict[str, Any]:
    """``record`` with each ``@N`` reference replaced by the id batch record N took."""

    def get(value: str) -> str:
        match = _BATCH_REF.fullmatch(value)
        if not match:
            return value
        index = int(match.group(1))
        if index > len(written):
            raise _error("batch", f"{value} names a record that is not earlier in this batch")
        return str(written[index - 1]["id"])

    for field in ("depends_on", "answers", "supersedes"):
        if isinstance(record.get(field), list):
            record[field] = [get(v) if isinstance(v, str) else v for v in record[field]]
    if isinstance(record.get("supports"), list):
        record["supports"] = [
            [get(v) if isinstance(v, str) else v for v in group]
            if isinstance(group, list)
            else group
            for group in record["supports"]
        ]
    for field in ("corrects", "reviews"):
        if isinstance(record.get(field), str):
            record[field] = get(record[field])
    return record


def append_many(
    path: Path | str, records: list[dict[str, Any]], *, dry_run: bool = False
) -> list[dict[str, Any]]:
    """Validate every record, then append them all, under one lock.

    Nothing is written unless every record validates, so a batch is all or
    nothing. A reference written ``@N`` names the Nth record of the batch,
    counted from 1, which lets a batch cite a record it is creating.
    ``dry_run`` returns the numbered records and writes nothing.
    """
    path = Path(path)
    with _ledger_lock(path):
        # flock is per file description, not per thread, so a locking read here
        # would block against the lock this call already holds.
        entries = read(path, lock=False, strict=True)
        written: list[dict[str, Any]] = []
        for record in records:
            candidate = _batch_refs(copy.deepcopy(record), written)
            if candidate.get("kind") == corrections.KIND:
                from_cli = not candidate.get("id")
                if from_cli:
                    candidate["id"] = corrections.allocate(
                        entries, str(candidate.get("corrects", ""))
                    )
                validate_record(candidate, previous=entries)
                if from_cli:
                    corrections.refuse(entries, candidate)
            elif candidate.get("kind") == reviews.KIND:
                if not candidate.get("id"):
                    candidate["id"] = reviews.allocate(entries, str(candidate.get("reviews", "")))
                    # Grounds are what the record owes under this lock, not what
                    # the caller saw before it.
                    reviews.refuse(entries, candidate)
                validate_record(candidate, previous=entries)
            else:
                if not candidate.get("id"):
                    kind = candidate.get("kind") or ""
                    candidate["id"] = allocate_id(entries, kind)
                validate_record(candidate, previous=entries)
            entries.append(candidate)
            written.append(candidate)
        if dry_run:
            return written
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            if path.exists():
                with path.open("rb+") as raw:
                    data = raw.read()
                    torn = _torn_tail(data.decode("utf-8", errors="replace"))
                    if torn is not None:
                        raw.truncate(data.rfind(b"\n") + 1)
            with path.open("a+", encoding="utf-8") as stream:
                if stream.tell() > 0:
                    stream.seek(0, os.SEEK_END)
                    stream.seek(stream.tell() - 1)
                    if stream.read(1) != "\n":
                        stream.seek(0, os.SEEK_END)
                        stream.write("\n")
                    else:
                        stream.seek(0, os.SEEK_END)
                stream.write(
                    "".join(
                        json.dumps(c, ensure_ascii=False, separators=(",", ":")) + "\n"
                        for c in written
                    )
                )
                stream.flush()
                os.fsync(stream.fileno())
        except OSError as exc:
            raise _error("append", f"cannot write {path}: {exc}") from exc
    return written


def parse_evidence(value: str) -> dict[str, str]:
    """Parse a plain reference or a strict JSON evidence object."""
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        return {"ref": value}
    if not isinstance(decoded, dict):
        raise _error("evidence", "JSON evidence must be an object")
    return decoded
