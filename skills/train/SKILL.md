---
name: train
description: Establish a TuneTune baseline, run bounded model experiments, retest existing models or deliver verified usable results. Use for an authorized research loop or a specific hypothesis, not just weight training.
---

# Improve through bounded experiments

Load [research-workspace](../research-workspace/SKILL.md), the proposal, relevant resources and a calibrated evaluation. Follow the shared [record guide](../research-workspace/references/records.md) and [tools](../research-workspace/references/tools.md) for mechanics. Establish an operational finite budget, permitted changes and stopping conditions. Carry existing authorization across rounds without repeated approvals; never infer new spending or private-data access. Count preparation, failures and retests, preserve the original deadline and reserve final-validation time.

Start with the unchanged system or simplest credible end-to-end baseline. Verify its model-to-score interface and keep a usable incumbent. A fixed-rule baseline is legitimate but does not fulfill an explicit training request. Training, data, inference and broader method changes are alternatives chosen to answer the question, not mandatory stages.

For each affordable round:

1. Check remaining scope, resources and unfinished work. State a hypothesis, expected observation and meaningful comparator. Distinguish code ancestry from inherited weights; neither automatically identifies the comparison.
2. Implement an interpretable change. Freeze necessary code and configuration, pin actual inputs including inherited model files, and preserve resolved parameters and environment. Execute one configured command through the runner, retaining `run.log` and process facts in status. These checks are not a sandbox.
3. Verify the actual model under the experiment's `model/` before finalizing success. Exit zero alone is insufficient. Create a fresh experiment-local evaluation with fixed model and evaluation hashes; save actual per-sample outputs, metrics and diagnostics before finalization. An evaluation failure need not trigger retraining.
4. Inspect compatible scores, outputs, failures and cost. Write the outcome and evidence-supported interpretation in `analysis.json`. Preserve measurements; change interpretations with conflict detection. Keep the incumbent when evidence is inconclusive. Continue, diagnose, use [review](../review/SKILL.md), or stop within the remaining budget.

Retries use new IDs. Changed evaluation requires comparable remeasurement, not a mixed ranking. Use development evidence for iteration and reserved independent checks for final selection; say best among tested alternatives, not optimal.

Stop exploration in time to verify model loading, dependencies and the intended inference interface with a real smoke test. Select verified experiment IDs in `project.deliveries`; models stay inside their experiments. Reuse evaluation outputs or generate only requested same-input comparison outputs. Selection neither copies nor deploys a model; export a standalone bundle only when requested.

Report improvement, uncertainty, unmet requirements, actual consumption and stopping reason in ordinary language. Keep user decisions in conversation and describe any genuinely running process without promising unsupported autonomous continuation.
