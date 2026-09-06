# Decision chains for long-running agent work

September 2026. This note synthesizes five literature reviews. It also states the
design those reviews point at.

## The problem

An agent settles dozens of small questions during a long task. Those answers stay
in prose. Compaction removes the prose. Twenty steps later the agent contradicts a
decision it already made, and nothing detects this.

There is a mechanical cause. Summarization flattens causal structure into plain
text. It destroys the links that record which conclusions depend on which earlier
claim. The dependency graph is the part that summarization discards.

## Current design

The decision graph is a YAML file in git. Each node holds a predicate. The model
answers each predicate with `settled`, `ruled-out`, or `open`. Deterministic code
walks the graph.

Each call appends one JSONL line. The line records the node, the question, the
answer, the edge taken, and a timestamp. That log serves three purposes. It is the
audit trail. It is the replay input. It is the eval set.

One implementation covers both modes. The modes differ only in the response to
`open`. With a human present, the walker stops and asks. The answer then becomes
`settled`. Without a human, the walker makes a ruling. It records what the ruling
costs if it is wrong. It continues, and it reports every ruling at the end.

Reversibility sets the threshold between the two. An open question whose wrong
answer costs a five-line edit gets a ruling and a log entry. An open question that
deletes data or writes to a shared branch stops and waits. This applies in both
modes.

Outcome-directed reasoning builds backward from the decision. A node earns its
place only if a different answer changes the final action. Open-ended exploration
uses none of this structure, because collapsing it destroys its purpose.

## What the evidence establishes

**Reasoning chains are often unfaithful.** The visible chain frequently fails to
reflect the computation that produced the answer (2503.08679, and Anthropic 2025).
Some 2026 work argues the trace can be epiphenomenal. In that view the model
settles the answer before it emits the thinking tokens (2606.13603, 2603.26410).
This is the most replicated finding in the review. A trace is therefore not a
record of *why*. It is a record of what the agent committed to. You can check that
record against later behavior.

**Elaborate topologies mostly provide extra compute.** At a fixed token budget,
tree and graph scaffolds deliver approximately what repeated sampling delivers
(2507.14419, 2506.04210). The Tree-of-Thoughts benefit depends on the model's
ability to discriminate good branches from bad ones. That ability collapses outside
curated puzzle benchmarks (2410.17820). One lab reported the Graph-of-Thoughts
gains on its own benchmarks, and no independent replication exists (2308.09687).

**Reasoning models search internally.** They often perform as well without an
external scaffold (2504.09858, 2510.19176). Imposed structure can degrade them
through overthinking (2412.21187, 2501.18585). External structure is worth its cost
only where it does something the model cannot do alone. Examples: tool calls,
retrieval, verification against ground truth, and persistence across a compaction
boundary.

**Agents contradict their earlier conclusions.** Several benchmarks measure this
(2606.22936, 2602.11619, 2608.08160). Hidden-state convergence at an early step
predicts later behavioral consistency. It does not predict correctness. Committed-
wrong and committed-correct trajectories are not separable in activation space. A
consistent agent is therefore not a correct agent.

**Confidence thresholds are the wrong deferral rule.** Mozannar and Sontag proved
the naive confidence-threshold rejector is inconsistent (2006.01862). Optimal
deferral depends on two error probabilities: the model's, and the expert's on that
same instance. Most LLM systems substitute an uncertainty proxy. This substitution
loses the consistency guarantee.

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

**Predicate order changes the answer.** Option order alone swings results up to 75
percent on some benchmarks (2308.11483). Premise order costs over 30 percent on
deductive tasks (2502.04134). Two causes contribute: real uncertainty near decision
boundaries, and positional bias independent of content. No general fix exists.

**Full automation is not the safe default.** Mixed-initiative autonomy outperforms
both extremes on robotics navigation tasks. It also reduces operator workload
(1911.04848, 2211.14095).

## What the evidence excludes

**DSPy.** It optimizes prompts per backend. A model swap requires a recompile. For
a comparison of two models on one predicate, it adds nothing over sending both the
same prompt. Its optimizers require roughly 50 to 100 labelled examples before they
are worth the cost.

**DMN.** It is a real OMG standard. It has the best verification tooling here,
including formal overlap and completeness checks for decision tables (Calvanese et
al., BPM 2016, and `dmn-check`). It serializes to XML. Its engines run on the JVM
and in JS. Nobody reviews DMN in a diff. Copy its completeness check, which is
about fifteen lines. Do not adopt the standard.

**LangGraph.** The shape is correct: checkpointed state and conditional edges. It
is a runtime for a loop you can write in fifty lines.

**Cedar and OPA.** These are worth their cost when several people own policy
independently, or when the project requires formal verification. Neither condition
applies at one-person scale.

**Guardrail frameworks.** They target safety and topic control. They produce no
audit trail, which is the actual requirement here.

**Argo, CWL, and BPMN.** These are task graphs. The requirement is a graph of
decisions, which is a different grain.

**PMML and ONNX.** These serialize models. They are the wrong abstraction layer.

## Four open gaps

Each gap has support in the literature. No published work occupies any of them.

**Reversibility as the deferral threshold.** Several independent 2025 and 2026
sources treat reversibility as a first-class variable (2608.07440, 2606.16465,
2506.23844). One states that a fully reversible action cannot generate claimable
loss, even under uncertainty. Deferral theory already carries a free cost-of-error
parameter. Nobody has applied blast radius to that parameter.

**Deferral where the expert degrades.** ML theory models the human as an oracle
with a fixed error rate. Human-factors research shows the act of deferring degrades
that oracle. A reviewer under high throughput stops reviewing and approves by
default (2502.10036, 2109.05067). No formulation exists in which the expert's error
rate depends on the deferral rate. This is the deepest of the four gaps.

**A relevance filter on sub-questions.** A question earns its place only if a
different answer changes the final action. Classical decision theory calls this
value of information. It is theoretically obvious and unimplemented for LLM
reasoning. The closest precedents never use the term (2503.22674, 2410.13788).

**A truth-maintenance-shaped ledger.** Truth maintenance systems record a
justification for each belief. They retract dependents automatically when a premise
is withdrawn (Doyle 1979). That is this design, from 1979. ReTree independently
re-derived dependency retraction for search trees and cited no TMS theory
(2608.10676). No system runs a real JTMS as an agent's belief store with a measured
before-and-after comparison.

Related prior art: DMN-Guided Prompting (Springer 2025) already uses DMN structure
to decompose decisions into steps an LLM can answer. Do not claim novelty there.

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

The graph freezes current thinking, and it only grows. Every surprise adds a node.
Nobody deletes one. Models improve and the graph does not.

## Implementation notes

No off-the-shelf product covers the full shape. A few hundred lines of Python
outperforms any surveyed framework at this scale.

The `PreToolUse` hook in Claude Code returns `allow`, `deny`, or `ask`. These map
onto the three predicate values exactly. The hook runs before the permission-mode
check. A `deny` holds even under `--dangerously-skip-permissions`. Anthropic has an
unshipped function-hook mechanism behind a flag in build 2.1.260. It replaces shell
commands with a TypeScript module.

Replay costs almost nothing. Run the same walker and supply the logged answers
instead of calling the model.

Codex through ChatGPT desktop is not callable from code. Automatic cross-model
disagreement is therefore unavailable. Sampling one model several times is the
substitute. Self-consistency is the better-calibrated signal in any case. Note that
its assumed mechanism does not hold: voting masks noise instead of verifying the
reasoning (2305.14279, 2506.18781).

For observability, Phoenix carries the least lock-in because it emits
OpenTelemetry spans. Braintrust and Langfuse both convert production traces into
eval sets.

## Verification limits

Several citations above came from search summaries, not from direct paper reads.
Check any citation before it carries weight. The two most quotable numbers need
this most: the 40 to 50 percent question-selection result (2503.22674), and the
abstention degradation finding (2506.09038).
