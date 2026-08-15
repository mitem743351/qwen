# Research Planning (Deterministic)

Phase 7 planning is **rule-based**. It classifies tasks, estimates complexity,
selects a workflow template, and derives requirements and a budget — without
invoking a model.

Module: `python/qwen_research/orchestration/planning.py`.

---

## Task classification

`TaskType` is a controlled vocabulary: `QUESTION_ANSWERING · DEEP_RESEARCH ·
LITERATURE_REVIEW · FACT_CHECK · DATA_ANALYSIS · COMPARISON ·
TECHNICAL_ANALYSIS · SYNTHESIS · REPORT_GENERATION · CUSTOM`.

Classification is keyword-driven (e.g. "compare"/"versus" → `COMPARISON`,
"dataset"/"csv" → `DATA_ANALYSIS`, "fact check" → `FACT_CHECK`), with an
explicit `task_type` override taking precedence. `CUSTOM` is the fallback for
unclassifiable tasks.

## Complexity classification

`TaskComplexity` (`SIMPLE · MODERATE · COMPLEX · VERY_COMPLEX`) is a **routing
heuristic**, never a claim about true difficulty. It starts from the reasoning
profile (FAST→SIMPLE … EXTREME→VERY_COMPLEX) and is bumped by content signals
(sub-question count, analysis/comparison/verification keywords, task type).

## Reasoning profile integration

The planner consumes the existing `FAST/NORMAL/DEEP/XHIGH/EXTREME` profiles and
derives **workflow-level** resource behavior (retrieval/verification/computation
budgets, parallelism), bounded by `ReasoningBudget`. No provider-specific
parameters are produced.

## Plan templates

Each task type maps to a deterministic template (see [`workflows.md`](workflows.md)):

- `DEEP_RESEARCH` — classify → plan → retrieve → assess → verify → [compute] → memory → synthesize → finalize
- `FACT_CHECK` — classify → retrieve → claim → assess → verify → contradictions → synthesize → finalize
- `DATA_ANALYSIS` — classify → plan → describe → compute → verify → memory → synthesize → finalize
- `LITERATURE_REVIEW` — classify → retrieve → corroborate → contradictions → memory → synthesize → finalize
- `TECHNICAL_ANALYSIS` — classify → plan → retrieve → assess → verify → compute → memory → synthesize → finalize

## Requirements & completion criteria

The planner explicitly identifies `needs_retrieval / needs_verification /
needs_computation / needs_memory / needs_contradiction_analysis /
needs_artifacts`, and each plan carries `CompletionCriteria` (minimum evidence
count, source diversity, verification completed, dataset profiled, result
persisted, provenance recorded). A task is **not** considered complete merely
because all stages ran.

## Capability filtering

If a `CapabilityRegistry` is supplied, stage types whose required capability is
unavailable are dropped **and their dependencies are rewired**, so downstream
stages never wait on a removed stage. MCP is not the capability registry.

A missing **required** capability is never silent: it is recorded on the plan
(`missing_capabilities`) and seeded into the run's `degradation`, so the run
terminates at `SYNTHESIS_REQUIRED` rather than a clean completion.

## Limitations

Phase 7 planning does **not** understand deep natural-language intent. A future
model-assisted planner will sit behind `ResearchPlanner` without changing the
workflow engine.
