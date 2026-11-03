---
name: build-evaluation
description: Design, calibrate or change executable TuneTune evaluations, representative samples and data separation before comparing models.
---

# Make useful behavior measurable

Load [research-workspace](../research-workspace/SKILL.md), the proposal, resources, conversation and existing measurement. Define useful outputs, consequential failures and trade-offs independently of the preferred algorithm. Explain what metrics measure and miss; labels are not required for every task.

Prepare representative successes, failures and boundary cases, with stable sample identities and justified references or executable checks. A strong model or the Agent can draft references but cannot make its own answers independent truth.

When references encode the person's judgment, they review them before freezing. Present the draft references with the boundary cases and disagreements that matter, record each sample's `reference_status`, and freeze only reviewed references. If the person explicitly delegates labeling instead, keep the drafts as `draft` and report scores as agreement with that draft, not with their preference. This review is the one routine pause after the proposal decision; prepare resources and a baseline meanwhile. Objective references from trusted sources need no review.

Separate development and calibration inputs from final checks at the source or grouping level needed to avoid leakage. Make the split before inspecting material for tuning when possible. Store preparation and split material under evaluation, pin the actual content and enforce exclusions in training preparation. Explain exposed or nonrepresentative evidence honestly; a reserved filename does not make a sample unseen. Read the relevant technical-map domain for leakage risks.

Implement repeatable sample preparation, scoring and aggregation behind a model-independent contract: the evaluation calls the target's entry point and scores what it returns. Prompts, preprocessing, inference and output parsing of every candidate, including the baseline, belong to that experiment's model, so a new method never needs a new evaluation. Distinguish process, parser and missing-output failures from low quality; absent measurements are not zero. Keep real outputs and diagnostics. Local candidates and API references need compatible input and scoring conditions, with cost and latency retained when measured.

Calibrate the actual path with justified positive, negative and trade-off examples and a small end-to-end model check. Inspect disagreement and repeatability where material. Before freezing, check task coverage, reference provenance, split isolation, metric meaning, runtime dependencies and package independence from mutable drafts. A smoke test proves execution, not real-world quality.

Use the shared record tools to freeze evaluation only after these checks and any required reference review. Include displayable samples, necessary scripts and fixed preparation evidence; exclude caches, secrets and unrelated inputs. Keep protected or large media elsewhere through explicit pinned references. Changed samples or scoring require a new version, never overwriting frozen evidence.

Select the evaluation with conflict detection and pass the runnable interface to [run-experiments](../run-experiments/SKILL.md) within authorization. Explain measurement limits and continue; beyond the reference review, ask only for a consequential unresolved judgment, presenting concrete examples and a recommendation.
