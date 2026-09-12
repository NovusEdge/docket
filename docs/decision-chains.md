# Decision chains for long-running agent work

September 2026. This note summarizes five literature reviews and the resulting
design. It separates behavior shipped in Docket 0.8.0 from future proposals.

## The problem

An agent settles dozens of small questions during a long task. The answers stay
in prose, and compaction removes that prose. Twenty steps later, the agent can
contradict an earlier decision without detection.

Summarization flattens causal structure into plain text. The links that record
which conclusions depend on which claims are the part the summary discards.

## Shipped in Docket 0.8.0

Docket stores schema 2 records in an append-only JSONL ledger. The three record
types are:

| Type | Recorded state | Meaning |
| --- | --- | --- |
| Claim | `unassessed`, `accepted`, `disputed`, `rejected` | A proposition. |
| Decision | `adopted`, `revoked` | A commitment with a required `choice`. |
| Question | `open` | An unresolved inquiry. An answer can give it effective state `resolved` in the derived view. |

Type, recorded state, and currentness are separate. Acceptance is a workflow
judgment and does not establish truth. A superseded record keeps its recorded
state and history while leaving the current view. A current accepted claim or
applicable adopted decision can resolve a question through an `answers` link without
rewriting the question line.

Claims and decisions can declare alternative support sets. Members of one set
are AND terms, and sets are OR alternatives:

```math
[[c1, c2], [c3]] = (c1 \land c2) \lor c3
```

A decision can also declare `depends_on` prerequisites. This operational
relation is separate from support and has no OR interpretation.

The session hook loads a bounded context briefing:

1. Rank pinned records first at startup.
2. For a task query, prioritize matching task text and scope over unrelated
   pins.
3. Include bounded related support, dependency, and answer records.
4. Report omitted records and keep whole record blocks within the character
   budget.

Evidence references, checked timestamps, commits, revisit conditions, and costs
provide provenance and review data. Docket does not report that evidence was
freshly verified.

The command does not retract dependent records automatically. A person or agent
reviews decisions whose prerequisites or support records become unusable. An
adopted decision with unavailable `depends_on` prerequisites remains adopted in
the ledger, is derived as blocked, and cannot resolve a question.

## Proposed future behavior

The typed graph and deterministic context walker are the 0.8.0 foundation.
Outcome tracking and an action gate remain separate future features.

| Proposed feature | Rule |
| --- | --- |
| Human review | Reversibility sets the review threshold. A low-cost mistake can continue with a recorded decision. An irreversible or shared change waits for a person. |
| Outcome-directed reasoning | Start with the final decision. A question matters when a different answer can change the final action. |
| Open-ended exploration | Keep exploration outside a fixed decision graph so the graph does not constrain its purpose. |

## Reported findings

### Reasoning traces

The visible reasoning chain can differ from the computation that produced the
answer (2503.08679; Anthropic 2025). Other work reports that a model can select
an answer before emitting reasoning tokens (2606.13603, 2603.26410).

A trace records the stated commitment. It provides no proof of the internal
computation.

### Search structure

At a fixed token budget, some studies report elaborate topologies with results
comparable to repeated sampling (2507.14419, 2506.04210). Tree-of-Thoughts also
depends on selecting useful branches; one study reports weaker selection outside
curated puzzle benchmarks (2410.17820).

Some studies report similar results from reasoning models without an external
scaffold (2504.09858, 2510.19176). Other studies report that imposed structure
can reduce performance (2412.21187, 2501.18585). External structure is useful
for operations that require persistent or verifiable state.

### Consistency and correctness

Several benchmarks measure agents contradicting earlier conclusions
(2606.22936, 2602.11619, 2608.08160). Hidden-state convergence at an early step
predicts later behavioral consistency, but it does not predict correctness.
Committed-wrong and committed-correct trajectories are not separable in
activation space. Consistency therefore does not establish correctness.

### Deferral and abstention

Mozannar and Sontag show that a basic confidence-threshold rejector is
inconsistent (2006.01862). Optimal deferral also depends on the expert's error
probability for the same instance. An uncertainty proxy does not preserve this
guarantee.

AbstentionBench tested 20 frontier models on 20 datasets (2506.09038).
Reasoning fine-tuning degraded abstention, and the models became more
confidently wrong. Scale did not correct this.

### Question selection

QuestBench asked models to name the single missing variable that makes a problem
solvable (2503.22674). They scored 40 to 50 percent, while solving the fully
specified versions. Models also detect ambiguity and answer without asking for
the missing information (2605.25284).

### Schema and pipeline structure

A schema during reasoning costs 10 to 30 percent on hard prompts (2603.13351,
2606.09410). Constrained decoding forces schema-legal tokens before reasoning
completes. A second pass that formats free-text reasoning recovers most of the
loss by removing the interleaving.

Convergent and divergent reasoning are separable capabilities (2510.26490,
2607.01433). Pipelines that keep them as separate stages outperform pipelines
that force both into one pass (2506.05128).

### Ordering and autonomy

Some benchmarks report answer changes of up to 75 percent after option reordering
(2308.11483). Premise order also changes results on deductive tasks (2502.04134).
Commuting answer transformations remove this sensitivity, while real updates do
not always commute.

Full automation is not the safe default for this design. Mixed-initiative
autonomy outperforms both extremes on robotics navigation tasks and reduces
operator workload (1911.04848, 2211.14095).

## Design choices

| System | Role in this design |
| --- | --- |
| DSPy | Optimizes prompts for a selected backend. Docket needs a stable decision record across backends, so DSPy does not replace the ledger. |
| DMN | Provides formal overlap and completeness checks for decision tables (Calvanese et al., BPM 2016; `dmn-check`). Docket can adopt relevant checks without adopting DMN as its storage format. |
| LangGraph | Provides checkpointed state and conditional edges. Its full workflow runtime is outside the current ledger design. |
| Cedar and OPA | Support independently managed policy. That policy layer is outside the current single-ledger design. |
| Guardrail frameworks | Control model output and tool use. Docket needs durable decision history. |
| Argo, CWL, and BPMN | Describe task graphs. Docket records decisions and their support relations. |
| PMML and ONNX | Serialize models. They do not represent a decision ledger. |

## Research questions

### Reversibility and deferral

Several sources treat reversibility as a decision variable (2608.07440,
2606.16465, 2506.23844). Deferral theory includes a cost-of-error parameter.
Further review must determine whether prior work maps operational impact to this
parameter.

Many models use a fixed human error rate. Human-factors studies report weaker
review at high throughput (2502.10036, 2109.05067). Further review must identify
models in which the expert's error rate depends on the deferral rate.

### Value of information

A question is relevant when a different answer can change the final action.
Classical decision theory calls this value of information. The cited agent work
uses related tests without this term (2503.22674, 2410.13788).

### Truth maintenance

Truth maintenance systems record justifications and retract dependents after
premise withdrawal (Doyle 1979). ReTree applies dependency retraction to search
trees (2608.10676). Further review must identify measured agent systems that use
a complete JTMS.

Holding a claim while any one of several justifications survives is the
assumption-based variant (de Kleer 1986). Its node label is a set of environments,
which has the shape of Docket's `supports` field.

The formal justification relation and the runtime field have different
contracts. `supports` records declared grounds for claims or decisions. It does
not entail its target, retract dependents, or propagate truth automatically.

DMN-Guided Prompting (Springer 2025) uses DMN structure to decompose decisions
into questions for an LLM. This decomposition is not a novel claim here.

## Open risks

- A per-call gate cannot see a plan. Most real damage comes from sequences of
  individually harmless calls.
- The `open` rate must stay in a narrow band, and nothing holds it there. A low
  rate catches little. A high rate produces rubber-stamping, which the
  human-factors literature reports as the normal outcome.
- The trace resembles evidence. Given the faithfulness results, a clean log of
  eight predicates can document a wrong answer in high resolution.
- Composed predicates can each be locally correct while the assembled decision
  is globally wrong (2605.30335). That paper offers a computable residual and a
  runtime repair, providing one cited example of an evaluated mitigation.
- Alternative justifications increase label size. An ATMS stores every minimal
  environment that supports a node (de Kleer 1986). The number of environments
  can grow exponentially with the number of assumptions, and Docket does not
  yet define a bound.
- The graph freezes current thinking and only grows. Every surprise adds a node.
  Models improve while the graph remains unchanged.

## Implementation constraints

- The ledger CLI remains a Python command over an append-only ledger. The native
  installer and graph viewer do not require a workflow framework or change the
  ledger model.
- The proposed action gate needs a hook before tool execution. The integration
  must map the ledger decision to the hook response for each supported harness.
- Replay can use recorded answers instead of new model calls. Evaluation export
  can use the same records after the project defines outcome labels.
- Cross-model comparison requires a callable interface for each selected model.
  Repeated sampling from one model measures a different property.

## Verification limits

Several citations came from search summaries rather than direct paper reads.
Check any citation before it carries weight. The two most quotable numbers need
this most: the 40 to 50 percent question-selection result (2503.22674) and the
abstention degradation finding (2506.09038).
