---
name: tunetune-init
description: Investigate a new or changed TuneTune goal and recommend a practical research proposal, alternatives and resources before evaluation or experiments.
---

# Turn a need into a research direction

Load [research-workspace](../research-workspace/SKILL.md). For installation follow the repository bootstrap guide and preserve the original request. Read relevant materials and existing work before asking what they already answer.

Understand intended use, representative inputs and useful outputs, unacceptable failures and the intended delivery. Distinguish stated requirements, your proposed defaults and unresolved assumptions. Ask concrete questions only where the answer changes the recommendation. For subjective tasks, show recognizable boundary examples and help the person decide what good means; do not ask them to design an algorithm. There is no minimum question count. Settle the output space at the level the person recognizes, such as categories, granularity or format, in the proposal; detailed rubrics and reference answers belong to the evaluation.

Read the shared [technical map](../research-workspace/references/technical-map.md), then investigate credible method families and current primary sources that could change the choice. Consider three roles: a cheap credible baseline, a recommended route within available resources, and a strong quality reference or challenge route. Roles may coincide; explain exclusions rather than inventing complexity. A baseline is a starting point, and a large model is a hypothesis, not a proven ceiling. Consider whether data, inference, retrieval, adaptation or training best addresses the need.

Inspect authorized data, code, compute and existing results. Maintain the resource inventory as the source of preparation facts: purpose, source and version, expected download and disk use, destination, environment isolation, API cost ceiling and data-transfer conditions where applicable. Mark estimates and unknowns honestly. Offer an API route when it has a concrete benefit; credentials belong in secure application settings or environment variables, never conversation or research records. Use [resource planning guidance](../research-workspace/references/resource-planning.md).

Write a coherent proposal using the shared record guide: need and examples, evidence and sources, recommended and alternative approaches, evaluation, finite initial budget and stopping conditions, delivery and next validation. It sets direction for the whole study; revise it when the goal, requirements, recommended direction or scope change, not to record progress or results. Reference resource IDs instead of duplicating acquisition details. Do not claim that installed dependencies or file existence establish feasibility.

Give the actual panel link and a summary sufficient to decide without opening it, in this order: the need and the output to be built; the research plan by role, each with what it tests, why it is worth running and which resources it needs, noting roles that coincide or are excluded and why; then the combined resource scope, budget and any data disclosure or cost. Normally ask once for that plan and scope together, using meaningful choices such as start the recommendation, revise it, or perform a feasible check without new resources. Accept natural-language changes. Existing explicit delegation can cover this decision; do not ask again. Approval never permits unspecified downloads, spending or private uploads.

Once covered, immediately prepare the listed resources and continue into [build-evaluation](../build-evaluation/SKILL.md) and [run-experiments](../run-experiments/SKILL.md) within scope, pausing only for the evaluation's reference review when references encode the person's judgment. If a decision is missing, identify it and recommend an answer instead of ending at “the model is unfinished.”
