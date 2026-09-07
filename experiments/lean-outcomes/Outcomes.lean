import Std

set_option autoImplicit false

namespace Docket.Outcomes

abbrev Chain (Step : Type) := List Step

abbrev Realization (Step Outcome : Type) := Chain Step → Outcome → Prop

abbrev Intent (Step Outcome : Type) := Chain Step → Outcome → Prop

section General

variable {Step Outcome : Type}

abbrev intentional (realizes : Realization Step Outcome) (intends : Intent Step Outcome)
    (chain : Chain Step) (outcome : Outcome) : Prop :=
  realizes chain outcome ∧ intends chain outcome

abbrev unintentional (realizes : Realization Step Outcome) (intends : Intent Step Outcome)
    (chain : Chain Step) (outcome : Outcome) : Prop :=
  realizes chain outcome ∧ ¬ intends chain outcome

theorem realized_iff_classified
    (realizes : Realization Step Outcome) (intends : Intent Step Outcome)
    (chain : Chain Step) (outcome : Outcome) :
    realizes chain outcome ↔
      intentional realizes intends chain outcome ∨
      unintentional realizes intends chain outcome := by
  classical
  constructor
  · intro happened
    by_cases aimed : intends chain outcome
    · exact Or.inl ⟨happened, aimed⟩
    · exact Or.inr ⟨happened, aimed⟩
  · intro classified
    cases classified with
    | inl intended => exact intended.1
    | inr unintended => exact unintended.1

theorem classifications_disjoint
    (realizes : Realization Step Outcome) (intends : Intent Step Outcome)
    (chain : Chain Step) (outcome : Outcome) :
    ¬ (intentional realizes intends chain outcome ∧
      unintentional realizes intends chain outcome) := by
  intro both
  exact both.2.2 both.1.2

end General

namespace Backup

inductive Step where
  | copyToFreshPath
  | copyOverExistingPath
  deriving DecidableEq, Repr

inductive Outcome where
  | backupCreated
  | oldBackupOverwritten
  deriving DecidableEq, Repr

def freshBackup : Chain Step := [.copyToFreshPath]

def overwriteBackup : Chain Step := [.copyOverExistingPath]

-- This table stipulates effects in one fixed situation; it does not execute a filesystem.
abbrev realizes : Realization Step Outcome := fun chain outcome =>
  (chain = freshBackup ∧ outcome = .backupCreated) ∨
  (chain = overwriteBackup ∧
    (outcome = .backupCreated ∨ outcome = .oldBackupOverwritten))

abbrev backupOnlyIntent : Intent Step Outcome := fun _ outcome =>
  outcome = .backupCreated

abbrev replaceIntent : Intent Step Outcome := fun _ outcome =>
  outcome = .backupCreated ∨ outcome = .oldBackupOverwritten

theorem backup_is_intended :
    intentional realizes backupOnlyIntent overwriteBackup .backupCreated := by
  decide

theorem overwrite_is_unintended :
    unintentional realizes backupOnlyIntent overwriteBackup .oldBackupOverwritten := by
  decide

theorem overwrite_is_intended_when_replacing :
    intentional realizes replaceIntent overwriteBackup .oldBackupOverwritten := by
  decide

theorem two_chains_one_outcome :
    freshBackup ≠ overwriteBackup ∧
    realizes freshBackup .backupCreated ∧ realizes overwriteBackup .backupCreated := by
  decide

theorem one_chain_two_outcomes :
    Outcome.backupCreated ≠ Outcome.oldBackupOverwritten ∧
    realizes overwriteBackup .backupCreated ∧
    realizes overwriteBackup .oldBackupOverwritten := by
  decide

theorem realization_does_not_determine_classification :
    ¬ (∀ (first second : Intent Step Outcome) (chain : Chain Step) (outcome : Outcome),
      intentional realizes first chain outcome ↔
      intentional realizes second chain outcome) := by
  intro sameClassification
  have classifiedAsIntended :=
    (sameClassification replaceIntent backupOnlyIntent overwriteBackup
      .oldBackupOverwritten).mp overwrite_is_intended_when_replacing
  exact overwrite_is_unintended.2 classifiedAsIntended.2

private def allOutcomes : List Outcome := [.backupCreated, .oldBackupOverwritten]

private def outcomeName : Outcome → String
  | .backupCreated => "backup created"
  | .oldBackupOverwritten => "old backup overwritten"

private def describe (outcomes : List Outcome) : String :=
  if outcomes.isEmpty then "none"
  else String.intercalate ", " (outcomes.map outcomeName)

private def report (title : String) (chain : Chain Step) (intends : Intent Step Outcome)
    [DecidablePred (intends chain)] : IO Unit := do
  let realized := allOutcomes.filter fun outcome => decide (realizes chain outcome)
  let intended := allOutcomes.filter fun outcome =>
    decide (intentional realizes intends chain outcome)
  let unintended := allOutcomes.filter fun outcome =>
    decide (unintentional realizes intends chain outcome)
  IO.println title
  IO.println s!"  Realized:   {describe realized}"
  IO.println s!"  Intended:   {describe intended}"
  IO.println s!"  Unintended: {describe unintended}"
  IO.println ""

def demo : IO Unit := do
  IO.println "A toy backup model. No files are copied or overwritten."
  IO.println ""
  report "1. Copy to a fresh path; aim to create a backup." freshBackup backupOnlyIntent
  report "2. Copy over an old backup; aim to create a backup." overwriteBackup backupOnlyIntent
  report "3. Same copy as case 2; aim to create a backup and replace the old one."
    overwriteBackup replaceIntent
  IO.println "Cases 2 and 3 have identical actions and effects."
  IO.println "Their supplied intent labels change the classification."

end Backup

end Docket.Outcomes

def main : IO Unit := Docket.Outcomes.Backup.demo
