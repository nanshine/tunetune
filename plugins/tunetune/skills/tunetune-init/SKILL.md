---
name: tunetune-init
description: Investigate a new or changed TuneTune goal and recommend a practical research proposal, alternatives and resource ceilings before evaluation or experiments.
license: Apache-2.0 (complete terms in LICENSE.txt)
---

# Turn a need into a research direction

Load [research-workspace](../research-workspace/SKILL.md). Initialize the directory as that skill describes if needed, and preserve the original request. Read relevant materials and existing work before asking what they already answer.

## Understand the need first

Understand intended use, representative inputs and useful outputs, unacceptable failures and the intended delivery. Before proposing, ask about what would change the recommendation: how the result will be used, which outputs the person would accept, and a few real inputs they want to see answered. Those inputs become proposal examples and acceptance inputs, so the person later judges the model on their own material rather than on examples you invented. For subjective tasks, show recognizable boundary examples from their material and help them decide what good means; do not ask them to design an algorithm. There is no minimum question count. Settle the output space at the level the person recognizes, such as categories, granularity or format; detailed rubrics and reference answers belong to the evaluation. Distinguish stated requirements, your proposed defaults and unresolved assumptions. Early answers about limits such as local-only work inform the proposal but do not confirm it, because the person cannot judge what resources buy before seeing the plan.

## Search widely, then recommend

Read the shared [technical map](../research-workspace/references/technical-map.md) and walk its intervention families against this task, then use the public lookup helper and current primary sources to find concrete models, datasets and implementations and to check licenses and fit on the person's hardware. A route you never looked up cannot be fairly excluded. Consider three roles: a cheap credible baseline, a recommended route within available resources, and a strong quality reference or challenge route, offering an API reference when it shows useful headroom. Roles may coincide; explain exclusions by evidence such as data size, hardware, privacy, latency or license rather than by habit. A baseline is a starting point, and a large model is a hypothesis, not a proven ceiling.

Before presenting, check the draft for blind spots: when the application can run a helper without this conversation's history, give it only the need, constraints and draft and ask which method families or risks are missing; otherwise answer that question yourself against the map. Adopt or reject each point with a reason.

## Plan resources as ceilings

Inspect authorized data, code, compute and existing results. Maintain the resource inventory as the source of preparation facts: purpose, source and version, expected download and disk use, destination, environment isolation, API cost ceiling and data-transfer conditions. Mark estimates and unknowns honestly. Ask for scope as kinds of resources with ceilings, such as public weights up to a total size, local execution, no data leaving the machine and an API spending limit, so a better candidate found later within the same ceilings does not force another approval. Credentials belong in secure application settings or environment variables, never conversation or research records. Use [resource planning guidance](../research-workspace/references/resource-planning.md).

## Write and present the proposal

Write a coherent proposal using the shared record guide: need and examples, intervention families considered with reasons for exclusion, evidence and sources, recommended and alternative approaches, evaluation, finite initial budget and stopping conditions, delivery and next validation. State the budget in what the person actually bears, such as wall time, compute, downloads, disk and spending, not as a count of training attempts: a count costs them nothing, a bug can use it up, and it can end the study while most of the agreed time remains. It sets direction for the whole study; revise it when the goal, requirements, recommended direction or scope change, keeping its examples consistent with the current direction, and never to record progress or results. Reference resource IDs instead of duplicating acquisition details.

Open the proposal in the panel with an attention note and give its verified link, so the full proposal is one click away; the decision itself is asked and answered in conversation. The message itself is short: what will be built, the plan by role in a line each, the combined resource ceilings and any cost or data disclosure, and your recommendation. Ask once for that plan and scope with meaningful choices: start and run through to delivery, start but show the evaluation, baseline and first experiment plan before experimenting, revise, or run a feasible check without new resources. Accept natural-language changes. Existing explicit delegation can cover this decision; do not ask again. Downloads, spending or private uploads beyond the agreed ceilings are the person's cost, so they need a new decision.

Once covered, immediately prepare the listed resources and continue into [build-evaluation](../build-evaluation/SKILL.md) and [run-experiments](../run-experiments/SKILL.md) within scope, pausing only for the evaluation's reference review and any checkpoint the person chose. If a decision is missing, identify it and recommend an answer instead of ending at “the model is unfinished.”
