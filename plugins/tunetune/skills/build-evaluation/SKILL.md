---
name: build-evaluation
description: Design, calibrate or change executable TuneTune evaluations, representative samples, data separation and the measured baseline before comparing models.
license: Apache-2.0 (complete terms in LICENSE.txt)
---

# Make useful behavior measurable

Load [research-workspace](../research-workspace/SKILL.md), the proposal, resources, conversation and existing measurement. Define useful outputs, consequential failures and trade-offs independently of the preferred algorithm. Explain what metrics measure and miss; labels are not required for every task.

## Samples and references

Prepare representative successes, failures and boundary cases, with stable sample identities and justified references or executable checks. A strong model or the Agent can draft references but cannot make its own answers independent truth.

When references encode the person's judgment, they review them before freezing: their answers define what good means for them, and scores against references they never saw would only measure agreement with you. Put the draft samples in `evaluation/draft/samples.jsonl`, open the panel's review with an attention note, and in conversation point out the boundary cases and disagreements that matter. The person confirms, corrects or questions each item there; apply their response to each sample's `reference_status`, settle questions, and freeze only reviewed references. Never ask them to read a local file instead. If the person explicitly delegates labeling instead, keep the drafts as `draft` and report scores as agreement with that draft, not with their preference. This review is the one routine pause after the proposal decision; prepare resources and the baseline meanwhile. Objective references from trusted sources need no review.

## Separation

Split development material from final checks at the source or grouping level needed to avoid leakage, before you or any method reads the material to design rules, prompts, label definitions or examples. Anything read while designing a method is development evidence for that method, so a final check is only meaningful if it stayed unseen. Drafting references for final checks is not method design; tuning a method while looking at their individual results is. The output space a method uses, such as categories or a tag vocabulary, comes from the person's confirmed requirements or the whole material, never from the references, otherwise a score only measures choosing among the answers' own labels. Size the final check to what the study can afford and say plainly when it is too small to be representative. Store preparation and split material under evaluation, pin the actual content and enforce exclusions in training preparation. Read the relevant technical-map domain for leakage risks.

## A model-independent contract

Implement repeatable sample preparation, scoring and aggregation behind a model-independent contract: the evaluation calls the target's entry point and scores what it returns. Prompts, preprocessing, inference and output parsing of every candidate belong to that experiment's model, so a new method never needs a new evaluation. Distinguish process, parser and missing-output failures from low quality; absent measurements are not zero. Keep real outputs and diagnostics. Where unlabeled material is available, also check output distributions on it, such as empty or malformed outputs, lengths and category frequencies; this cannot show correctness, but it reveals systematic bias and overfitting to a small labeled set cheaply. Local candidates and API references need compatible input and scoring conditions, with cost and latency retained when measured.

## Calibrate with the baseline

Build the cheapest credible baseline from the proposal as experiment `e000` and use it as the end-to-end check of the scoring path, together with justified positive, negative and trade-off examples. Writing the baseline before freezing keeps it from being tuned to the frozen samples afterwards. Inspect disagreement and repeatability where material. Before freezing, check task coverage, reference provenance, split isolation, metric meaning, runtime dependencies and package independence from mutable drafts. A smoke test proves execution, not real-world quality.

Use the shared record tools to freeze evaluation only after these checks and any required reference review, then measure the baseline on it. Include displayable samples, necessary scripts and fixed preparation evidence; exclude caches, secrets and unrelated inputs. Keep protected or large media elsewhere through explicit pinned references. Changed samples or scoring require a new version, never overwriting frozen evidence.

## Hand over

Select the evaluation with conflict detection and continue into [run-experiments](../run-experiments/SKILL.md) within authorization. If the person asked to see the evaluation and baseline first, write the first round of the experiment plan, open it in the panel with an attention note and ask once whether to proceed, with your recommendation. Explain measurement limits; beyond the reference review, ask only for a consequential unresolved judgment, presenting concrete examples and a recommendation.
