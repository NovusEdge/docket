"""The character budget: which selected records reach the page.

Split from docket.context to keep that file under the 300 line limit. The
selection layer decides what a briefing wants to say. This decides how much of
it fits, and it is the only part that has to be fast: the admission trial runs
once per candidate, so anything O(n) inside it makes the whole build O(n^2).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from docket.context_model import _text
from docket.context_render import _footer, _index_line, _render_record
from docket.context_select import _blocking_paths


class Admission:
    """One briefing's budget state, and the gate every record passes through.

    These were closures over a single build. The state they shared is now
    explicit, which is what lets the file stay readable: fifteen names cross
    between trial_length, admit and render, and none of them is derivable from
    the others.
    """

    def __init__(
        self,
        *,
        by_id: Mapping[str, Mapping[str, Any]],
        current_ids: list[str],
        relations: Mapping[str, list[str]],
        scores: Mapping[str, int],
        reasons: Mapping[str, str],
        task_matched: set[str],
        prefix: str,
        cfg: Mapping[str, Any],
        soft_limit: int,
        hard_limit: int,
        retired_count: int,
        no_match: bool,
        blocking_cache: dict[str, list[list[str]]],
        verify: bool = False,
    ) -> None:
        self.by_id = by_id
        self.current_ids = current_ids
        self.current_id_set = set(current_ids)
        self.relations = relations
        self.scores = scores
        self.reasons = reasons
        self.task_matched = task_matched
        self.prefix = prefix
        self.soft_limit = soft_limit
        self.hard_limit = hard_limit
        self.retired_count = retired_count
        self.no_match = no_match
        self.blocking_cache = blocking_cache
        self.verify = verify

        self.detail_min = cfg["index"]["detail_min"]
        self.detail_max = cfg["index"]["detail_max"]
        self.max_lines = cfg["index"]["max_lines"]

        self.included: set[str] = set()
        self.order: list[str] = []
        self.labels: dict[str, str] = {}
        self.record_cache: dict[tuple[str, str], str] = {}
        self.top_score = max(scores.values(), default=0) or 1

        # Counters for the admission trial. Rendering the whole briefing to
        # measure each candidate cost O(n) per admit, so a 10000-record ledger
        # took 20s.
        self.body_length = 0
        self.deferred_count = len(current_ids)
        self.related_pending: set[str] = set()
        self.needed_ids = set(task_matched)
        self.missing_count = len(self.needed_ids)
        self.index_head = len("# index: ")

        # The index names at most max_lines records, so the gate prices a
        # sliding window over current_ids instead of the whole list. The cursor
        # only moves forward, which keeps the whole admission pass linear.
        self.window: list[str] = []
        self.window_length = 0
        self.cursor = 0
        self._fill_window()
        self.base_length = len(prefix.rstrip("\n"))

    def shrink_prefix(self, short: str) -> None:
        """Fall back to the short header when the full one plus the footer overruns.

        Only diagnostic metadata shortens. Propositions and relationship
        formulas are never sliced, even when the caller supplies a giant path
        or query.
        """

        if len(self.prefix) + len(self.footer(set())) > self.hard_limit:
            self.prefix = short
            self.base_length = len(short.rstrip("\n"))

    def footer_text(self, included_count, shown, deferred_count, related_count, missing_count):
        return _footer(
            included_count,
            shown,
            deferred_count,
            related_count,
            missing_count,
            retired_count=self.retired_count,
            no_match=self.no_match,
        )

    def blocking_ids(self, ident):
        if _text(self.by_id[ident].get("kind")).casefold() != "decision":
            return ()
        return [
            step
            for path in _blocking_paths(ident, self.by_id, cache=self.blocking_cache)
            for step in path
        ]

    def footer(self, included, listed=None):
        deferred_count = sum(1 for ident in self.current_ids if ident not in included)
        shown = deferred_count if listed is None else listed
        related = {
            target
            for ident in included
            for target in self.relations[ident]
            if target not in included and target in self.current_id_set
        }
        needed = set(self.task_matched)
        for ident in included:
            needed.update(self.blocking_ids(ident))
        return self.footer_text(
            len(included), shown, deferred_count, len(related), len(needed - included)
        )

    def detail_of(self, ident):
        span = self.detail_max - self.detail_min
        return self.detail_min + (self.scores.get(ident, 0) * span) // self.top_score

    def rendered_record(self, ident):
        key = (ident, self.labels[ident])
        if key not in self.record_cache:
            self.record_cache[key] = _render_record(
                self.by_id[ident],
                self.labels[ident],
                self.reasons.get(ident, ""),
                self.by_id,
                blocking_cache=self.blocking_cache,
            )
        return self.record_cache[key]

    def render(self, candidate_order, candidate_set, index_ids=None, detail=None, names_only=False):
        full = "\n\n".join(self.rendered_record(i) for i in candidate_order)
        pool = self.current_ids if index_ids is None else index_ids
        deferred = [i for i in pool if i not in candidate_set]
        # Score order, so the cap keeps the records closest to the task.
        shown = deferred[: self.max_lines]
        parts = [self.prefix.rstrip("\n"), ""]
        if full:
            parts += [full, ""]
        if shown:
            if names_only:
                parts.append("# index: " + ", ".join(shown))
            else:
                parts.append(f"# index: {len(shown)} more current records")
                parts.append(
                    "\n".join(
                        _index_line(self.by_id[i], self.detail_of(i) if detail is None else detail)
                        for i in shown
                    )
                )
            if len(deferred) > len(shown):
                parts.append(f"# and {len(deferred) - len(shown)} more; docket list")
        return "\n".join(parts).rstrip("\n") + self.footer(candidate_set, len(shown))

    def _fill_window(self):
        while len(self.window) < self.max_lines and self.cursor < len(self.current_ids):
            candidate = self.current_ids[self.cursor]
            self.cursor += 1
            if candidate not in self.included:
                self.window.append(candidate)
                self.window_length += len(candidate)

    def _next_after_window(self, exclude):
        """The name that would enter the window if one left it."""

        scan = self.cursor
        while scan < len(self.current_ids):
            candidate = self.current_ids[scan]
            if candidate not in self.included and candidate != exclude:
                return candidate
            scan += 1
        return ""

    def trial_length(self, ident):
        """Length of the briefing that admitting ident would produce.

        This mirrors render(order + [ident], included | {ident}, names_only=True)
        exactly. A rendered record is never empty, so the full-text block is
        always present and only the index part varies.
        """

        full = self.body_length + len(self.rendered_record(ident)) + 2 * len(self.order)
        deferred = self.deferred_count - (1 if ident in self.current_id_set else 0)
        length, shown = self.window_length, len(self.window)
        if ident in self.window:
            length -= len(ident)
            shown -= 1
            entering = self._next_after_window(ident)
            if entering:
                length += len(entering)
                shown += 1
        if shown:
            index = self.index_head + length + 2 * (shown - 1)
            total = self.base_length + full + index + 4
            if deferred > shown:
                total += len(f"# and {deferred - shown} more; docket list") + 1
        else:
            # "\n".join ends with the empty part, and rstrip drops that newline.
            total = self.base_length + full + 2
        # Counted by difference. Copying either set per candidate was itself
        # O(n), which left a 100000-record briefing at 135s.
        related = len(self.related_pending) - (1 if ident in self.related_pending else 0)
        added: set[str] = set()
        for target in self.relations[ident]:
            if (
                target != ident
                and target not in self.included
                and target not in self.related_pending
                and target in self.current_id_set
                and target not in added
            ):
                added.add(target)
                related += 1
        missing = self.missing_count - (1 if ident in self.needed_ids else 0)
        added.clear()
        for step in self.blocking_ids(ident):
            if step not in self.needed_ids and step not in self.included and step not in added:
                added.add(step)
                missing += 1
        return total + len(
            self.footer_text(len(self.included) + 1, shown, deferred, related, missing)
        )

    def admit(self, ident, label, mandatory=False):
        if ident in self.included:
            return True
        self.labels[ident] = label
        # A task match may push past the target. Nothing may push past the
        # ceiling, which equals the target whenever the caller named one.
        limit = self.hard_limit if mandatory else self.soft_limit
        if self.verify:
            measured = len(
                self.render(self.order + [ident], self.included | {ident}, names_only=True)
            )
            computed = self.trial_length(ident)
            if measured != computed:
                raise AssertionError(
                    f"trial length for {ident}: computed {computed}, rendered {measured}"
                )
        if self.trial_length(ident) > limit:
            del self.labels[ident]
            # A refused candidate never reaches the output, so its rendered text
            # is dead. Keeping every one cost 35 MB at 40000 records.
            self.record_cache.pop((ident, label), None)
            return False
        self.included.add(ident)
        self.order.append(ident)
        self.body_length += len(self.rendered_record(ident))
        if ident in self.current_id_set:
            self.deferred_count -= 1
        if ident in self.window:
            self.window.remove(ident)
            self.window_length -= len(ident)
            self._fill_window()
        self.related_pending.discard(ident)
        self.related_pending.update(
            target
            for target in self.relations[ident]
            if target not in self.included and target in self.current_id_set
        )
        if ident in self.needed_ids:
            self.missing_count -= 1
        for step in self.blocking_ids(ident):
            if step not in self.needed_ids:
                self.needed_ids.add(step)
                if step not in self.included:
                    self.missing_count += 1
        return True


__all__ = ["Admission"]
