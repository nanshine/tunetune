---
name: build-evaluation
description: Build, calibrate or change executable TuneTune evaluations. Use to define useful results, test scoring rules and representative samples, or repair measurement gaps; unchanged-model retests belong in train.
---

# Make useful results measurable

Load [research-workspace](../research-workspace/SKILL.md), then read the proposal, relevant resources, existing evaluation and conversation. Define what a useful output does, which failures matter and which trade-offs need measurement. Explain what each metric captures and misses. Evaluation should follow the task, not the training algorithm's preferred data format.

Prepare representative successes, failures and boundary cases, with references or executable checks where appropriate. Labels are not mandatory for every task. Keep stable sample identities and explain sources, processing and coverage limits. Separate development and calibration material from independent final checks at the source or grouping level needed to avoid leakage. An example used to steer tuning is exposed, even if its filename says test.

Implement repeatable preparation, inference, scoring and aggregation. Trace the real path from model loading through preprocessing and output parsing to individual judgments and totals. Distinguish missing output, parser or process failure from a genuine low score; unavailable measurements are not zero. Preserve real outputs and diagnostics.

Calibrate this actual path with justified positive, negative and trade-off examples, including a small end-to-end model check. Inspect disagreements and judge repeatability where material. Investigate contradictory scores before moving thresholds. Ask the person about unresolved consequential judgments in conversation, using recognizable outputs rather than requiring exhaustive annotation. Synthetic examples or a smoke test alone do not establish real-world quality.

Use the shared [record guide](../research-workspace/references/records.md) and [tools](../research-workspace/references/tools.md) to freeze an immutable `evaluation/<version>/` with its definition, fixed `samples.jsonl`, scoring scripts and verified manifest. Include only samples suitable for display; keep protected or large inputs elsewhere and pin those actually used. Verify the package runs without mutable draft files. Describe calibration evidence and limitations with the evaluation's research explanation.

Select `project.current_evaluation` with conflict detection within the existing authorization. Changed samples or scoring require a new version and appropriate remeasurement, never replacement of old results. Hand the version and actual model interface to [train](../train/SKILL.md). Compare only compatible measurement and inference conditions; an existing model can be evaluated again without retraining. Report what is runnable, what the evidence supports and any remaining blocker.
