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

## 2026-09-12, after the index cap

`index.max_lines = 40`.

```
 records  unscoped   scoped  full  index
      33      7376     3744    10     23
     100      9398     9322    30     40
     250      9533    13063    41     40
     500      9543    22609    83      0
    1000      9482    23775    87      0
```

The unscoped briefing now flattens at about 9,500 characters from 100 records
upward, instead of growing to the point where the ladder discards the index.

One-pass relation scoring cuts the run from 15 seconds to 5, and every number
in the table is unchanged by it.

The scoped rows stay at the ceiling because the index is not what fills them.
Every `lib/**` record matches the file scope, so each one admits as mandatory
and renders in full: 83 records at 500 and 87 at 1000. Their index falls to
bare identifiers, which is the ladder, not the cap.

### Choosing the cap

The admission gate prices the index at one bare identifier per record, so the
rendered index costs about 40 characters per line beyond what the gate charged.
The unscoped briefing at 1000 records measures:

```
 cap   length
  20     8632
  30     9057
  40     9482
  60    10156
  90    11289
 120    12420
 200    15575
```

40 lines holds the briefing within about 20 percent of the 8,000 character
target. The plan proposed 120, which costs 12,400 characters, 55 percent over
the target, to name 80 further records that already scored below everything the
full-text tier admitted.
