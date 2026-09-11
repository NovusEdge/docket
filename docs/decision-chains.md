# Decision chains for long-running agent work

September 2026. This note summarizes five literature reviews. It also describes
the resulting design.

## The problem

An agent settles dozens of small questions during a long task. Those answers stay
in prose. Compaction removes the prose. Twenty steps later the agent contradicts a
decision it already made, and nothing detects this.

There is a mechanical cause. Summarization flattens causal structure into plain
text. It destroys the links that record which conclusions depend on which earlier
claim. The dependency graph is the part that summarization discards.

## Current system

Docket stores an append-only decision ledger. Each entry has a `settled`,
`ruled-out`, or `open` state.

An entry can record alternative support sets in `because`. A later entry can use
`supersedes` to retire an earlier entry.

The session hook loads current entries when an agent session starts. Docket keeps
retired entries in the history and omits them from normal views.

The current command does not retract dependent entries automatically. A person or
agent must review each entry that depends on a retired entry.

## Target system

The target system adds a decision graph and a deterministic graph walker. It also
adds automatic dependency retraction, outcome tracking, and an action gate.

Reversibility sets the proposed threshold for human review. A low-cost mistake can
continue with a recorded decision. An irreversible or shared change waits for a
person.

Outcome-directed reasoning starts with the final decision. A question is relevant
only when a different answer can change the final action.

Open-ended exploration does not use this structure. A fixed decision graph would
limit the purpose of exploration.

## Reported findings

**Reasoning chains can be unfaithful.** The visible chain can differ from the
computation that produced the answer (2503.08679; Anthropic 2025).

Other work reports that a model can select an answer before it emits reasoning
tokens (2606.13603, 2603.26410).

Therefore, treat a trace as a record of the stated commitment. Do not treat it as
proof of the internal computation.

**Elaborate topologies can provide extra compute.** At a fixed token budget, some
studies report results comparable to repeated sampling (2507.14419, 2506.04210).

Tree-of-Thoughts also depends on the model's ability to select useful branches.
One study reports weaker selection outside curated puzzle benchmarks
(2410.17820).

**Reasoning models can search internally.** Some studies report similar results
without an external scaffold (2504.09858, 2510.19176).

Other studies report that imposed structure can reduce performance
(2412.21187, 2501.18585). Use external structure for operations that require
persistent or verifiable state.

**Agents contradict their earlier conclusions.** Several benchmarks measure this
(2606.22936, 2602.11619, 2608.08160). Hidden-state convergence at an early step
predicts later behavioral consistency. It does not predict correctness. Committed-
wrong and committed-correct trajectories are not separable in activation space. A
consistent agent is therefore not a correct agent.

**Confidence alone is not a sufficient deferral rule.** Mozannar and Sontag show
that a basic confidence-threshold rejector is inconsistent (2006.01862).

Optimal deferral also depends on the expert's error probability for the same
instance. An uncertainty proxy does not preserve this guarantee.

**More capable models abstain worse.** AbstentionBench tested 20 frontier models on
20 datasets (2506.09038). Reasoning fine-tuning degraded abstention. The models
became more confidently wrong. Scale did not correct this.

**Models cannot identify which question matters.** QuestBench asked models to name
the single missing variable that makes a problem solvable (2503.22674). They scored
40 to 50 percent. The same models solved the fully specified versions. Models also
detect ambiguity and then answer anyway instead of asking (2605.25284).

**A schema during reasoning costs 10 to 30 percent** on hard prompts (2603.13351,
2606.09410). Constrained decoding forces schema-legal tokens before the reasoning
completes. A second pass that formats free-text reasoning recovers most of the
loss, because it removes the interleaving.

**Convergent and divergent reasoning are separable capabilities** (2510.26490,
2607.01433). Pipelines that keep them as separate stages outperform pipelines that
force both into one pass (2506.05128).

**Predicate order can change the answer.** Some benchmarks report changes of up
to 75 percent after option reordering (2308.11483).

Premise order also changes results on deductive tasks (2502.04134). Commuting
answer transformations remove this sensitivity, but real updates do not always
commute.

**Full automation is not the safe default.** Mixed-initiative autonomy outperforms
both extremes on robotics navigation tasks. It also reduces operator workload
(1911.04848, 2211.14095).

## Design choices

**DSPy.** DSPy optimizes prompts for a selected backend. Docket needs a stable
decision record across backends, so DSPy does not replace the ledger.

**DMN.** DMN provides formal overlap and completeness checks for decision tables
(Calvanese et al., BPM 2016; `dmn-check`). It also requires the DMN data model and
runtime.

Docket can adopt the relevant checks without adopting DMN as its storage format.

**LangGraph.** LangGraph provides checkpointed state and conditional edges. Docket
does not need its full workflow runtime for the current ledger.

**Cedar and OPA.** These systems support independently managed policy. Docket does
not need this policy layer for the current single-ledger design.

**Guardrail frameworks.** These frameworks control model output and tool use.
Docket instead needs a durable decision history.

**Argo, CWL, and BPMN.** These systems describe task graphs. Docket records
decisions and their support relations.

**PMML and ONNX.** These formats serialize models. They do not represent a
decision ledger.

## Research questions

**Can reversibility set the deferral threshold?** Several sources treat
reversibility as a decision variable (2608.07440, 2606.16465, 2506.23844).

Deferral theory includes a cost-of-error parameter. Further review must determine
whether prior work maps operational impact to this parameter.

**How does deferral rate affect the reviewer?** Many models use a fixed human
error rate. Human-factors studies report weaker review at high throughput
(2502.10036, 2109.05067).

Further review must identify models in which the expert's error rate depends on
the deferral rate.

**Can value of information filter sub-questions?** A question is relevant only
when a different answer can change the final action.

Classical decision theory calls this value of information. The cited agent work
uses related tests without this term (2503.22674, 2410.13788).

**Can a truth maintenance system support an agent ledger?** Truth maintenance
systems record justifications and retract dependents after premise withdrawal
(Doyle 1979).

ReTree applies dependency retraction to search trees (2608.10676). Further review
must identify measured agent systems that use a complete JTMS.

Holding a claim while any one of several justifications survives is the
assumption-based variant (de Kleer 1986). Its label for a node is a set of
environments, which is the shape `because` takes here.

DMN-Guided Prompting (Springer 2025) uses DMN structure to decompose decisions
into questions for an LLM. Do not claim this decomposition as novel.

## Risks with no known fix

A per-call gate cannot see a plan. Most real damage comes from a sequence of
individually harmless calls.

The `open` rate must stay in a narrow band, and nothing holds it there. A rate that
is too low catches nothing. A rate that is too high produces rubber-stamping, which
the human-factors literature reports as the normal outcome.

The trace resembles evidence. Given the faithfulness results, a clean log of eight
predicates can document a wrong answer in high resolution.

Composed predicates can each be locally correct while the assembled decision is
globally wrong (2605.30335). That paper offers a computable residual and a runtime
repair. This is the one evaluated mitigation available.

Alternative justifications increase label size. An ATMS stores every minimal
environment that supports a node (de Kleer 1986).

The number of environments can grow exponentially with the number of assumptions.
Docket does not yet define a bound.

The graph freezes current thinking, and it only grows. Every surprise adds a node.
Nobody deletes one. Models improve and the graph does not.

## Implementation constraints

The current implementation uses one Python command and an append-only ledger. It
does not require a workflow framework.

The proposed action gate needs a hook before tool execution. The integration must
map the ledger decision to the hook response for each supported harness.

Replay can use recorded answers instead of new model calls. Evaluation export can
use the same records after the project defines outcome labels.

Cross-model comparison requires a callable interface for each selected model.
Repeated sampling from one model measures a different property.

## Verification limits

Several citations above came from search summaries, not from direct paper reads.
Check any citation before it carries weight. The two most quotable numbers need
this most: the 40 to 50 percent question-selection result (2503.22674), and the
abstention degradation finding (2506.09038).
