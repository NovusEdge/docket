"""The two-pass driver: documents in, staged proposals out.

Pass 1 reads one document per call and can only ever emit a flat list. Pass 2
sees the whole proposal set and proposes the relations between them. Everything
the model returns is checked locally before it is staged.

The provider call is injected, so the whole driver runs under test without a
key and without a network.
"""

from __future__ import annotations

import concurrent.futures
import json
import subprocess
import time
from pathlib import Path

from docket.construct import client, extract, link, schema

# Both schemas travel with "strict": True, which requires every property to
# appear in `required` and every object to refuse extra properties. A field the
# document does not supply comes back as "" or [], never absent.
EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "records": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": list(schema.KINDS)},
                    "text": {"type": "string"},
                    "choice": {"type": "string"},
                    "rationale": {"type": "string"},
                    "anchor": {"type": "string"},
                    "scope": {"type": "array", "items": {"type": "string"}},
                    "confidence": {"type": "string", "enum": list(schema.CONFIDENCE)},
                },
                "required": ["kind", "text", "choice", "rationale", "anchor",
                             "scope", "confidence"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["records"],
    "additionalProperties": False,
}

LINK_SCHEMA = {
    "type": "object",
    "properties": {
        "edges": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": list(link.EDGE_KINDS)},
                    "from": {"type": "string"},
                    "to": {"type": "string"},
                },
                "required": ["kind", "from", "to"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["edges"],
    "additionalProperties": False,
}

_EXTRACT_PROMPT = """\
Read the document below and record the claims, decisions and open questions it
states. Record only what the document says; infer nothing it does not.

A claim is a premise the document asserts. A decision is a commitment it makes,
and needs the choice. A question is something it leaves open.

For every record, `anchor` must be one line copied verbatim from the document,
the line that carries the record. Do not paraphrase the anchor.

`scope` decides whether anyone ever sees the record again, so fill it whenever
you can. It lists the files or directories the record governs, written as paths
or globs with no spaces: `src/auth.py`, `src/**`, `alembic/**`. Never a sentence,
never a description of the coverage.

Take the paths from the document itself: filenames it names, modules it
discusses, directories it points at. A record about an authentication decision
in a project whose code sits under `src/` scopes to `src/auth/**` even when the
document never spells that path out. Leave it empty only when you can name no
part of the tree the record touches.

Where the document lists options it rejected, put them in `rationale`. Do not
record a rejected option as its own decision.

`confidence` says how firmly the document states the record. Use `high` when it
states the record outright and settles it. Use `medium` when it states the
record and leaves something open. Use `low` when the document is dated,
tentative, superseded further down, or a daily log of work already done.

Document: {path}

{body}
"""

_LINK_PROMPT = """\
Below are records extracted from one project's documents, each with the document
it came from and that document's date.

Propose the relations between them.

`supports` means the second record is a ground for the first.

`supersedes` means the first record replaces the second. Both must be the same
kind, and the first must come from a later date.

`contradicts` means the two cannot both hold. Use it when two records disagree
and nothing shown decides which wins; do not pick a winner with `supersedes`.
Records from documents written months apart often disagree this way.

Propose nothing you cannot argue from the records shown. An empty list is a
valid answer.

{rows}
"""


class RunError(RuntimeError):
    """The run cannot proceed at all."""


EXCLUDE = ("archive",)


def _tracked(root: Path) -> set[Path] | None:
    """Every markdown file git tracks under root, or None outside a repository.

    None and the empty set mean different things. A directory with no
    repository has no tracking to filter on, and refusing every document there
    would make construct useless on a plain folder of notes.
    """
    try:
        done = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--", "*.md"],
                              capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
    text = done.stdout.decode("utf-8", errors="surrogateescape")
    return {(root / name).resolve() for name in text.split("\0") if name}


def _walk(root: Path, exclude: tuple[str, ...], untracked: bool) -> list[Path]:
    """The markdown under one directory, past both filters.

    The first real run staged 891 proposals, 326 from documents git does not
    track and 582 from an archive path. Neither filter subsumes the other: 26
    of the 47 archive documents were tracked.
    """
    tracked = None if untracked else _tracked(root)
    found = []
    for path in sorted(root.rglob("*.md")):
        # A whole segment, never a substring: archived-designs/ is not archive/.
        if exclude and set(path.parts) & set(exclude):
            continue
        if tracked is not None and path.resolve() not in tracked:
            continue
        found.append(path)
    return found


def documents(paths: list[str], exclude: tuple[str, ...] = EXCLUDE,
              untracked: bool = False) -> list[Path]:
    """Every markdown file the given paths name, in a stable order.

    A named file is read whatever the filters say. Naming one document is an
    explicit instruction; the filters only shape a walk.
    """
    found: list[Path] = []
    for name in paths:
        path = Path(name)
        if path.is_file():
            found.append(path)
        elif path.is_dir():
            found.extend(_walk(path, exclude, untracked))
    return sorted(dict.fromkeys(found))


def _default_caller():
    """The real provider call. Imported here, never at module scope."""
    from openai import AuthenticationError, OpenAI, PermissionDeniedError

    cfg = client.config()
    api = OpenAI(api_key=cfg["api_key"], base_url=cfg["base_url"])

    def call(prompt: str, want: dict) -> dict:
        body = client.request(prompt, want, model=cfg["model"],
                              provider=cfg["provider"])
        try:
            reply = api.chat.completions.create(**body)
        except (AuthenticationError, PermissionDeniedError) as exc:
            # Raised as ClientError so the driver stops the whole run. Every
            # remaining document carries the same key and gets the same answer.
            raise client.ClientError(
                f"{cfg['provider']} rejected the key: {exc}") from None
        return client.parse(reply.choices[0].message.content or "", want)

    return call


ATTEMPTS = 4

# A rate limit reports itself differently per provider, so match the code and
# the words rather than an exception type the SDK may or may not raise.
_RATE_LIMITED = ("429", "rate limit", "resource_exhausted", "too many requests")


def _rate_limited(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(mark in text for mark in _RATE_LIMITED)


def _with_retry(call, sleep) -> dict:
    """One call, retried while the provider says it is rate limited.

    Extraction issues one call per document across a pool, so a 429 is expected.
    Without this, one rate limit costs a whole document's records.
    """
    for attempt in range(ATTEMPTS):
        try:
            return call()
        except Exception as exc:
            if attempt == ATTEMPTS - 1 or not _rate_limited(exc):
                raise
            sleep(client.backoff(attempt))
    raise AssertionError("unreachable")


def _one_document(path: str, text: str, date: str | None, caller,
                  sleep=time.sleep) -> tuple[list[dict], list[str]]:
    """Pass 1 for one document: the records that survive local checks."""
    prompt = _EXTRACT_PROMPT.format(path=path, body=text)
    reply = _with_retry(lambda: caller(prompt, EXTRACT_SCHEMA), sleep)
    raw = reply.get("records", [])
    kept: list[dict] = []
    notes: list[str] = []

    for record in raw:
        anchor = record.get("anchor", "")
        line = extract.anchor_line(anchor, text)
        if line is None:
            notes.append(f"{path}: dropped a record, its anchor quotes no line "
                         f"in the document: {anchor[:60]!r}")
            continue

        scope = list(record.get("scope") or [])
        bad = schema.invalid_scope(scope)
        if bad:
            notes.append(f"{path}: dropped {len(bad)} scope entr"
                         f"{'y' if len(bad) == 1 else 'ies'} that name no file")
            scope = [item for item in scope if item not in bad]

        try:
            item = schema.proposal(
                kind=record.get("kind", ""),
                text=record.get("text", ""),
                anchor=anchor,
                choice=record.get("choice", "") or "",
                rationale=record.get("rationale", "") or "",
                # An unknown value falls back rather than raising: one odd
                # confidence should cost a sort position, never the record.
                confidence=(record.get("confidence")
                            if record.get("confidence") in schema.CONFIDENCE
                            else "low"),
                scope=scope,
                source={"path": path, "date": date},
                line=line,
            )
        except schema.SchemaError as exc:
            notes.append(f"{path}: dropped a record, {exc}")
            continue
        kept.append(item)

    matched, total = extract.match_rate(raw, text)
    notes.append(f"{path}: {matched}/{total} anchors matched")
    return kept, notes


def _link(proposals: list[dict], caller, batch: int) -> tuple[list[dict], list[str]]:
    """Pass 2: the relations, validated locally before they are applied.

    One call per batch. A single call over the whole set does not scale, and a
    batch that loses a boundary-crossing edge still keeps every document whole.
    """
    groups = link.batches(proposals, size=batch)
    notes = [f"link: {len(groups)} batch{'' if len(groups) == 1 else 'es'}"]
    linked: list[dict] = []
    asked: list[dict] = []
    kept = 0

    for group in groups:
        rows = json.dumps(link.payload(group), indent=2)
        try:
            reply = caller(_LINK_PROMPT.format(rows=rows), LINK_SCHEMA)
        except Exception as exc:
            notes.append(f"link: a batch failed, {exc}; its records carry no relations")
            linked.extend(group)
            continue
        edges, dropped = link.validate(reply.get("edges", []), group)
        notes.extend(f"link: dropped {edge}" for edge in dropped)
        kept += len(edges)
        asked.extend(link.questions(edges, group))
        linked.extend(link.apply(edges, group))

    notes.append(f"link: kept {kept} edge{'' if kept == 1 else 's'}")
    if asked:
        notes.append(f"link: asked {len(asked)} question"
                     f"{'' if len(asked) == 1 else 's'} about contradictions")
    return linked + asked, notes


def _repo_root(found: list[Path], fallback: Path) -> Path:
    """The repository holding the documents.

    Never the working directory: reading another project's history is the main
    case, and there cwd names a repository the documents are not in. Both the
    identity key and the git date lookup are relative to this.
    """
    start = found[0].resolve().parent if found else fallback
    try:
        done = subprocess.run(["git", "-C", str(start), "rev-parse", "--show-toplevel"],
                              capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return fallback
    if done.returncode != 0:
        return fallback
    return Path(done.stdout.strip()).resolve()


def _relative(path: Path, root: Path) -> str:
    """The path as the repository names it.

    Both the identity key and the git date lookup hinge on this spelling. An
    absolute path would restage every record as new on the next run, and would
    miss every git date, which silently disables supersession.
    """
    try:
        return str(path.resolve().relative_to(root))
    except ValueError:
        return str(path)


def two_pass(paths: list[str], jobs: int = 8, dry_run: bool = False,
             caller=None, batch: int = link.BATCH,
             root: Path | None = None, sleep=time.sleep,
             exclude: tuple[str, ...] = EXCLUDE,
             untracked: bool = False) -> tuple[list[dict], list[str]]:
    """Both passes over the given documents.

    A document whose call fails costs only its own records. One provider error
    out of 180 should not discard the other 179.
    """
    found = documents(paths, exclude=exclude, untracked=untracked)
    if not found:
        raise RunError(f"no markdown found under {', '.join(paths)}")

    report = [f"read {len(found)} document{'' if len(found) == 1 else 's'}"]
    if dry_run:
        report.extend(f"  would read {path}" for path in found[:20])
        if len(found) > 20:
            report.append(f"  ... and {len(found) - 20} more")
        return [], report

    caller = caller or _default_caller()
    root = (root or _repo_root(found, Path.cwd())).resolve()
    git = extract.git_dates(root)
    bodies = {path: path.read_text(errors="replace") for path in found}
    names = {path: _relative(path, root) for path in found}
    dates = {path: extract.resolve_date(names[path], bodies[path], git)
             for path in found}

    proposals: list[dict] = []
    failed = 0
    fatal: client.ClientError | None = None
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        futures = {
            pool.submit(_one_document, names[path], bodies[path], dates[path],
                        caller, sleep): path
            for path in found
        }
        for future in concurrent.futures.as_completed(futures):
            path = futures[future]
            try:
                kept, notes = future.result()
            except client.ClientError as exc:
                # A rejected key answers for every remaining document. Cancelling
                # what has not started spends one call to learn it, never 60.
                fatal = exc
                for pending in futures:
                    pending.cancel()
                break
            except concurrent.futures.CancelledError:
                continue
            except Exception as exc:
                failed += 1
                report.append(f"{path}: extraction failed, {exc}")
                continue
            proposals.extend(kept)
            report.extend(notes)

    if fatal is not None:
        raise fatal
    if failed == len(found):
        raise RunError(
            f"every document failed: {failed} of {failed}. Nothing was staged.")

    proposals.sort(key=lambda item: (item["source"]["path"], item.get("line", 0)))

    if len(proposals) < 2:
        report.append("link: skipped, nothing to relate")
        return proposals, report

    try:
        proposals, notes = _link(proposals, caller, batch)
    except Exception as exc:
        report.append(f"link: failed, {exc}; proposals staged without relations")
        return proposals, report
    report.extend(notes)
    return proposals, report
