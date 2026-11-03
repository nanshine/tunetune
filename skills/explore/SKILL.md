---
name: explore
description: Investigate TuneTune evidence, diagnose stagnation or contradictions and recommend worthwhile research directions without automatically starting experiments.
---

# Find the next worthwhile question

Load [research-workspace](../research-workspace/SKILL.md). Identify the person's current question, proposal, evaluation, relevant experiments and remaining scope. Read the necessary actual inputs, implementations, object identities, process facts, logs and outputs; summaries are leads, not proof. With no experiments, assess proposed tests and missing evidence rather than inventing results.

Compare compatible measurements and recognizable output differences. Investigate whether apparent gains or plateaus reflect behavior, weak references, leakage, preprocessing, scoring, resource constraints or narrow exploration. Distinguish execution failure, uncertainty and evidence against a method. Preserve a usable model when only measurement failed.

Challenge the leading explanation and identify an observation that would distinguish alternatives. Read relevant [technical-map](../research-workspace/references/technical-map.md) guidance and current primary sources when they can change the recommendation. Consider a cheap diagnostic, a useful continuation and a meaningful method change or stronger reference. Do not universalize one failed trial or treat complexity as evidence of quality. Stop reading when further investigation no longer changes the next decision.

Present a short prioritized recommendation: the question each direction answers, evidence behind it, expected observation, resources and why it is worth the cost. Keep experiment interpretation in its existing analysis; revise the current proposal only when the recommended direction or scope changes, through conditional writes. Do not create another ledger or mandatory approval stage.

If goals change, return through [tunetune-init](../tunetune-init/SKILL.md); if measurement changes, use [build-evaluation](../build-evaluation/SKILL.md) and identify needed remeasurement. Within an authorized experiment loop, continue directly into [run-experiments](../run-experiments/SKILL.md). A request only to explore ends with actionable findings, not unrequested experiments. Missing consequential choices should be concrete and accompanied by a recommendation.
