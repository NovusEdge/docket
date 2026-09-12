# Briefing cost against ledger size

`generate.py` builds a synthetic ledger of N records and renders two briefings
from it: one with no task scope, and one scoped to `lib/render.py`. Columns are
the character length of each briefing, the number of records rendered in full
text, and the number of index lines in the scoped briefing.

Run it with `python3 experiments/context-scale/generate.py`.

## 2026-09-12, before the index cap

```
 records  unscoped   scoped  full  index
      33      7376     3744    10     23
     100     10427    10514    30     70
     250     16386    20312    41    209
     500      7994    23949    80      0
    1000      7870    23933    68      0
```

The budget target is 8,000 characters and the ceiling is 24,000. The scoped
briefing passes the target at 100 records and reaches the ceiling at 500. The
index is what grows: 209 lines at 250 records, each naming a record the reader
cannot act on.

Both 500-record columns show the degradation ladder working instead of the
budget. The unscoped briefing falls to the bare-identifier tier, which is why
its index-line count is zero and its length drops back under the target. The
scoped briefing stays at the ceiling because every `lib/**` record matches the
scope and admits as mandatory.

The whole run takes about 15 seconds, dominated by the per-record history scan
in relation scoring.
