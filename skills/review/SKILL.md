---
name: review
description: Explore TuneTune research evidence, diagnose stagnation or contradictory results, and recommend worthwhile next directions. Use when asked what was learned or what to try next; this is research exploration, not routine code review or a per-round approval gate.
---

# Learn from evidence before choosing more work

Load [research-workspace](../research-workspace/SKILL.md). Identify the question, current proposal, relevant evaluation and experiments, delivery choices and remaining scope. Follow actual inputs, implementation, model hashes, process status, logs and outputs where the explanation depends on them. Summaries are useful starting points, not proof. Read only the material needed to decide.

Compare compatible measurements and recognizable output differences, not aggregate scores alone. Ask whether an apparent gain or plateau reflects model behavior, insufficient evidence, narrow exploration, leakage, preprocessing, scoring or changed conditions. Distinguish execution failure from poor quality and uncertainty from evidence against a method. Preserve a usable model when only evaluation failed; a separate retest may answer the question more cheaply than retraining.

Challenge the leading explanation. Which observation would distinguish it from a plausible alternative? Which gains survive independent checks? Which requirement remains unmet despite better scores? With no completed experiments, assess the proposed tests and missing evidence honestly rather than inventing conclusions.

Research relevant methods, resources or implementations when that can change the recommendation. Respect access, privacy and remaining budget; distinguish external reports from results measured here. Compare a useful local continuation with a meaningful method change or diagnostic. Revisit a discarded direction when new conditions make it informative, without treating one failed trial as a universal verdict. Stop reading when further research no longer changes the next decision.

Present a short prioritized set of directions in conversation: the question each answers, evidence behind it, expected observation, required resources and why it is worth the cost. Keep experiment-specific interpretation and next directions in the relevant `analysis.json`, using the shared [record guide](../research-workspace/references/records.md) and [tools](../research-workspace/references/tools.md) for conflict-safe updates. Preserve measurements rather than creating another research ledger.

If understanding of the goal changes, update the current proposal through [tunetune-init](../tunetune-init/SKILL.md); if measurement changes, use [build-evaluation](../build-evaluation/SKILL.md) and identify necessary remeasurement. Explain conclusions and uncertainty in ordinary language. A review-only request ends with findings, not new experiments. Within an already authorized bounded loop, return directly to [train](../train/SKILL.md); pause only for a consequential missing decision or changed boundary.
