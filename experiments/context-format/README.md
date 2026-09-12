# Context format cost

`measure.py` prints the size of one ledger rendered four ways. It reports cost
and decides nothing: a token count compares format density, and whether a
format helps an agent needs a comprehension test this repository does not have.

## Run

```
python3 experiments/context-format/measure.py [LEDGER]
```

The ledger defaults to `.docket/ledger.jsonl` in the repository root. The token
column prints `-` unless `tiktoken` is importable. Docket takes no new
dependency for this, and the character column compares formats on its own.

## Variants

| Variant | Inputs |
| --- | --- |
| `scoped` | `files=("lib/docket_context.py",)` |
| `scoped tight` | the same files, with `budget.target` halved |
| `unscoped` | no query and no files |
| `all` | `all_records=True` |

A task match may exceed `budget.target` up to `budget.outer_multiple` times it,
so `scoped tight` does not halve the output.

## Baseline

2026-09-12, this repository's ledger at revision `4472b9f059ce`, 46 records,
`tiktoken` absent.

```
variant          chars  tokens  full
scoped            9295       -     9
scoped tight      8460       -     8
unscoped          9221       -     8
all               9615       -     9
```
