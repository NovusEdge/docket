import Std

set_option autoImplicit false

namespace Docket.StressTests

abbrev Predicate (α : Type) := α → Prop

namespace Reduction

variable {Outcome : Type}

def IsPartition (realized intended unintended : Predicate Outcome) : Prop :=
  (∀ outcome, realized outcome ↔ intended outcome ∨ unintended outcome) ∧
  (∀ outcome, ¬ (intended outcome ∧ unintended outcome))

theorem every_partition_is_representable
    (realized intended unintended : Predicate Outcome)
    (partition : IsPartition realized intended unintended) :
    ∃ intent : Predicate Outcome,
      (∀ outcome, intended outcome ↔ realized outcome ∧ intent outcome) ∧
      (∀ outcome, unintended outcome ↔ realized outcome ∧ ¬ intent outcome) := by
  refine ⟨intended, ?_, ?_⟩
  · intro outcome
    constructor
    · intro isIntended
      exact ⟨partition.1 outcome |>.mpr (Or.inl isIntended), isIntended⟩
    · exact fun represented => represented.2
  · intro outcome
    constructor
    · intro isUnintended
      refine ⟨partition.1 outcome |>.mpr (Or.inr isUnintended), ?_⟩
      intro isIntended
      exact partition.2 outcome ⟨isIntended, isUnintended⟩
    · intro represented
      cases partition.1 outcome |>.mp represented.1 with
      | inl isIntended => exact False.elim (represented.2 isIntended)
      | inr isUnintended => exact isUnintended

theorem classification_is_unique
    (realized intent intended₁ unintended₁ intended₂ unintended₂ : Predicate Outcome)
    (firstIntended : ∀ outcome, intended₁ outcome ↔ realized outcome ∧ intent outcome)
    (firstUnintended : ∀ outcome, unintended₁ outcome ↔ realized outcome ∧ ¬ intent outcome)
    (secondIntended : ∀ outcome, intended₂ outcome ↔ realized outcome ∧ intent outcome)
    (secondUnintended : ∀ outcome, unintended₂ outcome ↔ realized outcome ∧ ¬ intent outcome) :
    (∀ outcome, intended₁ outcome ↔ intended₂ outcome) ∧
    (∀ outcome, unintended₁ outcome ↔ unintended₂ outcome) := by
  constructor
  · intro outcome
    exact (firstIntended outcome).trans (secondIntended outcome).symm
  · intro outcome
    exact (firstUnintended outcome).trans (secondUnintended outcome).symm

end Reduction

namespace Consequences

variable {Outcome : Type}

abbrev Subset (left right : Predicate Outcome) :=
  ∀ outcome, left outcome → right outcome

structure ClosureLaws (close : Predicate Outcome → Predicate Outcome) : Prop where
  extensive : ∀ outcomes, Subset outcomes (close outcomes)
  monotone : ∀ {left right}, Subset left right → Subset (close left) (close right)
  idempotent : ∀ outcomes outcome, close (close outcomes) outcome ↔ close outcomes outcome
  preservesEmpty : ∀ outcome, ¬ close (fun _ => False) outcome

def conditionalAdjoin (extra outcomes : Predicate Outcome) : Predicate Outcome :=
  fun outcome =>
    outcomes outcome ∨ ((∃ seed, outcomes seed) ∧ extra outcome)

def indirect (close : Predicate Outcome → Predicate Outcome)
    (direct : Predicate Outcome) : Predicate Outcome :=
  fun outcome => close direct outcome ∧ ¬ direct outcome

theorem conditionalAdjoin_satisfies_closure_laws (extra : Predicate Outcome) :
    ClosureLaws (conditionalAdjoin extra) := by
  constructor
  · intro outcomes outcome present
    exact Or.inl present
  · intro left right included outcome closed
    cases closed with
    | inl present => exact Or.inl (included outcome present)
    | inr added =>
        rcases added.1 with ⟨seed, seedPresent⟩
        exact Or.inr ⟨⟨seed, included seed seedPresent⟩, added.2⟩
  · intro outcomes outcome
    constructor
    · intro closedTwice
      cases closedTwice with
      | inl closedOnce => exact closedOnce
      | inr added =>
          rcases added with ⟨⟨seed, seedClosed⟩, outcomeExtra⟩
          apply Or.inr
          constructor
          · cases seedClosed with
            | inl seedPresent => exact ⟨seed, seedPresent⟩
            | inr seedAdded => exact seedAdded.1
          · exact outcomeExtra
    · exact fun closedOnce => Or.inl closedOnce
  · intro outcome closed
    cases closed with
    | inl impossible => exact impossible
    | inr added =>
        rcases added.1 with ⟨seed, impossible⟩
        exact impossible

theorem closure_laws_allow_any_indirect_split
    (direct desiredIndirect : Predicate Outcome)
    (directNonempty : ∃ outcome, direct outcome)
    (disjoint : ∀ outcome, desiredIndirect outcome → ¬ direct outcome) :
    ∀ outcome,
      indirect (conditionalAdjoin desiredIndirect) direct outcome ↔
      desiredIndirect outcome := by
  intro outcome
  constructor
  · intro isIndirect
    cases isIndirect.1 with
    | inl isDirect => exact False.elim (isIndirect.2 isDirect)
    | inr added => exact added.2
  · intro desired
    exact ⟨Or.inr ⟨directNonempty, desired⟩, disjoint outcome desired⟩

inductive Path (edge : Outcome → Outcome → Prop) : Outcome → Outcome → Prop where
  | refl (outcome : Outcome) : Path edge outcome outcome
  | step {source middle target : Outcome} :
      edge source middle → Path edge middle target → Path edge source target

theorem Path.trans {edge : Outcome → Outcome → Prop} {source middle target : Outcome}
    (first : Path edge source middle) (second : Path edge middle target) :
    Path edge source target := by
  induction first with
  | refl outcome => exact second
  | step relation rest inductionHypothesis =>
      exact Path.step relation (inductionHypothesis second)

def generatedClosure (edge : Outcome → Outcome → Prop)
    (direct : Predicate Outcome) : Predicate Outcome :=
  fun outcome => ∃ source, direct source ∧ Path edge source outcome

theorem generatedClosure_satisfies_closure_laws (edge : Outcome → Outcome → Prop) :
    ClosureLaws (generatedClosure edge) := by
  constructor
  · intro outcomes outcome present
    exact ⟨outcome, present, Path.refl outcome⟩
  · intro left right included outcome reachable
    rcases reachable with ⟨source, present, path⟩
    exact ⟨source, included source present, path⟩
  · intro outcomes outcome
    constructor
    · intro reachableTwice
      rcases reachableTwice with ⟨middle, ⟨source, present, firstPath⟩, secondPath⟩
      exact ⟨source, present, firstPath.trans secondPath⟩
    · intro reachable
      exact ⟨outcome, reachable, Path.refl outcome⟩
  · intro outcome reachable
    rcases reachable with ⟨source, impossible, path⟩
    exact impossible

theorem generated_indirect_has_path
    (edge : Outcome → Outcome → Prop) (direct : Predicate Outcome) (outcome : Outcome) :
    indirect (generatedClosure edge) direct outcome →
      ∃ source, direct source ∧ source ≠ outcome ∧ Path edge source outcome := by
  intro isIndirect
  rcases isIndirect.1 with ⟨source, sourceDirect, path⟩
  refine ⟨source, sourceDirect, ?_, path⟩
  intro sameOutcome
  exact isIndirect.2 (sameOutcome ▸ sourceDirect)

end Consequences

namespace Parallel

abbrev Section (State : Type) := State → State

section Generic

variable {State Step : Type}

def sequence (first second : Section State) (initial : State) : State :=
  second (first initial)

def Commute (first second : Section State) : Prop :=
  ∀ initial, sequence first second initial = sequence second first initial

def IsStrictPartialOrder (dependsOn : Step → Step → Prop) : Prop :=
  (∀ step, ¬ dependsOn step step) ∧
  (∀ first second third,
    dependsOn first second → dependsOn second third → dependsOn first third)

def NoCrossing (dependsOn : Step → Step → Prop)
    (left right : Predicate Step) : Prop :=
  ∀ first second, left first → right second →
    ¬ dependsOn first second ∧ ¬ dependsOn second first

def runSteps (effect : Step → Section State) (steps : List Step) : Section State :=
  fun initial => steps.foldl (fun state step => effect step state) initial

def StepsCommute (effect : Step → Section State) (left right : List Step) : Prop :=
  ∀ first ∈ left, ∀ second ∈ right, Commute (effect first) (effect second)

theorem runSteps_cons (effect : Step → Section State) (step : Step) (rest : List Step)
    (initial : State) :
    runSteps effect (step :: rest) initial = runSteps effect rest (effect step initial) := by
  simp [runSteps]

theorem section_commutes_with_step
    (effect : Step → Section State) (left : List Step) (second : Step)
    (stepwise : ∀ first ∈ left, Commute (effect first) (effect second)) :
    Commute (runSteps effect left) (effect second) := by
  induction left with
  | nil => intro initial; simp [sequence, runSteps]
  | cons first rest inductionHypothesis =>
      intro initial
      have firstCommutes := stepwise first (List.mem_cons_self ..) initial
      have restCommutes :=
        inductionHypothesis (fun step present => stepwise step (List.mem_cons_of_mem _ present))
      simp only [Commute, sequence, runSteps_cons] at firstCommutes restCommutes ⊢
      rw [restCommutes, firstCommutes]

theorem stepwise_commutation_lifts_to_sections
    (effect : Step → Section State) (left right : List Step)
    (stepwise : StepsCommute effect left right) :
    Commute (runSteps effect left) (runSteps effect right) := by
  induction right with
  | nil => intro initial; simp [sequence, runSteps]
  | cons second rest inductionHypothesis =>
      intro initial
      have headCommutes :=
        section_commutes_with_step effect left second
          (fun step present => stepwise step present second (List.mem_cons_self ..))
      have restCommutes :=
        inductionHypothesis fun first present step inRest =>
          stepwise first present step (List.mem_cons_of_mem _ inRest)
      simp only [Commute, sequence, runSteps_cons] at headCommutes restCommutes ⊢
      rw [headCommutes, restCommutes]

end Generic

namespace Counterexample

inductive Step where
  | setOne
  | double
  deriving DecidableEq, Repr

def noDependency : Step → Step → Prop := fun _ _ => False

def crossingDependency : Step → Step → Prop
  | .setOne, .double => True
  | _, _ => False

def left : Predicate Step := fun step => step = .setOne

def right : Predicate Step := fun step => step = .double

def effect : Step → Section Nat
  | .setOne => fun _ => 1
  | .double => fun value => value * 2

theorem noDependency_is_strict : IsStrictPartialOrder noDependency := by
  constructor
  · intro step dependency
    exact dependency
  · intro first second third dependency
    exact False.elim dependency

theorem no_declared_dependency_crosses : NoCrossing noDependency left right := by
  intro first second inLeft inRight
  exact ⟨fun dependency => dependency, fun dependency => dependency⟩

theorem no_crossing_is_not_sufficient :
    sequence (effect .setOne) (effect .double) 0 ≠
    sequence (effect .double) (effect .setOne) 0 := by
  decide

theorem crossingDependency_is_strict : IsStrictPartialOrder crossingDependency := by
  constructor
  · intro step
    cases step <;> simp [crossingDependency]
  · intro first second third firstDependency secondDependency
    cases first <;> cases second <;> cases third <;>
      simp [crossingDependency] at firstDependency secondDependency ⊢

theorem declared_dependency_crosses : ¬ NoCrossing crossingDependency left right := by
  intro noCrossing
  have noSetThenDouble := noCrossing .setOne .double rfl rfl |>.1
  exact noSetThenDouble True.intro

theorem crossing_dependency_changes_composed_result :
    sequence (effect .setOne) (effect .double) 0 = 2 ∧
    sequence (effect .double) (effect .setOne) 0 = 1 := by
  decide

end Counterexample

end Parallel

namespace Retraction

abbrev Supports (Claim : Type) := Claim → Claim → Prop

section Generic

variable {Claim : Type}

inductive Removed (supports : Supports Claim) (premise : Claim) : Claim → Prop where
  | premise : Removed supports premise premise
  | dependent {claim support} :
      supports claim support → Removed supports premise support → Removed supports premise claim

def Survives (supports : Supports Claim) (premise claim : Claim) : Prop :=
  ¬ Removed supports premise claim

theorem survivors_are_closed_under_required_support
    (supports : Supports Claim) (premise claim support : Claim)
    (claimSurvives : Survives supports premise claim)
    (requires : supports claim support) :
    Survives supports premise support := by
  intro supportRemoved
  exact claimSurvives (Removed.dependent requires supportRemoved)

theorem removal_is_minimal
    (supports : Supports Claim) (premise : Claim) (otherRemoval : Predicate Claim)
    (removesPremise : otherRemoval premise)
    (removesDependents : ∀ claim support,
      supports claim support → otherRemoval support → otherRemoval claim) :
    ∀ claim, Removed supports premise claim → otherRemoval claim := by
  intro claim removed
  induction removed with
  | premise => exact removesPremise
  | dependent requires supportRemoved inductionHypothesis =>
      exact removesDependents _ _ requires inductionHypothesis

end Generic

namespace AlternativeCounterexample

inductive Claim where
  | premiseA
  | premiseB
  | conclusion
  deriving DecidableEq, Repr

def flatSupports : Supports Claim
  | .conclusion, .premiseA => True
  | .conclusion, .premiseB => True
  | _, _ => False

theorem premiseB_survives_retracting_premiseA :
    Survives flatSupports .premiseA .premiseB := by
  intro removed
  cases removed with
  | dependent requires supportRemoved => simp [flatSupports] at requires

theorem flat_support_over_retracts_alternatives :
    Removed flatSupports .premiseA .conclusion ∧
    Survives flatSupports .premiseA .premiseB ∧
    flatSupports .conclusion .premiseB := by
  constructor
  · exact Removed.dependent (by simp [flatSupports]) Removed.premise
  · exact ⟨premiseB_survives_retracting_premiseA, by simp [flatSupports]⟩

end AlternativeCounterexample

end Retraction

namespace Order

section Generic

variable {Question State : Type}

def evaluate (answer : Question → Parallel.Section State)
    (schedule : List Question) (initial : State) : State :=
  schedule.foldl (fun state question => answer question state) initial

-- Named for the operational property, not for logical independence of the
-- questions. Section 5 of STRESS-TESTS.md turns on the two being different.
def PairwiseCommuting (answer : Question → Parallel.Section State) : Prop :=
  ∀ first second, Parallel.Commute (answer first) (answer second)

theorem commuting_answers_are_permutation_invariant
    (answer : Question → Parallel.Section State)
    (commuting : PairwiseCommuting answer)
    {firstSchedule secondSchedule : List Question}
    (permutation : firstSchedule.Perm secondSchedule) :
    ∀ initial,
      evaluate answer firstSchedule initial = evaluate answer secondSchedule initial := by
  induction permutation with
  | nil => intro initial; rfl
  | cons question permutation inductionHypothesis =>
      intro initial
      simpa [evaluate] using inductionHypothesis (answer question initial)
  | swap first second tail =>
      intro initial
      simpa [evaluate, Parallel.Commute, Parallel.sequence] using
        congrArg (evaluate answer tail) (commuting second first initial)
  | trans firstPermutation secondPermutation firstHypothesis secondHypothesis =>
      intro initial
      exact (firstHypothesis initial).trans (secondHypothesis initial)

def TwoQuestionOrderInvariant (answer : Question → Parallel.Section State)
    (first second : Question) : Prop :=
  ∀ initial,
    evaluate answer [first, second] initial =
    evaluate answer [second, first] initial

theorem two_question_invariance_iff_updates_commute
    (answer : Question → Parallel.Section State) (first second : Question) :
    TwoQuestionOrderInvariant answer first second ↔
      Parallel.Commute (answer first) (answer second) := by
  rfl

end Generic

namespace Counterexample

inductive Question where
  | setOne
  | double
  deriving DecidableEq, Repr

def answer : Question → Parallel.Section Nat
  | .setOne => fun _ => 1
  | .double => fun value => value * 2

theorem schedules_are_permutations :
    [Question.setOne, Question.double].Perm [.double, .setOne] := by
  exact List.Perm.swap Question.double Question.setOne []

theorem noncommuting_answers_make_order_matter :
    evaluate answer [.setOne, .double] 0 = 2 ∧
    evaluate answer [.double, .setOne] 0 = 1 := by
  decide

end Counterexample

end Order

namespace Justification

-- `j γ` lists alternative justification sets; each inner list is jointly required.
abbrev Justifications (Claim : Type) := Claim → List (List Claim)

section Generic

variable {Claim : Type}

-- Least fixed point, so a claim holds only through a finite, grounded derivation.
inductive Holds (j : Justifications Claim) : Claim → Prop where
  | intro {claim : Claim} (set : List Claim) :
      set ∈ j claim → (∀ support ∈ set, Holds j support) → Holds j claim

def IsPremise (j : Justifications Claim) (claim : Claim) : Prop :=
  [] ∈ j claim

def IsReasoned (j : Justifications Claim) (claim : Claim) : Prop :=
  ∃ set ∈ j claim, set ≠ []

def IsUnsupported (j : Justifications Claim) (claim : Claim) : Prop :=
  j claim = []

theorem premise_holds (j : Justifications Claim) (claim : Claim)
    (premise : IsPremise j claim) : Holds j claim :=
  Holds.intro [] premise (by intro _ member; cases member)

theorem unsupported_never_holds (j : Justifications Claim) (claim : Claim)
    (unsupported : IsUnsupported j claim) : ¬ Holds j claim := by
  intro holds
  cases holds with
  | intro set member _ =>
      rw [IsUnsupported] at unsupported
      rw [unsupported] at member
      cases member

theorem classification_is_exhaustive (j : Justifications Claim) (claim : Claim) :
    IsUnsupported j claim ∨ IsPremise j claim ∨ IsReasoned j claim := by
  unfold IsUnsupported IsPremise IsReasoned
  cases sets : j claim with
  | nil => exact Or.inl rfl
  | cons first rest =>
      refine Or.inr ?_
      by_cases empty : first = []
      · exact Or.inl (by simp [empty])
      · exact Or.inr ⟨first, by simp, empty⟩

-- Withdrawing a premise removes only its empty justification; other sets remain.
def withdraw [DecidableEq Claim] (j : Justifications Claim) (premise : Claim) :
    Justifications Claim :=
  fun claim => if claim = premise then (j claim).filter (!·.isEmpty) else j claim

theorem withdrawn_is_not_premise [DecidableEq Claim]
    (j : Justifications Claim) (premise : Claim) :
    ¬ IsPremise (withdraw j premise) premise := by
  simp [IsPremise, withdraw]

theorem withdraw_leaves_others [DecidableEq Claim]
    (j : Justifications Claim) (premise claim : Claim) (other : claim ≠ premise) :
    withdraw j premise claim = j claim := by
  simp [withdraw, other]

-- The atomic-by-absence encoding: `j γ = ∅` marks a premise, retained by its own rule.
inductive HoldsAtomic (j : Justifications Claim) : Claim → Prop where
  | atomic {claim : Claim} : j claim = [] → HoldsAtomic j claim
  | reasoned {claim : Claim} (set : List Claim) :
      set ∈ j claim → (∀ support ∈ set, HoldsAtomic j support) → HoldsAtomic j claim

def assertUnsupported (j : Justifications Claim) : Justifications Claim :=
  fun claim => if (j claim).isEmpty then [[]] else j claim

theorem encodings_agree (j : Justifications Claim) (claim : Claim) :
    Holds (assertUnsupported j) claim ↔ HoldsAtomic j claim := by
  constructor
  · intro holds
    induction holds with
    | @intro claim set member _ supportsHold =>
        by_cases empty : (j claim).isEmpty
        · exact HoldsAtomic.atomic (List.isEmpty_iff.mp empty)
        · simp only [assertUnsupported, empty] at member
          exact HoldsAtomic.reasoned set member supportsHold
  · intro holds
    induction holds with
    | @atomic claim unsupported =>
        exact premise_holds _ _ (by simp [IsPremise, assertUnsupported, unsupported])
    | @reasoned claim set member _ supportsHold =>
        have nonempty : (j claim).isEmpty = false := by
          cases sets : j claim with
          | nil => rw [sets] at member; cases member
          | cons _ _ => rfl
        exact Holds.intro set (by simp [assertUnsupported, nonempty, member]) supportsHold

end Generic

namespace AlternativeSurvival

inductive Claim where
  | premiseA
  | premiseB
  | conclusion
  deriving DecidableEq, Repr

def j : Justifications Claim
  | .premiseA => [[]]
  | .premiseB => [[]]
  | .conclusion => [[.premiseA], [.premiseB]]

theorem conclusion_survives_withdrawing_premiseA :
    ¬ Holds (withdraw j .premiseA) .premiseA ∧ Holds (withdraw j .premiseA) .conclusion := by
  constructor
  · exact unsupported_never_holds _ _ (by simp [IsUnsupported, withdraw, j])
  · refine Holds.intro [.premiseB] (by decide) ?_
    intro support member
    simp at member
    subst member
    exact premise_holds _ _ (by simp [IsPremise, withdraw, j])

theorem conclusion_falls_when_both_withdrawn :
    ¬ Holds (withdraw (withdraw j .premiseA) .premiseB) .conclusion := by
  intro holds
  cases holds with
  | intro set member supportsHold =>
      have sets : set = [.premiseA] ∨ set = [.premiseB] := by
        simpa [withdraw, j] using member
      rcases sets with rfl | rfl
      · exact unsupported_never_holds _ .premiseA (by simp [IsUnsupported, withdraw, j])
          (supportsHold _ (by simp))
      · exact unsupported_never_holds _ .premiseB (by simp [IsUnsupported, withdraw, j])
          (supportsHold _ (by simp))

end AlternativeSurvival

namespace Circular

inductive Claim where
  | left
  | right
  deriving DecidableEq, Repr

def j : Justifications Claim
  | .left => [[.right]]
  | .right => [[.left]]

theorem circular_support_never_holds (claim : Claim) : ¬ Holds j claim := by
  intro holds
  induction holds with
  | @intro claim set member _ supportsFail =>
      cases claim <;> simp [j] at member <;> subst member <;>
        exact supportsFail _ (List.mem_singleton_self _)

end Circular

end Justification

namespace Supersession

open Justification

inductive Reason where
  | restate
  | revise
  | reverse
  deriving DecidableEq, Repr

-- Docket refuses to supersede a retired record, so each record has at most one successor.
abbrev Successor (Claim : Type) := Claim → Option (Claim × Reason)

section Generic

variable {Claim : Type}

-- Following successors whose reasons `admits` accepts ends at the current record `head`.
inductive Reaches (succ : Successor Claim) (admits : Reason → Prop) : Claim → Claim → Prop where
  | current {claim : Claim} : succ claim = none → Reaches succ admits claim claim
  | step {claim next head : Claim} {reason : Reason} :
      succ claim = some (next, reason) → admits reason → Reaches succ admits next head →
      Reaches succ admits claim head

-- `head` picks where each cited record resolves; a function argument keeps the
-- inductive strictly positive where an existential would not.
inductive HoldsThrough (j : Justifications Claim) (succ : Successor Claim)
    (admits : Reason → Prop) : Claim → Prop where
  | intro {claim : Claim} (set : List Claim) (head : Claim → Claim) :
      set ∈ j claim →
      (∀ support ∈ set, Reaches succ admits support (head support)) →
      (∀ support ∈ set, HoldsThrough j succ admits (head support)) →
      HoldsThrough j succ admits claim

def never : Reason → Prop := fun _ => False

def restates : Reason → Prop
  | .restate => True
  | _ => False

def forwards : Reason → Prop
  | .reverse => False
  | _ => True

-- Retirement as withdrawal: a cited record must still be current.
abbrev Strict (j : Justifications Claim) (succ : Successor Claim) := HoldsThrough j succ never

-- Holds with no review owed: citations follow restatements only.
abbrev Clean (j : Justifications Claim) (succ : Successor Claim) := HoldsThrough j succ restates

-- Holds, possibly owing review: citations follow restatements and revisions.
abbrev Live (j : Justifications Claim) (succ : Successor Claim) := HoldsThrough j succ forwards

def Flagged (j : Justifications Claim) (succ : Successor Claim) (claim : Claim) : Prop :=
  Live j succ claim ∧ ¬ Clean j succ claim

theorem reaches_mono {succ : Successor Claim} {narrow wide : Reason → Prop}
    (widens : ∀ reason, narrow reason → wide reason) {claim head : Claim} :
    Reaches succ narrow claim head → Reaches succ wide claim head := by
  intro reaches
  induction reaches with
  | current none => exact .current none
  | step next admitted _ rest => exact .step next (widens _ admitted) rest

theorem holds_mono {j : Justifications Claim} {succ : Successor Claim}
    {narrow wide : Reason → Prop} (widens : ∀ reason, narrow reason → wide reason)
    {claim : Claim} :
    HoldsThrough j succ narrow claim → HoldsThrough j succ wide claim := by
  intro holds
  induction holds with
  | intro set head member reaches _ supportsHold =>
      exact .intro set head member (fun support inSet => reaches_mono widens (reaches support inSet))
        supportsHold

theorem strict_implies_clean {j : Justifications Claim} {succ : Successor Claim} {claim : Claim} :
    Strict j succ claim → Clean j succ claim :=
  holds_mono (fun _ impossible => impossible.elim)

theorem clean_implies_live {j : Justifications Claim} {succ : Successor Claim} {claim : Claim} :
    Clean j succ claim → Live j succ claim :=
  holds_mono (fun reason restated => by cases reason <;> simp_all [restates, forwards])

theorem premise_holds_through {j : Justifications Claim} {succ : Successor Claim}
    {admits : Reason → Prop} {claim : Claim} (premise : IsPremise j claim) :
    HoldsThrough j succ admits claim :=
  .intro [] id premise (by intro _ member; cases member) (by intro _ member; cases member)

theorem superseded_unreachable {succ : Successor Claim} {admits : Reason → Prop}
    {claim next : Claim} {reason : Reason}
    (superseded : succ claim = some (next, reason)) (refused : ¬ admits reason) (head : Claim) :
    ¬ Reaches succ admits claim head := by
  intro reaches
  cases reaches with
  | current none => rw [superseded] at none; cases none
  | step successor admitted _ =>
      rw [superseded] at successor
      cases successor
      exact refused admitted

theorem single_ground_fails {j : Justifications Claim} {succ : Successor Claim}
    {admits : Reason → Prop} {claim ground : Claim} (single : j claim = [[ground]])
    (unreachable : ∀ head, ¬ Reaches succ admits ground head) :
    ¬ HoldsThrough j succ admits claim := by
  intro holds
  cases holds with
  | intro set head member reaches _ =>
      rw [single] at member
      simp at member
      subst member
      exact unreachable _ (reaches ground (by simp))

-- With nothing superseded, every reading is the plain retention rule of section 6.
theorem agrees_without_supersession {j : Justifications Claim} {succ : Successor Claim}
    {admits : Reason → Prop} (nothingSuperseded : ∀ claim, succ claim = none) (claim : Claim) :
    HoldsThrough j succ admits claim ↔ Holds j claim := by
  have resolvesToItself : ∀ {support head : Claim},
      Reaches succ admits support head → head = support := by
    intro support head reaches
    cases reaches with
    | current _ => rfl
    | step successor _ _ => rw [nothingSuperseded] at successor; cases successor
  constructor
  · intro holds
    induction holds with
    | intro set head member reaches _ supportsHold =>
        refine Holds.intro set member ?_
        intro support inSet
        have resolved := supportsHold support inSet
        rwa [resolvesToItself (reaches support inSet)] at resolved
  · intro holds
    induction holds with
    | intro set member _ supportsHold =>
        exact .intro set id member (fun support _ => .current (nothingSuperseded support))
          supportsHold

end Generic

namespace Example

inductive Claim where
  | old
  | new
  | other
  | dependent
  | backed
  deriving DecidableEq, Repr

def j : Justifications Claim
  | .old => [[]]
  | .new => [[]]
  | .other => [[]]
  | .dependent => [[.old]]
  | .backed => [[.old], [.other]]

def succ (reason : Reason) : Successor Claim
  | .old => some (.new, reason)
  | _ => none

theorem restate_keeps_dependent_clean :
    Clean j (succ .restate) .dependent ∧ ¬ Strict j (succ .restate) .dependent := by
  constructor
  · refine .intro [.old] (fun _ => .new) (by simp [j]) ?_ ?_
    · intro support inSet
      simp at inSet
      subst inSet
      exact .step rfl True.intro (.current rfl)
    · intro support _
      exact premise_holds_through (by simp [IsPremise, j])
  · exact single_ground_fails rfl (superseded_unreachable rfl id)

theorem revise_flags_dependent : Flagged j (succ .revise) .dependent := by
  constructor
  · refine .intro [.old] (fun _ => .new) (by simp [j]) ?_ ?_
    · intro support inSet
      simp at inSet
      subst inSet
      exact .step rfl True.intro (.current rfl)
    · intro support _
      exact premise_holds_through (by simp [IsPremise, j])
  · exact single_ground_fails rfl (superseded_unreachable rfl id)

theorem reverse_retracts_dependent : ¬ Live j (succ .reverse) .dependent :=
  single_ground_fails rfl (superseded_unreachable rfl id)

theorem reverse_spares_an_alternative : Live j (succ .reverse) .backed := by
  refine .intro [.other] id (by simp [j]) ?_ ?_
  · intro support inSet
    simp at inSet
    subst inSet
    exact .current rfl
  · intro support inSet
    simp at inSet
    subst inSet
    exact premise_holds_through (by simp [IsPremise, j])

end Example

end Supersession

end Docket.StressTests

def main : IO Unit := do
  IO.println "Formalism stress tests"
  IO.println ""
  IO.println "1. PASS: every exhaustive, disjoint intended/unintended partition is expressible by R and ι."
  IO.println "2. FAIL: closure laws, even with Cl(∅) = ∅, do not constrain indirect outcomes."
  IO.println "3. FAIL: a strict dependency order with no crossing edge does not rule out interference."
  IO.println "   PASS: step-level pairwise commutation lifts to whole sections."
  IO.println "4. PASS WITH LIMIT: transitive retraction is sound for jointly required supports."
  IO.println "   FAIL: a flat support set over-retracts alternative justifications."
  IO.println "5. PASS: commuting answer updates are permutation-invariant; two-update invariance iff they commute."
  IO.println "6. PASS: premises as j(γ) ∋ ∅ need no separate retention rule and agree with the atomic-by-absence rule."
  IO.println "   PASS: a conclusion survives one withdrawn alternative and falls when every alternative is withdrawn."
  IO.println "   PASS: circular support never holds under the least-fixed-point reading."
  IO.println "7. PASS: strict ⊆ clean ⊆ live, and all three equal section 6 when nothing is superseded."
  IO.println "   PASS: restate keeps a dependent clean, revise flags it, reverse retracts it unless an alternative survives."
