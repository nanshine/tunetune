---
name: run-experiments
description: Review TuneTune evidence, plan and run bounded experiment rounds, diagnose results, retest existing systems and deliver verified local models.
---

# Improve through rounds of informative experiments

Load [research-workspace](../research-workspace/SKILL.md), the current proposal, experiment plan, relevant resources and a calibrated evaluation, reviewed where its references encode the person's judgment. Use shared records and tools for mechanics. Work in rounds: survey the evidence, plan a few experiments, run them, interpret, then plan again or stop. A request only to investigate or recommend ends after the survey and plan, without running experiments.

## Survey before choosing

Read the proposal, the plan, the lineage, analyses and the actual outputs, implementations, logs and process facts behind them; summaries are leads, not proof. Locate the largest remaining uncertainty or gap to the goal. Investigate whether apparent gains or plateaus reflect behavior, weak references, leakage, preprocessing, scoring, resource constraints or narrow exploration. Distinguish execution failure, uncertainty and evidence against a method; a crashing output parser is not evidence that the method is weak. Challenge the leading explanation and identify an observation that would distinguish alternatives.

When exploration has stayed within one method family, or two rounds brought no real progress, revisit the [technical map](../research-workspace/references/technical-map.md) and look up current candidates with the public lookup helper. When the application can run a helper without this conversation's history, give it only the proposal, plan and lineage and ask for overlooked method families, recoverable earlier experiments and weakly supported conclusions; otherwise answer those questions yourself. Do not universalize one failed trial or treat complexity as evidence of quality.

## Plan a round

Write the round into the experiment plan: its goal, a budget in experiments and time, and two to four items. Each item reserves its experiment ID from the ID helper and states the question, intervention family, parent and comparator, the observation that would change the next decision, cost tier and resources. Balance deepening the current best route with testing a meaningfully different one when evidence allows, rather than always adding complexity or making tiny changes to the same method. Ideas not worth this round stay in the plan's idea list with the reason. Mark dropped items with why and when they would be worth reopening. The plan references experiment IDs and never repeats their results.

Continue without asking when the round fits the authorized resource ceilings and remaining budget. Ask once, with the round open in the panel and a recommendation, when it needs new kinds of resources, more cost, other data transfers or more budget than remains, or when the person started this skill directly and has not said how much to try. Offer meaningful sizes such as the recommended round, only the most promising item, or stop here.

## Run an experiment

Freeze necessary code and configuration and pin the actual inputs. Record method ancestry in `parent_experiment_id` so the lineage shows what each experiment builds on. Package each model with its own prompts, preprocessing and parsing behind an `invoke.json` entry point that degrades gracefully on unexpected model output, so evaluation, comparison and later use call it the same way. Run through the configured runner and its output locations, retain process facts and logs, and inspect the resulting local or API object before finalizing success. An API object identifies the provider, request configuration and calling code, not immutable remote weights; read the record guide for its contract. Keep credentials out of arguments, snapshots and logs.

Evaluate each candidate on the development split under a fresh experiment-local attempt with fixed object and evaluation references. Preserve real outputs, diagnostics and available cost, latency and usage. Retries use new IDs; evaluating an unchanged object does not require training again. Compare only compatible measurement and inference conditions, never a mixed ranking. Count preparation, failures and retests against the budget and keep enough for final validation.

## Interpret and decide

Interpret actual differences, failures and cost in each experiment analysis and close the round in the plan with one sentence. Preserve the incumbent when evidence is inconclusive. Revise the proposal only when evidence changes the recommended direction or scope. Plan the next round, or stop when the goal is met, the budget is spent or a round and a fresh review find no worthwhile direction; if goals change, return through [tunetune-init](../tunetune-init/SKILL.md), and if measurement must change, use [build-evaluation](../build-evaluation/SKILL.md) and identify needed remeasurement.

## Deliver

Run the acceptance inputs through the incumbent and promising candidates so the person can read real outputs in the panel's acceptance window, where they can also rerun local models and try new input themselves; this complements scores and never replaces them. Do not hand over results as a report file or a separate usage script. Measure the chosen model once on the final check. Verify local loading, dependencies and the `invoke.json` entry point on real inputs. Select only verified local experiment IDs for delivery; API references remain visible research results, not private local deliverables. Models remain experiment-local and export is separate when requested. Outputs you write yourself are not model outputs, so never mix them into a delivery. Applying the model to the person's data or systems is outside the study unless requested.

Report achieved behavior, evidence, uncertainty, actual consumption and stopping reason. When a gap to the goal remains, end with the most promising next round, what it would cost and your recommendation, rather than a bare unfinished-status report.
