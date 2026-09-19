"""What a briefing prints when the admitted records still overrun the ceiling.

Split from docket.context and docket.context_budget to keep both under the 300
line limit. Admission stops at the soft target; this runs only when the
rendered result is still too long, which is the caller's own header or query
being oversized rather than the records.
"""

from __future__ import annotations

import itertools

from docket.context_budget import Admission


def largest_fitting_keep(budget: Admission, head, chosen_order, chosen_set, deferred_ids) -> int:
    """How many bare names fit, over the same descending sequence as before.

    Length rises with the name count, so the sequence splits into a refused
    prefix and an accepted suffix. Probing it by bisection costs a handful of
    length computations instead of one render per step.
    """

    if not deferred_ids:
        return 0
    steps = []
    count = len(deferred_ids)
    while count > 0:
        steps.append(count)
        count -= max(1, count // 8)
    sums = [0, *itertools.accumulate(len(ident) for ident in deferred_ids)]
    body = sum(len(budget.rendered_record(i)) for i in chosen_order)
    full = body + 2 * (len(chosen_order) - 1) if chosen_order else 0
    related = {
        target
        for ident in chosen_set
        for target in budget.relations[ident]
        if target not in chosen_set and target in budget.current_id_set
    }
    needed = set(budget.task_matched)
    for ident in chosen_set:
        needed.update(budget.blocking_ids(ident))
    missing = len(needed - chosen_set)
    base = len(head.rstrip("\n")) + (full + 4 if chosen_order else 2)

    def length(keep):
        # render names at most max_lines of them and then says how many it left
        # out, so trimming past the cap only changes that count.
        shown = min(keep, budget.max_lines)
        index = budget.index_head + sums[shown] + 2 * (shown - 1)
        if keep > shown:
            index += len(f"# and {keep - shown} more; docket list") + 1
        tail = budget.footer_text(len(chosen_set), shown, len(deferred_ids), len(related), missing)
        computed = base + index + len(tail)
        if budget.verify:
            measured = len(
                budget.render(chosen_order, chosen_set, deferred_ids[:keep], names_only=True)
            )
            if measured != computed:
                raise AssertionError(
                    f"trim length at keep={keep}: computed {computed}, rendered {measured}"
                )
        return computed

    # Naming every record drops the "Not listed" line, so length falls at the
    # top of the range. Test the whole set first, then bisect the rest, where
    # length does rise with the name count.
    if length(steps[0]) <= budget.hard_limit:
        return steps[0]
    low, high = 1, len(steps)
    while low < high:
        middle = (low + high) // 2
        if length(steps[middle]) <= budget.hard_limit:
            high = middle
        else:
            low = middle + 1
    if low == len(steps):
        return 0
    return steps[low]


def degrade(budget: Admission, *, current_ids: list[str], short: str, revision: str) -> str:
    """The longest form of the briefing that fits the ceiling.

    In order: shrink every index line to the minimum detail, then drop to bare
    IDs, then trim the ID list. Bare IDs come before any trimming because they
    cost a few characters each, so naming thirty records that way is cheaper
    than listing four in full.
    """

    flat = budget.render(budget.order, budget.included, detail=budget.detail_min)
    if len(flat) <= budget.hard_limit:
        return flat
    # Trim the deferred list, not current_ids: records already in the full-text
    # tier occupy the head of current_ids, so trimming that list would drop
    # index lines while appearing to keep them.
    # Keep the full-text tier if it fits alongside bare names; drop it only
    # when even that overruns, and report the tier counts either way.
    for head in (budget.prefix, short):
        budget.prefix = head
        for chosen_order, chosen_set in ((budget.order, budget.included), ([], set())):
            deferred_ids = [i for i in current_ids if i not in chosen_set]
            keep = largest_fitting_keep(budget, head, chosen_order, chosen_set, deferred_ids)
            if keep:
                return budget.render(chosen_order, chosen_set, deferred_ids[:keep], names_only=True)
    return (
        f"# docket revision: {revision}\n# No records fit.\n"
        "# Retrieve full record: docket show RECORD_ID --json\n"
    )


__all__ = ["degrade"]
