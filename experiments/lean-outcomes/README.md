# First Lean experiment: outcomes and intent

This experiment checks a small part of the [outcome formalism](../../docs/outcome-formalism.md).
It contains eight theorems and a console example in [Outcomes.lean](Outcomes.lean).

The follow-up [formalism stress tests](STRESS-TESTS.md) check reduction
completeness, consequence operators, parallel validity, retraction, and order
invariance. Several original claims fail; the document gives the checked
counterexamples and repaired conditions.

The question is: **if we know what a program did and what happened, do we also
know which effects it intended?**

## Run it

With `elan` installed:

```sh
cd ~/Projects/docket/experiments/lean-outcomes
lean --run Outcomes.lean
```

The `lean-toolchain` file selects Lean 4.33.1 for this directory. Elan downloads
that compiler if needed. The experiment uses Lean's bundled standard library;
there are no additional packages or API keys to configure.

To check the proofs without running the console example:

```sh
lean -DwarningAsError=true Outcomes.lean
```

A successful check exits with code 0 and prints nothing. Unfinished proof goals
fail the check; warnings are also treated as errors by this command.

## What the example shows

Two possible chains copy a file to either a fresh path or an existing backup path.
The model records two possible effects: a backup is created, and an old backup
is overwritten.

| Case | Action | Declared aims | Unintended realized effects |
| --- | --- | --- | --- |
| 1 | Copy to a fresh path | Create a backup | None |
| 2 | Copy over an existing backup | Create a backup | Old backup overwritten |
| 3 | Same action as case 2 | Create a backup and overwrite the old one | None |

Cases 2 and 3 use the same action and realization relation. Only the supplied
intent changes. So this model cannot recover the intent label from the effects
alone.

The example is a table of stipulated effects. It does not copy or overwrite any
files. It describes one fixed situation, and only the two listed chains have
modeled effects.

## Read the Lean file

The file has three parts:

1. **Definitions.** A chain is a list of steps. `realizes chain outcome` means
   the effect happened. `intends chain outcome` means it was an aim. An
   intentional outcome satisfies both; an unintentional one happened without
   being an aim.
2. **Proofs.** `realized_iff_classified` proves the classification covers exactly
   the realized outcomes. `classifications_disjoint` proves that an outcome
   cannot belong to both groups. These apply to any realization and intent
   relations, without assuming one-to-many behavior.
3. **Backup example.** Five finite checks establish the example's classifications
   and its one-to-many and many-to-one cases. The final theorem,
   `realization_does_not_determine_classification`, refutes the claim that every
   choice of intent gives the same classification for the fixed realization
   relation. `main` prints the three cases.

`Prop` means a mathematical proposition. `∧` means "and", `¬` means "not", and
`↔` means "if and only if". A `theorem` states a claim; the code after `by`
supplies its proof. Here `decide` discharges finite checks by computation.

The general partition proof uses classical case analysis: either an outcome is
intended or it is not. Lean checks the proofs against its standard foundations;
the file introduces no custom axioms or admitted proofs.

## One change to try

Find `backupOnlyIntent` and add overwriting the old backup as another aim:

```lean
abbrev backupOnlyIntent : Intent Step Outcome := fun _ outcome =>
  outcome = .backupCreated ∨ outcome = .oldBackupOverwritten
```

Run the proof check again. `overwrite_is_unintended` now fails, because the model
says that overwriting was intended. This failure identifies a claim that no
longer follows after the definition changes. Restore the original definition
before continuing.

## What this establishes

The split into intended and unintended realized outcomes is consistent under
these definitions. The examples also show that intent is an independent input
unless we add constraints connecting intent to behavior.

This does not establish that the definitions capture real intentions, that the
taxonomy is novel, or that it improves agent behavior. An intended outcome that
never happens belongs to neither reported group. A later experiment could track
that unmet goal separately.

After exploring these definitions, the next useful step is a small simulation:
withdraw a premise, then check which decisions must change and which still have
independent support.
