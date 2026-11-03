# Research technical map

Use this map when proposing or revisiting an approach. It is a way to search the space of interventions, not an approved-model list. First ask where improvement could come from: missing knowledge, unclear task definition, weak representations, wrong output behavior, too little or noisy data, or resource limits. Then walk the families below against the task, look up concrete current candidates with `scout.py` (see [tools](tools.md)) and official sources, and keep the families you could not reasonably exclude.

## Intervention families

Cost tiers are rough: T0 minutes without training, T1 under an hour on a laptop or CPU, T2 hours of local training or a single GPU, T3 multiple GPUs, long runs or substantial API spending.

| Family | Consider when | Tier | Main risks |
|---|---|---|---|
| Rules, lexicons, classical features (TF-IDF, linear models, gradient boosting) | Surface form predicts the target, very little data, interpretability matters | T0 | Poor semantic generalization; easy to overfit by reading evaluation samples |
| Zero-shot use (embedding similarity to label descriptions, NLI, an off-the-shelf task model) | No labels but outputs have meaningful names or descriptions | T0 | Sensitive to label wording and language coverage |
| Prompting and few-shot generation, local or API | Outputs describable in language, few labels, a strong reference is useful | T0–T1 | Format drift, latency, per-call cost; small local models are weak on long or non-English input |
| Retrieval or tool use | The gap is knowledge or context, not behavior | T1 | Retrieval recall caps quality |
| Frozen representations with a light head (embeddings plus logistic regression, kNN or small MLP) | Tens to thousands of labels, semantic classification, clustering or matching | T1 | Encoder language, domain and length limits |
| Contrastive few-shot adaptation (SetFit-style) | Roughly 8–64 examples per class, frozen embeddings show signal but not enough | T1–T2 | Overfitting tiny sets; needs grouped evaluation |
| Fine-tuning a small encoder or task model | Hundreds to tens of thousands of labels, low-latency local delivery | T2 | Instability on small data; use several seeds |
| Parameter-efficient adaptation of a large model (LoRA, QLoRA) | Specific generation behavior or format, hundreds to tens of thousands of examples | T2–T3 | Memory, forgetting, harder evaluation |
| Distillation | A strong teacher exists and delivery must be small, cheap or private | T2 | Teacher errors become the ceiling |
| Preference or reinforcement learning | Verifiable rewards or preference data, supervised training has plateaued | T3 | Reward hacking; requires independent evaluation |
| Data work (cleaning, relabeling, augmentation, active learning, weak supervision) | Label noise, class imbalance or data volume is the bottleneck | T0–T1 | Often the largest gain and the most overlooked |

Families combine: a strong API model can label data for a small local student, and retrieval can feed a fine-tuned generator. Roles from the proposal (baseline, recommended, reference or challenge) are separate from families; the cheapest family is not automatically the baseline and the most complex is not automatically the reference.

## Using it

- In a proposal, state which families were considered, which are worth testing and why each other one is excluded by evidence: data size, hardware fit, privacy, latency, license or a measured result. "Not enough labels" excludes supervised training, not zero-shot or frozen-representation routes.
- Look up candidates instead of naming models from memory. Check language coverage, parameter count, license, gating and whether the model fits the person's hardware before listing it as a resource.
- When results stall, revisit the table before tuning the same method again.
- Published results motivate hypotheses, not claims about this study. Prefer a small end-to-end compatibility check before substantial preparation.

## Domain pitfalls

Read only the relevant guide for task-specific leakage, preprocessing and evaluation risks and official starting points.

| Task family | Guide |
|---|---|
| Tables, classification, regression, anomaly detection | [Tabular](domains/tabular.md) |
| Forecasting and temporal signals | [Time series](domains/time-series.md) |
| Text classification, retrieval and ranking | [Text](domains/text.md) |
| Language generation and behavior adaptation | [Language models](domains/language-models.md) |
| Image classification, detection and segmentation | [Vision](domains/vision.md) |
| Image synthesis and editing | [Image generation](domains/image-generation.md) |
| Speech recognition, synthesis and audio | [Audio](domains/audio.md) |
| Video understanding and generation | [Video](domains/video.md) |
| Documents, vision-language and cross-modal tasks | [Multimodal](domains/multimodal.md) |
| Graphs, point clouds, reconstruction and 3D generation | [Graphs and spatial](domains/spatial.md) |

Use the [tool index](tools-map.md) to distinguish training frameworks, inference engines and platform support, and [resource planning](resource-planning.md) to turn a route into resource ceilings. At execution, pin chosen revisions and actual inputs in experiment records rather than adding project-specific recipes here.
