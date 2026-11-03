---
name: build-evaluation
description: Design, calibrate or change executable TuneTune evaluations, representative samples and data separation before comparing models.
---

# Make useful behavior measurable

Load [research-workspace](../research-workspace/SKILL.md), the proposal, resources, conversation and existing measurement. Define useful outputs, consequential failures and trade-offs independently of the preferred algorithm. Explain what metrics measure and miss; labels are not required for every task.

Prepare representative successes, failures and boundary cases, with stable sample identities and justified references or executable checks. For subjective judgments, show consequential disagreements to the person before treating your draft labels as their preferences. A strong model can assist annotation but cannot make its own answers independent truth.

Separate development and calibration inputs from final checks at the source or grouping level needed to avoid leakage. Make the split before inspecting material for tuning when possible. Store preparation and split material under evaluation, pin the actual content and enforce exclusions in training preparation. Explain exposed or nonrepresentative evidence honestly; a reserved filename does not make a sample unseen. Read the relevant technical-map domain for leakage risks.

Implement repeatable preparation, model loading, preprocessing, inference, parsing, scoring and aggregation. Distinguish process, parser and missing-output failures from low quality; absent measurements are not zero. Keep real outputs and diagnostics. Local candidates and API references need compatible input and scoring conditions, with cost and latency retained when measured.

Calibrate the actual path with justified positive, negative and trade-off examples and a small end-to-end model check. Inspect disagreement and repeatability where material. Before freezing, check task coverage, reference provenance, split isolation, metric meaning, runtime dependencies and package independence from mutable drafts. A smoke test proves execution, not real-world quality.

Use the shared record tools to freeze evaluation only after these checks. Include displayable samples, necessary scripts and fixed preparation evidence; exclude caches, secrets and unrelated inputs. Keep protected or large media elsewhere through explicit pinned references. Changed samples or scoring require a new version, never overwriting frozen evidence.

Select the evaluation with conflict detection and pass the runnable interface to [run-experiments](../run-experiments/SKILL.md) within authorization. Explain measurement limits and continue; ask only for a consequential unresolved judgment, presenting concrete examples and a recommendation.
